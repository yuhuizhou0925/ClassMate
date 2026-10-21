#!/bin/bash
# Double-click to start Classmate. First run installs everything and asks for your API keys.
cd "$(dirname "$0")" || exit 1
pause() { echo; read -n 1 -s -r -p "按任意键关闭窗口…"; echo; }

if [ ! -x .venv/bin/python ]; then
  echo "首次运行：正在安装（大约 1–3 分钟，只需一次）…"
  if ! command -v python3 >/dev/null 2>&1; then
    echo "没有找到 Python 3。请先从 https://www.python.org/downloads/macos/ 安装，再双击本文件。"; pause; exit 1
  fi
  python3 -m venv .venv || { echo "创建虚拟环境失败"; pause; exit 1; }
  .venv/bin/python -m pip install -q --upgrade pip
fi
if [ ! -f .venv/.installed ] || [ pyproject.toml -nt .venv/.installed ]; then
  echo "正在安装 / 更新依赖…"
  .venv/bin/python -m pip install -q -e . || { echo "安装失败，请把上面的错误发给我"; pause; exit 1; }
  touch .venv/.installed
fi

if [ ! -f .env ]; then
  echo
  echo "首次运行：请粘贴 API key（输入时不显示，直接回车可跳过）"
  read -r -s -p "  AssemblyAI key（语音识别，必填）: " AAI; echo
  read -r -s -p "  DeepSeek key（回答；用豆包 / 通义千问可跳过，进软件后点 ⚙ 填）: " DS; echo
  read -r -s -p "  Anthropic / Claude key（可跳过）: " AN; echo
  {
    [ -n "$AAI" ] && echo "ASSEMBLYAI_API_KEY=$AAI"
    [ -n "$DS" ] && echo "DEEPSEEK_API_KEY=$DS"
    [ -n "$AN" ] && echo "ANTHROPIC_API_KEY=$AN"
  } > .env
  chmod 600 .env
  echo "已保存到 .env。用豆包 / 通义千问，或以后要改 key：在软件窗口右上角点 ⚙ 设置。"
  .venv/bin/python -m classmate --check-keys
fi

echo "课件：把 PDF / PPT 放进 notes 文件夹会自动读取。"
.venv/bin/python -m classmate "$@"
status=$?
[ $status -ne 0 ] && pause
exit $status
