-- 在庫リセット（テスト・デモ用）
-- りんご(P-001)は欠品のまま、スイカ/メロン/さくらんぼは在庫不足テスト用に少数、他は潤沢に
-- reserved_qty も全てリセット

UPDATE inventory SET quantity = 0,   reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-001'; -- りんご: 欠品のまま
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-002'; -- バナナ
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-003'; -- みかん
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-004'; -- ぶどう
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-005'; -- もも
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-006'; -- いちご
UPDATE inventory SET quantity = 1,    reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-007'; -- メロン: 少数（在庫不足テスト用）
UPDATE inventory SET quantity = 1,    reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-008'; -- スイカ: 少数（在庫不足テスト用）
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-009'; -- 梨
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-010'; -- マンゴー
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-011'; -- キウイ
UPDATE inventory SET quantity = 1,    reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-012'; -- さくらんぼ: 少数（在庫不足テスト用）
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-013'; -- いちじく
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-014'; -- レモン
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-015'; -- アボカド
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-016'; -- にんにく
UPDATE inventory SET quantity = 1000, reserved_qty = 0 WHERE tenant_id = 'T-001' AND product_id = 'P-017'; -- ブルーベリー
