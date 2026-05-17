# LINE会話履歴参照設計

> LINEから届いた短文返信や省略表現を、直近の会話履歴と確認待ち注文ドラフトを参照して処理するための設計。

## 背景

LINE Messaging API は、ユーザーがメッセージを送るたびに Webhook event を送る。
過去トーク履歴を後からまとめて取得する前提ではなく、受信したメッセージをアプリ側で保存し、
次回の Agent 呼び出し時に必要な履歴だけを渡す。

## 対応方針

- LINE Webhook 受信時に user message を Cosmos DB `message-history` に保存する。
- Agent 返信後に assistant message も同じ履歴に保存する。
- 次回メッセージ処理時に、同じ `tenant_id + channel + channel_user_id` の直近履歴を取得する。
- `OrderOrchestrator` には以下を渡す。
  - 現在のメッセージ
  - 直近の会話履歴
  - `order-sessions.pending_order_draft`
- Agent prompt では、省略表現や確認返信を会話履歴と pending draft から解釈するよう明示する。
- `OK` / `それでお願いします` などの明確な肯定返信は、pending draft から直接受注確定できる。

## 処理フロー

```text
LINE Webhook
  → webhookEventId で重複排除
  → active / awaiting_reply session を取得
  → message-history から直近20件を取得
  → user message を message-history に保存
  → OrderOrchestrator.process_order_message()
       - conversation_history
       - pending_order_draft
  → Agent処理 / pending draft 確定
  → assistant reply を message-history に保存
  → awaiting_reply の場合 pending_order_draft を session に保存
  → 確定注文の場合 session を completed に更新
```

## 保存データ

Cosmos DB `orders.message-history`:

```json
{
  "id": "hist-sess-U123-user-01H...",
  "tenant_id": "T-001",
  "session_id": "sess-U123-20260517100000",
  "channel": "line",
  "channel_user_id": "U123...",
  "role": "user",
  "text": "それでお願いします",
  "message_id": "LINE message id",
  "webhook_event_id": "01H...",
  "metadata": {},
  "created_at": "2026-05-17T10:00:00Z"
}
```

TTL は初期値30日。長期記憶は会話全文ではなく、確定注文と Learning Service の発注パターンに集約する。

## できるようになること

- 「それでOK」「1個で」「お願いします」のような確認返信を処理できる。
- 「白菜も追加で」「さっきのトマトは15kgに変更」などの省略表現を Agent が参照できる。
- LINE再送や一時障害時も、`webhookEventId` と履歴IDの冪等保存で重複に強くなる。

## 今後の改善

- pending draft への差分変更を構造的に適用する。
- 会話履歴の要約を保存して、長い会話でも prompt を肥大化させない。
- 顧客別の「直近注文」「前回注文」と会話履歴を分離して Agent に渡す。
- ダッシュボードで会話履歴を受注詳細から確認できるようにする。
