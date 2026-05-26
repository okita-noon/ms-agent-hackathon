# データフロー詳細

> チャネル別処理フロー・セッション管理・スケール戦略

**MVP方針**: Azure Container Apps に API・Webhook・バックグラウンド処理を統合する。
FastAPI アプリケーションとして LINE Webhook 受信・Agent 呼び出し・Learning Service を
1コンテナで実装し、シンプルに運用する。
ダッシュボードはチーム開発効率のため API コンテナから分離し、Azure Storage Static Website で配信する。
Service Bus はスケール時（本番運用・マルチテナント）に導入する。

## ソフトウェア処理フロー図

![注文受付から返信・ダッシュボード更新までのソフトウェア処理フロー](assets/software-flow.svg)

## LINE チャネル（MVP実装対象）

```
顧客 → LINE メッセージ送信
    → LINE Webhook → Container Apps (FastAPI: POST /api/line-webhook)
    → 署名検証（Channel Secret で HMAC-SHA256）
    → テナントID解決（LINE公式アカウント → テナント紐付け）
    → セッション判定（後述「LINE会話セッション管理」）
        ├─ 既存セッションあり → 該当セッションのAgent Threadに返信を追記
        └─ 新規 → 新しいAgent Thread作成
    → 顧客の現在注文を解決（1顧客1オープン注文）
        ├─ 現在注文なし → 新規注文候補として処理
        ├─ 現在注文あり・編集可 → 同一注文への更新依頼として処理
        └─ 現在注文あり・編集不可 → 自動変更せず要対応へ
    → Orchestrator Agent (Azure AI Agent Service)
        ├→ Intake Agent: 注文解析・顧客特定・現在注文への差分反映・商品正規化
        ├→ [必要に応じて] Exception Agent: 確認質問 / 異常検知
        ├→ Inventory Agent: 在庫照合
        └→ Communication Agent or Template Renderer: 返信生成・LINE送信
             ※ LINE返信はテンプレート優先。受注Noは表示しない
    → Cosmos DB (受注ドキュメント保存)
    → アプリ内イベントブローカーに `order_created` / `order_updated` を publish
    → Dashboard は `GET /api/orders/events` (SSE, Cookie認証) を購読し、イベント受信時に一覧を再取得
    → Learning Service (非同期: パターン記録・プロファイル更新)
    → ダッシュボード更新 (リアルタイム)
```

## メール チャネル（将来実装）

詳細設計と実装タスクは [メールチャネル設計・実装計画](email-channel-design.md) を参照。

```
顧客 → メール送信
    → Microsoft Graph API (Office 365 Change Notifications)
    → Container Apps (通知受信・メール本文取得)
    → テナントID解決（受信アドレス → テナント紐付け）
    → Orchestrator Agent → 各専門Agent
    → Cosmos DB (保存)
    → Azure Communication Services でメール自動返信
    → Learning Service (非同期)
```

## 電話（音声）チャネル（MVP実装対象）

```
顧客 → 電話発信
    → ACS Call Automation (着信受付・音声ストリーム取得)
    → Azure AI Speech (リアルタイム文字起こし)
    → テナントID解決（着信番号 → テナント紐付け）
    → Container Apps
       ├→ Phone Order Agent（注文抽出、電話中の同期応答）
       ├→ IInventoryService.check（Connector経由で同期在庫確認）
       └→ TTSで在庫確認結果を返答（既定20秒でフォールバック）
    → 既存 Orchestrator → 各専門Agent（非同期で正式検証・登録・学習）
    → Cosmos DB (保存) + 担当者ダッシュボードに表示 + SMS通知
    → Learning Service (非同期)
```

電話番号取得前のデモ・統合テストでは、`POST /api/phone-demo/message` に音声認識済みテキストを送る。
このAPIはACSの着信応答・TTS再生だけを省略し、`source=Phone`、電話チャネルのセッション管理、
Phone Order Agent による同期応答、在庫確認、非同期の Orchestrator Agent、Cosmos DB保存、Learning Service まで本番電話フローと同じ経路を通す。
公開環境では `/api/phone-webhook` と同じ `EVENTGRID_WEBHOOK_KEY` による共有鍵検証を必須とする。

電話中の同期AI応答は `PHONE_SYNC_AI_ENABLED` で切り替える。既定では `PHONE_SYNC_AI_TIMEOUT_SECONDS=20` 秒まで待ち、
超過時は「受付済み・確認後登録」のTTSを返し、`PHONE_BACKGROUND_VALIDATION_ENABLED=true` の場合は裏で既存マルチAgent処理を継続する。

「在庫ありますか」のような問い合わせは、受注保存・在庫引当を行わず、商品マスタの正規化後に
`IInventoryService.check` だけを実行して回答する。数量指定がある場合は必要数量に足りるかを答え、
数量指定がない場合は現在の有効在庫数を返す。

## LINE会話セッション管理

確認質問→顧客返信の会話継続と、現在注文への更新依頼を扱うためにセッション管理が必要。
ここで扱うのは「複数注文の並行管理」ではなく、**1顧客1オープン注文** を前提にした
**現在注文の参照と更新文脈の保持** である。
直近会話の保存・Agentへの渡し方は [LINE会話履歴参照設計](line-conversation-memory.md) を参照。

```
セッション管理テーブル（Cosmos DB: order-sessions）

{
  "id": "sess-U1234-20260515-001",
  "tenant_id": "T-001",
  "channel": "line",
  "channel_user_id": "U1234...",        // LINE User ID
  "customer_id": "C-042",
  "current_order_id": "ORD-20260515-001",
  "current_order_snapshot": { ... },
  "current_order_editable": true,
  "agent_thread_id": "thread_abc123",   // Azure AI Agent Service の Thread ID
  "status": "awaiting_reply",           // active / awaiting_reply / completed / expired
  "pending_order_draft": { ... },       // 確認中の注文ドラフト
  "pending_action_type": "update",
  "created_at": "2026-05-15T07:15:00Z",
  "expires_at": "2026-05-15T09:15:00Z", // 2時間でタイムアウト
  "last_message_at": "2026-05-15T07:15:30Z"
}

フロー:
  1. LINE Webhook受信 → channel_user_id + tenant_id でセッション検索
     → customer_id から現在注文を検索
  2. status=awaiting_reply のセッションがある
     → 既存の agent_thread_id に返信を追記
     → Orchestrator Agent が会話を継続（Thread内のコンテキストを保持）
  3. セッションがない or expired
     → 新しいセッション + Agent Thread を作成
     → 現在注文があればその更新として処理開始
     → 現在注文がなければ新規注文として処理開始
  4. 注文確定 / 更新確定
     → current_order_snapshot を更新
     → status=completed に更新
  5. タイムアウト → Container Apps のバックグラウンドタスク（APScheduler）で
     定期的に expired に更新
     → 担当者ダッシュボードに「返信待ちタイムアウト」として通知
```

### LINE 更新判断の要点

MVP では、同じ顧客から配送前に届く注文系メッセージを次のように扱う。

1. 現在注文がなければ **新規注文**
2. 現在注文があれば **同一注文の更新**
3. 現在注文があるが編集不可なら **要対応**

例:

- `白菜も追加で` → 現在注文への追加
- `卵だけなしで` → 現在注文の一部キャンセル
- `さっきのトマト15kgで` → 現在注文の数量変更
- `今日の便を午後で` → 現在注文の納品条件変更

## 受注→会話履歴の紐付け

受注詳細から元の注文会話（LINE/電話でのやり取り）を参照可能にするため、
Order ドキュメントに `session_id` を保持し、MessageHistory との紐付けを行う。

```
Order (Cosmos DB: order-documents)
  ├── session_id: "sess-U1234-20260515001"  ← セッションID（Optional）
  │
  └── → MessageHistory (Cosmos DB: message-history)
        WHERE session_id = @sid ORDER BY created_at ASC
        ├── { role: "user",      text: "りんご10箱お願いします" }
        ├── { role: "assistant", text: "りんご10箱、承りました。..." }
        └── { role: "user",      text: "はい、お願いします" }

API:
  GET /api/orders/{order_id}/messages
    → Order.session_id を取得
    → IMessageHistoryRepository.list_by_session_id() で会話取得
    → role が user/assistant のメッセージのみ返却
    → session_id が null（手入力受注等）の場合は空配列

ダッシュボード表示:
  受注詳細モーダル内にチャット形式で表示
  - user メッセージ: 左寄せ・グレー背景（「お客様」ラベル）
  - assistant メッセージ: 右寄せ・ブランドカラー背景（「AI」ラベル）
```

## 本番スケール時の構成変更

```
MVP構成:
  LINE Webhook → Container Apps (FastAPI) → Orchestrator Agent（直接呼び出し）

本番構成（マルチテナント・高負荷対応時に移行）:
  LINE Webhook → Container Apps → Service Bus (テナント別トピック)
              → Container Apps (別コンテナ/トリガー) → Orchestrator Agent

※ Service Bus を挟むことで:
  ・テナント間の負荷分離（1テナントの大量注文が他テナントに影響しない）
  ・デッドレターキューによる障害時のメッセージ保全
  ・ピーク時のバッファリング（朝の注文集中）
  が実現できる。MVP段階では不要。

※ Container Apps は 1→N のオートスケール対応済み（minReplicas: 1, maxReplicas: 5）。
  審査期間中のログイン後初回API・Webhook応答を安定させるため、APIコンテナを常時1台維持する。
```
