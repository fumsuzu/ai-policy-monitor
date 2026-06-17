"""総務省スクレイパー"""

import logging
from scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


class SoumuScraper(BaseScraper):
    """総務省 報道資料"""

    def __init__(self):
        super().__init__("soumu_news")

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        soup = await self.fetch_page()
        if not soup:
            return items

        # 総務省の報道資料一覧
        links = soup.select("div.news-body a") or soup.select(
            "ul.news-list li a"
        ) or soup.find_all("a")

        seen_urls = set()
        for link in links:
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
