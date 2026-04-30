#!/usr/bin/env bash
# 一键刷新价格: 抓取所有平台 + 生成汇总表
# 用法:
#   bash scripts/refresh.sh                    # 抓取全部 + 生成表格
#   bash scripts/refresh.sh --site vuvuva      # 只抓指定站点
#   bash scripts/refresh.sh --update-readme    # 同时更新 README
#   bash scripts/refresh.sh --install          # 安装依赖

set -euo pipefail
cd "$(dirname "$0")/.."

INSTALL=false
UPDATE_README=false
SITE_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)
            INSTALL=true
            shift
            ;;
        --update-readme)
            UPDATE_README=true
            shift
            ;;
        --site)
            SITE_ARGS+=(--site "$2")
            shift 2
            ;;
        *)
            echo "未知参数: $1"
            exit 1
            ;;
    esac
done

if $INSTALL; then
    echo "==> 安装 Python 依赖..."
    pip3 install -r scripts/requirements.txt
    echo "==> 安装 Playwright 浏览器..."
    python3 -m playwright install chromium
    echo "==> 安装完成"
    exit 0
fi

echo "==> 开始抓取价格..."
python3 scripts/scrape_prices.py "${SITE_ARGS[@]}"

echo ""
echo "==> 生成价格汇总表..."
if $UPDATE_README; then
    python3 scripts/generate_table.py --update-readme
else
    python3 scripts/generate_table.py
fi

echo ""
echo "==> 完成! 查看结果:"
echo "    data/prices.json       - 原始数据"
echo "    data/prices_table.md   - Markdown 表格"
