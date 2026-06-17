"""経産省スクレイパー"""

import logging
from datetime import datetime
from typing import Optional

from scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


class MetiScraper(BaseScraper):
    """経産省 プレスリリース"""

    def __init__(self):
        super().__init__("meti_press")

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        soup = await self.fetch_page()
        if not soup:
            return items

        # 経産省のプレスリリース一覧からリンクを抽出
        # ページ構造に依存するため、複数セレクタを試行
        links = soup.select("ul.news_list li a") or soup.select(
            "div.news-list a"
        ) or soup.find_all("a")

        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or not href:
                continue

            # AI関連キーワードでフィルタ
            matched = self.match_keywords(title)
            if not matched:
                continue

            url = self.resolve_url(href)
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


class MetiGeniacScraper(BaseScraper):
    """経産省 GENIAC ページ"""

    def __init__(self):
        super().__init__("meti_geniac")

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        soup = await self.fetch_page()
        if not soup:
            return items

        # GENIACページの更新情報・リンクを取得
        links = soup.find_all("a")
        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or not href or len(title) < 5:
                continue

            # GENIAC関連は全て収集（既にGENIACページなので）
            # ただし追加キーワードマッチもチェック
            matched = self.match_keywords(title)
            if not matched:
                matched = ["GENIAC"]  # GENIACページ上のコンテンツは全て関連

            url = self.resolve_url(href)
            # 外部リンクや画像は除外
            if not url.startswith("http"):
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
