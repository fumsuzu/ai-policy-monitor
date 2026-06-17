# AI政策モニタリングアプリ

日本政府（内閣府・経産省・総務省・文科省）および自民党のAI政策動向を自動モニタリングするアプリケーション。

## 対象トピック
- AI推進法（AI Promotion Act）
- 生成AIの透明性・知的財産に関する行動規範（案）
- プリンシプルコード
- 経産省 AI GENIAC
- フロンティアAI

## 機能
1. **定期スクレイピング** - 各省庁・自民党HPを定期巡回し、関連情報を収集
2. **パブリックコメント検知** - e-Govからの新規パブコメを検出
3. **締切アラート** - パブコメ締切が近い案件を通知
4. **Webダッシュボード** - 収集した情報をブラウザで閲覧

## 対象サイト
| 機関 | URL |
|------|-----|
| 内閣府 AI戦略 | https://www8.cao.go.jp/cstp/ai/index.html |
| 経産省 GENIAC | https://www.meti.go.jp/policy/mono_info_service/geniac/ |
| 経産省 プレスリリース | https://www.meti.go.jp/press/ |
| 総務省 報道資料 | https://www.soumu.go.jp/menu_news/ |
| 文科省 報道発表 | https://www.mext.go.jp/b_menu/houdou/ |
| 自民党 活動 | https://www.jimin.jp/activity/ |
| e-Gov パブコメ | https://public-comment.e-gov.go.jp/ |

## セットアップ

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 初回起動（DB初期化含む）
python main.py

# Webダッシュボードにアクセス
# http://localhost:8000
```

## 定期実行
- アプリ内蔵スケジューラで1時間ごとに自動巡回
- または cron / Task Scheduler で `python scraper.py` を定期実行

## 通知方法
- Webダッシュボード上のアラート表示
- メール通知（SMTP設定後）
- Slack Webhook通知（設定後）
