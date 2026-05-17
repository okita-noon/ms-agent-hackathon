-- ============================================================
-- 002: users テーブル追加（認証・マルチテナント紐付け）
-- ============================================================

CREATE TABLE users (
    user_id         NVARCHAR(50)   PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    email           NVARCHAR(200)  NOT NULL,
    password_hash   NVARCHAR(500)  NULL,
    display_name    NVARCHAR(200)  NOT NULL,
    auth_provider   NVARCHAR(20)   NOT NULL DEFAULT 'local'
                    CHECK (auth_provider IN ('local', 'microsoft')),
    entra_oid       NVARCHAR(200)  NULL,
    active          BIT            NOT NULL DEFAULT 1,
    created_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT UQ_users_email UNIQUE (email)
);
GO

CREATE INDEX IX_users_tenant ON users(tenant_id);
CREATE INDEX IX_users_entra_oid ON users(entra_oid) WHERE entra_oid IS NOT NULL;
GO

-- ============================================================
-- デモユーザー（パスワード: demo1234）
-- bcrypt hash は seed スクリプトで生成するため、ここでは仮の値
-- 実際の投入は scripts/seed_users.py で行う
-- ============================================================
