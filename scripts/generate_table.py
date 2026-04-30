#!/usr/bin/env python3
"""
从 data/prices.json 生成 Markdown 价格对比表。

发卡平台和 API 中转站分开展示:
  - 发卡: 按商品分类 (ChatGPT/Claude/...) 分表，显示固定价格 + 库存
  - 中转: 按平台分表，显示模型名 + 输入/输出价格 + 倍率 + 折扣

用法:
    python scripts/generate_table.py                 # 生成 data/prices_table.md
    python scripts/generate_table.py --update-readme  # 同时更新 README.md
    python scripts/generate_table.py --stdout          # 输出到终端
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES_FILE = ROOT / "data" / "prices.json"
TABLE_FILE = ROOT / "data" / "prices_table.md"
README_FILE = ROOT / "README.md"

FAKA_CATEGORY_ORDER = [
    "ChatGPT", "Claude", "Gemini", "Midjourney",
    "Cursor", "Copilot", "Suno", "Poe",
    "API/Key", "邮箱/账号", "其他",
]

README_START_MARKER = "<!-- PRICE_TABLE_START -->"
README_END_MARKER = "<!-- PRICE_TABLE_END -->"


def load_prices():
    if not PRICES_FILE.exists():
        print(f"错误: 找不到 {PRICES_FILE}，请先运行 scrape_prices.py")
        sys.exit(1)
    with open(PRICES_FILE, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 抓取概况
# ---------------------------------------------------------------------------

def build_summary_table(data):
    lines = ["### 抓取概况\n"]
    lines.append("| 平台 | 类型 | 状态 | 数量 |")
    lines.append("|------|------|------|------|")
    for s in data.get("summary", []):
        status = s.get("status", "unknown")
        icon = "ok" if status == "ok" else "fail"
        stype = "发卡" if s.get("type") == "faka" else "中转"
        count = s.get("count", "-")
        if status != "ok":
            count = s.get("error", "error")[:40]
        lines.append(f"| {s['site']} | {stype} | {icon} | {count} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 发卡平台表格
# ---------------------------------------------------------------------------

def build_faka_tables(data):
    products = data.get("faka", {}).get("products", [])
    if not products:
        return []

    by_cat = defaultdict(list)
    for p in products:
        by_cat[p.get("category", "其他")].append(p)

    sections = []
    all_cats = list(FAKA_CATEGORY_ORDER) + sorted(set(by_cat) - set(FAKA_CATEGORY_ORDER))

    for cat in all_cats:
        items = by_cat.get(cat)
        if not items:
            continue

        lines = [f"#### {cat}\n"]
        lines.append("| 商品名称 | 平台 | 价格 (CNY) | 库存 | 状态 | 标签 |")
        lines.append("|----------|------|-----------|------|------|------|")

        items.sort(key=lambda x: (x.get("price") or 99999, x.get("name", "")))

        for p in items:
            name = p["name"][:50]
            platform = p["platform"]
            price = f"¥{p['price']:.2f}" if p.get("price") else "-"
            stock = p.get("stock_text") or ("-" if p.get("stock") is None else str(p["stock"]))
            status = "售罄" if p.get("soldout") else "在售"
            tags = ", ".join(p.get("tags", []))[:30] or "-"
            lines.append(f"| {name} | {platform} | {price} | {stock} | {status} | {tags} |")

        sections.append("\n".join(lines))

    return sections


# ---------------------------------------------------------------------------
# API 中转站表格
# ---------------------------------------------------------------------------

def build_relay_tables(data):
    models = data.get("relay", {}).get("models", [])
    if not models:
        return []

    by_platform = defaultdict(list)
    for m in models:
        by_platform[m["platform"]].append(m)

    sections = []
    for platform in sorted(by_platform):
        items = by_platform[platform]
        if not items:
            continue

        first = items[0]
        raw_keys = list(first.get("raw", {}).keys())

        if raw_keys:
            lines = [f"#### {platform}\n"]
            headers = raw_keys
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

            for m in items:
                row = m.get("raw", {})
                cells = [row.get(h, "-")[:40] for h in headers]
                lines.append("| " + " | ".join(cells) + " |")
        else:
            lines = [f"#### {platform}\n"]
            lines.append("| 模型 | 价格 | 说明 |")
            lines.append("|------|------|------|")
            for m in items:
                model = m.get("model", "-")
                prices = ", ".join(m.get("prices", []))[:60] or "-"
                desc = m.get("description", "-")[:60]
                lines.append(f"| {model} | {prices} | {desc} |")

        sections.append("\n".join(lines))

    return sections


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def generate_markdown(data):
    scraped_at = data.get("scraped_at", "-")
    faka_total = data.get("faka", {}).get("total", 0)
    relay_total = data.get("relay", {}).get("total", 0)

    parts = [
        f"## 商品价格汇总\n",
        f"> 数据抓取时间: {scraped_at} | 发卡商品: {faka_total} | 中转模型: {relay_total}\n",
        build_summary_table(data),
        "",
        "---",
        "",
        "### 发卡平台 - 商品价格\n",
    ]

    faka_tables = build_faka_tables(data)
    if faka_tables:
        parts.extend(faka_tables)
    else:
        parts.append("_暂无数据_")

    parts.extend(["", "---", "", "### API 中转站 - 模型定价\n"])

    relay_tables = build_relay_tables(data)
    if relay_tables:
        parts.extend(relay_tables)
    else:
        parts.append("_暂无数据_")

    return "\n\n".join(parts)


def update_readme(md_content):
    if not README_FILE.exists():
        print("README.md 不存在，跳过更新")
        return False

    readme = README_FILE.read_text(encoding="utf-8")
    block = f"{README_START_MARKER}\n{md_content}\n{README_END_MARKER}"

    if README_START_MARKER in readme and README_END_MARKER in readme:
        pattern = re.compile(
            re.escape(README_START_MARKER) + r".*?" + re.escape(README_END_MARKER),
            re.DOTALL,
        )
        new_readme = pattern.sub(block, readme)
    else:
        anchor = "## 💰 价格对比（持续更新）"
        if anchor in readme:
            old_section = re.compile(
                re.escape(anchor) + r".*?(?=\n---|\n## |\Z)", re.DOTALL
            )
            new_readme = old_section.sub(f"{anchor}\n\n{block}\n", readme)
        else:
            new_readme = readme + f"\n\n{block}\n"

    README_FILE.write_text(new_readme, encoding="utf-8")
    print(f"README.md 已更新")
    return True


def main():
    parser = argparse.ArgumentParser(description="生成价格对比表")
    parser.add_argument("--update-readme", action="store_true", help="更新 README.md")
    parser.add_argument("--stdout", action="store_true", help="输出到终端")
    args = parser.parse_args()

    data = load_prices()
    md = generate_markdown(data)

    if args.stdout:
        print(md)
        return

    TABLE_FILE.parent.mkdir(parents=True, exist_ok=True)
    TABLE_FILE.write_text(md, encoding="utf-8")
    print(f"价格表已生成 -> {TABLE_FILE}")

    if args.update_readme:
        update_readme(md)


if __name__ == "__main__":
    main()
