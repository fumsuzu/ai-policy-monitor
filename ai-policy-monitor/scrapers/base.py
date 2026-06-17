"""スクレイパー基底クラス"""

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from config import settings

logger = logging.getLogger(__name__)


@dataclass
class ScrapedItem:
    """スクレイピング結果1件"""

    title: str
    url: str
    source_id: str
    source_name: str
    article_type: str
    summary: Optional[str] = None
    published_date: Optional[datetime] = None
    matched_keywords: list[str] = field(default_factory=list)
    # パブコメ用
    ministry: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    status: Optional[str] = None


class BaseScraper(ABC):
    """スクレイパー基底クラス"""

    def __init__(self, source_id: str):
        self.source_id = source_id
        source_config = settings.sources[source_id]
        self.source_name = source_config["name"]
        self.base_url = source_config["url"]
        self.article_type = source_config["type"]
        self.keywords = settings.keywords

    async def fetch_page(self, url: Optional[str] = None) -> Optional[BeautifulSoup]:
        """ページ取得してBeautifulSoupで解析"""
        target_url = url or self.base_url
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja,en;q=0.9",
        }
        try:
            async with httpx.AsyncClient(
                timeout=30.0, follow_redirects=True
            ) as client:
                response = await client.get(target_url, headers=headers)
                response.raise_for_status()
                # エンコーディング推定
                content_type = response.headers.get("content-type", "")
                if "charset" not in content_type:
                    response.encoding = "utf-8"
                return BeautifulSoup(response.text, "lxml")
        except Exception as e:
            logger.error(f"ページ取得失敗 [{self.source_id}] {target_url}: {e}")
            return None

    def match_keywords(self, text: str) -> list[str]:
        """テキストに含まれるキーワードを抽出"""
        if not text:
            return []
        matched = []
        text_lower = text.lower()
        for kw in self.keywords:
            if kw.lower() in text_lower:
                matched.append(kw)
        return matched

    def resolve_url(self, relative_url: str) -> str:
        """相対URLを絶対URLに変換"""
        return urljoin(self.base_url, relative_url)

    @abstractmethod
    async def scrape(self) -> list[ScrapedItem]:
        """スクレイピング実行（各サブクラスで実装）"""
        pass

    async def run(self) -> tuple[list[ScrapedItem], float, Optional[str]]:
        """実行してログ情報も返す"""
        start = time.time()
        error_msg = None
        items = []
        try:
            items = await self.scrape()
            logger.info(
                f"[{self.source_id}] {len(items)}件取得"
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"[{self.source_id}] スクレイピングエラー: {e}")
        duration = time.time() - start
        return items, duration, error_msg
