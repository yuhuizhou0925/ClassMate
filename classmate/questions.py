"""Fast, local question detection on finished speaker turns (English and Chinese).

Runs in microseconds, so answering starts the moment the ASR closes a turn.
It is deliberately recall-oriented; the UI also has an "answer now" button for
anything it misses.
"""
from __future__ import annotations

import re

LEAD = r"^(so,?\s+|okay,?\s+|ok,?\s+|now,?\s+|and\s+|right,?\s+|alright,?\s+|well,?\s+)*"
EN_WH = re.compile(LEAD + r"(what|why|how|when|where|which|who|whom|whose)\b", re.I)
EN_AUX = re.compile(LEAD + r"(is|are|was|were|do|does|did|can|could|would|should|will|has|have|had|may|might|"
                    r"shall|isn't|aren't|doesn't|don't|didn't|won't|wouldn't|can't|couldn't|shouldn't)\b", re.I)
EN_CUES = re.compile(
    r"\b(anyone (know|tell|guess|remember|want|explain)|any(body|one) (know|have|got)|"
    r"can (someone|somebody|anyone|you) (tell|explain|guess|give|think)|"
    r"who (can|wants to|knows)|what do you (think|reckon|guys think)|any (ideas|guesses|thoughts)|"
    r"tell me (why|how|what)|explain (why|how|what)|i('d| would) like (someone|you) to)\b", re.I)
ZH_END = re.compile(r"[吗呢么嘛吧][？?。.!！]?$")
ZH_CUES = re.compile(r"(什么|为什么|为啥|怎么|怎样|如何|哪(个|些|里|儿)|谁|多少|是否|是不是|有没有|能不能|"
                     r"可不可以|对不对|知道|大家(觉得|认为)|请问|你们(觉得|认为)|同学们?)")
NOT_QUESTION = re.compile(r"\b(i wonder|no question|let me (ask|show)|the question is whether)\b", re.I)
# "What we'll do today is...", "How this works is...", "Which means..." are statements
PSEUDO_CLEFT = re.compile(LEAD + r"((what|how|why|when|where) (we|i|you|this|that|it)('ll|'re|'ve| will| are| is| did| do|"
                          r" want| need| have)\b|which (is|means|was)\b)", re.I)


def question_score(text: str) -> float:
    """0..1 likelihood that a finished turn asks something of the audience."""
    t = text.strip()
    if not t:
        return 0.0
    words = t.split()
    score = 0.0
    if t.endswith(("?", "？")):
        score += 0.6
    if EN_WH.search(t):
        score += 0.55
    elif EN_AUX.search(t):
        score += 0.4 + (0.1 if re.search(r"\b(you|we|anyone|someone)\b", t, re.I) else 0)
    if EN_CUES.search(t):
        score += 0.5
    if ZH_END.search(t):
        score += 0.45
    cues = {m.group(0) for m in ZH_CUES.finditer(t)}
    score += 0.3 * min(2, len(cues))
    if t.endswith(("。", ".")) and score < 0.6:     # a full stop after a cue word is usually a statement
        score -= 0.15
    if NOT_QUESTION.search(t):
        score -= 0.4
    if PSEUDO_CLEFT.search(t) and not t.endswith(("?", "？")):
        score -= 0.5
    is_cjk = bool(re.search(r"[一-鿿]", t))
    if (not is_cjk and len(words) < 3) or (is_cjk and len(t) < 4):
        score -= 0.4
    return max(0.0, min(1.0, score))


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s*", text.strip())
    return [p for p in parts if p]


def find_question(turn: str, threshold: float = 0.5) -> str | None:
    """Return the question sentence(s) inside a finished turn, or None.

    Lecturers often ask then keep talking ("What is overfitting? Think about...").
    The last questioning sentence plus its preceding sentence is returned.
    """
    sentences = split_sentences(turn) or [turn]
    best = None
    for i, s in enumerate(sentences):
        if question_score(s) >= threshold:
            best = i
    if best is None:
        return turn if question_score(turn) >= threshold else None
    start = max(0, best - 1)
    return " ".join(sentences[start:best + 1])


# Words that point back to an earlier question or answer. Plain "这个 / this" is not enough on its own: in a
# lecture it usually means the slide ("这个卷积核的作用是什么"), not the previous answer.
ZH_BACK = re.compile(r"(它们?|刚才|刚刚|上面|前面|之前|上一[个题问步]|上述|继续|接着|再说|还有呢|那么|同样|此外|另外|"
                     r"区别|对比|比较|相比|[这那][个种](方案|方法|做法|算法|技术|架构|设计|模型|思路|结果|答案)|"
                     r"这样做|那样做|^那.{0,12}[呢吗]|^为什么[？?]?$)")
EN_BACK = re.compile(r"\b(it|its|they|them|those|that one|the (previous|last|above|same)|earlier|above|also|"
                     r"what about|how about|instead|compared?|difference|differ|versus|vs\.?|then why|and why|why not)\b",
                     re.I)


def is_follow_up(question: str) -> bool:
    """Does this question build on an earlier one ("那性能呢？", "how does it scale?")? Only then are earlier
    questions and answers sent along, so an unrelated new question is not steered towards the old topic."""
    q = " ".join((question or "").split())
    if not q:
        return False                                  # a screenshot: a new item
    if ZH_BACK.search(q) or EN_BACK.search(q):
        return True
    cjk = len(re.findall(r"[一-鿿]", q))
    words = len(re.findall(r"[A-Za-z]+", q))
    return (cjk and cjk <= 6 and words <= 1) or (not cjk and words <= 3)    # "为什么呢？", "why so?"
