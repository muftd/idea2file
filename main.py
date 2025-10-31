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
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover - optional dependency for offline demos
    OpenAI = None  # type: ignore[assignment]

TEMPLATE_PATH = Path(__file__).with_name("prompt_template.txt")

# V2: 预定义的笔记分类及对应文件夹名称
CATEGORIES = {
    "通用心智": "通用心智",
    "设计模式": "设计模式",
    "产品方法论": "产品方法论",
    "战略洞察": "战略洞察",
    "其他": "其他",
}


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


def determine_category(content: str, api_key: Optional[str]) -> str:
    """Analyze Markdown content and determine its category.

    使用 LLM API（如果可用）来智能判断笔记的分类。
    如果 API 不可用，则使用关键词匹配的降级策略。

    Args:
        content: 笔记的完整 Markdown 内容
        api_key: OpenAI API 密钥（可选）

    Returns:
        分类名称，必定是 CATEGORIES 中的一个键
    """

    # 策略1: 尝试使用 LLM 进行智能分类
    if api_key and OpenAI is not None:
        try:
            client = OpenAI(
                api_key=api_key,
                base_url=os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1"),
            )

            # 构建分类提示词
            category_list = "、".join(CATEGORIES.keys())
            classify_prompt = f"""请分析以下 Markdown 笔记内容，并将其归类到以下类别之一：
{category_list}

分类说明：
- 通用心智：关于思维方式、认知模型、心理学原理等通用思维框架
- 设计模式：软件设计模式、架构模式、代码组织方式等技术设计
- 产品方法论：产品设计、用户体验、产品开发流程等方法论
- 战略洞察：商业战略、市场分析、行业趋势等宏观洞察
- 其他：无法明确归类的内容

笔记内容：
{content[:1000]}

请仅返回最合适的分类名称，不要包含任何其他解释。"""

            completion = client.chat.completions.create(
                model="openrouter/auto",
                messages=[
                    {"role": "system", "content": "你是一个专业的内容分类助手。"},
                    {"role": "user", "content": classify_prompt},
                ],
            )

            choices = getattr(completion, "choices", None) or []
            if choices:
                first_choice = choices[0]
                message = getattr(first_choice, "message", None)
                category = getattr(message, "content", None) if message else None

                # 验证返回的分类是否有效
                if category:
                    category = category.strip()
                    for valid_category in CATEGORIES.keys():
                        if valid_category in category:
                            print(f"📊 LLM 分类结果：{valid_category}")
                            return valid_category

        except Exception as e:
            print(f"⚠️ LLM 分类失败: {e}")

    # 策略2: 降级到关键词匹配
    print("📊 使用关键词匹配进行分类...")

    # 将内容转为小写以便匹配
    content_lower = content.lower()

    # 定义每个分类的关键词
    keywords = {
        "通用心智": ["思维", "认知", "心理", "思考方式", "心智模型", "认知偏差", "思维框架"],
        "设计模式": ["设计模式", "架构", "代码", "编程", "软件", "重构", "面向对象", "函数式"],
        "产品方法论": ["产品", "用户", "需求", "功能", "体验", "迭代", "敏捷", "原型", "mvp"],
        "战略洞察": ["战略", "市场", "竞争", "商业", "趋势", "行业", "布局", "定位", "商业模式"],
    }

    # 统计每个分类的关键词出现次数
    scores = {}
    for category, words in keywords.items():
        score = sum(1 for word in words if word in content_lower)
        scores[category] = score

    # 找到得分最高的分类
    if scores:
        best_category = max(scores, key=scores.get)
        if scores[best_category] > 0:
            print(f"📊 关键词匹配结果：{best_category}（匹配 {scores[best_category]} 个关键词）")
            return best_category

    # 如果没有任何匹配，返回"其他"
    print("📊 未找到明确分类，归入：其他")
    return "其他"


def categorize_and_move_file(filepath: Path, api_key: Optional[str]) -> Path:
    """Categorize the generated Markdown file and move it to the appropriate folder.

    这个函数实现了 V2 规范中的"自动分类"功能：
    1. 读取生成的 Markdown 文件内容
    2. 调用 determine_category() 判断分类
    3. 创建对应的分类文件夹（如果不存在）
    4. 将文件移动到分类文件夹中
    5. 返回文件的新路径

    Args:
        filepath: 原始 Markdown 文件的路径（Path 对象）
        api_key: OpenAI API 密钥，用于智能分类（可选）

    Returns:
        移动后的文件路径（Path 对象）
    """

    # 步骤1: 读取文件内容
    try:
        content = filepath.read_text(encoding="utf-8")
    except Exception as e:
        print(f"⚠️ 读取文件失败: {e}")
        return filepath  # 如果读取失败，返回原路径

    # 步骤2: 判断分类
    category = determine_category(content, api_key)

    # 步骤3: 创建分类文件夹
    # 文件夹位于脚本所在目录下
    category_folder = Path(__file__).parent / CATEGORIES[category]
    category_folder.mkdir(parents=True, exist_ok=True)

    # 步骤4: 构建新路径并移动文件
    new_path = category_folder / filepath.name

    # 如果目标位置已存在同名文件，添加后缀避免覆盖
    suffix = 2
    while new_path.exists():
        stem = filepath.stem  # 文件名（不含扩展名）
        new_path = category_folder / f"{stem}-{suffix}.md"
        suffix += 1

    # 使用 shutil.move 移动文件
    shutil.move(str(filepath), str(new_path))

    print(f"📁 已移动到分类文件夹：{category} → {new_path.name}")

    return new_path


def update_index() -> None:
    """Update the index.md file with all generated notes.

    这个函数实现了 V2 规范中的"索引文件生成"功能：
    1. 扫描脚本所在目录及所有子文件夹中的 .md 文件
    2. 提取每个笔记的标题和生成日期
    3. 按时间倒序排列（最新的在最上面）
    4. 生成或更新 index.md 文件

    索引格式示例：
    - [笔记标题](./相对路径/文件名.md) — YYYY-MM-DD
    """

    # 步骤1: 获取脚本所在目录
    base_dir = Path(__file__).parent

    # 步骤2: 扫描所有 .md 文件（排除 index.md 本身和特殊目录）
    all_md_files = []

    # 需要排除的目录
    excluded_dirs = {".venv", ".git", "node_modules", "__pycache__"}

    # 使用 rglob 递归查找所有 .md 文件
    for md_file in base_dir.rglob("*.md"):
        # 排除 index.md 本身
        if md_file.name.lower() == "index.md":
            continue

        # 检查文件路径是否包含需要排除的目录
        if any(excluded_dir in md_file.parts for excluded_dir in excluded_dirs):
            continue

        all_md_files.append(md_file)

    if not all_md_files:
        print("📇 未找到任何笔记文件，跳过索引更新")
        return

    # 步骤3: 提取每个文件的元信息
    note_entries = []

    for md_file in all_md_files:
        try:
            # 读取文件内容以提取标题
            content = md_file.read_text(encoding="utf-8")

            # 提取标题：找第一行以 # 开头的内容
            title = None
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("#"):
                    # 移除开头的 # 符号和空格
                    title = line.lstrip("#").strip()
                    break

            # 如果没有找到标题，使用文件名（去除扩展名）
            if not title:
                title = md_file.stem

            # 获取文件修改时间
            # 使用 stat().st_mtime 获取修改时间戳
            mtime = md_file.stat().st_mtime
            date_obj = datetime.fromtimestamp(mtime)
            date_str = date_obj.strftime("%Y-%m-%d")

            # 计算相对路径
            # 使用 relative_to 获取相对于 base_dir 的路径
            relative_path = md_file.relative_to(base_dir)

            # 存储索引项：(时间戳, 标题, 相对路径, 日期字符串)
            note_entries.append((mtime, title, relative_path, date_str))

        except Exception as e:
            print(f"⚠️ 处理文件 {md_file.name} 时出错: {e}")
            continue

    # 步骤4: 按时间倒序排列（最新的在前）
    note_entries.sort(key=lambda x: x[0], reverse=True)

    # 步骤5: 生成索引内容
    index_lines = ["# 笔记索引\n", "\n"]

    for _, title, relative_path, date_str in note_entries:
        # 格式：- [标题](./相对路径) — YYYY-MM-DD
        # 使用 .as_posix() 确保路径使用正斜杠（跨平台兼容）
        index_line = f"- [{title}](./{relative_path.as_posix()}) — {date_str}\n"
        index_lines.append(index_line)

    # 步骤6: 写入 index.md 文件
    index_path = base_dir / "index.md"

    try:
        index_path.write_text("".join(index_lines), encoding="utf-8")
        print(f"📇 已更新索引文件：共 {len(note_entries)} 条笔记")
    except Exception as e:
        print(f"⚠️ 写入索引文件失败: {e}")


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

    # V2: 自动分类并移动文件
    final_path = categorize_and_move_file(output_path, api_key)

    # V2: 更新索引文件
    update_index()

    print(f"\n🎉 完成！文件位于：{final_path.relative_to(Path(__file__).parent)}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # Gracefully handle Ctrl+C so the script exits without a stack trace.
        sys.exit("\n操作已取消。")
