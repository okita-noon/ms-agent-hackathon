# 認証セットアップガイド

## 概要

foogent はID/パスワード認証と Microsoft SSO (Entra ID) に対応。
ユーザーはテナントに紐付いており、ログイン後は自動的に所属テナントのデータのみ表示される。

---

## 1. データベースセットアップ

### users テーブル作成

Azure Portal の SQL Database (db-orderai-dev) のクエリエディタ、または SSMS/Azure Data Studio で以下を実行:

```sql
-- infra/sql/002-add-users.sql の内容を実行
```

### デモユーザー投入

```bash
# パスワードと接続文字列を環境変数で指定
export DEMO_PASSWORD="任意のパスワード"
export SQL_CONNECTION_STRING="..."

# 投入実行
pip install pyodbc passlib[bcrypt] bcrypt==4.0.1
python scripts/seed_users.py
```

投入されるユーザー:

| ID | テナント | メールアドレス | 名前 |
|---|---|---|---|
| U-001 | T-001 (丸山食品) | admin@maruyama.example.com | 丸山 太郎 |
| U-002 | T-001 (丸山食品) | staff@maruyama.example.com | 丸山 花子 |
| U-003 | T-002 (鈴木青果) | admin@suzuki.example.com | 鈴木 一郎 |
| U-004 | T-002 (鈴木青果) | staff@suzuki.example.com | 鈴木 次郎 |

パスワードは `DEMO_PASSWORD` 環境変数で指定した値が全ユーザー共通で設定される。

---

## 2. バックエンド環境変数

Container Apps に以下を追加:

```bash
az containerapp update \
  --name ca-api-orderai-dev2 \
  --resource-group rg-orderai-dev2 \
  --set-env-vars \
    "JWT_SECRET_KEY=<python3 -c 'import secrets; print(secrets.token_urlsafe(48))' で生成>" \
    "AZURE_AD_ALLOWED_TENANTS=<Entra テナントID>"
```

### JWT_SECRET_KEY の生成方法

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

| 変数 | 必須 | 説明 |
|---|---|---|
| `JWT_SECRET_KEY` | Yes | JWT署名用シークレット。未設定・既知のダミー値だと起動時に `RuntimeError` |
| `JWT_ISSUER` | No | JWT `iss` クレーム（デフォルト `orderai-api`）。トークン検証時に厳密一致 |
| `JWT_AUDIENCE` | No | JWT `aud` クレーム（デフォルト `orderai-dashboard`）。トークン検証時に厳密一致 |
| `JWT_EXPIRE_HOURS` | No | トークン有効期限(デフォルト: 24時間) |
| `AUTH_COOKIE_SECURE` | No | 認証 Cookie の `Secure` 属性（デフォルト: `true`）。ローカルHTTP検証時のみ `false` |
| `AUTH_COOKIE_SAMESITE` | No | 認証 Cookie の `SameSite` 属性（デフォルト: `none`）。静的サイト/API別ドメイン運用では `none` |
| `AZURE_AD_ALLOWED_TENANTS` | SSO使用時 Yes | Microsoft Entra `tid` のカンマ区切り allowlist。未設定なら全 SSO 拒否（fail-closed） |
| `AZURE_AD_ALLOWED_DOMAINS` | No | email/UPN ドメインの追加 allowlist（小文字、カンマ区切り） |
| `REGISTRATION_ENABLED` | No | `true` でセルフ登録解放（デフォルト無効＝`/api/auth/register` は 404） |
| `REGISTRATION_INVITE_TOKEN` | 登録有効時 Yes | `X-Invite-Token` ヘッダで照合する招待トークン |

> **セキュリティ上の重要事項**: `JWT_SECRET_KEY` のデフォルト値は撤去されました。設定漏れがあると起動時に明示的なエラーが出ます。

---

## 3. Microsoft Entra ID (SSO) セットアップ

### 3-1. Azure Portal でアプリ登録

1. Azure Portal → **Microsoft Entra ID** → **アプリの登録** → **新規登録**
2. 以下を入力:
   - 名前: `foogent Dashboard`
   - サポートされるアカウントの種類: **この組織ディレクトリのみ**（シングルテナント）
     - 外部ユーザーも許可する場合は「任意の組織ディレクトリ」を選択
   - リダイレクト URI:
     - 種類: **SPA (Single Page Application)**
     - URI: `https://storderaidev2.z11.web.core.windows.net/`
3. **登録** をクリック

### 3-2. アプリケーション情報の取得

登録後の「概要」画面から:
- **アプリケーション (クライアント) ID** → `ENTRA_CLIENT_ID` として使用
- **ディレクトリ (テナント) ID** → `ENTRA_TENANT_ID` として使用

### 3-3. API のアクセス許可

左メニュー → **API のアクセス許可** → **アクセス許可の追加**:
- Microsoft Graph → 委任されたアクセス許可:
  - `openid`
  - `profile`
  - `email`
- **管理者の同意を与える** をクリック

### 3-4. トークンの構成

左メニュー → **トークンの構成** → **オプションの要求を追加**:
- トークンの種類: **ID**
- 要求: `email`, `preferred_username` にチェック
- **追加** をクリック

### 3-5. 環境変数の設定

**バックエンド（Container Apps）:**

```bash
az containerapp update \
  --name ca-api-orderai-dev2 \
  --resource-group rg-orderai-dev2 \
  --set-env-vars \
    "ENTRA_CLIENT_ID=<アプリケーション(クライアント)ID>" \
    "AZURE_AD_ALLOWED_TENANTS=<ディレクトリ(テナント)ID>" \
    "FRONTEND_ORIGINS=https://storderaidev2.z11.web.core.windows.net" \
    "FRONTEND_URL=https://storderaidev2.z11.web.core.windows.net/"
```

> `AZURE_AD_ALLOWED_TENANTS` は SSO 受け入れテナントの allowlist。複数組織を許可するならカンマ区切り。
> **未設定だと SSO ログインが全部拒否される（fail-closed）**ので注意。

**フロントエンド（GitHub Repository Variables / ビルド時）:**

`.env` または CI で:
```
VITE_ENTRA_CLIENT_ID=<アプリケーション(クライアント)ID>
VITE_ENTRA_TENANT_ID=<ディレクトリ(テナント)ID>
```

ビルド後に反映される（`npm run build`）。

### 3-6. ローカル開発時

ローカルでSSO をテストする場合、Entra ID のアプリ登録に以下のリダイレクト URI を追加:
- `http://localhost:5173/`（Vite dev server）

---

## 4. ユーザーの追加・管理

### 方法1: seed スクリプトを編集

`scripts/seed_users.py` の `DEMO_USERS` リストに行を追加して再実行。

### 方法2: SQL で直接追加

```sql
-- パスワードハッシュは Python で生成:
-- python3 -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('パスワード'))"

INSERT INTO users (user_id, tenant_id, email, password_hash, display_name, auth_provider)
VALUES (
    N'U-005',
    N'T-001',
    N'newuser@example.com',
    N'$2b$12$...',  -- bcrypt ハッシュ
    N'新規 ユーザー',
    N'local'
);
```

### 方法3: API で登録（招待制）

セルフ登録はデフォルトで**無効化**（`/api/auth/register` は 404）。
有効化する場合は以下の env を設定し、招待トークンをユーザーに共有してから叩いてもらう:

```bash
az containerapp update --name ca-api-orderai-dev2 --resource-group rg-orderai-dev2 \
  --set-env-vars \
    "REGISTRATION_ENABLED=true" \
    "REGISTRATION_INVITE_TOKEN=<ランダムな招待トークン>"
```

```bash
curl -X POST https://<BASE_URL>/api/auth/register \
  -H "Content-Type: application/json" \
  -H "X-Invite-Token: <REGISTRATION_INVITE_TOKEN と同じ値>" \
  -d '{
    "email": "newuser@example.com",
    "password": "パスワード",
    "display_name": "新規 ユーザー",
    "tenant_id": "T-001"
  }'
```

### Microsoft SSO ユーザー

**自動登録は無効**。SSO で初めてサインインするユーザーは、事前に `users` テーブルに
レコードを挿入（方法1 or 方法2）しておく必要がある。`auth_provider='microsoft'` と
`entra_oid=<対象ユーザーの Entra OID>` を指定する。未登録のままサインインすると
403 が返る。

> セキュリティ上の理由で、過去にあった「初回サインインで `SSO_DEFAULT_TENANT` (T-001) に
> 自動所属」挙動は撤去された。テナントは事前にレコードで明示すること。

---

## 5. 認証フロー

### ID/パスワード

```
ブラウザ → POST /api/auth/login {email, password}
        ← Set-Cookie: foogent_access_token=<JWT>; HttpOnly; Secure; SameSite=None
        → 以後全 API に Cookie を自動送信（fetch credentials: include）
```

### Microsoft SSO

```
ブラウザ → MSAL.js ポップアップ → Microsoft ログイン → id_token 取得
        → POST /api/auth/microsoft {id_token}
        ← Set-Cookie: foogent_access_token=<JWT>; HttpOnly; Secure; SameSite=None
        → 以後全 API に Cookie を自動送信（fetch credentials: include）
```

### トークン

- JWT (HS256), 有効期限 24 時間
- ペイロード: `iss`, `aud`, `iat`, `exp`, `sub` (user_id), `tenant_id`, `email`, `display_name`
- 検証時に `iss` (`JWT_ISSUER`) と `aud` (`JWT_AUDIENCE`) も照合される
- 全ビジネス API は JWT から `tenant_id` を取得（query parameter 不要）
- JWT は原則として HttpOnly Cookie に保存し、フロントエンド JavaScript から読めないようにする
- Cookie 認証での状態変更リクエストは `Origin` を `FRONTEND_ORIGINS` と照合して CSRF リスクを抑える

---

## 6. API エンドポイント

| メソッド | パス | 認証 | 説明 |
|---|---|---|---|
| POST | `/api/auth/login` | 不要 | ID/PW ログイン |
| POST | `/api/auth/register` | 招待トークン | `REGISTRATION_ENABLED=true` かつ `X-Invite-Token` ヘッダ必須。デフォルト 404 |
| POST | `/api/auth/microsoft` | 不要 | Microsoft SSO（事前登録ユーザーのみ） |
| POST | `/api/auth/logout` | Cookie | 認証 Cookie を削除 |
| GET | `/api/auth/me` | 必要 | 現在のユーザー情報 |
| GET | `/api/orders` | 必要 | 受注一覧。tenant_id は JWT から取得 |
| GET | `/api/orders/events` | 必要 | 受注更新の Server-Sent Events。Cookie 認証 |
| GET | `/api/orders/{id}` | 必要 | 受注詳細。tenant_id ミスマッチは 404（IDOR ガード） |
| GET | `/api/customers` | 必要 | 顧客一覧 |
| ... | その他ビジネスAPI | 必要 | JWT から tenant_id 取得 |
| POST | `/api/line-webhook` | LINE 署名 | `x-line-signature` ヘッダ必須（無いと 401）、HMAC 検証失敗で 403 |
| POST | `/api/phone-webhook` | EventGrid 共有鍵 | `?code=<EVENTGRID_WEBHOOK_KEY>` または `X-EventGrid-Webhook-Key` ヘッダ必須 |
