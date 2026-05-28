-- 005-add-product-aliases.sql
-- 全商品に対して日本語表記ゆれ（ひらがな/カタカナ/漢字）と英語別名を投入

SET NOCOUNT ON;

DECLARE @tenant_id NVARCHAR(50) = N'T-001';

;WITH aliases(product_id, alias_name) AS (
    SELECT N'P-001', N'りんご' UNION ALL
    SELECT N'P-001', N'リンゴ' UNION ALL
    SELECT N'P-001', N'林檎' UNION ALL
    SELECT N'P-001', N'apple' UNION ALL

    SELECT N'P-002', N'ばなな' UNION ALL
    SELECT N'P-002', N'バナナ' UNION ALL
    SELECT N'P-002', N'banana' UNION ALL

    SELECT N'P-003', N'みかん' UNION ALL
    SELECT N'P-003', N'ミカン' UNION ALL
    SELECT N'P-003', N'蜜柑' UNION ALL
    SELECT N'P-003', N'mandarin' UNION ALL

    SELECT N'P-004', N'ぶどう' UNION ALL
    SELECT N'P-004', N'ブドウ' UNION ALL
    SELECT N'P-004', N'葡萄' UNION ALL
    SELECT N'P-004', N'grape' UNION ALL

    SELECT N'P-005', N'もも' UNION ALL
    SELECT N'P-005', N'モモ' UNION ALL
    SELECT N'P-005', N'桃' UNION ALL
    SELECT N'P-005', N'peach' UNION ALL

    SELECT N'P-006', N'いちご' UNION ALL
    SELECT N'P-006', N'イチゴ' UNION ALL
    SELECT N'P-006', N'苺' UNION ALL
    SELECT N'P-006', N'strawberry' UNION ALL

    SELECT N'P-007', N'めろん' UNION ALL
    SELECT N'P-007', N'メロン' UNION ALL
    SELECT N'P-007', N'melon' UNION ALL

    SELECT N'P-008', N'すいか' UNION ALL
    SELECT N'P-008', N'スイカ' UNION ALL
    SELECT N'P-008', N'西瓜' UNION ALL
    SELECT N'P-008', N'watermelon' UNION ALL

    SELECT N'P-009', N'なし' UNION ALL
    SELECT N'P-009', N'ナシ' UNION ALL
    SELECT N'P-009', N'梨' UNION ALL
    SELECT N'P-009', N'pear' UNION ALL

    SELECT N'P-010', N'まんごー' UNION ALL
    SELECT N'P-010', N'マンゴー' UNION ALL
    SELECT N'P-010', N'芒果' UNION ALL
    SELECT N'P-010', N'mango' UNION ALL

    SELECT N'P-011', N'きうい' UNION ALL
    SELECT N'P-011', N'キウイ' UNION ALL
    SELECT N'P-011', N'kiwi' UNION ALL

    SELECT N'P-012', N'さくらんぼ' UNION ALL
    SELECT N'P-012', N'サクランボ' UNION ALL
    SELECT N'P-012', N'桜桃' UNION ALL
    SELECT N'P-012', N'cherry' UNION ALL

    SELECT N'P-013', N'いちじく' UNION ALL
    SELECT N'P-013', N'イチジク' UNION ALL
    SELECT N'P-013', N'無花果' UNION ALL
    SELECT N'P-013', N'fig' UNION ALL

    SELECT N'P-014', N'れもん' UNION ALL
    SELECT N'P-014', N'レモン' UNION ALL
    SELECT N'P-014', N'檸檬' UNION ALL
    SELECT N'P-014', N'lemon' UNION ALL

    SELECT N'P-015', N'あぼかど' UNION ALL
    SELECT N'P-015', N'アボカド' UNION ALL
    SELECT N'P-015', N'avocado' UNION ALL

    SELECT N'P-016', N'にんにく' UNION ALL
    SELECT N'P-016', N'ニンニク' UNION ALL
    SELECT N'P-016', N'大蒜' UNION ALL
    SELECT N'P-016', N'garlic' UNION ALL

    SELECT N'P-017', N'ぶるーべりー' UNION ALL
    SELECT N'P-017', N'ブルーベリー' UNION ALL
    SELECT N'P-017', N'blueberry'
)
INSERT INTO product_aliases (tenant_id, product_id, alias_name)
SELECT @tenant_id, a.product_id, a.alias_name
FROM aliases a
WHERE NOT EXISTS (
    SELECT 1
    FROM product_aliases pa
    WHERE pa.tenant_id = @tenant_id
      AND pa.product_id = a.product_id
      AND pa.alias_name = a.alias_name
);

