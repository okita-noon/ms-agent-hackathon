-- 008-add-dashboard-vegetable-products.sql
-- Dashboard DB: トマト/キャベツ/卵を追加し、在庫とエイリアスを整備する

SET NOCOUNT ON;

DECLARE @tenant_id NVARCHAR(50) = N'T-001';

-- 1) products を upsert（存在すれば有効化・基本属性更新）
MERGE products AS target
USING (
    SELECT N'P-101' AS product_id, N'トマト' AS name, N'kg' AS default_unit, N'常温' AS temperature_zone UNION ALL
    SELECT N'P-102' AS product_id, N'キャベツ' AS name, N'kg' AS default_unit, N'常温' AS temperature_zone UNION ALL
    SELECT N'P-103' AS product_id, N'卵'     AS name, N'ダース' AS default_unit, N'冷蔵' AS temperature_zone
) AS src
ON target.tenant_id = @tenant_id
AND target.name = src.name
WHEN MATCHED THEN
    UPDATE SET
        target.default_unit = src.default_unit,
        target.temperature_zone = src.temperature_zone,
        target.active = 1,
        target.updated_at = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (
        product_id,
        tenant_id,
        name,
        default_unit,
        temperature_zone,
        is_variable_weight,
        active,
        created_at,
        updated_at
    )
    VALUES (
        src.product_id,
        @tenant_id,
        src.name,
        src.default_unit,
        src.temperature_zone,
        0,
        1,
        SYSUTCDATETIME(),
        SYSUTCDATETIME()
    );

-- 2) inventory を upsert（指定数量で反映）
;WITH stock(name, quantity, unit) AS (
    SELECT N'トマト',  CAST(1000.0 AS DECIMAL(12,3)), N'kg' UNION ALL
    SELECT N'キャベツ', CAST(1000.0 AS DECIMAL(12,3)), N'kg' UNION ALL
    SELECT N'卵',      CAST(1000.0 AS DECIMAL(12,3)), N'ダース'
)
UPDATE i
SET
    i.quantity = s.quantity,
    i.unit = s.unit,
    i.updated_at = SYSUTCDATETIME()
FROM inventory i
INNER JOIN products p
    ON p.product_id = i.product_id
   AND p.tenant_id = i.tenant_id
INNER JOIN stock s
    ON s.name = p.name
WHERE i.tenant_id = @tenant_id
  AND i.warehouse IS NULL;

;WITH stock(name, quantity, unit) AS (
    SELECT N'トマト',  CAST(1000.0 AS DECIMAL(12,3)), N'kg' UNION ALL
    SELECT N'キャベツ', CAST(1000.0 AS DECIMAL(12,3)), N'kg' UNION ALL
    SELECT N'卵',      CAST(1000.0 AS DECIMAL(12,3)), N'ダース'
)
INSERT INTO inventory (tenant_id, product_id, quantity, unit, reserved_qty, warehouse, updated_at)
SELECT
    @tenant_id,
    p.product_id,
    s.quantity,
    s.unit,
    0,
    NULL,
    SYSUTCDATETIME()
FROM stock s
INNER JOIN products p
    ON p.tenant_id = @tenant_id
   AND p.name = s.name
WHERE NOT EXISTS (
    SELECT 1
    FROM inventory i
    WHERE i.tenant_id = @tenant_id
      AND i.product_id = p.product_id
      AND i.warehouse IS NULL
);

-- 3) product_aliases を追加（既存は重複回避）
;WITH aliases(product_name, alias_name) AS (
    SELECT N'トマト', N'とまと' UNION ALL
    SELECT N'トマト', N'TOMATO' UNION ALL
    SELECT N'トマト', N'tomato' UNION ALL
    SELECT N'キャベツ', N'きゃべつ' UNION ALL
    SELECT N'キャベツ', N'きゃべつ' UNION ALL
    SELECT N'キャベツ', N'CABBAGE' UNION ALL
    SELECT N'キャベツ', N'cabbage' UNION ALL
    SELECT N'卵', N'たまご' UNION ALL
    SELECT N'卵', N'タマゴ' UNION ALL
    SELECT N'卵', N'EGG' UNION ALL
    SELECT N'卵', N'egg'
)
INSERT INTO product_aliases (tenant_id, product_id, alias_name)
SELECT DISTINCT
    @tenant_id,
    p.product_id,
    a.alias_name
FROM aliases a
INNER JOIN products p
    ON p.tenant_id = @tenant_id
   AND p.name = a.product_name
WHERE NOT EXISTS (
    SELECT 1
    FROM product_aliases pa
    WHERE pa.tenant_id = @tenant_id
      AND pa.product_id = p.product_id
      AND pa.alias_name = a.alias_name
);
