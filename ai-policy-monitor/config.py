"""アプリケーション設定"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # DB
    database_url: str = "sqlite+aiosqlite:///./ai_policy_monitor.db"

    # スクレイピング間隔（分）
    scrape_interval_minutes: int = 60

    # パブコメ締切アラート（何日前に通知するか）
    pubcom_deadline_alert_days: int = 7

    # Slack通知
    slack_webhook_url: Optional[str] = None

    # メール通知
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    notification_email: Optional[str] = None

    # モニタリング対象キーワード
    keywords: list[str] = [
        "AI推進法",
        "人工知能関連技術の研究開発及び活用の推進",
        "生成AI",
        "透明性",
        "知的財産",
        "行動規範",
        "プリンシプル",
        "GENIAC",
        "フロンティアAI",
        "基盤モデル",
        "AI戦略",
        "AI安全",
        "著作権",
        "学習データ",
    ]

    # モニタリング対象URL
    sources: dict[str, dict] = {
        "cabinet_office": {
            "name": "内閣府 AI戦略",
            "url": "https://www8.cao.go.jp/cstp/ai/index.html",
            "type": "government",
        },
        "meti_geniac": {
            "name": "経産省 GENIAC",
            "url": "https://www.meti.go.jp/policy/mono_info_service/geniac/",
            "type": "government",
        },
        "meti_press": {
            "name": "経産省 プレスリリース",
            "url": "https://www.meti.go.jp/press/",
            "type": "government",
        },
        "soumu_news": {
            "name": "総務省 報道資料",
            "url": "https://www.soumu.go.jp/menu_news/s-news/",
            "type": "government",
        },
        "mext_news": {
            "name": "文科省 報道発表",
            "url": "https://www.mext.go.jp/b_menu/houdou/index.htm",
            "type": "government",
        },
        "jimin_activity": {
            "name": "自民党 活動",
            "url": "https://www.jimin.jp/activity/",
            "type": "party",
        },
        "egov_pubcom": {
            "name": "e-Gov パブリックコメント",
            "url": "https://public-comment.e-gov.go.jp/",
            "type": "public_comment",
        },
    }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
