"""AI政策モニタリングアプリ - メインエントリポイント"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select, func, and_

from config import settings
from database import init_db, async_session
from models import Article, PublicComment, ScrapeLog
from scheduler import run_all_scrapers

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# スケジューラ
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションのライフサイクル管理"""
    # 起動時
    logger.info("AI政策モニター起動中...")
    await init_db()
    logger.info("データベース初期化完了")

    # 定期スクレイピングジョブ登録
    scheduler.add_job(
        run_all_scrapers,
        "interval",
        minutes=settings.scrape_interval_minutes,
        id="scrape_job",
        next_run_time=datetime.now() + timedelta(seconds=10),  # 起動10秒後に初回実行
    )
    scheduler.start()
    logger.info(
        f"スケジューラ起動 (間隔: {settings.scrape_interval_minutes}分)"
    )

    yield

    # 終了時
    scheduler.shutdown()
    logger.info("AI政策モニター終了")


app = FastAPI(
    title="AI政策モニター",
    description="日本のAI政策動向を自動モニタリング",
    lifespan=lifespan,
)

templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """メインダッシュボード"""
    async with async_session() as session:
        # 統計情報
        total_articles = (
            await session.execute(select(func.count(Article.id)))
        ).scalar() or 0
        new_articles = (
            await session.execute(
                select(func.count(Article.id)).where(Article.is_new == True)
            )
        ).scalar() or 0
        open_pubcoms = (
            await session.execute(
                select(func.count(PublicComment.id)).where(
                    PublicComment.status == "open"
                )
            )
        ).scalar() or 0

        # 締切間近（7日以内）
        deadline_threshold = datetime.now() + timedelta(
            days=settings.pubcom_deadline_alert_days
        )
        deadline_soon = (
            await session.execute(
                select(func.count(PublicComment.id)).where(
                    and_(
                        PublicComment.status == "open",
                        PublicComment.end_date != None,
                        PublicComment.end_date <= deadline_threshold,
                        PublicComment.end_date > datetime.now(),
                    )
                )
            )
        ).scalar() or 0

        # 締切間近パブコメ一覧
        deadline_result = await session.execute(
            select(PublicComment)
            .where(
                and_(
                    PublicComment.status == "open",
                    PublicComment.end_date != None,
                    PublicComment.end_date <= deadline_threshold,
                    PublicComment.end_date > datetime.now(),
                )
            )
            .order_by(PublicComment.end_date.asc())
        )
        deadline_comments = deadline_result.scalars().all()

        # 最新記事一覧（50件）
        articles_result = await session.execute(
            select(Article).order_by(Article.scraped_at.desc()).limit(50)
        )
        articles = articles_result.scalars().all()

        # 最終更新日時
        last_log = await session.execute(
            select(ScrapeLog).order_by(ScrapeLog.scraped_at.desc()).limit(1)
        )
        last_log_entry = last_log.scalar_one_or_none()
        last_update = (
            last_log_entry.scraped_at.strftime("%Y/%m/%d %H:%M")
            if last_log_entry
            else None
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": {
                "total_articles": total_articles,
                "new_articles": new_articles,
                "open_pubcoms": open_pubcoms,
                "deadline_soon": deadline_soon,
            },
            "deadline_comments": deadline_comments,
            "articles": articles,
            "last_update": last_update,
        },
    )


@app.post("/api/scrape")
async def trigger_scrape():
    """手動スクレイピング実行API"""
    try:
        await run_all_scrapers()
        return {"status": "ok", "message": "スクレイピング完了"}
    except Exception as e:
        logger.error(f"手動スクレイピングエラー: {e}")
        return {"status": "error", "message": str(e)}


@app.get("/api/articles")
async def get_articles(
    source: str = None, keyword: str = None, limit: int = 50
):
    """記事一覧API"""
    async with async_session() as session:
        query = select(Article).order_by(Article.scraped_at.desc())
        if source:
            query = query.where(Article.source_id == source)
        if keyword:
            query = query.where(Article.matched_keywords.contains(keyword))
        query = query.limit(limit)
        result = await session.execute(query)
        articles = result.scalars().all()
        return [
            {
                "id": a.id,
                "source_id": a.source_id,
                "source_name": a.source_name,
                "title": a.title,
                "url": a.url,
                "matched_keywords": a.matched_keywords,
                "scraped_at": a.scraped_at.isoformat(),
                "is_new": a.is_new,
            }
            for a in articles
        ]


@app.get("/api/public-comments")
async def get_public_comments(status: str = None):
    """パブコメ一覧API"""
    async with async_session() as session:
        query = select(PublicComment).order_by(PublicComment.end_date.asc())
        if status:
            query = query.where(PublicComment.status == status)
        result = await session.execute(query)
        comments = result.scalars().all()
        return [
            {
                "id": c.id,
                "title": c.title,
                "url": c.url,
                "ministry": c.ministry,
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "status": c.status,
                "matched_keywords": c.matched_keywords,
                "is_new": c.is_new,
            }
            for c in comments
        ]


@app.post("/api/articles/{article_id}/read")
async def mark_as_read(article_id: int):
    """記事を既読にする"""
    async with async_session() as session:
        result = await session.execute(
            select(Article).where(Article.id == article_id)
        )
        article = result.scalar_one_or_none()
        if article:
            article.is_new = False
            await session.commit()
            return {"status": "ok"}
        return {"status": "error", "message": "記事が見つかりません"}


@app.get("/api/status")
async def get_status():
    """システムステータスAPI"""
    async with async_session() as session:
        # 最新ログ
        result = await session.execute(
            select(ScrapeLog).order_by(ScrapeLog.scraped_at.desc()).limit(10)
        )
        logs = result.scalars().all()
        return {
            "scheduler_running": scheduler.running,
            "interval_minutes": settings.scrape_interval_minutes,
            "recent_logs": [
                {
                    "source_id": log.source_id,
                    "scraped_at": log.scraped_at.isoformat(),
                    "success": log.success,
                    "articles_found": log.articles_found,
                    "duration": log.duration_seconds,
                    "error": log.error_message,
                }
                for log in logs
            ],
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
