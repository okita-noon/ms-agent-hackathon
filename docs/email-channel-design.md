# メールチャネル設計・実装計画

> Microsoft Graph で受信したメール注文を、既存の LINE / 電話と同じ Orchestrator に流すための設計。

## 目的

食品卸・食材メーカーの受注現場では、LINE や電話に加えてメール注文も残りやすい。
メール対応では、Agent の中核処理を増やすのではなく、入力チャネルを共通形式に正規化して
既存の Intake / Exception / Inventory / Communication / Learning の流れに載せる。

## 基本方針

- 受信は **Microsoft Graph Change Notifications** を使い、メールボックスの新着を検知する。
- 通知 payload だけで処理せず、Graph API で対象メッセージを取得して本文・件名・送信者を正規化する。
- 通知漏れや subscription 失効に備えて、**Delta Query** による定期同期を併用する。
- Agent にはチャネル固有の情報を直接渡さず、`InboundMessage` に変換してから Orchestrator に渡す。
- 返信は初期実装では Graph `sendMail` を優先し、必要に応じて Azure Communication Services Email に差し替える。
- メール原文、HTML本文、添付ファイルは Blob Storage に保存し、監査・再処理に使えるようにする。

## 全体フロー

```text
顧客
  → メール送信
  → Microsoft Graph Change Notification
  → FastAPI: POST /api/email-webhook
  → Graph API で message を取得
  → HTML / quoted text / signature を除去
  → 受信メールアドレスから tenant_id を解決
  → 送信者メールアドレスから customer_id を解決
  → Email Session を検索または作成
  → OrderOrchestrator に InboundMessage を渡す
  → Intake Agent: 注文解析・顧客特定・商品正規化・パターン照合
  → Exception Agent: 曖昧表現・異常数量・添付不足などを判定
  → Inventory Agent: 在庫照合・代替品提案
  → Communication Agent: 確認質問または受注確定メールを生成
  → Cosmos DB: 受注・セッション・処理ログ保存
  → Learning Service: 発注パターン更新
  → Dashboard: source=email として表示
```

## コンポーネント設計

### 1. Graph Webhook

追加エンドポイント:

| メソッド | パス | 用途 |
|---|---|---|
| POST | `/api/email-webhook` | Microsoft Graph Change Notifications 受信 |
| POST | `/api/email-subscriptions/renew` | subscription 更新ジョブ用 |
| POST | `/api/email-sync/delta` | Delta Query による再同期・取りこぼし復旧 |

実装ポイント:

- Graph の validation request に応答する。
- 通知を受けたら即 Agent を呼ばず、対象 message ID を取得して冪等チェックする。
- 同じメール通知が複数回来ても、`tenant_id + graph_message_id` で一度だけ処理する。
- subscription の expiration を保存し、期限前に更新する。
- lifecycle notification を受けた場合は、subscription 再作成または Delta Query 再同期に切り替える。

### 2. メール本文取得・正規化

`EmailIngestionService` を追加する。

責務:

- Graph API から message を取得する。
- HTML本文をテキスト化する。
- 返信引用、署名、免責文、過去スレッドを可能な範囲で除去する。
- 添付ファイルの有無とメタデータを抽出する。
- メール原文・HTML本文・添付ファイルを Blob Storage に保存する。
- 共通入力モデル `InboundMessage` に変換する。

モデル案:

```python
class InboundMessage(BaseModel):
    tenant_id: str
    channel: Literal["line", "phone", "email"]
    channel_user_id: str
    customer_id: str | None = None
    subject: str | None = None
    text: str
    raw_text: str | None = None
    received_at: datetime
    external_message_id: str
    conversation_id: str | None = None
    reply_to_message_id: str | None = None
    attachments: list[InboundAttachment] = []
```

### 3. テナント・顧客解決

メールでは、受信側と送信側の両方を見る。

| 解決対象 | 入力 | 解決先 |
|---|---|---|
| テナント | 受信メールアドレス、メールボックスID、alias | `tenant_id` |
| 顧客 | From アドレス、Reply-To、顧客名候補 | `customer_id` |
| 会話 | Graph `conversationId`、`In-Reply-To`、件名正規化 | `order_session_id` |

追加データ案:

- `tenant_email_routes`
  - `tenant_id`
  - `mailbox_user_id`
  - `email_address`
  - `reply_from_address`
  - `active`
- `customers.email` は既存項目を使う。
- 複数メールアドレス対応が必要なら `customer_email_aliases` を追加する。

### 4. セッション管理

メールの確認質問は、LINE と同じく Cosmos DB `order-sessions` で扱う。

```json
{
  "id": "sess-email-T001-C042-20260517-001",
  "tenant_id": "T-001",
  "channel": "email",
  "channel_user_id": "chef@example.com",
  "customer_id": "C-042",
  "agent_thread_id": "thread_abc123",
  "status": "awaiting_reply",
  "conversation_id": "AAMkAG...",
  "last_external_message_id": "AAMkAG.../messages/123",
  "pending_order_draft": {},
  "expires_at": "2026-05-18T09:00:00Z"
}
```

LINE は短い往復が多いため TTL 2時間でよいが、メールは返信が遅い。
メールセッションは 24-48 時間を初期値にし、テナント設定で変更可能にする。

### 5. Communication Plugin

既存の `Communication Agent` に `send_email` 実装を追加する。

返信ルール:

- 入力チャネルが email の場合、原則 email で返す。
- 確認質問は件名を維持し、本文冒頭に確認内容を明示する。
- 受注確定メールには、商品・数量・納品予定日・不足/代替の有無を含める。
- 人手確認が必要な場合は、顧客へは受付済みメッセージを送り、担当者ダッシュボードに escalated として表示する。

送信方式:

| 方式 | 用途 | 備考 |
|---|---|---|
| Graph `sendMail` | Microsoft 365 メールボックスから返信 | スレッド継続・デモに向く |
| Azure Communication Services Email | アプリ独自送信基盤 | 大量送信・運用分離に向く |

初期実装は Graph `sendMail` を採用する。

### 6. ダッシュボード

受注一覧・詳細に以下を追加する。

- `source=email` バッジ
- 送信者名 / From アドレス
- 件名
- 本文プレビュー
- 添付有無
- 処理状態: `received`, `parsed`, `awaiting_reply`, `confirmed`, `escalated`, `failed`
- 原文表示または Blob への参照

## セキュリティ・運用

- Graph API は最小権限にする。
- Application permissions を使う場合は、対象メールボックスを限定する。
- client secret は Key Vault で管理する。可能なら managed identity / workload identity へ移行する。
- webhook の `clientState` を検証し、想定外通知を拒否する。
- メール本文には個人情報・取引情報が含まれるため、ログには全文を出さない。
- 添付ファイルはサイズ上限・拡張子制限・ウイルススキャン方針を決める。
- 処理失敗時は再試行し、一定回数を超えたら Dashboard に `failed` として表示する。

## 実装タスクリスト

### Phase 1: デモ対応

- [ ] Entra ID アプリ登録を作成する。
- [ ] Graph API 権限 `Mail.Read` / `Mail.Send` を設定する。
- [ ] Graph 接続情報を Key Vault secret と Container Apps 環境変数に追加する。
- [ ] `src/models/inbound.py` に `InboundMessage` / `InboundAttachment` を追加する。
- [ ] `EmailIngestionService` を追加し、Graph message 取得・本文正規化を実装する。
- [ ] `POST /api/email-webhook` を追加し、validation request と通知受信に対応する。
- [ ] 受信メールアドレスから `tenant_id` を解決する処理を `TenantResolver` に追加する。
- [ ] From アドレスから顧客を検索する処理を確認・補強する。
- [ ] `OrderOrchestrator` に email `InboundMessage` を渡す入口を追加する。
- [ ] `CommunicationPlugin.send_email` を実装する。
- [ ] ダッシュボードで `source=email`、件名、送信者、本文プレビューを表示する。
- [ ] HTMLメール、プレーンテキストメール、通常注文メールのテストを追加する。

### Phase 2: 業務品質

- [ ] Graph subscription の作成・更新ジョブを追加する。
- [ ] subscription expiration と deltaLink を Cosmos DB に保存する。
- [ ] Delta Query による取りこぼし復旧を実装する。
- [ ] lifecycle notification に対応する。
- [ ] quoted reply / signature / disclaimer 除去ロジックを強化する。
- [ ] 添付ファイルを Blob Storage に保存する。
- [ ] メール原文と処理ログを紐づけて監査できるようにする。
- [ ] 重複通知の冪等テストを追加する。
- [ ] 確認質問メールへの返信が同一セッションに継続されるテストを追加する。

### Phase 3: マルチテナント運用

- [ ] `tenant_email_routes` を追加する。
- [ ] テナントごとに mailbox / alias / reply_from を設定できるようにする。
- [ ] 顧客の複数メールアドレス対応を追加する。
- [ ] Service Bus 経由でメール処理を非同期化する。
- [ ] Dead Letter Queue と再処理画面を追加する。
- [ ] Application Access Policy などで Graph アクセス範囲をメールボックス単位に制限する。
- [ ] メールテンプレートをテナント別に差し替え可能にする。

## 受け入れ条件

- 顧客がメールで注文すると、Dashboard に `source=email` の受注が作成される。
- メール本文の「鶏もも肉10kg、白菜5ケース」が既存の Intake Agent で構造化される。
- 在庫が十分な場合、自動で受注確定メールが返信される。
- 曖昧な数量・異常数量の場合、確認質問メールが送信される。
- 顧客が確認メールに返信すると、既存セッションに紐づいて処理が継続される。
- 同じ Graph 通知が複数回来ても、受注は重複作成されない。
- Graph subscription が一時失効しても、Delta Query で取りこぼしを復旧できる。
