# セキュリティガイド

このリポジトリで開発する際のセキュリティルールです。
**全メンバー必読**です。

---

## 絶対にやってはいけないこと

1. **APIキー・パスワードをコードに直接書かない**
   - Azure OpenAI のキー、接続文字列、トークン等を `.py` や `.js` ファイルに書かないでください
   - 悪い例: `api_key = "sk-abc123..."`
   - 良い例: `api_key = os.environ["AZURE_OPENAI_API_KEY"]`

2. **`.env` ファイルをコミット・プッシュしない**
   - `.env` にはAPIキー等の秘密情報を入れます
   - `.gitignore` で除外済みですが、`git add .` の際は特に注意してください

3. **秘密鍵ファイル（`.pem`, `.key` 等）をリポジトリに入れない**

## 環境変数の使い方

1. `.env.example` をコピーして `.env` を作成
   ```
   cp .env.example .env
   ```
2. `.env` に自分のAPIキー等を記入
3. 新しい環境変数を追加したら、**キー名だけ**（値なし）を `.env.example` にも追記

## 安全装置

- **pre-commit フック**: コミット時に秘密情報の混入を自動チェックします
- **PR テンプレート**: PRを出す際にセキュリティチェックリストを確認してください

## ランタイム上の認証境界

| 経路 | 認証 |
|---|---|
| `/api/auth/login` | 公開（パスワード検証） |
| `/api/auth/register` | デフォルト無効。`REGISTRATION_ENABLED=true` + `X-Invite-Token` ヘッダ必須 |
| `/api/auth/microsoft` | Microsoft Entra の id_token を検証。`AZURE_AD_ALLOWED_TENANTS` allowlist の `tid` のみ受理。自動登録なし（事前 provision 必須） |
| `/api/auth/me` ほかビジネス API | Bearer JWT 必須。`tenant_id` は JWT クレームから取得（クエリ不可） |
| `GET /api/orders/{id}` | JWT の `tenant_id` と doc の `tenant_id` 一致時のみ返却（IDOR ガード） |
| `/api/line-webhook` | `x-line-signature` ヘッダで HMAC-SHA256 を検証（必須） |
| `/api/phone-webhook` | `EVENTGRID_WEBHOOK_KEY` を `?code=` クエリか `X-EventGrid-Webhook-Key` ヘッダで検証（必須） |

JWT は `iss` / `aud` も検証する（`JWT_ISSUER` / `JWT_AUDIENCE`）。
`JWT_SECRET_KEY` は未設定だと起動時に `RuntimeError`（フェイルクローズ）。

### pre-commit フックのセットアップ

クローン後に以下を実行してください:

```bash
git config core.hooksPath .githooks
```

## もし秘密情報をコミットしてしまったら

**git の履歴に残るため、push前でも以下を実施してください:**

1. 漏洩したキー・パスワードを**即座に無効化・再生成**する（Azure Portal等から）
2. チームに報告する
3. 履歴からの削除が必要な場合はチーム内で相談する

**push 済みの場合は、キーの再生成が最優先です。**
