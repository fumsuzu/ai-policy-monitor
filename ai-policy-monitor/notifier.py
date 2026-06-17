"""通知モジュール（Slack・メール）"""

import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional

import httpx

from config import settings
from models import Article, PublicComment

logger = logging.getLogger(__name__)


async def notify_new_articles(articles: list[Article]):
    """新規記事の通知"""
    if not articles:
        return

    message = _format_articles_message(articles)

    if settings.slack_webhook_url:
        await _send_slack(message)
    if settings.notification_email and settings.smtp_host:
        _send_email(
            subject=f"[AI政策モニター] 新着{len(articles)}件",
            body=message,
        )


async def notify_public_comment_deadline(comments: list[PublicComment]):
    """パブコメ締切アラート通知"""
    if not comments:
        return

    message = _format_deadline_message(comments)

    if settings.slack_webhook_url:
        await _send_slack(message)
    if settings.notification_email and settings.smtp_host:
        _send_email(
            subject=f"[AI政策モニター] パブコメ締切間近 {len(comments)}件",
            body=message,
        )


async def notify_new_public_comments(comments: list[PublicComment]):
    """新規パブコメの通知"""
    if not comments:
        return

    message = _format_new_pubcom_message(comments)

    if settings.slack_webhook_url:
        await _send_slack(message)
    if settings.notification_email and settings.smtp_host:
        _send_email(
            subject=f"[AI政策モニター] 新規パブコメ {len(comments)}件",
            body=message,
        )


def _format_articles_message(articles: list[Article]) -> str:
    """記事通知メッセージの整形"""
    lines = ["📰 *AI政策 新着情報*\n"]
    for a in articles[:10]:  # 最大10件
        keywords = a.matched_keywords or ""
        lines.append(f"• [{a.source_name}] {a.title}")
        lines.append(f"  🔗 {a.url}")
        if keywords:
            lines.append(f"  🏷️ {keywords}")
        lines.append("")
    if len(articles) > 10:
        lines.append(f"...他 {len(articles) - 10}件")
    return "\n".join(lines)


def _format_deadline_message(comments: list[PublicComment]) -> str:
    """締切アラートメッセージの整形"""
    lines = ["⏰ *パブリックコメント 締切間近*\n"]
    for c in comments:
        days_left = (c.end_date - datetime.now()).days if c.end_date else "不明"
        lines.append(f"• {c.title}")
        lines.append(f"  📅 締切: {c.end_date.strftime('%Y/%m/%d') if c.end_date else '不明'} (あと{days_left}日)")
        lines.append(f"  🏛️ {c.ministry or '不明'}")
        lines.append(f"  🔗 {c.url}")
        lines.append("")
    return "\n".join(lines)


def _format_new_pubcom_message(comments: list[PublicComment]) -> str:
    """新規パブコメ通知メッセージ"""
    lines = ["📋 *新規パブリックコメント募集*\n"]
    for c in comments:
        lines.append(f"• {c.title}")
        if c.end_date:
            lines.append(f"  📅 締切: {c.end_date.strftime('%Y/%m/%d')}")
        lines.append(f"  🏛️ {c.ministry or '不明'}")
        lines.append(f"  🔗 {c.url}")
        if c.matched_keywords:
            lines.append(f"  🏷️ {c.matched_keywords}")
        lines.append("")
    return "\n".join(lines)


async def _send_slack(message: str):
    """Slack Webhook送信"""
    if not settings.slack_webhook_url:
        return
    try:
        async with httpx.AsyncClient() as client:
            payload = {"text": message}
            response = await client.post(
                settings.slack_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info("Slack通知送信完了")
    except Exception as e:
        logger.error(f"Slack通知エラー: {e}")


def _send_email(subject: str, body: str):
    """メール送信"""
    if not all([settings.smtp_host, settings.smtp_user, settings.notification_email]):
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = settings.smtp_user
        msg["To"] = settings.notification_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        logger.info("メール通知送信完了")
    except Exception as e:
        logger.error(f"メール通知エラー: {e}")
