"""文科省スクレイパー"""

import logging
from scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


class MextScraper(BaseScraper):
    """文科省 報道発表"""

    def __init__(self):
        super().__init__("mext_news")

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        soup = await self.fetch_page()
        if not soup:
            return items

        # 文科省の報道発表一覧
        links = soup.select("ul.news_list li a") or soup.select(
            "div.content-main a"
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
