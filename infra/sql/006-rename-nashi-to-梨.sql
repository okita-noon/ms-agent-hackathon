-- 商品名「なし」を「梨」に変更
-- 「なし」は否定語と紛らわしいため正式名称に統一
UPDATE products SET name = N'梨' WHERE product_id = N'P-009' AND tenant_id = N'T-001';
UPDATE products SET display_name = N'梨' WHERE product_id = N'P-009' AND tenant_id = N'T-001' AND display_name = N'なし';
