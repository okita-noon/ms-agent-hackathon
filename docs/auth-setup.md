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
  --name ca-api-orderai-dev \
  --resource-group rg-orderai-dev \
  --set-env-vars \
    "JWT_SECRET_KEY=<ランダムな文字列(32文字以上)>" \
    "SSO_DEFAULT_TENANT=T-001"
```

### JWT_SECRET_KEY の生成方法

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

| 変数 | 必須 | 説明 |
|---|---|---|
| `JWT_SECRET_KEY` | Yes | JWT署名用シークレット。本番では必ずランダム値を設定 |
| `JWT_EXPIRE_HOURS` | No | トークン有効期限(デフォルト: 24時間) |
| `SSO_DEFAULT_TENANT` | No | SSO新規ユーザーのデフォルトテナント(デフォルト: T-001) |

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
     - URI: `https://storderaidev.z11.web.core.windows.net/dashboard/`
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
  --name ca-api-orderai-dev \
  --resource-group rg-orderai-dev \
  --set-env-vars \
    "ENTRA_CLIENT_ID=<アプリケーション(クライアント)ID>" \
    "ENTRA_TENANT_ID=<ディレクトリ(テナント)ID>" \
    "FRONTEND_ORIGINS=https://storderaidev.z11.web.core.windows.net" \
    "FRONTEND_URL=https://storderaidev.z11.web.core.windows.net/dashboard/"
```

**フロントエンド（GitHub Repository Variables / ビルド時）:**

`.env` または CI で:
```
VITE_ENTRA_CLIENT_ID=<アプリケーション(クライアント)ID>
VITE_ENTRA_TENANT_ID=<ディレクトリ(テナント)ID>
```

ビルド後に反映される（`npm run build`）。

### 3-6. ローカル開発時

ローカルでSSO をテストする場合、Entra ID のアプリ登録に以下のリダイレクト URI を追加:
- `http://localhost:5173/dashboard`（Vite dev server）

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

### 方法3: API で登録

```bash
curl -X POST https://<BASE_URL>/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "newuser@example.com",
    "password": "パスワード",
    "display_name": "新規 ユーザー",
    "tenant_id": "T-001"
  }'
```

### Microsoft SSO ユーザー

Microsoft アカウントでの初回ログイン時に自動登録される。
デフォルトで `SSO_DEFAULT_TENANT`（T-001）に紐付く。

テナントを変更するには SQL で:
```sql
UPDATE users SET tenant_id = 'T-002' WHERE email = 'user@example.com';
```

---

## 5. 認証フロー

### ID/パスワード

```
ブラウザ → POST /api/auth/login {email, password}
        ← {access_token, tenant_id, display_name}
        → 以後全 API に Authorization: Bearer <token>
```

### Microsoft SSO

```
ブラウザ → MSAL.js ポップアップ → Microsoft ログイン → id_token 取得
        → POST /api/auth/microsoft {id_token}
        ← {access_token, tenant_id, display_name}
        → 以後全 API に Authorization: Bearer <token>
```

### トークン

- JWT (HS256), 有効期限 24 時間
- ペイロード: `sub` (user_id), `tenant_id`, `email`, `display_name`, `exp`
- 全ビジネス API は JWT から `tenant_id` を取得（query parameter 不要）

---

## 6. API エンドポイント

| メソッド | パス | 認証 | 説明 |
|---|---|---|---|
| POST | `/api/auth/login` | 不要 | ID/PW ログイン |
| POST | `/api/auth/register` | 不要 | ユーザー登録 |
| POST | `/api/auth/microsoft` | 不要 | Microsoft SSO |
| GET | `/api/auth/me` | 必要 | 現在のユーザー情報 |
| GET | `/api/orders` | 必要 | 受注一覧 |
| GET | `/api/customers` | 必要 | 顧客一覧 |
| ... | その他ビジネスAPI | 必要 | JWT から tenant_id 取得 |
| POST | `/api/line-webhook` | 不要 | LINE 署名検証 |
| POST | `/api/phone-webhook` | 不要 | ACS EventGrid |
