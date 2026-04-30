#!/usr/bin/env python3
"""
抓取收录平台的商品/模型价格数据。
使用 Playwright 无头浏览器处理 JS 动态渲染页面。

支持两种平台类型:
  - faka  (发卡平台): 固定价格商品 (账号/CDK/订阅)
  - relay (API中转站): 按 token 计价的模型定价表

用法:
    python scripts/scrape_prices.py                  # 抓取所有启用的站点
    python scripts/scrape_prices.py --site vuvuva    # 只抓取指定站点
    python scripts/scrape_prices.py --type faka      # 只抓发卡平台
    python scripts/scrape_prices.py --type relay     # 只抓中转站
    python scripts/scrape_prices.py --list           # 列出所有站点
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except ImportError:
    print("错误: 请先安装依赖 - pip install playwright && playwright install chromium")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
SITES_FILE = ROOT / "scripts" / "sites.json"
OUTPUT_FILE = ROOT / "data" / "prices.json"

PRICE_RE = re.compile(r"[¥￥$]\s*(\d+(?:\.\d+)?)")
PRICE_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[元¥￥]")


def load_sites(site_filter=None, type_filter=None):
    with open(SITES_FILE, encoding="utf-8") as f:
        data = json.load(f)
    sites = [s for s in data["sites"] if s.get("enabled", True)]
    if site_filter:
        sites = [s for s in sites if s["id"] in site_filter]
    if type_filter:
        sites = [s for s in sites if s.get("type") == type_filter]
    return sites


def extract_price(text):
    text = text.strip()
    m = PRICE_RE.search(text)
    if m:
        return float(m.group(1))
    m = PRICE_NUM_RE.search(text)
    if m:
        return float(m.group(1))
    nums = re.findall(r"(\d+(?:\.\d+)?)", text)
    for n in nums:
        v = float(n)
        if 0.1 <= v <= 99999:
            return v
    return None


def parse_stock(text):
    m = re.search(r"(\d+)", text)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# 发卡平台 (faka) 抓取
# ---------------------------------------------------------------------------

def scrape_faka(page, site):
    url = site["url"]
    page.goto(url, wait_until="networkidle", timeout=30000)

    try:
        page.wait_for_selector(
            ".acg-card, .tokyo-commodity-row, .goods-title, .product-item",
            timeout=15000,
        )
    except PWTimeout:
        pass

    time.sleep(3)

    products = page.evaluate("""() => {
        const results = [];

        // === acg-faka (异次元发卡) ===
        const acgCards = document.querySelectorAll('.acg-card');
        if (acgCards.length > 0) {
            for (const card of acgCards) {
                const nameEl = card.querySelector('.goods-title');
                const priceEl = card.querySelector('.price');
                const stockEl = card.querySelector('.stat-bottom');
                const tags = Array.from(card.querySelectorAll('.badge-soft'))
                    .map(t => t.textContent.trim());
                const soldout = card.classList.contains('soldout');

                let priceText = '';
                if (priceEl) {
                    const unit = priceEl.querySelector('.unit');
                    priceText = (unit ? unit.textContent : '') +
                        priceEl.textContent.replace(unit ? unit.textContent : '', '').trim();
                }

                let stock = '', sold = '';
                if (stockEl) {
                    for (const s of stockEl.querySelectorAll('span')) {
                        const t = s.textContent.trim();
                        if (t.includes('库存')) stock = t;
                        if (t.includes('已售')) sold = t;
                    }
                }

                if (nameEl) {
                    results.push({
                        name: nameEl.textContent.trim(),
                        price_text: priceText,
                        stock, sold, tags, soldout,
                        source: 'acg-faka'
                    });
                }
            }
            return results;
        }

        // === tokyo 主题 ===
        const tokyoRows = document.querySelectorAll('.tokyo-commodity-row');
        if (tokyoRows.length > 0) {
            for (const row of tokyoRows) {
                const nameEl = row.querySelector('.tokyo-commodity-name');
                const priceEl = row.querySelector('.tokyo-commodity-price-main');
                const stockEl = row.querySelector('.tokyo-commodity-col-stock');
                const soldEl = row.querySelector('.tokyo-commodity-col-sold');
                const tags = Array.from(row.querySelectorAll('.tokyo-pill'))
                    .filter(p => !p.classList.contains('tokyo-pill-mobile-meta'))
                    .map(t => t.textContent.trim());

                if (nameEl) {
                    results.push({
                        name: nameEl.textContent.trim(),
                        price_text: priceEl ? priceEl.textContent.trim() : '',
                        stock: stockEl ? stockEl.textContent.trim() : '',
                        sold: soldEl ? soldEl.textContent.trim() : '',
                        tags, soldout: false,
                        source: 'tokyo'
                    });
                }
            }
            return results;
        }

        // === 通用兜底 ===
        const priceEls = document.querySelectorAll('[class*="price"], [class*="amount"]');
        for (const el of priceEls) {
            const parent = el.closest(
                '.card, [class*="goods"], [class*="product"], [class*="item"], div, li, article'
            ) || el.parentElement;
            if (!parent) continue;
            const nameEl = parent.querySelector('[class*="name"], [class*="title"], h3, h4, h5');
            const name = nameEl
                ? nameEl.textContent.trim()
                : parent.textContent.replace(el.textContent, '').trim().slice(0, 80);
            if (name && name.length > 1) {
                results.push({
                    name, price_text: el.textContent.trim(),
                    stock: '', sold: '', tags: [], soldout: false,
                    source: 'generic'
                });
            }
        }
        return results;
    }""")

    return products


def normalize_faka(raw_products, site):
    seen = set()
    products = []
    for item in raw_products:
        name = item.get("name", "").strip()
        if not name or name in seen or len(name) < 2 or len(name) > 200:
            continue
        seen.add(name)
        price = extract_price(item.get("price_text", ""))
        products.append({
            "name": name,
            "price": price,
            "price_text": item.get("price_text", ""),
            "stock": parse_stock(item.get("stock", "")),
            "stock_text": item.get("stock", ""),
            "sold_text": item.get("sold", ""),
            "soldout": item.get("soldout", False),
            "tags": item.get("tags", []),
            "platform": site["name"],
            "platform_id": site["id"],
            "url": site["url"],
            "source": item.get("source", "unknown"),
            "category": categorize_faka(name),
        })
    return products


def categorize_faka(name):
    n = name.lower()
    if any(k in n for k in ["chatgpt", "gpt-4", "gpt4", "gpt-5", "gpt5", "openai"]):
        return "ChatGPT"
    if "plus" in n and "claude" not in n:
        return "ChatGPT"
    if any(k in n for k in ["claude", "anthropic", "opus", "sonnet", "haiku", "max"]):
        return "Claude"
    if any(k in n for k in ["midjourney", "mj"]):
        return "Midjourney"
    if any(k in n for k in ["gemini", "gcp"]):
        return "Gemini"
    if "cursor" in n:
        return "Cursor"
    if any(k in n for k in ["copilot", "github"]):
        return "Copilot"
    if "suno" in n:
        return "Suno"
    if "poe" in n:
        return "Poe"
    if "pro" in n and "卡密" in n:
        return "Claude"
    if any(k in n for k in ["api", "key", "token", "额度"]):
        return "API/Key"
    if any(k in n for k in ["gmail", "邮箱", "outlook", "谷歌"]):
        return "邮箱/账号"
    return "其他"


# ---------------------------------------------------------------------------
# API 中转站 (relay) 抓取
# ---------------------------------------------------------------------------

def scrape_relay(page, site):
    url = site["url"]
    page.goto(url, wait_until="networkidle", timeout=30000)

    try:
        page.wait_for_selector("table, .pricing-table, [class*='pricing']", timeout=15000)
    except PWTimeout:
        pass

    time.sleep(3)

    models = page.evaluate("""() => {
        const results = [];

        // === 策略1: pricing-table 表格 (DragonCode 等) ===
        const pricingTable = document.querySelector('.pricing-table, table');
        if (pricingTable) {
            const headers = Array.from(pricingTable.querySelectorAll('thead th, thead td'))
                .map(h => h.textContent.trim());
            const rows = pricingTable.querySelectorAll('tbody tr');
            for (const row of rows) {
                const cells = Array.from(row.querySelectorAll('td'));
                if (cells.length < 2) continue;
                const obj = {};
                for (let i = 0; i < cells.length && i < headers.length; i++) {
                    obj[headers[i]] = cells[i].textContent.trim();
                }
                if (Object.keys(obj).length > 0) {
                    results.push(obj);
                }
            }
            if (results.length > 0) return {type: 'table', headers, rows: results};
        }

        // === 策略2: 定价卡片 (API Mart 等) ===
        const cards = document.querySelectorAll(
            '[class*="card"], [class*="pricing"], [class*="model"]'
        );
        const cardResults = [];
        const seenNames = new Set();
        for (const card of cards) {
            const nameEl = card.querySelector('h3, h4, h2, [class*="title"], [class*="name"]');
            const priceEls = card.querySelectorAll('[class*="price"]');
            if (!nameEl || priceEls.length === 0) continue;
            const name = nameEl.textContent.trim();
            if (seenNames.has(name) || name.length < 2) continue;
            seenNames.add(name);

            const prices = Array.from(priceEls).map(p => p.textContent.trim());
            const descEl = card.querySelector('p, [class*="desc"]');
            cardResults.push({
                model: name,
                prices: prices,
                description: descEl ? descEl.textContent.trim().slice(0, 200) : ''
            });
        }
        if (cardResults.length > 0) return {type: 'cards', items: cardResults};

        return {type: 'empty'};
    }""")

    return models


def normalize_relay(raw_data, site):
    models = []
    data_type = raw_data.get("type", "empty")

    if data_type == "table":
        headers = raw_data.get("headers", [])
        for row in raw_data.get("rows", []):
            model_name = row.get("模型名", row.get("模型", row.get("Model", "")))
            if not model_name:
                first_key = headers[0] if headers else ""
                model_name = row.get(first_key, "")
            if not model_name:
                continue
            models.append({
                "model": model_name,
                "raw": row,
                "platform": site["name"],
                "platform_id": site["id"],
                "url": site["url"],
            })

    elif data_type == "cards":
        for item in raw_data.get("items", []):
            models.append({
                "model": item["model"],
                "prices": item.get("prices", []),
                "description": item.get("description", ""),
                "raw": {},
                "platform": site["name"],
                "platform_id": site["id"],
                "url": site["url"],
            })

    return models


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(site_filter=None, type_filter=None, headless=True):
    sites = load_sites(site_filter, type_filter)
    if not sites:
        print("没有找到匹配的站点")
        return

    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
    faka_products = []
    relay_models = []
    results_summary = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
        )

        for site in sites:
            sid = site["id"]
            sname = site["name"]
            stype = site.get("type", "faka")
            print(f"[{sid}] 正在抓取 {sname} ({site['url']}) [{stype}] ...")

            page = context.new_page()
            try:
                if stype == "relay":
                    raw = scrape_relay(page, site)
                    models = normalize_relay(raw, site)
                    relay_models.extend(models)
                    count = len(models)
                else:
                    raw = scrape_faka(page, site)
                    products = normalize_faka(raw, site)
                    faka_products.extend(products)
                    count = len(products)

                results_summary.append({"site": sname, "type": stype, "status": "ok", "count": count})
                print(f"  -> 提取到 {count} 条数据")
            except Exception as e:
                results_summary.append({"site": sname, "type": stype, "status": "error", "error": str(e)})
                print(f"  -> 抓取失败: {e}")
            finally:
                page.close()

        browser.close()

    output = {
        "scraped_at": now,
        "sites_scraped": len(results_summary),
        "summary": results_summary,
        "faka": {
            "total": len(faka_products),
            "products": faka_products,
        },
        "relay": {
            "total": len(relay_models),
            "models": relay_models,
        },
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n抓取完成!")
    print(f"  发卡平台: {len(faka_products)} 个商品")
    print(f"  API中转站: {len(relay_models)} 个模型")
    print(f"  -> {OUTPUT_FILE}")
    return output


def main():
    parser = argparse.ArgumentParser(description="抓取发卡/中转平台价格")
    parser.add_argument("--site", nargs="+", help="只抓取指定站点ID")
    parser.add_argument("--type", choices=["faka", "relay"], help="只抓取指定类型")
    parser.add_argument("--list", action="store_true", help="列出所有站点")
    parser.add_argument("--no-headless", action="store_true", help="显示浏览器窗口(调试用)")
    args = parser.parse_args()

    if args.list:
        sites = load_sites()
        print(f"共 {len(sites)} 个启用的站点:\n")
        for s in sites:
            t = s.get("type", "faka")
            print(f"  {s['id']:20s} {s['name']:20s} [{t:5s}] {s['url']}")
        return

    run(site_filter=args.site, type_filter=args.type, headless=not args.no_headless)


if __name__ == "__main__":
    main()
