---
name: fetch-prices
description: >
  抓取收录平台的商品价格并汇总成表格。支持发卡平台(固定价格)和API中转站(token计价)两种类型。
  当用户说"刷新价格""更新商品""抓取价格""fetch prices""refresh""比价""中转价格"时触发。
  也可通过关键词触发：价格汇总、价格对比、商品列表、更新表格、scrape、模型定价。
---

# 价格抓取技能 (fetch-prices)

抓取 `scripts/sites.json` 中收录平台的价格数据，分两类汇总：

- **发卡平台 (faka)**: 账号/CDK/订阅等固定价格商品
- **API 中转站 (relay)**: 按 token 计价的模型定价表（输入/输出价格、倍率、折扣）

---

## 前置条件

首次使用需安装依赖：

```bash
bash scripts/refresh.sh --install
```

---

## 工作流 A: 全量刷新

```bash
python3 scripts/scrape_prices.py
python3 scripts/generate_table.py
```

或一键执行：

```bash
bash scripts/refresh.sh
```

加 `--update-readme` 可同时更新 README.md。

### 输出结果

告知用户：
- 发卡平台抓到多少商品、中转站抓到多少模型
- 哪些平台失败及原因
- 表格文件位置：`data/prices_table.md`

---

## 工作流 B: 按类型刷新

只刷发卡平台：
```bash
python3 scripts/scrape_prices.py --type faka
```

只刷中转站：
```bash
python3 scripts/scrape_prices.py --type relay
```

---

## 工作流 C: 指定平台刷新

```bash
python3 scripts/scrape_prices.py --site <site_id>
```

站点 ID 列表：`python3 scripts/scrape_prices.py --list`

---

## 工作流 D: 添加新平台

编辑 `scripts/sites.json`，在 `sites` 数组中添加：

```json
{
  "id": "新站ID",
  "name": "站点名称",
  "url": "https://example.com/",
  "type": "faka 或 relay",
  "enabled": true
}
```

- `type: "faka"` — 发卡平台（账号、CDK、订阅，固定价格）
- `type: "relay"` — API 中转站（按 token 计价，定价表）

测试：`python3 scripts/scrape_prices.py --site 新站ID`

---

## 文件说明

| 文件 | 用途 |
|------|------|
| `scripts/sites.json` | 平台配置（URL、类型） |
| `scripts/scrape_prices.py` | Playwright 抓取脚本 |
| `scripts/generate_table.py` | Markdown 表格生成 |
| `scripts/refresh.sh` | 一键刷新 |
| `scripts/requirements.txt` | Python 依赖 |
| `data/prices.json` | 抓取原始数据（发卡 + 中转分开存储） |
| `data/prices_table.md` | 生成的 Markdown 表格 |
