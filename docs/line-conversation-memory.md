# LINE会話履歴参照設計

> LINEから届いた短文返信や省略表現を、直近の会話履歴、確認待ち注文ドラフト、現在注文スナップショットを参照して処理するための設計。

## 背景

LINE Messaging API は、ユーザーがメッセージを送るたびに Webhook event を送る。
過去トーク履歴を後からまとめて取得する前提ではなく、受信したメッセージをアプリ側で保存し、
次回の Agent 呼び出し時に必要な履歴だけを渡す。

## 業務前提

この設計は、次の業務前提に基づく。

1. **1顧客につき、配送完了まで開いている注文は1件**
2. 配送完了前に届く注文系 LINE は、基本的に **現在注文の更新依頼**
3. LINE では受注Noを顧客へ出さず、内部では `current_order_id` で管理する

このため、会話履歴は「どの注文を作るか」以上に、
**いま開いている注文をどう更新するか** を解釈するために使う。

## 対応方針

- LINE Webhook 受信時に user message を Cosmos DB `message-history` に保存する。
- Agent 返信後に assistant message も同じ履歴に保存する。
- 次回メッセージ処理時に、同じ `tenant_id + channel + channel_user_id` の直近履歴を取得する。
- 同時に、顧客の **現在注文（open order）** を解決する。
- `OrderOrchestrator` には以下を渡す。
  - 現在のメッセージ
  - 直近の会話履歴
  - `order-sessions.pending_order_draft`
- `current_order`
- 顧客に配送完了前の現在注文がある場合は、`current_order_id` / `current_order_snapshot` も渡す。
- Agent prompt では、省略表現や確認返信を会話履歴、pending draft、現在注文から解釈するよう明示する。
- `OK` / `それでお願いします` などの明確な肯定返信は、pending draft から直接受注確定できる。
- `白菜も追加で` / `卵だけなしで` のような差分依頼は、現在注文を基準に更新として扱う。
- 顧客に編集可能な現在注文がある間は、商品名だけの短文も **追加依頼** とみなす。
- 顧客に現在注文がない場合だけ、新規注文として扱う。

## 解釈ルール

会話履歴と現在注文は、次の優先順で解釈する。

1. **pending draft がある**  
   → まず確認中の内容に対する肯定 / 否定 / 修正として解釈する
2. **pending draft はないが current_order がある**  
   → 現在注文への追加 / 変更 / キャンセルとして解釈する
3. **pending draft も current_order もない**  
   → 新規注文または問い合わせとして解釈する

つまり、MVP では **同じ顧客の注文系 LINE を複数注文へ振り分けない**。

## 処理フロー

```text
LINE Webhook
  → webhookEventId で重複排除
  → active / awaiting_reply session を取得
  → 顧客の現在注文（open order）を解決
  → message-history から直近20件を取得
  → user message を message-history に保存
  → OrderOrchestrator.process_order_message()
       - conversation_history
       - pending_order_draft
       - current_order
  → Agent処理
       - pending draft 確定
       - 現在注文更新
       - 現在注文なしの場合のみ新規注文作成
  → assistant reply を message-history に保存
  → awaiting_reply の場合 pending_order_draft / pending_action_type を session に保存
  → 確定更新の場合 current_order_snapshot を更新
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

`order-sessions` には、確認待ちだけでなく現在注文の参照情報も保持する。

```json
{
  "current_order_id": "ORD-20260525-001",
  "current_order_editable": true,
  "current_order_snapshot": {
    "status": "受注済み",
    "items": [
      {"product_name": "りんご", "quantity": 10, "unit": "箱"}
    ]
  },
  "pending_action_type": "update"
}
```

`pending_action_type` は少なくとも次を持てるようにする。

- `new_order`
- `add_item`
- `change_item`
- `partial_cancel`
- `full_cancel`
- `change_delivery`

## できるようになること

- 「それでOK」「1個で」「お願いします」のような確認返信を処理できる。
- 「白菜も追加で」「さっきのトマトは15kgに変更」などの省略表現を Agent が参照できる。
- 「現在注文は1件」という業務前提のもとで、LINE を新規注文より更新依頼に寄せて扱える。
- LINE再送や一時障害時も、`webhookEventId` と履歴IDの冪等保存で重複に強くなる。

## 今後の改善

- pending draft への差分変更を構造的に適用する。
- current order に対する一部キャンセル / 全体キャンセルをより deterministic に扱う。
- 会話履歴の要約を保存して、長い会話でも prompt を肥大化させない。
- 顧客別の「直近注文」「前回注文」と会話履歴を分離して Agent に渡す。
- ダッシュボードで会話履歴を受注詳細から確認できるようにする。
