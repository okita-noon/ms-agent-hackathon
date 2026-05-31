-- トマトを商品マスタと在庫に追加（幕張: 2026-05-31）

SET NOCOUNT ON;

DECLARE @tenant_id NVARCHAR(50) = N'T-001';

-- products: 既存レコードがあればスキップ（重複防止）
IF NOT EXISTS (
    SELECT 1 FROM products
    WHERE tenant_id = @tenant_id AND name = N'トマト'
)
BEGIN
    INSERT INTO products (product_id, tenant_id, name, default_unit, temperature_zone, is_variable_weight, price_per_unit)
    VALUES (N'P-020', @tenant_id, N'トマト', N'kg', N'常温', 0, NULL);
END

-- inventory: 対応する在庫行がなければ追加
INSERT INTO inventory (tenant_id, product_id, quantity, unit, reserved_qty)
SELECT @tenant_id, p.product_id, 1000, N'kg', 0
FROM products p
WHERE p.tenant_id = @tenant_id
  AND p.name = N'トマト'
  AND NOT EXISTS (
      SELECT 1 FROM inventory i
      WHERE i.tenant_id = @tenant_id AND i.product_id = p.product_id
  );

-- product_aliases: 表記ゆれ対応
;WITH aliases(alias_name) AS (
    SELECT N'とまと' UNION ALL
    SELECT N'TOMATO' UNION ALL
    SELECT N'tomato'
)
INSERT INTO product_aliases (tenant_id, product_id, alias_name)
SELECT DISTINCT @tenant_id, p.product_id, a.alias_name
FROM aliases a
CROSS JOIN products p
WHERE p.tenant_id = @tenant_id
  AND p.name = N'トマト'
  AND NOT EXISTS (
      SELECT 1 FROM product_aliases pa
      WHERE pa.tenant_id = @tenant_id
        AND pa.product_id = p.product_id
        AND pa.alias_name = a.alias_name
  );
