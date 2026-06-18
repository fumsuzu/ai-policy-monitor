"""
GitHub Actions用: スクレイピング → 静的HTML生成 (v4)
- 日本時間(JST)表示
- デジタル庁追加
- 2週間以内の情報のみ表示
- 手動更新ボタン付き
"""

import asyncio
import json
import os
import re
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from jinja2 import Template

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# 日本時間
JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


# ===== 設定 =====

# 新着として表示する期間（日数）
MAX_AGE_DAYS = 14

KEYWORDS = [
    "AI推進法",
    "人工知能関連技術の研究開発及び活用の推進",
    "生成AI",
    "generative AI",
    "透明性",
    "知的財産",
    "行動規範",
    "プリンシプル",
    "GENIAC",
    "フロンティアAI",
    "frontier AI",
    "基盤モデル",
    "foundation model",
    "AI戦略",
    "AI安全",
    "AI safety",
    "著作権",
    "学習データ",
    "AI法",
    "AI Act",
    "デジタル社会推進",
    "AI・web3",
]

SOURCES = {
    "cabinet_office": {
        "name": "内閣府",
        "url": "https://www8.cao.go.jp/cstp/ai/index.html",
        "encoding": "utf-8",
    },
    "digital_agency": {
        "name": "デジタル庁",
        "url": "https://www.digital.go.jp/news",
        "encoding": "utf-8",
    },
    "meti_en_press": {
        "name": "経産省(EN)",
        "url": "https://www.meti.go.jp/english/press/category_03.html",
        "encoding": "utf-8",
    },
    "meti_geniac": {
        "name": "経産省 GENIAC",
        "url": "https://www.meti.go.jp/english/policy/mono_info_service/geniac/",
        "encoding": "utf-8",
    },
    "soumu_news": {
        "name": "総務省",
        "url": "https://www.soumu.go.jp/menu_news/s-news/",
        "encoding": "shift_jis",
    },
    "mext_news": {
        "name": "文科省",
        "url": "https://www.mext.go.jp/b_menu/houdou/index.htm",
        "encoding": "utf-8",
    },
    "jimin_news": {
        "name": "自民党",
        "url": "https://www.jimin.jp/news/?category=policy",
        "encoding": "utf-8",
    },
    "egov_pubcom": {
        "name": "e-Gov パブコメ",
        "url": "https://public-comment.e-gov.go.jp/",
        "encoding": "utf-8",
    },
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}

DATA_FILE = "docs/data.json"
OUTPUT_DIR = "docs"


# ===== データ構造 =====

@dataclass
class ScrapedItem:
    title: str
    url: str
    source_id: str
    source_name: str
    matched_keywords: list[str] = field(default_factory=list)
    scraped_at: str = ""
    is_public_comment: bool = False
    end_date: Optional[str] = None
    ministry: Optional[str] = None


# ===== スクレイピング =====

def match_keywords(text: str) -> list[str]:
    if not text:
        return []
    matched = []
    text_lower = text.lower()
    for kw in KEYWORDS:
        if kw.lower() in text_lower:
            matched.append(kw)
    return matched


async def fetch_page(url: str, encoding: str = "utf-8") -> Optional[BeautifulSoup]:
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            if encoding != "utf-8":
                content = resp.content.decode(encoding, errors="replace")
            else:
                content_type = resp.headers.get("content-type", "")
                if "charset" not in content_type:
                    resp.encoding = "utf-8"
                content = resp.text
            return BeautifulSoup(content, "lxml")
    except Exception as e:
        logger.error(f"取得失敗 {url}: {e}")
        return None


async def scrape_source(source_id: str) -> list[ScrapedItem]:
    """汎用スクレイパー"""
    config = SOURCES[source_id]
    items = []
    soup = await fetch_page(config["url"], config.get("encoding", "utf-8"))
    if not soup:
        return items

    seen_urls = set()
    for link in soup.find_all("a"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or not href or len(title) < 5:
            continue

        url = urljoin(config["url"], href)
        if url in seen_urls:
            continue
        seen_urls.add(url)

        matched = match_keywords(title)

        if source_id == "meti_geniac" and not matched:
            if len(title) > 10:
                matched = ["GENIAC"]

        if source_id == "jimin_news" and not matched:
            party_keywords = ["デジタル", "AI", "人工知能", "知的財産", "著作権", "科学技術", "情報通信", "IT"]
            if any(kw in title for kw in party_keywords):
                matched = ["AI戦略"]

        if source_id == "digital_agency" and not matched:
            da_keywords = ["AI", "人工知能", "デジタル", "データ", "クラウド"]
            if any(kw in title for kw in da_keywords):
                matched = ["AI戦略"]

        if not matched:
            continue

        items.append(ScrapedItem(
            title=title,
            url=url,
            source_id=source_id,
            source_name=config["name"],
            matched_keywords=matched,
            scraped_at=now_jst().strftime("%Y/%m/%d %H:%M"),
        ))

    logger.info(f"[{source_id}] {len(items)}件取得")
    return items


async def scrape_egov_pubcom() -> list[ScrapedItem]:
    """e-Govパブコメ用スクレイパー"""
    items = []
    urls = [
        "https://public-comment.e-gov.go.jp/servlet/Public?CLASSNAME=PCM1031_CLS&fromType=list",
        "https://public-comment.e-gov.go.jp/",
    ]

    soup = None
    for url in urls:
        soup = await fetch_page(url)
        if soup:
            break
    if not soup:
        logger.info("[egov_pubcom] 0件取得")
        return items

    seen_urls = set()
    for link in soup.find_all("a"):
        title = link.get_text(strip=True)
        href = link.get("href", "")
        if not title or not href or len(title) < 5:
            continue

        full_url = urljoin(urls[0], href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        matched = match_keywords(title)
        if not matched:
            continue

        parent = link.find_parent("tr") or link.find_parent("div")
        end_date = None
        ministry = None
        if parent:
            text = parent.get_text()
            date_match = re.search(r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})", text)
            if date_match:
                try:
                    end_date = f"{date_match.group(1)}/{date_match.group(2).zfill(2)}/{date_match.group(3).zfill(2)}"
                except (ValueError, IndexError):
                    pass
            for m in ["内閣府", "経済産業省", "総務省", "文部科学省", "デジタル庁"]:
                if m in text:
                    ministry = m
                    break

        items.append(ScrapedItem(
            title=title,
            url=full_url,
            source_id="egov_pubcom",
            source_name="e-Gov パブコメ",
            matched_keywords=matched,
            scraped_at=now_jst().strftime("%Y/%m/%d %H:%M"),
            is_public_comment=True,
            end_date=end_date,
            ministry=ministry,
        ))

    logger.info(f"[egov_pubcom] {len(items)}件取得")
    return items


async def scrape_soumu_ai() -> list[ScrapedItem]:
    """総務省AI関連を追加で検索"""
    items = []
    ai_urls = [
        "https://www.soumu.go.jp/menu_seisaku/ictseisaku/",
        "https://www.soumu.go.jp/main_sosiki/kenkyu/ai_network/",
    ]
    for url in ai_urls:
        soup = await fetch_page(url, "shift_jis")
        if not soup:
            continue
        seen = set()
        for link in soup.find_all("a"):
            title = link.get_text(strip=True)
            href = link.get("href", "")
            if not title or not href or len(title) < 5:
                continue
            full_url = urljoin(url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            matched = match_keywords(title)
            if not matched:
                continue
            items.append(ScrapedItem(
                title=title,
                url=full_url,
                source_id="soumu_news",
                source_name="総務省",
                matched_keywords=matched,
                scraped_at=now_jst().strftime("%Y/%m/%d %H:%M"),
            ))
    logger.info(f"[soumu_ai追加] {len(items)}件取得")
    return items


async def run_all_scrapers() -> list[ScrapedItem]:
    """全スクレイパー実行"""
    all_items = []

    tasks = []
    for source_id in SOURCES:
        if source_id == "egov_pubcom":
            tasks.append(scrape_egov_pubcom())
        else:
            tasks.append(scrape_source(source_id))

    tasks.append(scrape_soumu_ai())

    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, list):
            all_items.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"スクレイパーエラー: {result}")

    return all_items


# ===== データ管理 =====

def load_existing_data() -> list[dict]:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def merge_data(existing: list[dict], new_items: list[ScrapedItem]) -> list[dict]:
    existing_urls = {item["url"] for item in existing}

    for item in new_items:
        if item.url not in existing_urls:
            existing.append({
                "title": item.title,
                "url": item.url,
                "source_id": item.source_id,
                "source_name": item.source_name,
                "matched_keywords": item.matched_keywords,
                "scraped_at": item.scraped_at,
                "is_public_comment": item.is_public_comment,
                "end_date": item.end_date,
                "ministry": item.ministry,
                "is_new": True,
            })
            existing_urls.add(item.url)

    existing.sort(key=lambda x: x.get("scraped_at", ""), reverse=True)
    return existing[:500]


def filter_recent(data: list[dict], days: int = MAX_AGE_DAYS) -> list[dict]:
    """指定日数以内のデータのみ返す"""
    cutoff = now_jst() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y/%m/%d %H:%M")
    recent = [item for item in data if item.get("scraped_at", "") >= cutoff_str]
    return recent


def save_data(data: list[dict]):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===== HTML生成 =====

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI政策モニター</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', 'Hiragino Sans', 'Noto Sans JP', sans-serif;
            background: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }
        .container { max-width: 1000px; margin: 0 auto; padding: 20px; }
        header {
            background: linear-gradient(135deg, #1a237e, #283593);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 25px;
        }
        header h1 { font-size: 1.6em; margin-bottom: 5px; }
        header p { opacity: 0.85; font-size: 0.9em; }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 12px;
            margin-bottom: 25px;
        }
        .stat-card {
            background: white;
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.06);
            text-align: center;
        }
        .stat-card .number { font-size: 1.8em; font-weight: bold; color: #1a237e; }
        .stat-card .label { color: #666; font-size: 0.85em; }
        .tabs {
            display: flex; gap: 5px; margin-bottom: 20px; flex-wrap: wrap;
        }
        .tab {
            padding: 8px 16px; border: none; background: white;
            border-radius: 8px; cursor: pointer; font-size: 0.85em;
            box-shadow: 0 1px 4px rgba(0,0,0,0.05);
        }
        .tab:hover { background: #e8eaf6; }
        .tab.active { background: #1a237e; color: white; }
        .update-time { text-align: right; font-size: 0.8em; color: #999; margin-bottom: 10px; }
        .section { margin-bottom: 25px; }
        .section h2 { font-size: 1.2em; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 2px solid #e8eaf6; }
        .card {
            background: white; padding: 15px; border-radius: 10px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.05); border-left: 4px solid #1a237e;
            margin-bottom: 10px; transition: transform 0.15s;
        }
        .card:hover { transform: translateX(4px); }
        .card.pubcom { border-left-color: #2e7d32; }
        .card.deadline { border-left-color: #d32f2f; }
        .card.digital { border-left-color: #6200ea; }
        .card .source {
            font-size: 0.75em; color: #666; background: #f0f0f0;
            padding: 2px 8px; border-radius: 4px; display: inline-block; margin-bottom: 4px;
        }
        .card .title { font-weight: 600; margin-bottom: 4px; }
        .card .title a { color: #1a237e; text-decoration: none; }
        .card .title a:hover { text-decoration: underline; }
        .card .meta { font-size: 0.8em; color: #888; display: flex; gap: 10px; flex-wrap: wrap; }
        .kw-tag {
            display: inline-block; background: #e8eaf6; color: #1a237e;
            padding: 1px 7px; border-radius: 10px; font-size: 0.7em; margin-right: 3px;
        }
        .deadline-badge {
            background: #ffebee; color: #c62828;
            padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold;
        }
        .empty { text-align: center; padding: 30px; color: #999; }
        .refresh-link {
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #1a237e;
            color: white;
            border: none;
            padding: 12px 20px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 0.85em;
            text-decoration: none;
            box-shadow: 0 4px 15px rgba(26, 35, 126, 0.4);
        }
        .refresh-link:hover { transform: scale(1.05); }
        .period-note { font-size: 0.8em; color: #999; margin-bottom: 15px; }
    </style>
</head>
<body>
<div class="container">
    <header>
        <h1>🏛️ AI政策モニター</h1>
        <p>AI推進法 / 透明性・知的財産行動規範 / プリンシプルコード / GENIAC / フロンティアAI</p>
    </header>

    <div class="stats">
        <div class="stat-card"><div class="number">{{ total }}</div><div class="label">直近2週間</div></div>
        <div class="stat-card"><div class="number">{{ pubcom_count }}</div><div class="label">パブコメ</div></div>
        <div class="stat-card"><div class="number">{{ deadline_count }}</div><div class="label">締切間近</div></div>
    </div>

    <div class="tabs">
        <button class="tab active" onclick="filter('all')">すべて</button>
        <button class="tab" onclick="filter('pubcom')">パブコメ</button>
        <button class="tab" onclick="filter('cabinet_office')">内閣府</button>
        <button class="tab" onclick="filter('digital_agency')">デジタル庁</button>
        <button class="tab" onclick="filter('meti')">経産省</button>
        <button class="tab" onclick="filter('soumu_news')">総務省</button>
        <button class="tab" onclick="filter('mext_news')">文科省</button>
        <button class="tab" onclick="filter('jimin')">自民党</button>
    </div>

    <div class="update-time">最終更新: {{ update_time }} (JST)</div>
    <div class="period-note">※ 直近2週間以内の情報を表示しています</div>

    {% if deadlines %}
    <div class="section">
        <h2>⏰ パブコメ締切間近</h2>
        {% for item in deadlines %}
        <div class="card deadline">
            <span class="source">{{ item.ministry or 'パブコメ' }}</span>
            <div class="title"><a href="{{ item.url }}" target="_blank">{{ item.title }}</a></div>
            <div class="meta">
                <span class="deadline-badge">締切: {{ item.end_date }}</span>
                {% for kw in item.matched_keywords %}<span class="kw-tag">{{ kw }}</span>{% endfor %}
            </div>
        </div>
        {% endfor %}
    </div>
    {% endif %}

    <div class="section">
        <h2>📰 最新情報</h2>
        <div id="articles">
        {% for item in articles %}
        <div class="card {{ 'pubcom' if item.is_public_comment else '' }} {{ 'digital' if item.source_id == 'digital_agency' else '' }}" data-source="{{ item.source_id }}">
            <span class="source">{{ item.source_name }}</span>
            <div class="title"><a href="{{ item.url }}" target="_blank">{{ item.title }}</a></div>
            <div class="meta">
                <span>{{ item.scraped_at }}</span>
                {% for kw in item.matched_keywords %}<span class="kw-tag">{{ kw }}</span>{% endfor %}
            </div>
        </div>
        {% endfor %}
        {% if not articles %}
        <div class="empty">直近2週間以内のAI政策関連情報はありません。</div>
        {% endif %}
        </div>
    </div>
</div>

<a class="refresh-link" href="{{ actions_url }}" target="_blank">🔄 手動更新</a>

<script>
function filter(type) {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    event.target.classList.add('active');
    document.querySelectorAll('#articles .card').forEach(card => {
        const src = card.dataset.source;
        if (type === 'all') card.style.display = '';
        else if (type === 'pubcom') card.style.display = card.classList.contains('pubcom') ? '' : 'none';
        else if (type === 'meti') card.style.display = (src === 'meti_en_press' || src === 'meti_geniac') ? '' : 'none';
        else if (type === 'jimin') card.style.display = src === 'jimin_news' ? '' : 'none';
        else card.style.display = src === type ? '' : 'none';
    });
}
</script>
</body>
</html>"""


def generate_html(data: list[dict]):
    now = now_jst()
    today_str = now.strftime("%Y/%m/%d %H:%M")

    # 2週間以内のデータのみ表示
    recent_data = filter_recent(data)

    deadlines = []
    pubcom_count = 0
    for item in recent_data:
        if item.get("is_public_comment"):
            pubcom_count += 1
            if item.get("end_date"):
                try:
                    parts = item["end_date"].split("/")
                    end_dt = datetime(int(parts[0]), int(parts[1]), int(parts[2]), tzinfo=JST)
                    if now < end_dt <= now + timedelta(days=7):
                        deadlines.append(item)
                except (ValueError, IndexError):
                    pass

    repo_name = os.environ.get("GITHUB_REPOSITORY", "fumsuzu/ai-policy-monitor")
    actions_url = f"https://github.com/{repo_name}/actions/workflows/scrape.yml"

    template = Template(HTML_TEMPLATE)
    html = template.render(
        total=len(recent_data),
        pubcom_count=pubcom_count,
        deadline_count=len(deadlines),
        update_time=today_str,
        deadlines=deadlines,
        articles=recent_data[:100],
        actions_url=actions_url,
    )

    output_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML生成完了: {output_path} (直近2週間: {len(recent_data)}件)")


# ===== メイン =====

async def main():
    logger.info("=== AI政策モニター v4: スクレイピング開始 ===")

    new_items = await run_all_scrapers()
    logger.info(f"合計 {len(new_items)}件 新規取得")

    existing = load_existing_data()
    merged = merge_data(existing, new_items)
    save_data(merged)
    logger.info(f"データ保存完了 (合計{len(merged)}件)")

    generate_html(merged)
    logger.info("=== 完了 ===")


if __name__ == "__main__":
    asyncio.run(main())
