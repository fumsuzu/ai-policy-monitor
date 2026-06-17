"""スクレイピングスケジューラ"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import async_session
from models import Article, PublicComment, ScrapeLog
from notifier import notify_new_articles, notify_public_comment_deadline, notify_new_public_comments
from scrapers import (
    MetiScraper,
    MetiGeniacScraper,
    SoumuScraper,
    MextScraper,
    CabinetOfficeScraper,
    JiminScraper,
    EgovPublicCommentScraper,
)

logger = logging.getLogger(__name__)

# 全スクレイパーのインスタンス
ALL_SCRAPERS = [
    CabinetOfficeScraper(),
    MetiScraper(),
    MetiGeniacScraper(),
    SoumuScraper(),
    MextScraper(),
    JiminScraper(),
    EgovPublicCommentScraper(),
]


async def run_all_scrapers():
    """全スクレイパーを実行し、結果をDBに保存"""
    logger.info("=== スクレイピング開始 ===")
    new_articles = []
    new_pubcoms = []

    async with async_session() as session:
        for scraper in ALL_SCRAPERS:
            items, duration, error_msg = await scraper.run()

            # ログ保存
            log = ScrapeLog(
                source_id=scraper.source_id,
                scraped_at=datetime.utcnow(),
                success=error_msg is None,
                articles_found=len(items),
                error_message=error_msg,
                duration_seconds=duration,
            )
            session.add(log)

            # 記事保存
            for item in items:
                if item.article_type == "public_comment":
                    pubcom = await _save_public_comment(session, item)
                    if pubcom:
                        new_pubcoms.append(pubcom)
                else:
                    article = await _save_article(session, item)
                    if article:
                        new_articles.append(article)

        await session.commit()

    # 通知
    if new_articles:
        logger.info(f"新着記事 {len(new_articles)}件 → 通知送信")
        await notify_new_articles(new_articles)

    if new_pubcoms:
        logger.info(f"新規パブコメ {len(new_pubcoms)}件 → 通知送信")
        await notify_new_public_comments(new_pubcoms)

    # 締切間近のパブコメチェック
    await check_deadline_alerts()

    logger.info("=== スクレイピング完了 ===")


async def _save_article(session: AsyncSession, item) -> Article | None:
    """記事を保存（重複チェック付き）"""
    # URL重複チェック
    existing = await session.execute(
        select(Article).where(Article.url == item.url)
    )
    if existing.scalar_one_or_none():
        return None  # 既に存在

    article = Article(
        source_id=item.source_id,
        source_name=item.source_name,
        title=item.title,
        url=item.url,
        summary=item.summary,
        published_date=item.published_date,
        matched_keywords=",".join(item.matched_keywords),
        is_new=True,
        article_type=item.article_type,
    )
    session.add(article)
    return article


async def _save_public_comment(session: AsyncSession, item) -> PublicComment | None:
    """パブコメを保存（重複チェック付き）"""
    existing = await session.execute(
        select(PublicComment).where(PublicComment.url == item.url)
    )
    if existing.scalar_one_or_none():
        return None

    pubcom = PublicComment(
        title=item.title,
        url=item.url,
        ministry=item.ministry,
        start_date=item.start_date,
        end_date=item.end_date,
        status=item.status or "open",
        matched_keywords=",".join(item.matched_keywords),
        is_new=True,
        deadline_notified=False,
    )
    session.add(pubcom)
    return pubcom


async def check_deadline_alerts():
    """締切間近のパブコメをチェックして通知"""
    alert_threshold = datetime.now() + timedelta(
        days=settings.pubcom_deadline_alert_days
    )

    async with async_session() as session:
        result = await session.execute(
            select(PublicComment).where(
                PublicComment.status == "open",
                PublicComment.end_date != None,
                PublicComment.end_date <= alert_threshold,
                PublicComment.end_date > datetime.now(),
                PublicComment.deadline_notified == False,
            )
        )
        approaching_deadlines = result.scalars().all()

        if approaching_deadlines:
            logger.info(
                f"締切間近パブコメ {len(approaching_deadlines)}件 → アラート送信"
            )
            await notify_public_comment_deadline(approaching_deadlines)

            # 通知済みフラグ更新
            for pc in approaching_deadlines:
                pc.deadline_notified = True
            await session.commit()
