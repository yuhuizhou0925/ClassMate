# Classmate：课堂实时转写 + 提问回答草稿

在 Mac 上实时转写老师讲课的内容。老师向全班提问时，自动识别出问题，并在 1 秒左右开始流式生成一份回答草稿。界面是本机浏览器里的一个普通网页窗口。

```
麦克风 / Zoom 声音 ──► 流式语音识别 ──► 问题识别（本地，<1ms）──► 流式生成回答 ──► 浏览器界面
                     (AssemblyAI 等)                              (Claude Haiku 等)
                                                       ▲
                                     课件/笔记 + 最近 8 分钟的转写作为上下文
```

## 最简单的用法：双击启动

1. 解压后，**双击 `Classmate.command`**。
   - 第一次 macOS 可能提示"无法验证开发者"：右键点它 → 打开 → 打开，之后就能直接双击了。
2. **只有第一次**会自动安装（约 1–3 分钟），并让你在终端里粘贴 key：AssemblyAI 必填，DeepSeek 和 Claude 填一个就行；用豆包或通义千问的话这里直接回车跳过，进软件后在 ⚙ 设置里填。
3. 之后每次**双击就直接打开**，自动用你填了 key 的那家模型。
4. 课件放进 `notes` 文件夹会自动读取。换模型、换 key、改快捷键：点窗口右上角的 **⚙**（或按 <kbd>⌘,</kbd>）。

想放到桌面：右键 `Classmate.command` → 制作替身，把替身拖到桌面。

## 功能

- **实时转写**：灰色斜体是识别中的文字，确定后变成黑色，并标上时间。
- **自动识别提问**：中英文都支持。像 "Can anyone tell me…"、"大家觉得为什么…" 这类口语问法，以及 ASR 没加问号的问句，都能识别；"What we'll do today is…" 这类陈述句会被排除。
- **流式回答**：语音问题先给一句直接答案，再列最多 3 个要点。**截图题会先提取题目（翻成中文），再完整作答**：选择题给答案和理由，计算题写步骤，代码题给完整代码，图或表则逐部分讲解；长度不设限制（上限 `shot_max_tokens` 3000）。**强制中文回答**：英文课、英文课件、英文截图也一样用中文，关键术语第一次出现时附英文原词，比如"单应性（homography）"，代码和公式保持原样。如果模型还是开始用英文答，会自动丢掉、用更强的要求重新生成中文回答（界面上那段英文会被清掉）。回答优先使用课件里的术语。
- **偏好编程语言**：⚙ 设置里选（Python、Java、C++… 或自己输入）。代码题自己写的解答、示例都用这个语言；题目给出的代码（找 bug、改错、判断输出）修正版保持原语言；题目明确要求别的语言时按题目来。留空 = 跟随题目。
- **手动触发**：按 **空格** 或点 "Answer now"，立即针对刚才说的话生成回答；也可以在输入框里自己打字提问。
- **Deeper answer**：遇到难题时，用更强的模型生成更完整的解释。
- **课件导入**：支持 PDF、PPTX、DOCX、Markdown、TXT 或整个文件夹，回答会贴合课程内容。课件部分会走 Prompt Caching，后续回答更快也更便宜。
- **自动保存**：每节课的转写和问答保存为 `sessions/日期_时间.md`，方便课后复习。
- **设置面板（⚙）**：在窗口里切换回答模型（Claude / DeepSeek / 豆包 / 通义千问 / 任意 OpenAI 兼容接口）、改模型名、填 API key、换语音识别、改快捷键。保存后**立即生效，不用重启**。
- **延迟显示**：每个回答下方显示"出第一个字用了多久 / 全部完成用了多久"，从老师说完那一刻开始计时。

## 操作方式

界面是一个原生 Mac 小窗口，默认 460×620。加 `--browser` 可以改用浏览器打开。

| 按键 | 作用 |
|---|---|
| **Tab** | 截取**你正在看的窗口**（Zoom、PPT、浏览器等，自动跳过 Classmate 自己），**直接作为一个单独的新问题**生成回答，左侧列表显示为"截图 1""截图 2"…… |
| **Shift + Tab** | 框选屏幕上的一块区域截图，然后同样直接回答 |
| **按一下 Ctrl** | **开始录音**（没开始监听的话会自动开始），说的话在红框里**实时显示**；录音期间不会自动回答 |
| **再按一下 Ctrl** | **立即回答**刚才录的内容，连还没识别完的半句也算进去，不用等这句说完。Esc 放弃这次录音 |
| **按一下 `**（中文输入法下打出 · 的那个键） | **追加到当前问题**：开始录音，内容接在当前问题后面；再按一下 ` 或 Ctrl 结束，把补充后的完整问题重新回答，卡片上标"已补充" |
| 不按 Ctrl | 老师说完一段话（声音停顿）就自动生成（顶栏"自动 ✓"可以关掉）；当前回答还在生成时听到的话会排队，**当前回答完成后自动作为下一题** |

只有**单独按一下** Ctrl 才算：按着 Ctrl 再按别的键（⌃C、⌃V 这类组合键）不会触发录音。想用原来"按住 Ctrl 收录、松开回答、回答后再按 = 补充"的方式：⚙ 设置 → 提问方式 → Ctrl 用法 → 按住。
| **Shift + ↑ / ↓** | 上一题 / 下一题。翻看旧题时有新问题进来，会提示"有新问题 ⇧↓" |
| **⌘ ,** | 打开设置 |
| 顶栏 **◐** 滑块 | 调窗口透明度（20%–100%），拖动时实时变化，松手后记住，下次打开沿用。只在原生窗口里有，浏览器模式没有 |
| **↑ ↓ ← →** | 移动窗口，每次 40 像素；加 **Option** 每次 10 像素微调 |
| Space | 立即回答刚才的话（包括还没说完的那句） |
| Esc | 放弃正在收录的内容，下一段话作为新问题 |
| D / C | 对当前题生成深度回答 / 复制答案 |
| M | 切换自动回答范围："仅提问"只回答识别为提问的话，"每段话"是每次停顿都回答 |
| L | 显示 / 隐藏左侧问题列表 |
| T / / / ? | 展开实时转写 / 打字提问 / 显示快捷键 |

- **自定义快捷键**：上表除方向键（固定用来移动窗口）外都能改。在 ⚙ 设置的"快捷键"里点一下对应按钮，再按新按键即可；冲突会标红并拒绝保存，"恢复默认"一键还原。所有键都可以是组合键（如 ⌃⌥S）。截图、框选截图、收录这三个在其他软件里也生效；框选截图默认是 ⇧ + 截图键，改截图键时会自动跟着变。收录键可以只是一个修饰键（按住 Ctrl / ⌥ / ⌘），也可以是组合键（按住 ⌥Space）；如果收录键是单个修饰键，其他快捷键就不能再用这个修饰键，不然一按就会开始收录。也可以写在 `config.yaml` 的 `keys:` 里（见 `config.example.yaml`）。
- **不会回答语气词**："每段话"模式下，"嗯""是的""好的""OK"这类很短的应答不会触发回答（阈值 `min_turn_chars` 可调）。
- **左侧问题列表**：每个问题一行摘要，下面一行是回答的开头。语音问题显示问题内容，截图问题显示"截图 N"。点击或 Shift+↑↓ 切换。
- **截图怎么发给模型**：用 Claude、豆包时直接发送图片，公式、图表、代码都能看懂；用通义千问时，截图题自动换成能看图的 `qwen3-vl-plus`（设置里的"截图模型"）；用 DeepSeek 时，先用 Mac 自带的文字识别（本地、免费、中英文）转成文字再发送，所以图里的图表 DeepSeek 看不到。可以用 `vision: image / ocr` 强制指定。
- **后面的问题参考前面的答案**：每次生成时，会把最近 6 轮问答（`history_answers` 可调）连同课件和最近 8 分钟转写一起发给模型。追问、"和刚才那个有什么区别"这类问题能接得上，回答也会和之前保持一致、不重复。
- **方向键只在 Classmate 窗口有焦点时生效**，否则会影响你在其他软件里打字。**Ctrl 和 Tab 是全局的**，焦点在 Zoom 或 PPT 上也能用。注意：在其他软件里正常按 Tab（比如填表、写代码），也会触发截图并调用一次模型。如果嫌干扰，在 ⚙ 设置里把截图键改成 F5 等不常用的键。
- 第一次运行时，macOS 会要求给终端权限，在 系统设置 → 隐私与安全性 里打开：
  - **辅助功能**、**输入监控**：全局 Ctrl 和 Tab 需要；
  - **屏幕录制**：截图需要。没有这个权限的话，截图里只有桌面背景，看不到窗口内容。
  不想给全局按键权限，可以加 `--no-global-keys`，Ctrl 和 Tab 就只在 Classmate 窗口有焦点时生效。
- 这是普通窗口，共享屏幕时和其他窗口一样，会被看到。

## 安装（macOS，Python 3.10+）

```bash
cd classmate
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env             # 填入你要用的 API key
cp config.example.yaml config.yaml   # 可选：改默认设置、课件路径、专业术语
```

需要两个 key：一个语音识别的（默认 AssemblyAI），一个生成模型的（默认 Anthropic）。

第一次运行时，macOS 会询问"终端"能否使用麦克风，选允许。如果之前拒绝过，到 **系统设置 → 隐私与安全性 → 麦克风** 里打开。

## 使用

```bash
python -m classmate --demo                      # 先看效果：模拟的一段课，不需要 key 和麦克风
python -m classmate                             # 默认麦克风 + 自动回答
python -m classmate --notes ~/Documents/COMP90086/week10   # 带上本周课件
python -m classmate --language zh               # 中文课；默认 auto 自动识别、支持中英混说
python -m classmate --no-auto                   # 不自动生成，只在按 Ctrl 录完 / 按空格时生成
python -m classmate --mode questions            # 只对识别为提问的话生成（默认每次停顿都生成）
python -m classmate --browser                   # 用浏览器代替原生窗口
python -m classmate --list-devices              # 列出输入设备
```

### 网课：直接转写 Zoom / Teams 里老师的声音

用麦克风录扬声器里的声音效果会差。更好的办法是用免费的虚拟声卡 BlackHole 直接接系统声音：

1. `brew install blackhole-2ch`，或从 existential.audio 下载安装。
2. 打开 **音频 MIDI 设置**，点左下角 "+" → **创建多输出设备**，同时勾选你的耳机或扬声器和 BlackHole 2ch。
3. 在 Zoom 或 Teams 的音频设置里，把扬声器设为这个多输出设备。这样你自己照样听得到。
4. 运行 `python -m classmate --device BlackHole`。

## 模型选择

默认组合是按"速度和准确率都要好"选的。所有选项都可以在 `config.yaml` 里或用命令行参数切换。

| 环节 | 默认 | 备选 | 说明 |
|---|---|---|---|
| 语音识别 | AssemblyAI Universal-Streaming（`universal-3-6-pro`） | ElevenLabs Scribe v2 Realtime；Deepgram Nova-3 | 在第三方实时评测里，AssemblyAI 是唯一在延迟（约 1 秒）和词错率（约 4%）上都排前面的，支持中文和中英混说。ElevenLabs 自动识别语言、覆盖 90 多种语言。Deepgram 延迟最低，适合纯英文 |
| 回答生成 | Claude Haiku（`claude-haiku-5-5`） | DeepSeek、豆包、通义千问、任意 OpenAI 兼容接口（Groq、Cerebras、OpenAI…） | Haiku 首字延迟低，回答质量好。国内网络推荐豆包或通义千问。Groq、Cerebras 上的开源模型每秒能出几百到上千个 token，但答案质量通常不如 Haiku |
| 深度回答 | Claude Sonnet（`claude-sonnet-5-5`） | 同上 | 只在点 "Deeper answer" 时使用 |

各家的默认模型（都能在 ⚙ 设置里改）：

| 服务商 | `--llm` | key（`.env`） | 普通回答 | 深度回答（开思考） | 截图 |
|---|---|---|---|---|---|
| Claude | `anthropic` | `ANTHROPIC_API_KEY` | `claude-haiku-5-5` | `claude-sonnet-5-5` | 发图片 |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | `deepseek-flash` | `deepseek-v4-pro` | 本机文字识别 |
| 豆包（火山方舟） | `doubao` | `ARK_API_KEY` | `doubao-seed-1-6-flash-250828` | `doubao-seed-1-6-251015` | 发图片 |
| 通义千问（阿里云百炼） | `qwen` | `DASHSCOPE_API_KEY` | `qwen-flash` | `qwen-plus` | `qwen3-vl-plus` 看图 |
| OpenAI 兼容 | `openai` | `OPENAI_API_KEY` | 必须自己填 | 同普通回答 | 发图片 |

普通回答一律关闭思考模式，出字最快；深度回答开启思考，思考过程不显示，所以要等一会儿才出字。

例：改用 DeepSeek（`.env` 里填 `DEEPSEEK_API_KEY`，在 platform.deepseek.com 申请）：

```bash
python -m classmate --llm deepseek
```

例：改用豆包（在 [火山方舟控制台](https://console.volcengine.com/ark) → API Key 管理 创建 key，填到 `ARK_API_KEY`）：

```bash
python -m classmate --llm doubao
python -m classmate --llm doubao --model doubao-seed-1-6-251015   # 或控制台"模型列表"里的其他 Model ID / 接入点 ep-xxxx
```

豆包的模型名带日期版本号，火山方舟会不定期上新、下线旧版本。如果提示模型不存在，到控制台的模型列表复制最新的 Model ID，填进 ⚙ 设置。

例：改用通义千问（在 [阿里云百炼控制台](https://bailian.console.aliyun.com/) 创建 API Key，填到 `DASHSCOPE_API_KEY`）：

```bash
python -m classmate --llm qwen
```

阿里云国际站的账号要把接口地址改成 `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`（⚙ 设置 → 接口地址，或 `--base-url`）。

例：改用 Groq 上的开源模型，追求极致速度：

```bash
python -m classmate --llm openai --base-url https://api.groq.com/openai/v1 --model openai/gpt-oss-120b
```

**提升准确率的几个办法：**
- 在 `config.yaml` 的 `keyterms` 里写上课程专有名词，比如 homography、RANSAC，识别会更准。
- 用 `--notes` 导入当周课件。
- 网课用 BlackHole，不要用麦克风去录扬声器。

## 用的时候请注意

这个工具是用来帮你**跟上课堂、理解问题、组织自己的回答**的。如果课堂发言计入成绩，或者课程对 AI 使用有规定（你们的课就有），请按规定使用和披露。界面是普通窗口，共享屏幕时可以只共享具体的应用窗口。

## 开发

```bash
pip install -e ".[dev]"
pytest -q          # 77 个测试：问题识别、三家 ASR 协议、端到端会话、Ctrl 录音（按一下 / 按住）/补充/排队、强制中文、历史问答、截图、图片/OCR、DeepSeek / 豆包 / 通义千问、设置面板、快捷键
```

| 文件 | 作用 |
|---|---|
| `classmate/audio.py` | 麦克风 / BlackHole 采集、WAV 回放 |
| `classmate/asr/` | AssemblyAI、ElevenLabs、Deepgram 流式识别，统一的事件接口 |
| `classmate/questions.py` | 本地中英文问题识别 |
| `classmate/config.py` | 设置（`config.yaml` → 设置面板的 `settings.yaml` → 命令行参数）、各家模型的默认值（`PROVIDERS`）、快捷键校验 |
| `classmate/llm.py` | 提示词与流式生成（Anthropic / OpenAI 兼容：DeepSeek、豆包、通义千问…） |
| `classmate/context.py` | 课件读取、转写缓冲 |
| `classmate/app.py` | 问题收录规则（Ctrl / 补充 / 排队）、历史问答、断线重连、会话日志、WebSocket 服务 |
| `classmate/desktop.py` | 原生窗口（pywebview）、全局收录键 / 截图键（pynput，改键后自动重启监听） |
| `classmate/screenshot.py` | 截屏（macOS screencapture）、本地文字识别（macOS Vision） |
| `classmate/ui/index.html` | 界面、设置面板（自动适配深色模式） |

## 常见问题

- **按 Caps Lock 切换中英文时程序闪退**：已修复。原因是全局按键监听库 pynput 会在后台线程里处理 Caps Lock 切换输入法时发出的系统事件，新版 macOS 不允许这样做，会直接结束程序。现在不再监听这类事件（只影响音量、播放这类媒体键，本软件用不到）。

## 许可证

[MIT](LICENSE)：可以自由下载、修改、二次发布，保留版权声明即可。
