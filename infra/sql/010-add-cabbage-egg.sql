-- キャベツ・卵を商品マスタと在庫に追加

INSERT INTO products (product_id, tenant_id, name, default_unit, temperature_zone, is_variable_weight, price_per_unit) VALUES
    (N'P-018', N'T-001', N'キャベツ', N'kg', N'常温', 0, NULL),
    (N'P-019', N'T-001', N'卵', N'ダース', N'冷蔵', 0, NULL);

INSERT INTO inventory (tenant_id, product_id, quantity, unit) VALUES
    (N'T-001', N'P-018', 500, N'kg'),
    (N'T-001', N'P-019', 100, N'ダース');
