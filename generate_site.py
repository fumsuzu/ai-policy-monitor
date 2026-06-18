"""
GitHub Actions用: スクレイピング → 静的HTML生成 (v6)
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

JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


MAX_AGE_DAYS = 14

KEYWORDS = [
    "AI推進法", "人工知能関連技術の研究開発及び活用の推進",
    "生成AI", "generative AI", "透明性", "知的財産", "行動規範",
    "プリンシプル", "GENIAC", "フロンティアAI", "frontier AI",
    "基盤モデル", "foundation model", "AI戦略", "AI安全", "AI safety",
    "著作権", "学習データ", "AI法", "AI Act", "デジタル社会推進", "AI・web3",
    "ガイドライン", "guideline",
]

SOURCES = {
    "cabinet_office": {"name": "内閣府", "url": "https://www8.cao.go.jp/cstp/ai/index.html", "encoding": "utf-8"},
    "digital_agency": {"name": "デジタル庁", "url": "https://www.digital.go.jp/news", "encoding": "utf-8"},
    "digital_ai": {"name": "デジタル庁(AI)", "url": "https://www.digital.go.jp/policies/genai", "encoding": "utf-8"},
"digital_ai_board": {"name": "デジタル庁(AI会議)", "url": "https://www.digital.go.jp/councils/ai-advisory-board", "encoding": "utf-8"},

    "meti_en_press": {"name": "経産省(EN)", "url": "https://www.meti.go.jp/english/press/category_03.html", "encoding": "utf-8"},
    "meti_geniac": {"name": "経産省 GENIAC", "url": "https://www.meti.go.jp/english/policy/mono_info_service/geniac/", "encoding": "utf-8"},
    "soumu_news": {"name": "総務省", "url": "https://www.soumu.go.jp/menu_news/s-news/", "encoding": "shift_jis"},
    "mext_news": {"name": "文科省", "url": "https://www.mext.go.jp/b_menu/houdou/index.htm", "encoding": "utf-8"},
    "jimin_news": {"name": "自民党", "url": "https://www.jimin.jp/news/?category=policy", "encoding": "utf-8"},
    "egov_pubcom": {"name": "e-Gov パブコメ", "url": "https://public-comment.e-gov.go.jp/", "encoding": "utf-8"},
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
}

DATA_FILE = "docs/data.json"
OUTPUT_DIR = "docs"

MONTH_EN = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass
class ScrapedItem:
    title: str
    url: str
    source_id: str
    source_name: str
    matched_keywords: list[str] = field(default_factory=list)
    scraped_at: str = ""
    published_date: str = ""
    is_public_comment: bool = False
    end_date: Optional[str] = None
    ministry: Optional[str] = None


def extract_date_ja(text):
    m = re.search(r"令和(\d+)年(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{int(m.group(1))+2018}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    m = re.search(r"(\d{4})[年/\-](\d{1,2})[月/\-](\d{1,2})", text)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    return None


def extract_date_en(text):
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})", text)
    if m:
        month = MONTH_EN.get(m.group(1).lower())
        if month:
            return f"{m.group(3)}/{month:02d}/{int(m.group(2)):02d}"
    return None


def find_nearby_date(element):
    for parent in [element.parent, element.parent.parent if element.parent else None]:
        if not parent:
            continue
        text = parent.get_text()
        d = extract_date_ja(text) or extract_date_en(text)
        if d:
            return d
    prev = element.find_previous_sibling()
    if prev:
        d = extract_date_ja(prev.get_text())
        if d:
            return d
    return None


def match_keywords(text):
    if not text:
        return []
    text_lower = text.lower()
    return [kw for kw in KEYWORDS if kw.lower() in text_lower]


async def fetch_page(url, encoding="utf-8"):
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=HEADERS)
            resp.raise_for_status()
            if encoding != "utf-8":
                content = resp.content.decode(encoding, errors="replace")
            else:
                if "charset" not in resp.headers.get("content-type", ""):
                    resp.encoding = "utf-8"
                content = resp.text
            return BeautifulSoup(content, "lxml")
    except Exception as e:
        logger.error(f"取得失敗 {url}: {e}")
        return None


async def scrape_source(source_id):
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
        if source_id == "meti_geniac" and not matched and len(title) > 10:
            matched = ["GENIAC"]
        if source_id == "jimin_news" and not matched:
            if any(kw in title for kw in ["デジタル", "AI", "人工知能", "知的財産", "著作権", "科学技術", "情報通信"]):
                matched = ["AI戦略"]
        if source_id in ("digital_agency", "digital_ai") and not matched:
            if any(kw in title for kw in ["AI", "人工知能", "生成", "データ", "クラウド", "ガイドライン"]):
                matched = ["AI戦略"]
        if not matched:
            continue

        items.append(ScrapedItem(
            title=title, url=url, source_id=source_id, source_name=config["name"],
            matched_keywords=matched, scraped_at=now_jst().strftime("%Y/%m/%d %H:%M"),
            published_date=find_nearby_date(link) or "",
        ))
    logger.info(f"[{source_id}] {len(items)}件取得")
    return items


async def scrape_egov_pubcom():
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
        end_date, ministry, pub_date = None, None, ""
        if parent:
            text = parent.get_text()
            dm = re.search(r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})", text)
            if dm:
                end_date = f"{dm.group(1)}/{dm.group(2).zfill(2)}/{dm.group(3).zfill(2)}"
                pub_date = end_date
            for m in ["内閣府", "経済産業省", "総務省", "文部科学省", "デジタル庁"]:
                if m in text:
                    ministry = m
                    break

        items.append(ScrapedItem(
            title=title, url=full_url, source_id="egov_pubcom", source_name="e-Gov パブコメ",
            matched_keywords=matched, scraped_at=now_jst().strftime("%Y/%m/%d %H:%M"),
            published_date=pub_date, is_public_comment=True, end_date=end_date, ministry=ministry,
        ))
    logger.info(f"[egov_pubcom] {len(items)}件取得")
    return items


async def scrape_soumu_ai():
    items = []
    for url in ["https://www.soumu.go.jp/menu_seisaku/ictseisaku/", "https://www.soumu.go.jp/main_sosiki/kenkyu/ai_network/"]:
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
                title=title, url=full_url, source_id="soumu_news", source_name="総務省",
                matched_keywords=matched, scraped_at=now_jst().strftime("%Y/%m/%d %H:%M"),
                published_date=find_nearby_date(link) or "",
            ))
    logger.info(f"[soumu_ai追加] {len(items)}件取得")
    return items


async def run_all_scrapers():
    tasks = []
    for source_id in SOURCES:
        if source_id == "egov_pubcom":
            tasks.append(scrape_egov_pubcom())
        else:
            tasks.append(scrape_source(source_id))
    tasks.append(scrape_soumu_ai())

    all_items = []
    for result in await asyncio.gather(*tasks, return_exceptions=True):
        if isinstance(result, list):
            all_items.extend(result)
        elif isinstance(result, Exception):
            logger.error(f"スクレイパーエラー: {result}")
    return all_items


def load_existing_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def merge_data(existing, new_items):
    existing_urls = {item["url"] for item in existing}
    for item in new_items:
        if item.url not in existing_urls:
            existing.append({
                "title": item.title, "url": item.url, "source_id": item.source_id,
                "source_name": item.source_name, "matched_keywords": item.matched_keywords,
                "scraped_at": item.scraped_at, "published_date": item.published_date,
                "is_public_comment": item.is_public_comment, "end_date": item.end_date,
                "ministry": item.ministry, "is_new": True,
            })
            existing_urls.add(item.url)
    existing.sort(key=lambda x: x.get("published_date") or x.get("scraped_at", "")[:10], reverse=True)
    return existing[:500]


def filter_recent(data):
    cutoff_str = (now_jst() - timedelta(days=MAX_AGE_DAYS)).strftime("%Y/%m/%d")
    return [item for item in data if (item.get("published_date") or item.get("scraped_at", "")[:10]) >= cutoff_str]


def save_data(data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI政策モニター</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Segoe UI','Hiragino Sans','Noto Sans JP',sans-serif;background:#f5f7fa;color:#333;line-height:1.6}
.container{max-width:1000px;margin:0 auto;padding:20px}
header{background:linear-gradient(135deg,#1a237e,#283593);color:#fff;padding:30px;border-radius:12px;margin-bottom:25px}
header h1{font-size:1.6em;margin-bottom:5px}header p{opacity:.85;font-size:.9em}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:25px}
.stat-card{background:#fff;padding:15px;border-radius:10px;box-shadow:0 2px 8px rgba(0,0,0,.06);text-align:center}
.stat-card .number{font-size:1.8em;font-weight:700;color:#1a237e}.stat-card .label{color:#666;font-size:.85em}
.tabs{display:flex;gap:5px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:8px 16px;border:none;background:#fff;border-radius:8px;cursor:pointer;font-size:.85em;box-shadow:0 1px 4px rgba(0,0,0,.05)}
.tab:hover{background:#e8eaf6}.tab.active{background:#1a237e;color:#fff}
.update-time{text-align:right;font-size:.8em;color:#999;margin-bottom:10px}
.period-note{font-size:.8em;color:#999;margin-bottom:15px}
.section{margin-bottom:25px}.section h2{font-size:1.2em;margin-bottom:12px;padding-bottom:6px;border-bottom:2px solid #e8eaf6}
.card{background:#fff;padding:15px;border-radius:10px;box-shadow:0 2px 6px rgba(0,0,0,.05);border-left:4px solid #1a237e;margin-bottom:10px;transition:transform .15s}
.card:hover{transform:translateX(4px)}.card.pubcom{border-left-color:#2e7d32}.card.deadline{border-left-color:#d32f2f}.card.digital{border-left-color:#6200ea}
.card .source{font-size:.75em;color:#666;background:#f0f0f0;padding:2px 8px;border-radius:4px;display:inline-block;margin-bottom:4px}
.card .title{font-weight:600;margin-bottom:4px}.card .title a{color:#1a237e;text-decoration:none}.card .title a:hover{text-decoration:underline}
.card .meta{font-size:.8em;color:#888;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.card .pub-date{color:#1a237e;font-weight:500}
.kw-tag{display:inline-block;background:#e8eaf6;color:#1a237e;padding:1px 7px;border-radius:10px;font-size:.7em;margin-right:3px}
.deadline-badge{background:#ffebee;color:#c62828;padding:2px 8px;border-radius:10px;font-size:.75em;font-weight:700}
.empty{text-align:center;padding:30px;color:#999}
.refresh-link{position:fixed;bottom:30px;right:30px;background:#1a237e;color:#fff;padding:12px 20px;border-radius:50px;font-size:.85em;text-decoration:none;box-shadow:0 4px 15px rgba(26,35,126,.4)}
.refresh-link:hover{transform:scale(1.05)}
</style>
</head>
<body>
<div class="container">
<header><h1>🏛️ AI政策モニター</h1><p>AI推進法 / 透明性・知的財産行動規範 / プリンシプルコード / GENIAC / フロンティアAI</p></header>
<div class="stats">
<div class="stat-card"><div class="number">{{ total }}</div><div class="label">直近2週間</div></div>
<div class="stat-card"><div class="number">{{ pubcom_count }}</div><div class="label">パブコメ</div></div>
<div class="stat-card"><div class="number">{{ deadline_count }}</div><div class="label">締切間近</div></div>
</div>
<div class="tabs">
<button class="tab active" onclick="filter('all')">すべて</button>
<button class="tab" onclick="filter('pubcom')">パブコメ</button>
<button class="tab" onclick="filter('cabinet_office')">内閣府</button>
<button class="tab" onclick="filter('digital')">デジタル庁</button>
<button class="tab" onclick="filter('meti')">経産省</button>
<button class="tab" onclick="filter('soumu_news')">総務省</button>
<button class="tab" onclick="filter('mext_news')">文科省</button>
<button class="tab" onclick="filter('jimin')">自民党</button>
</div>
<div class="update-time">最終更新: {{ update_time }} (JST)</div>
<div class="period-note">※ 直近2週間以内の情報を公開日順に表示</div>
{% if deadlines %}
<div class="section"><h2>⏰ パブコメ締切間近</h2>
{% for item in deadlines %}
<div class="card deadline"><span class="source">{{ item.ministry or 'パブコメ' }}</span>
<div class="title"><a href="{{ item.url }}" target="_blank">{{ item.title }}</a></div>
<div class="meta"><span class="deadline-badge">締切: {{ item.end_date }}</span>{% for kw in item.matched_keywords %}<span class="kw-tag">{{ kw }}</span>{% endfor %}</div></div>
{% endfor %}</div>
{% endif %}
<div class="section"><h2>📰 最新情報</h2><div id="articles">
{% for item in articles %}
<div class="card {{ 'pubcom' if item.is_public_comment else '' }} {{ 'digital' if item.source_id in ('digital_agency','digital_ai') else '' }}" data-source="{{ item.source_id }}">
<span class="source">{{ item.source_name }}</span>
<div class="title"><a href="{{ item.url }}" target="_blank">{{ item.title }}</a></div>
<div class="meta">{% if item.published_date %}<span class="pub-date">📅 {{ item.published_date }}</span>{% else %}<span>{{ item.scraped_at }}</span>{% endif %}{% for kw in item.matched_keywords %}<span class="kw-tag">{{ kw }}</span>{% endfor %}</div></div>
{% endfor %}
{% if not articles %}<div class="empty">直近2週間以内のAI政策関連情報はありません。</div>{% endif %}
</div></div></div>
<a class="refresh-link" href="{{ actions_url }}" target="_blank">🔄 手動更新</a>
<script>
function filter(type){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));event.target.classList.add('active');document.querySelectorAll('#articles .card').forEach(card=>{const src=card.dataset.source;if(type==='all')card.style.display='';else if(type==='pubcom')card.style.display=card.classList.contains('pubcom')?'':'none';else if(type==='meti')card.style.display=(src==='meti_en_press'||src==='meti_geniac')?'':'none';else if(type==='jimin')card.style.display=src==='jimin_news'?'':'none';else if(type==='digital')card.style.display=(src==='digital_agency'||src==='digital_ai')?'':'none';else card.style.display=src===type?'':'none';})}
</script>
</body></html>"""


def generate_html(data):
    now = now_jst()
    recent_data = filter_recent(data)
    deadlines, pubcom_count = [], 0
    for item in recent_data:
        if item.get("is_public_comment"):
            pubcom_count += 1
            if item.get("end_date"):
                try:
                    p = item["end_date"].split("/")
                    end_dt = datetime(int(p[0]), int(p[1]), int(p[2]), tzinfo=JST)
                    if now < end_dt <= now + timedelta(days=7):
                        deadlines.append(item)
                except (ValueError, IndexError):
                    pass

    repo_name = os.environ.get("GITHUB_REPOSITORY", "fumsuzu/ai-policy-monitor")
    actions_url = f"https://github.com/{repo_name}/actions/workflows/scrape.yml"

    html = Template(HTML_TEMPLATE).render(
        total=len(recent_data), pubcom_count=pubcom_count, deadline_count=len(deadlines),
        update_time=now.strftime("%Y/%m/%d %H:%M"), deadlines=deadlines,
        articles=recent_data[:100], actions_url=actions_url,
    )
    with open(os.path.join(OUTPUT_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML生成完了 (直近2週間: {len(recent_data)}件)")


async def main():
    logger.info("=== AI政策モニター v6 ===")
    new_items = await run_all_scrapers()
    logger.info(f"合計 {len(new_items)}件取得")
    existing = load_existing_data()
    merged = merge_data(existing, new_items)
    save_data(merged)
    generate_html(merged)
    logger.info("=== 完了 ===")


if __name__ == "__main__":
    asyncio.run(main())
