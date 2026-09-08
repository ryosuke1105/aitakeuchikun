# 映画風サイバー認証 ✕ 原宿ゆめかわいい Drive横断PDF Q&A Webアプリ 💖💻

ハリウッド映画風の極秘サイバー認証画面から、認証突破時にノイズ・ブラックアウト演出を経て、原宿系超ゆめかわいいQ&A空間へと切り替わるギャップ演出型Webアプリケーションです。
Google Driveフォルダ内の複数PDF資料をGemini APIが横断解析し、指定文字数以内で完結した自然な日本語で回答します。

---

## 🌟 特徴と見どころ

1. **【画面A】シリアス・サイバーセキュリティ認証画面**
   - 漆黒（`#000000`）背景にCRTモニター風の走査線（スキャンライン）アニメーション。
   - シルバー・メタリック立体タイポグラフィ、点滅カーソル、ハッカーライクなログ演出。
2. **【トランジション】ノイズ＆ブラックアウト演出**
   - 正しいパスワード（デフォルト: `CYBER_SECRET_2026`）入力時、画面が歪みグリッチノイズと共にゆめかわいい画面へダイナミック移行。
3. **【画面B】原宿超ゆめかわいいQ&Aメイン画面**
   - パステル（ミルキーピンク、ラベンダー、ミントグリーン、イエロー）のファンシーグラデーション。
   - 浮遊する雲（☁️）、キラキラ（✨）、ハート（💖）のアニメーション。
   - ぷっくり角丸カード、キャンディGlossボタン、雲型回答フレーム。
4. **Google Drive ✕ Gemini API PDF横断Q&A**
   - 指定Google Driveフォルダ内の全PDFを取得・ロード。
   - Gemini APIが複数ドキュメントを横断分析し、指定文字数（10〜1000文字）を厳密に遵守して回答生成。

---

## 📁 ディレクトリ構成

```text
AIMEYER/
├── app.py                      # Flask バックエンド（ルーティング、セッション、API）
├── drive_loader.py             # Google Drive API & Gemini API 連携モジュール
├── requirements.txt            # Python 依存ライブラリ
├── Procfile                    # Render デプロイ用Webサーバー起動設定
├── .env.example                # 環境変数テンプレート
├── README.md                   # 説明書
├── templates/
│   └── index.html              # 画面A / 画面B 共通SPAテンプレート
└── static/
    ├── css/
    │   ├── cyber.css           # サイバー認証画面用CSS & ノイズエフェクト
    │   └── yumekawaii.css      # 原宿ゆめかわいい画面用CSS
    └── js/
        └── app.js              # フロントエンド非同期通信 & DOM操作スクリプト
```

---

## ⚙️ 環境変数設定 (`.env`)

ローカル開発やRenderデプロイ時には以下の環境変数を設定してください。

| 環境変数名 | 説明 | 例 / 設定値 |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | Google AI Studioから取得したGemini APIキー | `AIzaSy...` |
| `GOOGLE_DRIVE_FOLDER_ID` | 対象のPDFが保存されているGoogle DriveフォルダのID | `1A2b3C4d...` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Google CloudサービスアカウントのJSON文字列 | `{"type":"service_account", ...}` |
| `APP_PASSWORD` | 画面Aの認証パスワード | `CYBER_SECRET_2026` |
| `SECRET_KEY` | Flaskセッション暗号化キー | `super_secret_key_123` |

> 💡 **補足**: `GOOGLE_SERVICE_ACCOUNT_JSON` や `GEMINI_API_KEY` が未設定の場合でも、アプリはデモモックモードで安全に起動・テスト可能です。

---

## 🚀 ローカル起動手順

1. **リポジトリの準備 & 依存ライブラリのインストール**:
   ```bash
   pip install -r requirements.txt
   ```

2. **環境変数の作成**:
   `.env.example` をコピーして `.env` を作成し、必要なAPIキーを設定します。
   ```bash
   cp .env.example .env
   ```

3. **Flask アプリの起動**:
   ```bash
   python app.py
   ```
   ブラウザで `http://localhost:5000` にアクセスしてください。

---

## ☁️ Render へのデプロイ手順

1. **GitHub にコードをプッシュ**
2. **Render Dashboard** (`https://dashboard.render.com/`) で `New +` -> `Web Service` を選択。
3. GitHubリポジトリを接続し、以下の項目を設定：
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app` (Procfileがある場合は自動認識されます)
4. **Environment Variables** に上記テーブルの環境変数を登録して `Deploy Web Service` を実行してください。

---

## 💖 ライセンス & 著作権
Created for Harajuku Kawaii Security Q&A Project.
