"""Streaming answer generation (Anthropic, or any OpenAI-compatible endpoint: DeepSeek, Doubao, Qwen, ...)."""
from __future__ import annotations

import re
from typing import AsyncIterator

from .config import PROVIDERS

# Answers are always in Chinese. Lectures, notes and slides are often English and models drift into the language
# of their context, so the rule opens the system prompt, is repeated around the question, and an answer that
# still starts in English is thrown away and regenerated (see Answerer.stream).
CHINESE = """必须全程使用简体中文作答，绝对不要用英文作答——即使老师、问题、课件、转写或截图全是英文也一样。
代码、公式、符号、人名保持原样；关键专业术语第一次出现时在括号里附英文原词，例如：单应性（homography）。
Always answer in Simplified Chinese only. Never answer in English.

"""

SYSTEM = CHINESE + """You help a university student follow a live lecture. When the lecturer asks the class a question, \
draft a short answer the student could give in their own words, so they can think it through and respond.

Rules:
- Start with a one-sentence direct answer, then up to 3 short supporting bullet points.
- Prefer the course's own terminology, definitions and examples from the notes and transcript below.
- If the question is ambiguous, answer the most likely reading and note the alternative in a few words.
- If you are unsure, say what you are unsure about instead of inventing facts.
- Earlier questions and the answers already drafted are given for continuity: build on them for follow-up
  questions, stay consistent with them, and do not repeat them unless asked.
- No preamble, no restating the question."""

SCREENSHOT = CHINESE + """You help a university student with material the lecturer has put on screen (a slide, a posted image,
a question, code, a table or a diagram). The screenshot is a NEW item: handle what is on screen now, not an earlier
question. Earlier Q&A and the transcript are background only. Ignore anything that belongs to this assistant's own
window (titles like "Classmate", "截图 N", earlier drafted answers) and unrelated window chrome.

Do the actual work; do not just describe the picture:
1. Start with "**题目：**" and give the question(s), task or key text from the screen faithfully, translated into
   Chinese (keep option letters, code, formulas and symbols unchanged; condense long passages).
2. Then "**解答：**" and solve it completely, in Chinese:
   - multiple choice: the correct option first, then why, and briefly why the others are wrong;
   - calculation / derivation: every step and the final result;
   - code: what it does, the output or the bug, and corrected or complete code in a fenced code block;
   - open question / discussion prompt: a full, well-structured answer the student could give;
   - a figure, table, diagram or slide without an explicit question: explain what it shows, each part and the
     key takeaways, and anticipate what the lecturer is likely to ask about it, with answers.
   If several questions are shown, answer every one, numbered.
3. Length should follow the material: be as long as needed to be complete (headings, numbered steps and code
   blocks are fine). Use the course notes' terminology where relevant.
- If part of the screen is unreadable or cut off, say what is missing instead of guessing."""

DETAILED = "\n- This time give a fuller explanation (up to about 150 words), still starting with the direct answer."

def code_rule(language: str) -> str:
    """Preferred programming language for code the model writes (settings: code_language)."""
    language = (language or "").strip()
    if not language:
        return ""
    return (f"\n- Code: write the code you produce yourself (solutions, examples, complete programs) in {language}. "
            f"If the task is about code that is already given (find the bug, predict the output, fix it), keep that "
            f"code's language for the corrected version, then add the {language} version only if it is short. "
            f"If the question explicitly requires another language, use that language.")


REMINDER_BEFORE = "【请用简体中文回答，不要用英文】\n\n"
REMINDER_AFTER = "\n\n请用简体中文回答。"
STRICT = ("【最高优先级】上一次你用英文作答，这是错误的。这一次必须完整地用简体中文作答，"
          "只有代码、公式和括号里的术语原词可以是英文。\n\n")
RESTART = object()          # yielded by Answerer.stream: drop the text so far, a Chinese answer follows

CJK = re.compile(r"[\u4e00-\u9fff]")
LATIN = re.compile(r"[A-Za-z]")


def looks_english(text: str) -> bool:
    """The prose of an answer (code removed) is mostly English letters with hardly any Chinese."""
    prose = re.sub(r"```.*?(```|$)", " ", text, flags=re.S)
    prose = re.sub(r"`[^`]*`", " ", prose)
    latin, cjk = len(LATIN.findall(prose)), len(CJK.findall(prose))
    return latin >= 80 and cjk * 6 < latin


def format_history(history) -> str:
    """history: list of (question, answer) pairs, oldest first."""
    items = [f"Q{i}: {q}\nA{i}: {a.strip()}" for i, (q, a) in enumerate(history, 1) if a and a.strip()]
    return "\n\n".join(items)


def build_prompt(question: str, transcript: str, notes: str, detailed=False, history=(), screen_text=None,
                 has_images=False, strict=False, code_language=""):
    on_screen = has_images or bool(screen_text)
    system = (SCREENSHOT if on_screen else SYSTEM + (DETAILED if detailed else "")) + code_rule(code_language)
    blocks = [system]
    if notes:
        blocks.append(f"<course_notes>\n{notes}\n</course_notes>")
    earlier = format_history(history)
    user = ((f"<earlier_questions_and_answers>\n{earlier}\n</earlier_questions_and_answers>\n\n" if earlier else "")
            + f"<recent_lecture_transcript>\n{transcript or '(none yet)'}\n</recent_lecture_transcript>\n\n")
    if screen_text:
        user += f"<screenshot_text>\n{screen_text}\n</screenshot_text>\n\n"
    if question and on_screen:
        user += (f"The lecturer just said: \"{question}\"\nThe screenshot shows the material being discussed. "
                 "Extract it and answer fully.")
    elif on_screen:
        user += ("New item from the screen" + (" (text recognised from the screenshot above)" if screen_text else "")
                 + ". Extract the question or content and answer it fully.")
    else:
        user += f"The lecturer just asked: \"{question}\""
    user = (STRICT if strict else REMINDER_BEFORE) + user + REMINDER_AFTER
    return blocks, user


def vision_mode(settings) -> str:
    if settings.vision in ("image", "ocr"):
        return settings.vision
    return PROVIDERS.get(settings.llm, {}).get("vision", "image")


def thinking_options(provider: str, deep: bool) -> dict:
    """Reasoning delays the first visible word: off for normal answers, on for the "deep" answer
    (its reasoning is not shown, only the final text)."""
    style = PROVIDERS.get(provider, {}).get("thinking")
    if style == "type":                    # DeepSeek, Doubao (火山方舟)
        return {"thinking": {"type": "enabled" if deep else "disabled"}}
    if style == "enable_thinking":         # Qwen (DashScope)
        return {"enable_thinking": deep}
    return {}


class Answerer:
    def __init__(self, settings):
        self.s = settings
        self._anthropic = None
        self._openai = None

    def _client(self):
        if self.s.llm == "anthropic":
            if self._anthropic is None:
                from anthropic import AsyncAnthropic
                self._anthropic = AsyncAnthropic(api_key=self.s.key("anthropic"))
            return self._anthropic
        if self._openai is None:
            from openai import AsyncOpenAI
            self._openai = AsyncOpenAI(api_key=self.s.key(self.s.llm), base_url=self.s.llm_base_url)
        return self._openai

    async def stream(self, question, transcript, notes, deep=False, history=(), images=(),
                     screen_text=None) -> AsyncIterator:
        """Stream the answer; if it comes out in English, yield RESTART and stream a Chinese one instead."""
        text, chinese = "", False
        first = self._stream_once(question, transcript, notes, deep, history, images, screen_text)
        try:
            async for delta in first:
                yield delta
                if chinese:
                    continue
                text += delta
                if len(CJK.findall(text)) >= 40:
                    chinese = True                 # clearly Chinese: no more checks needed
                elif looks_english(text):
                    break
            else:
                return
        finally:
            await first.aclose()
        yield RESTART
        async for delta in self._stream_once(question, transcript, notes, deep, history, images, screen_text,
                                             strict=True):
            yield delta

    async def _stream_once(self, question, transcript, notes, deep=False, history=(), images=(),
                           screen_text=None, strict=False) -> AsyncIterator[str]:
        from .screenshot import b64, ocr_many
        model = self.s.llm_deep_model if deep else self.s.llm_model
        images = list(images or [])
        mode = vision_mode(self.s)
        if images and mode == "ocr" and screen_text is None:
            screen_text = await ocr_many(images)
        send_images = images if mode == "image" else []
        if send_images and self.s.llm_vision_model:
            model = self.s.llm_vision_model                   # the text model cannot see pictures
        blocks, user = build_prompt(question, transcript, notes, detailed=deep or self.s.answer_style == "detailed",
                                    history=history, screen_text=screen_text, has_images=bool(send_images),
                                    strict=strict, code_language=getattr(self.s, "code_language", ""))
        max_tokens = self.s.max_tokens * (2 if deep else 1)
        if images:
            max_tokens = max(max_tokens, self.s.shot_max_tokens)      # screenshots get full-length answers
        client = self._client()
        if self.s.llm == "anthropic":
            # Notes are a stable prefix: cache them so repeated questions start faster and cost less.
            system = [{"type": "text", "text": b} for b in blocks]
            system[-1]["cache_control"] = {"type": "ephemeral"}
            content = [{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(p)}}
                       for p in send_images] + [{"type": "text", "text": user}]
            async with client.messages.stream(model=model, max_tokens=max_tokens, system=system,
                                              messages=[{"role": "user", "content": content}]) as stream:
                async for text in stream.text_stream:
                    yield text
        else:
            extra = {}
            body = thinking_options(self.s.llm, deep)
            if body:
                extra["extra_body"] = body
                if deep:
                    max_tokens = max(max_tokens, 4000)       # reasoning tokens count towards the limit
            response = await client.chat.completions.create(
                model=model, max_tokens=max_tokens, stream=True,
                messages=[{"role": "system", "content": "\n\n".join(blocks)},
                          {"role": "user", "content": user if not send_images else
                           [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(p)}"}}
                            for p in send_images] + [{"type": "text", "text": user}]}],
                **extra)
            async for chunk in response:
                if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

    async def warmup(self):
        """Open the HTTPS connection early so the first real answer is not slowed by TLS setup."""
        gen = self.stream("Reply with OK.", "", "", deep=False)
        try:
            async for _ in gen:
                break
        except Exception as error:
            return str(error)
        finally:
            await gen.aclose()
        return None
