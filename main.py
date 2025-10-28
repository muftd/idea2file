"""idea2file CLI entry point.

This script collects a user's idea, merges it with a Markdown template,
optionally calls an LLM to expand the idea, and writes the output to a
timestamped Markdown file.  The code is intentionally verbose with comments so that
non-technical teammates can follow along.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover - optional dependency for offline demos
    OpenAI = None  # type: ignore[assignment]

TEMPLATE_PATH = Path(__file__).with_name("prompt_template.txt")


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
    """Send the prompt to OpenRouter-compatible Chat Completions API."""

    if OpenAI is None:
        print("⚠️ 未找到 OpenAI SDK，无法连接到 OpenRouter。")
        return None

    client = OpenAI(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
    )

    try:
        completion = client.chat.completions.create(
            model="openrouter/auto",
            messages=[
                {"role": "system", "content": "你是知识结构化助手。"},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception:
        return None

    choices = getattr(completion, "choices", None) or []
    if not choices:
        return None

    first_choice = choices[0]
    message = getattr(first_choice, "message", None)
    content = getattr(message, "content", None) if message else None
    if isinstance(content, str):
        return content.strip()

    return None


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


def _sanitize_visible_text(text: str, *, max_length: int = 10) -> str:
    """Return the first ``max_length`` visible characters without special symbols."""

    visible = "".join(ch for ch in text if not ch.isspace())
    truncated = visible[:max_length]
    sanitized = re.sub(r"[^\w\u4e00-\u9fff]", "", truncated)
    return sanitized or "idea"


def build_output_path(idea: str) -> Path:
    """Create a timestamped Markdown filename derived from the user's idea."""

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    stem = _sanitize_visible_text(idea)
    base_name = f"{timestamp}-{stem}.md"
    candidate = Path(__file__).with_name(base_name)

    suffix = 2
    while candidate.exists():
        candidate = Path(__file__).with_name(f"{timestamp}-{stem}-{suffix}.md")
        suffix += 1

    return candidate


def main() -> None:
    """Entry point executed when the script runs from the command line."""

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="将想法转换为结构化的 Markdown 文件"
    )
    parser.add_argument(
        "--idea",
        type=str,
        help="直接通过命令行提供想法，而不使用交互式输入",
    )
    args = parser.parse_args()

    # Use command-line argument if provided, otherwise prompt interactively
    if args.idea:
        user_idea = args.idea.strip()
    else:
        user_idea = input("请输入你的想法：").strip()

    template = read_template()
    api_key = load_api_key()

    markdown = generate_markdown(template, user_idea, api_key)
    output_path = build_output_path(user_idea)
    output_path.write_text(markdown, encoding="utf-8")

    print(f"✅ 已生成 {output_path.name}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Gracefully handle Ctrl+C so the script exits without a stack trace.
        sys.exit("\n操作已取消。")
