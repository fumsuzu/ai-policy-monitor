"""e-Gov パブリックコメント スクレイパー"""

import re
import logging
from datetime import datetime
from typing import Optional

from scrapers.base import BaseScraper, ScrapedItem

logger = logging.getLogger(__name__)


class EgovPublicCommentScraper(BaseScraper):
    """e-Gov パブリックコメント（意見募集中案件）"""

    def __init__(self):
        super().__init__("egov_pubcom")
        # パブコメ一覧のURL（意見募集中）
        self.list_url = "https://public-comment.e-gov.go.jp/servlet/Public?CLASSNAME=PCM1031_CLS&fromType=list"

    async def scrape(self) -> list[ScrapedItem]:
        items = []
        # e-Govのパブコメ一覧ページを取得
        soup = await self.fetch_page(self.list_url)
        if not soup:
            # フォールバック: ベースURLも試行
            soup = await self.fetch_page()
            if not soup:
                return items

        # パブコメ一覧からリンクと情報を抽出
        # e-Govのページ構造に基づいて解析
        rows = soup.select("table tr") or soup.select("div.result-list div.item")

        for row in rows:
            link = row.find("a")
            if not link:
                continue

            title = link.get_text(strip=True)
            href = link.get("href", "")

            if not title or not href:
                continue

            # AI関連キーワードでフィルタ
            matched = self.match_keywords(title)
            if not matched:
                continue

            url = self.resolve_url(href)

            # 日付情報を取得（テーブル内のセルから）
            end_date = self._extract_date(row)

            # 所管省庁を取得
            ministry = self._extract_ministry(row)

            # ステータス判定
            status = "open"
            if end_date and end_date < datetime.now():
                status = "closed"

            items.append(
                ScrapedItem(
                    title=title,
                    url=url,
                    source_id=self.source_id,
                    source_name=self.source_name,
                    article_type="public_comment",
                    matched_keywords=matched,
                    ministry=ministry,
                    start_date=None,
                    end_date=end_date,
                    status=status,
                )
            )

        return items

    def _extract_date(self, element) -> Optional[datetime]:
        """要素内から日付を抽出"""
        text = element.get_text()
        # 日本語日付パターン: 令和X年X月X日 or 2025年X月X日 or 2025/X/X
        patterns = [
            r"(\d{4})[年/](\d{1,2})[月/](\d{1,2})日?",
            r"令和(\d+)年(\d{1,2})月(\d{1,2})日",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                try:
                    if "令和" in pattern:
                        year = int(groups[0]) + 2018
                    else:
                        year = int(groups[0])
                    month = int(groups[1])
                    day = int(groups[2])
                    return datetime(year, month, day)
                except (ValueError, IndexError):
                    continue
        return None

    def _extract_ministry(self, element) -> Optional[str]:
        """要素内から所管省庁を抽出"""
        text = element.get_text()
        ministries = [
            "内閣府",
            "経済産業省",
            "総務省",
            "文部科学省",
            "デジタル庁",
            "厚生労働省",
            "法務省",
            "金融庁",
        ]
        for ministry in ministries:
            if ministry in text:
                return ministry
        return None
