"""内閣府スクレイパー"""

import logging
from scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


class CabinetOfficeScraper(BaseScraper):
    """内閣府 AI戦略"""

    def __init__(self):
        super().__init__("cabinet_office")

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        soup = await self.fetch_page()
        if not soup:
            return items

        # 内閣府AI戦略ページのリンク・更新情報を取得
        links = soup.find_all("a")

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

            # AI関連キーワードでフィルタ（内閣府AI戦略ページなので広めに取る）
            matched = self.match_keywords(title)
            if not matched:
                # AI戦略ページ上であれば関連性が高い
                if any(
                    kw in title
                    for kw in ["AI", "人工知能", "戦略", "会議", "有識者"]
                ):
                    matched = ["AI戦略"]
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
