-- ============================================================
-- AI受発注自動一元管理システム - マスタ・在庫スキーマ
-- Azure SQL Database 初期化スクリプト
-- ============================================================

-- テナント管理
CREATE TABLE tenants (
    tenant_id       NVARCHAR(50)   PRIMARY KEY,
    name            NVARCHAR(200)  NOT NULL,
    [plan]          NVARCHAR(50)   NOT NULL DEFAULT 'demo',
    active          BIT            NOT NULL DEFAULT 1,
    created_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);

-- 顧客マスタ
CREATE TABLE customers (
    customer_id     NVARCHAR(50)   PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    name            NVARCHAR(200)  NOT NULL,
    short_name      NVARCHAR(100),
    line_user_id    NVARCHAR(200),
    email           NVARCHAR(200),
    phone           NVARCHAR(50),
    fax             NVARCHAR(50),
    default_route   NVARCHAR(50),
    default_carrier NVARCHAR(50),
    default_time_slot NVARCHAR(50),
    delivery_lead_time NVARCHAR(20),
    active          BIT            NOT NULL DEFAULT 1,
    created_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_customers_tenant ON customers(tenant_id);
CREATE INDEX IX_customers_line ON customers(line_user_id) WHERE line_user_id IS NOT NULL;

-- 商品マスタ
CREATE TABLE products (
    product_id      NVARCHAR(50)   PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    name            NVARCHAR(200)  NOT NULL,
    display_name    NVARCHAR(200),
    category        NVARCHAR(100),
    default_unit    NVARCHAR(20)   NOT NULL,
    temperature_zone NVARCHAR(10)  NOT NULL CHECK (temperature_zone IN (N'常温', N'冷蔵', N'冷凍')),
    unit_weight_kg  DECIMAL(10,3),
    is_variable_weight BIT         NOT NULL DEFAULT 0,
    price_per_unit  DECIMAL(12,2),
    active          BIT            NOT NULL DEFAULT 1,
    created_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    updated_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME()
);
CREATE INDEX IX_products_tenant ON products(tenant_id);

-- 商品名エイリアス（表記ゆれ対応）
CREATE TABLE product_aliases (
    alias_id        INT            IDENTITY(1,1) PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    product_id      NVARCHAR(50)   NOT NULL REFERENCES products(product_id),
    alias_name      NVARCHAR(200)  NOT NULL,
    UNIQUE (product_id, alias_name)
);

-- 在庫
CREATE TABLE inventory (
    inventory_id    INT            IDENTITY(1,1) PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    product_id      NVARCHAR(50)   NOT NULL REFERENCES products(product_id),
    quantity         DECIMAL(12,3) NOT NULL DEFAULT 0,
    unit            NVARCHAR(20)   NOT NULL,
    reserved_qty    DECIMAL(12,3)  NOT NULL DEFAULT 0,
    warehouse       NVARCHAR(100),
    updated_at      DATETIME2      NOT NULL DEFAULT SYSUTCDATETIME(),
    UNIQUE (tenant_id, product_id, warehouse)
);
CREATE INDEX IX_inventory_tenant_product ON inventory(tenant_id, product_id);

-- 配送ルート定義
CREATE TABLE delivery_routes (
    route_id        NVARCHAR(50)   PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    name            NVARCHAR(100)  NOT NULL,
    region          NVARCHAR(100),
    carriers        NVARCHAR(500),
    active          BIT            NOT NULL DEFAULT 1
);

-- Connector 設定レジストリ
CREATE TABLE connector_registry (
    registry_id     INT            IDENTITY(1,1) PRIMARY KEY,
    tenant_id       NVARCHAR(50)   NOT NULL REFERENCES tenants(tenant_id),
    interface_name  NVARCHAR(200)  NOT NULL,
    adapter_type    NVARCHAR(100)  NOT NULL,
    config_json     NVARCHAR(MAX)  NOT NULL,
    active          BIT            NOT NULL DEFAULT 1,
    UNIQUE (tenant_id, interface_name)
);

-- ============================================================
-- デモ用初期データ
-- ============================================================

-- テナント
INSERT INTO tenants (tenant_id, name, [plan]) VALUES
    (N'T-001', N'デモ環境A（食品卸）', N'demo'),
    (N'T-002', N'デモ環境B（食材メーカー）', N'demo');

-- 顧客
INSERT INTO customers (customer_id, tenant_id, name, short_name, email, default_route, default_carrier, delivery_lead_time) VALUES
    (N'C-001', N'T-001', N'ビストロ青葉', N'青葉', NULL, N'北関東便', N'自社便',     N'翌日'),
    (N'C-002', N'T-001', N'炭火焼鳥とり善', N'とり善', NULL, N'西日本便', N'芦川便',     N'中1日'),
    (N'C-003', N'T-001', N'洋食キッチンつばめ', N'つばめ', NULL, N'中部便',   N'自社便',     N'翌日'),
    (N'C-004', N'T-001', N'鮨処みなと', N'みなと', NULL, N'九州便',   N'自社便',     N'当日'),
    (N'C-005', N'T-001', N'カフェ森ノ音', N'森ノ音', NULL, N'北海道便', N'芦川便',     N'中1日'),
    (N'C-006', N'T-001', N'中華食堂龍華', N'龍華', NULL, N'東北便',   N'自社便',     N'中2日'),
    (N'C-007', N'T-001', N'イタリア食堂イルソーレ', N'イルソーレ', NULL, N'関東便',   N'自社便',     N'翌日'),
    (N'C-008', N'T-001', N'レストラン花水木', N'花水木', NULL, N'関西便',   N'芦川便',     N'中1日'),
    (N'C-009', N'T-001', N'和食処こまち', N'こまち', NULL, N'中国便',   N'自社便',     N'当日'),
    (N'C-010', N'T-001', N'ベーカリー麦の庭', N'麦の庭', NULL, N'四国便',   N'自社便',     N'中2日'),
    (N'C-011', N'T-001', N'株式会社Zennハッカソン', N'Zenn社', N'ikirisa1234@aibaske1103gmail.onmicrosoft.com', N'北関東便', N'自社便', N'翌日');

-- 商品
INSERT INTO products (product_id, tenant_id, name, default_unit, temperature_zone, is_variable_weight, price_per_unit) VALUES
    (N'P-001', N'T-001', N'りんご', N'箱', N'冷蔵', 0, NULL),
    (N'P-002', N'T-001', N'バナナ', N'kg', N'常温', 0, NULL),
    (N'P-003', N'T-001', N'みかん', N'個', N'冷凍', 0, 400),
    (N'P-004', N'T-001', N'ぶどう', N'房', N'常温', 0, 1000),
    (N'P-005', N'T-001', N'もも', N'箱', N'冷蔵', 1, 7200),
    (N'P-006', N'T-001', N'いちご', N'パック', N'常温', 0, 633),
    (N'P-007', N'T-001', N'メロン', N'玉', N'冷凍', 0, NULL),
    (N'P-008', N'T-001', N'スイカ', N'個', N'常温', 0, NULL),
    (N'P-009', N'T-001', N'梨', N'個', N'冷蔵', 0, NULL),
    (N'P-010', N'T-001', N'マンゴー', N'個', N'冷凍', 0, NULL),
    (N'P-011', N'T-001', N'キウイ', N'個', N'常温', 0, NULL),
    (N'P-012', N'T-001', N'さくらんぼ', N'パック', N'冷蔵', 0, NULL),
    (N'P-013', N'T-001', N'いちじく', N'箱', N'冷凍', 0, NULL),
    (N'P-014', N'T-001', N'レモン', N'個', N'常温', 0, NULL),
    (N'P-015', N'T-001', N'アボカド', N'個', N'冷蔵', 0, NULL),
    (N'P-016', N'T-001', N'にんにく', N'kg', N'常温', 0, NULL),
    (N'P-017', N'T-001', N'ブルーベリー', N'箱', N'冷凍', 0, NULL);

-- 在庫
INSERT INTO inventory (tenant_id, product_id, quantity, unit) VALUES
    (N'T-001', N'P-001', 50, N'箱'),
    (N'T-001', N'P-002', 200, N'kg'),
    (N'T-001', N'P-003', 500, N'個'),
    (N'T-001', N'P-004', 30, N'房'),
    (N'T-001', N'P-005', 40, N'箱'),
    (N'T-001', N'P-006', 100, N'パック'),
    (N'T-001', N'P-007', 15, N'玉'),
    (N'T-001', N'P-008', 10, N'個'),
    (N'T-001', N'P-009', 60, N'個'),
    (N'T-001', N'P-010', 25, N'個'),
    (N'T-001', N'P-011', 80, N'個'),
    (N'T-001', N'P-012', 45, N'パック'),
    (N'T-001', N'P-013', 20, N'箱'),
    (N'T-001', N'P-014', 70, N'個'),
    (N'T-001', N'P-015', 30, N'個'),
    (N'T-001', N'P-016', 50, N'kg'),
    (N'T-001', N'P-017', 15, N'箱');

-- 配送ルート
INSERT INTO delivery_routes (route_id, tenant_id, name, region, carriers) VALUES
    (N'R-001', N'T-001', N'北関東便', N'北関東', N'自社便'),
    (N'R-002', N'T-001', N'西日本便', N'西日本', N'芦川便'),
    (N'R-003', N'T-001', N'中部便', N'中部', N'自社便'),
    (N'R-004', N'T-001', N'九州便', N'九州', N'自社便'),
    (N'R-005', N'T-001', N'北海道便', N'北海道', N'芦川便,冷蔵ヤマト便,冷凍ヤマト便'),
    (N'R-006', N'T-001', N'東北便', N'東北', N'自社便,冷凍ヤマト便'),
    (N'R-007', N'T-001', N'関東便', N'関東', N'自社便'),
    (N'R-008', N'T-001', N'関西便', N'関西', N'芦川便'),
    (N'R-009', N'T-001', N'中国便', N'中国', N'自社便'),
    (N'R-010', N'T-001', N'四国便', N'四国', N'自社便'),
    (N'R-011', N'T-001', N'沖縄便', N'沖縄', N'芦川便'),
    (N'R-012', N'T-001', N'北陸便', N'北陸', N'自社便');
