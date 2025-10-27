"""idea2file CLI entry point.

This script collects a user's idea, merges it with a Markdown template,
optionally calls an LLM to expand the idea, and writes the output to
``idea.md``.  The code is intentionally verbose with comments so that
non-technical teammates can follow along.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

TEMPLATE_PATH = Path(__file__).with_name("prompt_template.txt")
OUTPUT_PATH = Path(__file__).with_name("idea.md")


def load_api_key() -> Optional[str]:
    """Retrieve the first available API key from environment variables.

    Currently we only check ``OPENAI_API_KEY`` because this script targets
    OpenAI-compatible endpoints.  The function is isolated so that future
    maintainers can add more sources (for example, a ``.env`` file) without
    touching the rest of the flow.
    """

    env_var_names = ["OPENAI_API_KEY"]
    for name in env_var_names:
        value = os.getenv(name)
        if value:
            return value
    return None


def read_template() -> str:
    """Load the Markdown template from disk."""

    try:
        return TEMPLATE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - should not happen after setup
        raise SystemExit(
            "模板文件不存在，请确认 prompt_template.txt 已经被创建。"
        ) from exc


def merge_template_with_idea(template: str, idea: str) -> str:
    """Insert the raw idea into the template to produce fallback Markdown."""

    sanitized_idea = idea.strip() or "（尚未提供标题）"
    merged = template.replace("# 标题", f"# 标题\n{sanitized_idea}")
    return f"{merged.strip()}\n\n原始想法：{sanitized_idea}\n"


def call_openai_api(prompt: str, api_key: str) -> Optional[str]:
    """Send the prompt to OpenAI's Chat Completions API.

    The function returns the generated Markdown string if the call succeeds,
    otherwise ``None`` which signals the caller to fall back to offline mode.
    """

    request_body = json.dumps(
        {
            "model": "gpt-3.5-turbo",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一名结构化思维助手。请依据用户提供的模板和原始想法，"
                        "生成清晰、可执行的 Markdown。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        return None
    except json.JSONDecodeError:
        return None

    choices = payload.get("choices") or []
    if not choices:
        return None

    message = choices[0].get("message") or {}
    content = message.get("content")
    return content.strip() if isinstance(content, str) else None


def generate_markdown(template: str, idea: str, api_key: Optional[str]) -> str:
    """Produce the final Markdown, using the LLM when possible."""

    base_prompt = merge_template_with_idea(template, idea)

    if not api_key:
        print("⚠️ 未检测到 API Key，已启用离线演示模式。")
        return base_prompt

    llm_response = call_openai_api(base_prompt, api_key)
    if llm_response:
        return f"{llm_response.strip()}\n\n原始想法：{idea.strip()}"

    print("⚠️ LLM 调用失败，已使用模板内容作为替代输出。")
    return base_prompt


def main() -> None:
    """Entry point executed when the script runs from the command line."""

    user_idea = input("请输入你的想法：").strip()
    template = read_template()
    api_key = load_api_key()

    markdown = generate_markdown(template, user_idea, api_key)
    OUTPUT_PATH.write_text(markdown, encoding="utf-8")

    print("✅ 已生成 idea.md")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Gracefully handle Ctrl+C so the script exits without a stack trace.
        sys.exit("\n操作已取消。")
