# プロジェクト進捗状況

> 最終更新: 2026-06-01（電話・メール注文の既存受注変更処理を修正）

## 実装済み

### インフラ（Azure）
- [x] Bicep テンプレート（13モジュール）作成・デプロイ済み
- [x] Azure SQL スキーマ + デモデータ投入済み（7テーブル）
- [x] Cosmos DB データベース + コンテナ作成済み（5コンテナ）
- [x] Key Vault シークレット設定済み（8件）
- [x] Container Apps 環境変数注入済み
- [x] GitHub Actions CI/CD パイプライン構築済み
- [x] サービスプリンシパル `github-orderai-deploy` 作成済み

### バックエンド
- [x] データモデル（9 Pydantic モデル：order, customer, product, picking, intelligence, inbound, message_history, session, tenant）
- [x] Connector インターフェース（7 Protocol）
- [x] Cosmos DB アダプタ（受注・セッション・メッセージ履歴・パターン学習）
- [x] Azure SQL アダプタ（顧客・在庫）
- [x] Azure AI Search アダプタ（商品マスタ検索。`ja.microsoft` アナライザーで漢字↔かな↔ローマ字の表記ゆれに対応。`AI_SEARCH_ENDPOINT`/`AI_SEARCH_KEY` 未設定時は SQL LIKE にフォールバック）
- [x] Semantic Kernel Plugin（Intake・Inventory・Exception・Communication）
- [x] Agent 定義 + Orchestrator（gpt-5.4-mini 連携）
- [x] LINE Webhook ハンドラ（署名検証・セッション管理・会話履歴保存）
- [x] 電話 Webhook ハンドラ（ACS Call Automation・音声認識・TTS応答）
- [x] 電話番号取得前のデモ受注API（`POST /api/phone-demo/message`、音声認識済みテキストをPhoneチャネル処理へ注入）
- [x] Phone Order Agent による電話同期応答（注文抽出 + `IInventoryService.check` の同期在庫確認 + 在庫OK時の同期受注保存 + 20秒タイムアウト時フォールバック）
- [x] 電話チャネルの音声応答では受注Noを読み上げないように変更。内部APIレスポンスの `order_id` は維持し、ダッシュボード連携・ログ用途は継続
- [x] 電話・メールチャネルで既存受注への数量変更を新規注文として保存しないよう修正。例: `ORD-E35B0ECE` のりんご10箱を5箱へ変更する発話では、既存受注を更新し在庫引当差分を解除
- [x] 電話/LINEの在庫問い合わせ応答（受注・引当を行わず `IInventoryService.check` で回答）
- [x] 電話・メールにも LINE と同じ会話分岐を拡張。挨拶・天気の話・感謝だけの発話は `small_talk` として注文抽出前に自然応答し、「今の注文は？」は電話・メールでも未配送受注サマリを返す。メールは直近会話履歴を Orchestrator に渡して確認待ち文脈を維持
- [x] チャネル×ユーザー単位の非同期ロック（並行処理の安全性）
- [x] Learning Service（パターン記録・プロファイル更新）
- [x] テナント解決サービス（LINE/電話→テナント紐付け）
- [x] 認証（ID/パスワード + Microsoft SSO、HttpOnly CookieでJWT発行）
- [x] FastAPI アプリ（REST API 30+ エンドポイント：認証・受注・在庫・顧客・Agent・LINE Tester・電話発注 等）
- [x] 受注→会話セッション紐付け（Order.session_id）
- [x] 会話メッセージ取得API（`GET /api/orders/{id}/messages`）
- [x] 会話履歴を全チャネルで保存（`src/services/message_history_logger.py` で共通化）。従来 LINE のみだった `message-history` への保存を**メール・電話**にも拡張。メールは受注を会話セッションに紐付ける `session_id` も付与し、ダッシュボードの受注詳細でメール／電話のやり取りも表示可能に
- [x] 受注ステータス分離（未処理 / 要対応 の自動判定）
- [x] LINE返信ポリシー（会社名呼びかけ・汎用締め文の抑制、配達日/配達時間の確認）
- [x] Dashboard Agent サービス（Exception Triage：Z-score 数量異常 / 単位異常 / 在庫不足 / 要対応）
- [x] Resolution Agent プレビュー API（推奨アクション・顧客向け文面・確認待ち）
- [x] `/api/agent/features`, `/api/agent/exceptions`, `/api/agent/resolutions/preview` の REST API
- [x] 受注ステータスを5種に整理（要対応 / 受注済み / 配送中 / 完了 / キャンセル）。旧 `未処理`・`製造` は `受注済み`、旧 `配送` は `配送中`、旧 `返信待ち` は `要対応` に統合・自動マッピング（#64）
- [x] Dashboard Agent の Exception Triage と受注一覧フィルタで、Cosmos DB に残る旧 `返信待ち` ステータスも `要対応` として取得
- [x] 受注メモ欄（`Order.memo`）と更新 API `PUT /api/orders/{order_id}/memo`（#69）
- [x] 顧客に納品グループ（`Customer.delivery_lead_time` = 当日 / 翌日 / 中1日 / 中2日）を追加。SQL スキーマも `infra/sql/003-add-delivery-lead-time.sql` で拡張（#65）
- [x] 配送予定日の自動確定（顧客リードタイム・締め時間・定休日・臨時休業を考慮）。幅でなく確定日を受注確定メッセージに含める（#82）
- [x] 休眠顧客への販促営業メッセージ自動送信サービス（`src/services/dormant_customer_service.py`）。テンプレート3パターン × 変数埋め込み、LINE プッシュ・メール両チャネル対応、dry_run 可。テンプレートは `_templates/` で外部管理
- [x] メールチャネル（Graph API Webhook）で注文メールを受信・AI処理・自動返信（`src/services/email_handler.py`）
- [x] メール返信をビジネスメール形式に整形。テンプレート（`_templates/メール返信_*.txt`）+ 設定JSON（`_templates/メール設定.json`）で管理。署名・件名ルールを設定JSONに一元化
- [x] 受注No をメール本文（`ご注文を承りました。（受注No: ORD-xxx）`）と件名（`Re: 件名 【受注No: ORD-xxx】`）に自動付与
- [x] 未登録メールアドレスのデモモード（`EMAIL_DEMO_MODE=true` + `EMAIL_DEMO_CUSTOMER_ID` で切替可能。既存の未登録対応は維持）
- [x] メールデモモードの顧客名フォールバック修正（`InboundMessage.customer_name` 追加。Intake Agentに顧客情報を直接渡し、未登録メールでも「None様」ではなくフォールバック顧客名を表示）
- [x] テナント会社名を「AINOKハッカソン食品株式会社」に統一（テナント設定・Agent定義・メール署名設定）
- [x] デモ用顧客 C-011（株式会社Zennハッカソン）追加。未登録メールのデフォルトフォールバック先
- [x] LINE 返信テンプレート基盤（`_templates/line/` + `line_template_renderer.py`）を追加。LINE では受注Noを表示せず、定型返信を優先
- [x] LINE の現在注文コンテキスト（`current_order_id` / `current_order_snapshot`）をセッションとオーケストレータに追加。1顧客1オープン注文前提で追加・変更・取消へ寄せる
- [x] LINE の欠品返信後に、需要把握用の `要対応` 受注を次メッセージの現在注文として扱わないよう修正。バナナ・桃など後続の新規注文が直前の欠品注文へ混入しないようにし、顧客が明示した単位（例: `1個`, `1kg`, `一キロ`）を保持しつつ内部処理は商品マスタ単位へ正規化、換算が業務推測になる場合は確認待ちにする補正と、確認待ち単品への数量だけ返信を LLM なしで反映する処理を追加
- [x] LINE/メール/電話の在庫不足提示後、顧客が「どうしても」「なんとか」「至急」など強要望を示した場合の分岐（B-15）。`OrderIntent.INSIST_ON_SHORTAGE` をルール＋LLMで分類し、元の希望数量で `要対応` 注文を作成、テンプレ `stock_shortage_escalate.txt` で「担当者が手配可能か確認のうえ折り返します」と返す
- [x] 受注作成時の業務日をJST基準に統一。Container Apps のUTC日付に引きずられて、JST深夜帯の注文が前日扱いになる問題を修正
- [x] 注文・在庫・意図分類の業務サービス層（`OrderApplicationService`, `InventoryApplicationService`, `OrderMemoryService`, `IntentUnderstandingService`）を追加。自然文キャンセル、LLM Intent による曖昧キャンセル分類、在庫不足後の数量だけ返信（例:「じゃあ1kg」）、LINE/メール/電話の「いつもの」「前と同じ」注文復元をテスト付きで対応
- [x] 既存受注データのJST日付補正スクリプト（`scripts/fix_order_dates_jst.py`）を追加。dry-runで差分確認後、`--apply` でCosmos DBの `order_date` と同日自動設定の `delivery_date` / `preparation_date` を補正可能
- [x] Cosmos DB 本番デモデータの未来日受注（`DEMO-20260527-*`）を2026-05-26基準へ補正し、再投入用シードJSONも同様に更新
- [x] 受注ステータス更新 API `PUT /api/orders/{order_id}/status`（要対応→受注済み等、完了/キャンセル状態への戻し以外を許可、SSE `order_updated` を発火）
- [x] LINE/メール未登録ユーザーからの受信時に新規顧客を自動作成（`ICustomerRepository.create` で SQL に即時登録、LINE は `line_user_id`・メールは `email` を紐付け）
- [x] LINE Tester ページ（`/line-tester`）：ブラウザ上で LINE チャネルと同じ処理パスを通せるテスト画面。アクセスコード認証・顧客選択・デバッグログ表示付き
- [x] セルフ登録 API `POST /api/auth/register`（`REGISTRATION_ENABLED=true` + `X-Invite-Token` ヘッダ必須）
- [x] Graph API メール Webhook の subscription 自動作成（`lifespan` でアプリ起動時に登録、`GET /api/email-webhook` でサブスクリプション検証に対応）
- [x] Cosmos セッション検索で期限切れメール/LINE/電話セッションを再利用しないよう修正。`expires_at` を見て `active` / `awaiting_reply` を絞り込み、古い確認待ち文脈に新規注文が巻き込まれる問題を防止
- [x] ダッシュボード SPA 配信（`/dashboard/{path}` でフロントエンド HTML を返却、Container Apps 単体でもダッシュボードにアクセス可能）

### フロントエンド
- [x] ダッシュボード（React + Vite + Tailwind）
  - ログイン画面（ID/パスワード + Microsoft SSO）
  - サイドバーナビゲーション（受注・在庫・顧客・電話発注）
  - 受注一覧テーブル（日付選択・ステータスバッジ・温度帯表示）
  - 受注一覧の最終処理時刻表示
  - 受注ステータスは5種類（要対応 / 受注済み / 配送中 / 完了 / キャンセル）。旧ステータスは表示時に自動正規化
  - 受注詳細モーダル（注文会話履歴チャット表示・メモ編集欄付き）
  - Dashboard Agent サイドパネル（Exception Case 一覧・Resolution プレビュー・推奨アクション表示・表示切り替え）。日付絞り込みなしでも、現在の受注一覧ページ範囲に合わせて例外を表示
  - 顧客一覧（常設編集ボタン・納品グループ列）
  - 顧客編集モーダル（納品グループ選択追加）
  - プロフィールドロップダウン（ログアウト）
  - プロフィールアイコンの表示名フォールバックと、デモユーザー表示名補正SQLを追加
  - API未接続時のデモデータフォールバック
  - デモ顧客名を法人記号形式から飲食店・レストラン想定の店舗名へ更新
  - ログイン画面用の濃色ロゴを追加し、白背景でも `foogent` が読めるように改善
  - JWT保存をlocalStorageからHttpOnly Cookieへ移行。`/api/auth/me` でログイン状態を復元し、API呼び出しは `credentials: include` でCookie認証
  - Microsoft SSO のMSALキャッシュを `sessionStorage` に変更し、ブラウザ永続ストレージに認証トークンを残さない方針へ寄せた
  - プライベートウィンドウ向けに Bearer トークンフォールバックを追加。`/api/auth/login` `/api/auth/microsoft` のレスポンス body に `access_token` を含め、フロントは `sessionStorage` に保存し以後 `Authorization: Bearer` で併送。Cookie がブロックされる環境（クロスサイト 3rd-party Cookie）でも SSO 後にダッシュボードへ遷移できる。バックエンドの `get_current_user` は Authorization → Cookie の順で参照（既存）。SSE (`/api/orders/events`) は `EventSource` 仕様上 Authorization を付けられないため、プライベートでは購読不可（手動再取得は可）
  - Microsoft SSO の `loginRedirect` に OIDC `max_age=28800`（8時間）を付与。最後の Entra 認証から 8 時間以上経過した状態でログインボタンを押すと、Entra が再認証（必要なら MFA 含む）を強制する。設定値は `frontend/src/auth/AuthContext.tsx` の `MS_LOGIN_MAX_AGE_SECONDS` 定数
  - 受注一覧にSSEライブ更新を追加。`/api/orders/events` をCookie認証で購読し、新着・更新イベント受信時に一覧とDashboard Agentパネルを再取得、新着行を一時ハイライト
  - 電話発注（Web）ページ（`/web-phone`）：Azure Speech SDK（STT）+ Azure Speech REST API（TTS）による電話発注デモ。顧客選択ドロップダウンで発注元を指定可能。Agent処理・在庫確認・受注保存は実際の電話チャネルと同一コードパスを使用し、ACS電話番号取得後はそのまま本番電話受注に切替可能
  - ダッシュボードの日付初期値・前日/翌日移動・デモデータ日付をJST基準に統一し、受注日/配送日フィルターのUTCずれを解消
  - Dashboard Agent の `foogent ai` ラベル表記と折り返しを調整
  - 電話発注（Web）の通話 ID 表示をユーザー向け画面から非表示化
  - 電話発注（Web）の発信時に短いコール音を追加し、音声入力ボタンの文言を電話デモ向けに調整
  - 電話発注（Web）の説明文を審査員向けに変更し、内部情報寄りのターン数・音声基盤注記を非表示化
  - 電話発注（Web）の会話タイムラインで、受注確定・要対応のシステム表示から受注IDを非表示化
  - 電話発注（Web）の自由テキスト入力欄を復活。音声入力・定型文ボタンと併用できるように整理
  - 電話発注（Web）のAI応答待ち中に「AIが注文内容を確認しています...」をタイムラインへ表示し、無音待機中でも処理状況が伝わるよう改善
  - 電話発注（Web）のテスト用テンプレート（Quick Messages）を大幅拡充。通常発注・追加変更・全体取消・リピート・在庫代替・曖昧例外の6カテゴリに整理し、切り替え用タブUIを導入してテストしやすさを向上
  - 受注詳細の注文会話履歴で、電話チャネルも受注側メッセージが右側に揃うよう表示を統一
  - ログイン画面のサブコピーを「受注業務をスマートに」に変更
  - Dashboard Agent の「要対応」案件に「対応済みにする」2タップ式ボタンを追加（ExceptionModal フッター + 受注詳細モーダルの StatusBadge 下）。表示条件は **注文の `status == 要対応`**（needs_review に限らず、同一注文に紐づく在庫不足・数量異常などの例外を選択中でも表示）。押下するとステータスを「受注済み」に更新し、SSE 経由で例外パネルから当該注文の要対応タグ起因の案件が消える
  - セキュリティ上の理由でログイン画面のヘルプペインから「🔑 デモアカウント」コピー欄、フォーム下部の「🎮 デモでログイン」ボタン、`DEMO_EMAIL`/`DEMO_PASSWORD` 定数を削除。併せて DB（Azure SQL `users` テーブル）の `U-DEMO` / `demo@foogent.example.com` レコードも削除し、`scripts/seed_users.py` の `DEMO_USERS` から該当エントリを除外（マイグレーション: `infra/sql/008-remove-demo-user.sql`）
  - サイドバーがページスクロールで流れる問題を修正（`fixed` ポジション化）
  - ブラウザタブのタイトルを「受注業務をスマートに」に変更
  - 受注詳細UIから未使用の「手配日」フィールドを削除
  - 在庫一覧ページ（`/inventory`）
  - 要対応ステータスの受注行を薄赤ハイライト表示
  - 新着受注トースト通知（SSE 経由で自動表示）

### CI/CD
- [x] `deploy-api.yml`: main push → ACR Build → Container Apps Deploy → Health Check
- [x] `deploy-frontend.yml`: main push → Vite Build → Storage Static Website Upload
- [x] `test.yml`: PR → ruff check/format + pytest

## デモデータ（Azure SQL 投入済み）

### テナント

| tenant_id | 名称 | プラン |
|---|---|---|
| T-001 | AINOKハッカソン食品（旧: デモ環境A・食品卸） | demo |
| T-002 | デモ環境B（食材メーカー） | demo |

### 顧客（T-001 配下・11社）

| customer_id | 会社名 | 略称 | 配送ルート | 運送便 | リードタイム | 備考 |
|---|---|---|---|---|---|---|
| C-001 | 株式会社A | A社 | 北関東便 | 自社便 | 翌日 | |
| C-002 | 株式会社B | B社 | 西日本便 | 芦川便 | 中1日 | |
| C-003 | 株式会社C | C社 | 中部便 | 自社便 | 翌日 | |
| C-004 | 株式会社D | D社 | 九州便 | 自社便 | 当日 | |
| C-005 | 株式会社E | E社 | 北海道便 | 芦川便 | 中1日 | |
| C-006 | 株式会社F | F社 | 東北便 | 自社便 | 中2日 | |
| C-007 | 株式会社G | G社 | 関東便 | 自社便 | 翌日 | |
| C-008 | 株式会社H | H社 | 関西便 | 芦川便 | 中1日 | |
| C-009 | 株式会社I | I社 | 中国便 | 自社便 | 当日 | |
| C-010 | 株式会社J | J社 | 四国便 | 自社便 | 中2日 | |
| C-011 | 株式会社Zennハッカソン | Zenn社 | 北関東便 | 自社便 | 翌日 | メールデモモードのフォールバック先（`EMAIL_DEMO_CUSTOMER_ID=C-011`） |

### 商品（T-001 配下・19品）

| product_id | 商品名 | 単位 | 温度帯 | 在庫数 |
|---|---|---|---|---|
| P-001 | りんご | 箱 | 冷蔵 | 50 |
| P-002 | バナナ | kg | 常温 | 200 |
| P-003 | みかん | 個 | 冷凍 | 500 |
| P-004 | ぶどう | 房 | 常温 | 30 |
| P-005 | もも | 箱 | 冷蔵 | 40 |
| P-006 | いちご | パック | 常温 | 100 |
| P-007 | メロン | 玉 | 冷凍 | 15 |
| P-008 | スイカ | 個 | 常温 | 10 |
| P-009 | 梨 | 個 | 冷蔵 | 60 |
| P-010 | マンゴー | 個 | 冷凍 | 25 |
| P-011 | キウイ | 個 | 常温 | 80 |
| P-012 | さくらんぼ | パック | 冷蔵 | 45 |
| P-013 | いちじく | 箱 | 冷凍 | 20 |
| P-014 | レモン | 個 | 常温 | 70 |
| P-015 | アボカド | 個 | 冷蔵 | 30 |
| P-016 | にんにく | kg | 常温 | 50 |
| P-017 | ブルーベリー | 箱 | 冷凍 | 15 |
| P-018 | キャベツ | kg | 常温 | 500 |
| P-019 | 卵 | ダース | 冷蔵 | 100 |
| P-020 | トマト | kg | 常温 | 1000 |

### 配送ルート（T-001 配下・12路線）

| route_id | ルート名 | 地域 | 運送便 |
|---|---|---|---|
| R-001 | 北関東便 | 北関東 | 自社便 |
| R-002 | 西日本便 | 西日本 | 芦川便 |
| R-003 | 中部便 | 中部 | 自社便 |
| R-004 | 九州便 | 九州 | 自社便 |
| R-005 | 北海道便 | 北海道 | 芦川便,冷蔵ヤマト便,冷凍ヤマト便 |
| R-006 | 東北便 | 東北 | 自社便,冷凍ヤマト便 |
| R-007 | 関東便 | 関東 | 自社便 |
| R-008 | 関西便 | 関西 | 芦川便 |
| R-009 | 中国便 | 中国 | 自社便 |
| R-010 | 四国便 | 四国 | 自社便 |
| R-011 | 沖縄便 | 沖縄 | 芦川便 |
| R-012 | 北陸便 | 北陸 | 自社便 |

## 未実装（残タスク）

### Must（デモ必須）

| タスク | 優先度 | 見積もり | 備考 |
|---|---|---|---|
| LINE E2Eテスト | 高 | 1h | LINE Developers Console でWebhook URL設定後、実際のLINEメッセージで動作確認 |
| テナント切り替えデモ | 中 | 1h | T-001/T-002 の切り替えUI + `tenant_resolver.py` の複数テナント対応 |

> **以下は実装済み（旧 Must）**:
> - ~~顧客の LINE User ID 紐付け~~ → LINE/メール未登録ユーザーの自動顧客作成で解決
> - ~~Orchestrator の Agent 呼び出し改善~~ → マルチ Agent チェーン実装済み（`USE_MULTI_AGENT=true`）
> - ~~Learning Service 非同期実行~~ → 注文確定後に `record_pattern` + `update_customer_profile` を呼び出し済み

### Should

| タスク | 見積もり | 備考 |
|---|---|---|
| Embedding ベースのパターン検索 | 2h | `cosmos_intelligence_store.py` の `find_pattern_by_embedding` を AI Search ベクトル検索に置換 |
| ピッキングリストPDF生成 | 2h | `src/models/picking.py` のモデルは定義済み。PDF生成ロジック + API エンドポイント追加 |

### Could

| タスク | 見積もり | 備考 |
|---|---|---|
| pytest テストスイート拡充 | 2h | 基本テストはCI済み。E2E・統合テストの追加 |
| 管理コンソール | 4h | テナント設定・商品マスタ編集UI |

## 既知の問題

1. **SMTP経由のメール送信がGmailでSPAM判定される場合がある**: Container Appsは `EMAIL_EXTERNAL_ROUTE_MODE=smtp_first` でSMTP優先送信済み。SMTP送信自体は成功するが、Gmailがスパム判定することがある。原因候補: subscription大量蓄積（73件→1件に整理済み）で短期間に大量通知が発生しレピュテーション低下、またはメール本文に「None様」等の不自然な表現が含まれている点
2. **Graph webhook subscriptionの蓄積**: subscriptionを作成するだけで削除しない運用だったため73件まで蓄積し、1通のメールに対して数十回webhookが発火していた。2026-05-24に全削除→1件に整理済み。subscription更新ジョブの自動化は未実装
3. **Dockerfileに `_templates/` のCOPY漏れ**: メールテンプレート外部化（#113）後、`COPY _templates/ _templates/` がDockerfileに含まれておらず、メール返信時にFileNotFoundErrorが発生していた。#115で修正済み
4. **~~メールテンプレートの顧客名がNone表示~~（修正済み）**: `InboundMessage.customer_name` を追加し、デモモードフォールバック時にも顧客名を正しく設定。Intake Agentに `known_customer_id` / `known_customer_name` として渡すことで解決
5. **SQL アダプタの `product_aliases` 運用未反映**: `SqlProductMaster.fuzzy_match` は `product_aliases` テーブルも検索する。`infra/sql/005-add-product-aliases.sql` を追加済みだが、各環境DBへの適用は別途実施が必要
6. **`aioodbc` の ODBC ドライバ**: Dockerfile で `msodbcsql18` をインストールしているが、SQL接続文字列のフォーマットが `pymssql` 形式（Key Vault格納値）。Container Apps 上での `aioodbc` 接続は未テスト。問題があれば `pymssql` ベースのアダプタに差し替える
7. **Container Apps のスケール設定**: APIは min=1, max=5 で常時1台を維持するよう設定済み（2026-05-24適用）。アイドル課金は月$5〜10程度だが、コールドスタートを完全に回避できる
8. **LINE reply token の有効期限**: LINE の `replyToken` は30秒で失効。Agent処理に時間がかかる場合は `push` メッセージにフォールバックする必要がある
9. **`infra/modules/functions.bicep`**: Azure Functions は不使用（VM quota制約で断念）。ファイルは残存しているが `main.bicep` からの参照は削除済み

## ローカル開発

```bash
# 環境変数（.env に設定）
COSMOS_CONNECTION_STRING=...
SQL_CONNECTION_STRING=...
AZURE_OPENAI_ENDPOINT=https://ai-orderai-dev2.openai.azure.com/
AZURE_OPENAI_KEY=...
LINE_CHANNEL_ID=...
LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...

# 起動
pip install -r requirements.txt
uvicorn src.api.main:app --reload --port 8080

# Docker ビルド（amd64）
docker buildx build --platform linux/amd64 -t orderai-api:latest -f Dockerfile .

# ACR にプッシュ
az acr login --name acrorderaidev2
docker tag orderai-api:latest acrorderaidev2.azurecr.io/orderai-api:latest
docker push acrorderaidev2.azurecr.io/orderai-api:latest

# Container Apps 更新
az containerapp update --name ca-api-orderai-dev2 --resource-group rg-orderai-dev2 --image acrorderaidev2.azurecr.io/orderai-api:latest
```

## デモシナリオ（ハッカソン審査用）

`docs/mvp-scope.md` のシナリオ1〜4を実演:

1. **通常注文**: LINEで「りんご10箱、バナナ20kg」→ 自動受注確定 → ダッシュボードに即反映
2. **曖昧表現の学習**: 初回「ツナ缶100g」→ 確認質問 → 2回目以降は自動解釈
3. **誤発注検知**: 「トマト150kg」（普段15kg）→ 異常検知 → 確認質問
4. **いつもの注文**: 「いつものお願い」→ 学習済みパターンで自動確定
