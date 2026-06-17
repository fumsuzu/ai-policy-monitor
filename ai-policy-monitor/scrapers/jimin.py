"""自民党スクレイパー"""

import logging
from scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


class JiminScraper(BaseScraper):
    """自民党 活動ページ (https://www.jimin.jp/activity/)"""

    def __init__(self):
        super().__init__("jimin_activity")

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        soup = await self.fetch_page()
        if not soup:
            return items

        # 自民党の活動ページから記事リンクを取得
        # 部会・調査会・委員会などの活動報告が掲載される
        article_links = soup.select("article a") or soup.select(
            "div.activity-list a"
        ) or soup.select("ul.list-news li a") or soup.find_all("a")

        seen_urls = set()
        for link in article_links:
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or not href or len(title) < 5:
                continue

            url = self.resolve_url(href)
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # AI関連キーワードでフィルタ
            matched = self.match_keywords(title)
            if not matched:
                # 自民党特有のキーワードも追加チェック
                party_ai_keywords = [
                    "デジタル社会推進",
                    "知的財産戦略",
                    "AI",
                    "人工知能",
                    "デジタル",
                    "情報通信",
                    "科学技術",
                    "著作権",
                ]
                if any(kw in title for kw in party_ai_keywords):
                    matched = ["AI戦略"]  # 広くマッチさせる
                else:
                    continue

            items.append(
                ScrapedItem(
                    title=title,
                    url=url,
                    source_id=self.source_id,
                    source_name=self.source_name,
                    article_type=self.article_type,
                    matched_keywords=matched,
                )
            )

        return items
