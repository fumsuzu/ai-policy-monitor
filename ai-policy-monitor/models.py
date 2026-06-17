"""データベースモデル定義"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Article(Base):
    """収集した記事・ニュース"""

    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(50), nullable=False, index=True)  # config.sourcesのキー
    source_name = Column(String(100), nullable=False)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False, unique=True)
    summary = Column(Text, nullable=True)
    published_date = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    matched_keywords = Column(String(500), nullable=True)  # カンマ区切り
    is_new = Column(Boolean, default=True)  # 未読フラグ
    article_type = Column(String(50), nullable=False)  # government, party, public_comment


class PublicComment(Base):
    """パブリックコメント"""

    __tablename__ = "public_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=False, unique=True)
    ministry = Column(String(100), nullable=True)  # 所管省庁
    start_date = Column(DateTime, nullable=True)  # 募集開始日
    end_date = Column(DateTime, nullable=True)  # 募集締切日
    status = Column(String(50), default="open")  # open, closed, upcoming
    matched_keywords = Column(String(500), nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_new = Column(Boolean, default=True)
    deadline_notified = Column(Boolean, default=False)  # 締切通知済みフラグ


class ScrapeLog(Base):
    """スクレイピング実行ログ"""

    __tablename__ = "scrape_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(50), nullable=False)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    success = Column(Boolean, nullable=False)
    articles_found = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    duration_seconds = Column(Float, nullable=True)
