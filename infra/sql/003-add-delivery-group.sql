-- 顧客マスタに納品グループカラムを追加
-- 例: '翌日配送', '中1日', '2日後' など

ALTER TABLE customers ADD delivery_group NVARCHAR(50) NULL;
