-- ============================================================
-- 003: customers テーブルに納品グループ（delivery_lead_time）追加
-- 「当日」「翌日」「中1日」「中2日」など、受注日から納品日までの
-- リードタイムを顧客ごとに保持する。
-- ============================================================

ALTER TABLE customers
ADD delivery_lead_time NVARCHAR(20) NULL;
GO

-- デモデータ：既存顧客に納品グループを割り当て
UPDATE customers SET delivery_lead_time = N'翌日'  WHERE customer_id IN (N'C-001', N'C-003', N'C-007');
UPDATE customers SET delivery_lead_time = N'中1日' WHERE customer_id IN (N'C-002', N'C-005', N'C-008');
UPDATE customers SET delivery_lead_time = N'当日'  WHERE customer_id IN (N'C-004', N'C-009');
UPDATE customers SET delivery_lead_time = N'中2日' WHERE customer_id IN (N'C-006', N'C-010');
GO
