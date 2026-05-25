-- ============================================================
-- 004: デモユーザーの表示名補正
-- ============================================================
-- 既存デモ環境で display_name が未設定または '?' のまま残っている場合に、
-- 右上プロフィールアイコンへ有効な頭文字が出るよう補正する。

UPDATE users
   SET display_name = CASE user_id
       WHEN N'U-001' THEN N'丸山 太郎'
       WHEN N'U-002' THEN N'丸山 花子'
       WHEN N'U-003' THEN N'鈴木 一郎'
       WHEN N'U-004' THEN N'鈴木 次郎'
       ELSE display_name
   END,
       updated_at = SYSUTCDATETIME()
 WHERE user_id IN (N'U-001', N'U-002', N'U-003', N'U-004')
   AND (display_name IS NULL OR LTRIM(RTRIM(display_name)) IN (N'', N'?'));
GO
