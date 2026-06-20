# mobile-agent

[简体中文](README.md) | [English](README.en.md) | **日本語**

---

**Telegram リモート + Android (adbkit) + iOS (iphone-ctl/WDA)** の自己完結型パッケージ。

単体でクローン・配布・実行でき、外部の業務プロジェクトに依存しません。

> **Telegram 設定** → [docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md)  
> **依存関係・インストール** → [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) · [docs/INSTALL.md](docs/INSTALL.md) · [scripts/README.md](scripts/README.md)

## ディレクトリ構成

```
mobile-agent/
├── mobagent            # 統合 CLI エントリ
├── .env                # 設定（.env.example からコピー）
├── SKILL.md            # Agent 統合スキル
├── droid-ctl/ + droid-ctl-skill/
├── iphone-ctl/ + iphone-ctl-skill/
├── tg-notify/ + tg-notify-skill/
├── mob-compose/             # ワンコマンド setup / check / スクリーンショット送信
├── WebDriverAgent/     # iOS WDA
└── scripts/
    ├── setup-telegram.sh # ★ Telegram ワンクリック設定
    ├── install-skill.sh
    └── tg-relay.py     # Telegram コマンド受信 Bot
```

## スキル組み合わせ（個別インストール可）

各スキルは**独立**で**自由に組み合わせ**可能。一度に全部入れる必要はありません：

| 組み合わせ | インストール | 典型シナリオ |
|------------|--------------|--------------|
| TG のみ | `--only tg` | CI ビルド通知 |
| Android のみ | `--only adb` | ローカル adb 自動化 |
| iOS のみ | `--only ios` | ローカル iPhone 自動化 |
| TG + Android | `--only tg,adb` | リモート Android 受入 |
| TG + iOS | `--only tg,ios` | リモート iPhone 受入 |
| デュアル端末 | `--only adb,ios` | 同一 Mac で 2 台制御 |
| フルスタック | デフォルト `--all` | TG 受令 + デュアル + Agent |

```bash
# 必要なスキルのみインストール
./mob install-skill --only tg,adb
./mob install-skill --list

# Python パッケージ + スキルを必要分だけ
./mob setup --only ios --with-ios-wda
./mob setup --only tg,adb --test
```

組み合わせの詳細は **[docs/SKILL_COMPOSE.md](docs/SKILL_COMPOSE.md)** を参照。

## クイックスタート

```bash
cd mobile-agent
chmod +x mobagent mob-compose/compose mob-compose/scripts/*.sh scripts/*.sh tg-relay.py tg-relay/setup-telegram.sh

# ★ Telegram ワンクリック設定
./mob tg-setup --test

./mob setup --test
./mob install-skill
./mob check
```

詳細は **[docs/TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md)** を参照。

## 3 つの使い方

### 1. Cursor Agent（推奨）

スキルインストール後、Agent に次のように指示：

> 「mobile-agent check を実行して、Android と iOS の両方をスクリーンショットして Telegram に送って」

Agent は `SKILL.md` の vision loop に従い、端末を操作して結果を返します。

### 2. Telegram Bot でコマンド受信

```bash
./mob tg-start
```

| コマンド | 作用 |
|----------|------|
| `/new claude\|codex [prompt]` | 新しいタブで AI セッションを起動 |
| `/tabs` | ターミナルのタブ一覧 + ルーティングヒント |
| `/tab [N]` | 転送先ターミナルを選択（引数なしで一覧+ボタン、`/tab 2`=2番目、`/tab 1:1`=ウィンドウ:タブ、`/tab off`=解除）。永続デフォルトとして以降の無接頭辞メッセージに適用。`TG_TERM_BACKEND` に応じて iTerm / Terminal.app を列挙 |
| `/format html\|markdown\|plain\|screenshot` | 返信フォーマット設定（即時反映） |
| `/stop` | 実行を停止（対象セッションに Esc を 1 回送信） |
| `/reset` | セッションをリセット（`/clear` を注入） |
| `/compact` | コンテキストを圧縮（`/compact` を注入） |
| `/model opus\|sonnet\|haiku\|fable` | AI モデルの確認/切替 |
| `/think low\|medium\|high\|xhigh\|max\|auto` | 思考強度を設定（`/effort` 相当） |
| `/shot android` | Android スクリーンショット → TG |
| `/shot ios` | iOS スクリーンショット → TG |
| `/tap 540 1200` | タップ（デフォルト Android） |
| `/tap 200 400 ios` | iOS タップ |
| `/swipe x1 y1 x2 y2` | スワイプ |
| `/check` | 環境チェック |
| `/devices` | 端末一覧 |
| `/help` | 利用可能なコマンドを表示 |
| 自然言語 | 対象タブに注入（または `inbox/pending.txt` に書き込み） |

> Bot 起動時に `setMyCommands` でコマンドを登録。候補のあるコマンド（`/new` `/format`
> `/shot` `/model` `/think`）は引数なしで送るとインラインボタンの**サブメニュー**が出ます。
> セキュリティ：chat-id 許可リスト（`TG_RELAY_ALLOWED_CHAT_IDS`）で Bot を操作できる
> チャットを制限できます。許可リストと `TELEGRAM_CHAT_ID` の両方が空なら relay は起動を拒否します（fail-closed）。

未処理確認：`./mob tg-inbox`

### 3. コマンドライン直接操作

```bash
./mob shot-android -c "受入"
./mob ios-start
./mob shot-ios -c "受入"
adbkit tap 540 1200
ioskit tap 540 1200
```

## 設定

すべての設定は **mobile-agent パッケージ内**：

| ファイル | 用途 |
|----------|------|
| `.env` | `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、端末シリアルなど |
| `mob-compose/compose.env` | iOS WDA（`devkit.env.example` からコピー） |

環境変数 `TGKIT_ENV_FILE` で外部 `.env` パスを指定することも可能。

## iOS の注意

初回は Xcode で `WebDriverAgentRunner` を一度 Run（Team 選択、証明書を信頼）。以降は毎日：

```bash
./mob ios-start
```

## 依存関係

- macOS（iOS スクリーンショット / WDA / tg-notify ウィンドウキャプチャ）
- Python 3.10+
- `brew install libimobiledevice`（iOS USB）
- `pip install python-telegram-bot`（`tg-start` のみ必要）

MIT

## 他の言語

- [ドキュメント索引](docs/README.md)
- [依存関係（中/En/日）](docs/DEPENDENCIES.md)
- [インストール（中/En/日）](docs/INSTALL.md)
- [Telegram 設定（中/En/日）](docs/TELEGRAM_SETUP.md)
- [简体中文](README.md)
- [English SKILL](SKILL.md) · [简体中文 SKILL](mob-remote-skill/SKILL.zh-CN.md) · [日本語 SKILL](mob-remote-skill/SKILL.ja.md)
