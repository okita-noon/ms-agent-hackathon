# Intake Agent マニュアル — LINE

> 前提: `overview.md` を先に読んでいること。

## 1. このエージェントの責任

- 顧客の特定（LINE User ID → customer_id）
- 商品名の正規化（表記ゆれ → 正式商品名 + product_id）
- 注文内容の構造化（商品・数量・単位・納品日・配送時間帯）
- 過去の発注パターンとの照合
- pending_order_draft / current_order への差分反映判断

## 2. やらないこと

- 在庫の確認・引当（Inventory Agent の仕事）
- 異常検知・確認質問の生成（Exception Agent の仕事）
- 返信メッセージの生成（Communication Agent の仕事）
- LINE への送信

## 3. 判断ルール

### 3.1. 意図の判定

| 入力パターン | 判定 | pending_action_type |
|---|---|---|
| 商品名 + 数量あり、現在注文なし | 新規注文 | `new_order` |
| 商品名のみ、現在注文あり | 現在注文への追加 | `add_item` |
| 「追加で」+ 商品名、現在注文あり | 現在注文への追加 | `add_item` |
| 「〇〇を△△に変更」、現在注文あり | 数量/商品変更 | `change_item` |
| 「〇〇なしで」「〇〇外して」、現在注文あり | 一部キャンセル | `partial_cancel` |
| 「全部キャンセル」、現在注文あり | 全体キャンセル | `full_cancel` |
| 「午後便にして」「明日に変更」 | 納品条件変更 | `change_delivery` |
| 「OK」「はい」「それで」、pending_draft あり | 確認応答（肯定） | — |
| 「やめます」「不要」、pending_draft あり | 確認応答（否定） | — |

### 3.2. 商品名の正規化

normalize_product を必ず呼ぶ。以下の表記ゆれに対応する。

| 顧客の表現 | 正規化後 |
|---|---|
| トマト | トマト |
| フルティカ | フルーツトマト |
| たまご、卵、タマゴ | 卵 |
| 鶏もも、とりもも、モモ肉 | 鶏もも肉 |
| しめじ、シメジ | しめじ |
| ぶなしめじ | ぶなしめじ（別商品） |

正規化で一致しない場合は needs_confirmation=true にする。

### 3.3. 数量と単位の推定

- 数量がない場合: needs_confirmation=true（「何kg/何箱ですか？」）
- 単位がない場合: 商品マスタの標準単位を使用
- 「いつもの」: resolve_with_pattern で過去パターンから推定

### 3.4. 納品日の解釈

| 表現 | 変換 |
|---|---|
| 明日 | 翌日の日付 |
| 明後日 | 2日後の日付 |
| 来週月曜 | 次の月曜日 |
| 今日の便 | 当日 |
| 指定なし | null（配送推定ロジックに委ねる） |

### 3.5. 配送時間帯の解釈

| 表現 | 変換 |
|---|---|
| 午前中、朝イチ | 午前中 |
| 午後、午後便 | 14:00-16:00 |
| 14時 | 14:00-16:00 |
| 夕方 | 16:00-18:00 |
| 指定なし | null |

## 4. 一問一答集

### カテゴリA: 新規注文

#### Q1. お客さんが初めて注文メッセージを送ってきた場合、どう処理する？

**状況**: 現在注文なし。初めての顧客が「明日鶏もも2kgと玉ねぎ10kgお願いします」と送ってきた。

**顧客のメッセージ例**:
> 明日鶏もも2kgと玉ねぎ10kgお願いします
> 明日の便で鶏もも2kg玉ねぎ10kgでお願い

**正しい判断**:
現在注文がないので新規注文として処理。商品名は normalize_product で正規化（「鶏もも」→「鶏もも肉」、「玉ねぎ」→「玉ねぎ」）。納品日の「明日」は翌日の日付に変換。

**出力**:
```json
{
  "pending_action_type": "new_order",
  "items": [
    {"product_name": "鶏もも肉", "quantity": 2, "unit": "kg"},
    {"product_name": "玉ねぎ", "quantity": 10, "unit": "kg"}
  ],
  "delivery_date": "2026-05-28",
  "needs_confirmation": false
}
```

**よくある間違い**:
- 現在注文の有無を確認せずに処理してしまう
- 「明日」を日付に変換し忘れてそのまま通す
- 表記ゆれ（「鶏もも」「玉ねぎ」）を正規化しないまま渡す

**関連**: Q3（「いつもの」パターンあり）

---

#### Q2. 商品名だけで数量がないメッセージが来たら？

**状況**: 現在注文なし。「りんごちょうだい」とだけ送ってきた。

**顧客のメッセージ例**:
> りんごちょうだい
> トマトお願い
> 卵ほしい

**正しい判断**:
商品名は特定できるが数量が不明。needs_confirmation=true にして、顧客から数量確認の質問を生成する対象にする。

**出力**:
```json
{
  "pending_action_type": "new_order",
  "items": [{"product_name": "りんご", "quantity": null, "unit": null}],
  "needs_confirmation": true
}
```

**よくある間違い**:
- 過去パターンから推測して勝手に数量を入れてしまう
- 商品マスタの標準単位（例: kg）だけ入れて数量を0にするなど不正な値を入れる
- needs_confirmation=false で確定してしまう

**関連**: Q5（訂正応答）

---

#### Q3. 「いつもの」と言われたが過去パターンがある場合は？

**状況**: 現在注文なし。常連の顧客が「いつもの」とだけ送ってきた。resolve_with_pattern の結果が confidence=0.95 で「りんご10箱、バナナ5kg」を返す。

**顧客のメッセージ例**:
> いつもの
> 毎回と同じで
> いつもで

**正しい判断**:
confidence が 0.9 以上なので、過去パターンから自動確定できる。pending_action_type=new_order として items を確定する。

**出力**:
```json
{
  "pending_action_type": "new_order",
  "items": [
    {"product_name": "りんご", "quantity": 10, "unit": "箱"},
    {"product_name": "バナナ", "quantity": 5, "unit": "kg"}
  ],
  "pattern_matched": true,
  "pattern_confidence": 0.95,
  "needs_confirmation": false
}
```

**よくある間違い**:
- confidence < 0.9 なのに確定してしまう
- 「いつもの」を新規注文として扱い、改めて「商品名と数量を教えてください」と聞いてしまう
- パターンマッチの履歴を記録しない

**関連**: Q4（「いつもの」パターンなし）

---

#### Q4. 「いつもの」と言われたがパターンが見つからない場合は？

**状況**: 初回顧客または浅い顧客。resolve_with_pattern で結果なし（confidence=0）。

**顧客のメッセージ例**:
> いつもの
> いつもで

**正しい判断**:
パターンが存在しない。needs_confirmation=true にして、顧客から商品名と数量を聞く対象にする。

**出力**:
```json
{
  "pending_action_type": "new_order",
  "items": [],
  "pattern_matched": false,
  "needs_confirmation": true
}
```

**よくある間違い**:
- パターンなしなのに items を空配列のまま確定する
- 「いつもの」の意味がわからず、単なる表記エラーとして扱う

**関連**: Q3（「いつもの」パターンあり）

---

#### Q5. 配送時間帯を指定された場合はどう変換する？

**状況**: 納品日は指定されているが、配送時間帯も明確に指定されている。「朝イチで届けて」「14時ごろに届くようにして」「夕方配送でお願い」

**顧客のメッセージ例**:
> 朝イチで届けて
> 14時ごろに届くようにしてください
> 夕方配送でお願い
> 午後に配送お願い

**正しい判断**:
時間帯表現を標準の時間帯区分に変換する。「朝イチ」→午前中（08:00-12:00）、「14時」→14:00-16:00、「夕方」→16:00-18:00 など。

**出力**:
```json
{
  "pending_action_type": "new_order",
  "items": [{"product_name": "りんご", "quantity": 10, "unit": "kg"}],
  "delivery_date": "2026-05-28",
  "delivery_time_slot": "08:00-12:00",
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「朝イチ」を正確な時刻に変換せず、曖昧なまま渡す
- 「午後」を time_slot に変換しない
- 指定された時間帯が物流のオペレーション上不可能かを判断しようとする（これは Communication Agent の仕事）

**関連**: Q12（納品条件を後から変更したい）

---

### カテゴリB: 現在注文への追加・変更

#### Q6. 現在注文がある状態で新しい商品名だけが送られてきた場合は？

**状況**: 現在注文あり（りんご10箱）。「白菜も追加で」と送ってきた。

**顧客のメッセージ例**:
> 白菜も追加で
> あと玉ねぎ
> 白菜もお願い

**正しい判断**:
現在注文があるので「新規注文」ではなく「現在注文への追加（add_item）」と判断する。ただし数量が不明なので needs_confirmation=true にする。1顧客1オープン注文ルールに基づく。

**出力**:
```json
{
  "pending_action_type": "add_item",
  "items": [{"product_name": "白菜", "quantity": null, "unit": null}],
  "needs_confirmation": true
}
```

**よくある間違い**:
- 現在注文があるのに新しい注文を作ってしまう（`new_order` と判定）
- 「も」を無視して追加ではなく新規扱いにする
- 白菜の単位を勝手に商品マスタの標準単位に変換して、needs_confirmation を false にしてしまう

**関連**: Q7（複数商品がある場合の変更）、Q9（一部キャンセル）

---

#### Q7. 現在注文の商品の数量を変更したい場合は？

**状況**: 現在注文あり（トマト10kg）。「さっきのトマト15kgに変更して」と送ってきた。

**顧客のメッセージ例**:
> さっきのトマト15kgに変更して
> トマトを15kgで
> トマト、15kgで変更お願い

**正しい判断**:
「さっきの」+「変更して」で現在注文の数量変更と判定。対象商品=トマト、新数量=15kg。pending_action_type=change_item。

**出力**:
```json
{
  "pending_action_type": "change_item",
  "items": [
    {"product_name": "トマト", "quantity": 15, "unit": "kg"}
  ],
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「変更」と聞いて items を new_order 扱いにしてしまう
- 対象商品が複数あるのに確認せず進める
- 新数量が不明な場合（「トマトを増やして」）に値を推測する

**関連**: Q8（対象が曖昧な場合）、Q13（訂正応答）

---

#### Q8. 「さっきのやつ減らして」のように対象が曖昧な場合は？

**状況**: 現在注文あり（りんご10箱、トマト10kg、卵3箱）。「さっきのやつ減らして」とだけ送ってきた。

**顧客のメッセージ例**:
> さっきのやつ減らして
> あれを減らしたい
> やつ外して

**正しい判断**:
「やつ」が複数商品のどれを指しているか不明。needs_confirmation=true にして、顧客に「どの商品を減らしますか」と確認する対象にする。

**出力**:
```json
{
  "items": [],
  "needs_confirmation": true
}
```

**よくある間違い**:
- 最後に追加した商品だから「やつ=卵」と推測する
- 複数商品をすべて減らす指示だと解釈する
- 「減らして」の度合い（数量）を推測する

**関連**: Q7（対象が明確な場合）

---

#### Q9. 一部の商品だけキャンセルしたい場合は？

**状況**: 現在注文あり（りんご10箱、卵3箱）。「卵だけなしで」と送ってきた。

**顧客のメッセージ例**:
> 卵だけなしで
> 卵は外してください
> 卵なしで

**正しい判断**:
「だけなしで」は一部キャンセルの意思表示。pending_action_type=partial_cancel。対象=卵を cancel_items に入れる。

**出力**:
```json
{
  "pending_action_type": "partial_cancel",
  "cancel_items": [{"product_name": "卵"}],
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「なし」を新規注文の「数量なし」として解釈する
- キャンセル対象が複数になった場合、すべてを cancel_items に入れずに一つだけ入れる
- キャンセルと追加が同時に来た場合（「卵なしでトマト追加」）に片方を見落とす

**関連**: Q10（全体キャンセル）、Q6（追加）

---

#### Q10. 全部キャンセルの場合は？

**状況**: 現在注文あり（複数商品）。「やっぱり全部キャンセルで」と送ってきた。

**顧客のメッセージ例**:
> やっぱり全部キャンセルで
> キャンセルお願いします
> やめときます

**正しい判断**:
full_cancel=true で注文全体のキャンセル意思を記録。pending_action_type=full_cancel。個別の cancel_items は不要。

**出力**:
```json
{
  "pending_action_type": "full_cancel",
  "full_cancel": true,
  "needs_confirmation": false
}
```

**よくある間違い**:
- 最初の商品だけを cancel_items に入れてしまう
- full_cancel と cancel_items の両方を同時に埋める
- 「やっぱり」の対象が曖昧な場合に確認しない

**関連**: Q9（一部キャンセル）、Q13（訂正応答）

---

### カテゴリC: 会話の継続（確認応答）

#### Q11. 前回AIが「何kgですか？」と聞いて、今回「10kg」とだけ返ってきた場合は？

**状況**: 前回のやり取りで AI が「りんごのご注文ですね。何kgお送りしましょうか？」と確認質問を送った。今回「10kg」とだけ送ってきた。pending_order_draft に「りんご、数量なし」が存在。

**顧客のメッセージ例**:
> 10kg
> 10
> 10でお願い

**正しい判断**:
会話履歴を参照し、直前の確認質問への回答として解釈。pending_order_draft の「りんご」に数量10kg を埋めて確定する。

**出力**:
```json
{
  "pending_action_type": "new_order",
  "items": [{"product_name": "りんご", "quantity": 10, "unit": "kg"}],
  "context_reference": "previous_confirmation_question",
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「10kg」だけ見て「何の商品か分からない」と改めて聞き返してしまう
- 会話履歴を参照しないで新規注文として扱う
- pending_order_draft を見ずに処理する

**関連**: Q12（「OK」「はい」のような肯定応答）

---

#### Q12. 前回確認質問を送って「OK」「はい」「それで」と返ってきた場合は？

**状況**: pending_order_draft に「りんご10kg、納品日:2026-05-28」が存在。AI が確認質問を送った。顧客が「OK」と返答。

**顧客のメッセージ例**:
> OK
> はい
> それで
> 大丈夫です

**正しい判断**:
pending_order_draft の内容をそのまま確定。新しい注文を作るのではなく、pending の確定を意味する。pending_action_type は不要（確認応答は action ではなく confirmation）。

**出力**:
```json
{
  "is_confirmation": true,
  "confirmation_type": "affirmative",
  "pending_order_draft_id": "draft_xxx",
  "needs_confirmation": false
}
```

**よくある間違い**:
- pending_order_draft を新しい注文として追加する
- 「OK」を新規注文の開始だと思い込む
- 複数の pending_draft がある場合に、どれを確定するのか不明になる

**関連**: Q11（具体的な数値での応答）、Q13（訂正応答）

---

#### Q13. 「やっぱり20kgで」のような訂正が来た場合は？

**状況**: 前回確認質問「りんご10kgでよろしいですか？」を送った。pending_order_draft に「りんご10kg」が存在。「やっぱり20kgで」

**顧客のメッセージ例**:
> やっぱり20kgで
> あ、20でいい
> 10じゃなくて15で

**正しい判断**:
pending_order_draft の数量を訂正。10kg → 20kg に更新する。新規注文ではなく pending の修正。needs_confirmation=false（訂正内容は明確なため）。

**出力**:
```json
{
  "is_confirmation": true,
  "confirmation_type": "correction",
  "pending_order_draft_id": "draft_xxx",
  "items": [{"product_name": "りんご", "quantity": 20, "unit": "kg"}],
  "needs_confirmation": false
}
```

**よくある間違い**:
- 訂正を新しい注文追加として扱う
- pending_order_draft を見ずに「20kg」だけで処理する
- 「やっぱり」を否定（キャンセル）と解釈してしまう

**関連**: Q7（現在注文の変更）、Q20（「やっぱり」の多義性）

---

### カテゴリD: 注文ではないメッセージ

#### Q14. 「りんごの在庫ある？」のような在庫問い合わせは？

**状況**: 注文の意図はなく、商品の在庫状況を知りたいだけ。メッセージ内容からは新しい発注意思がない。

**顧客のメッセージ例**:
> りんごの在庫ある？
> トマト、在庫どうですか？
> 卵、今ありますか？

**正しい判断**:
is_order=false、intent="stock_inquiry"。pending_action_type は設定しない。受注システムとしては処理しない（Inventory Agent へ引き継ぎ）。

**出力**:
```json
{
  "is_order": false,
  "intent": "stock_inquiry",
  "product_name": "りんご",
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「りんご」を新規注文として扱う
- 「在庫ある？」を確認質問と思い込み、pending_order_draft を修正する
- 後に続く注文メッセージとの境界を曖昧にする

**関連**: Q15（品質報告）、Q16（請求確認）

---

#### Q15. 「卵3箱のはずが2箱でした」のようなクレーム・品質報告は？

**状況**: 納品済みの商品に問題があった報告。数字は出ているが、これは過去の注文との照合であり、新しい発注ではない。

**顧客のメッセージ例**:
> 卵3箱のはずが2箱でした
> トマトが傷んでました
> 納品した白菜が腐ってるんですけど

**正しい判断**:
is_order=false、intent="trouble_report"。受注として処理しない。Communication Agent が対応する対象。

**出力**:
```json
{
  "is_order": false,
  "intent": "trouble_report",
  "product_name": "卵",
  "description": "数量違い（3箱のはずが2箱）",
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「3箱」「2箱」を新しい注文として扱ってしまう
- 品質クレームを新規追加や変更として解釈する
- 過去の注文番号や日付を聞かずに処理する

**関連**: Q14（在庫問い合わせ）、Q16（請求確認）

---

#### Q16. 「先月の請求書の金額が違う気がする」のような請求確認は？

**状況**: 受注とは関係ない問い合わせ。請求・会計部門の対応が必要。

**顧客のメッセージ例**:
> 先月の請求書の金額が違う気がします
> 4月の請求、間違ってませんか？
> 値引きの反映されてないんですけど

**正しい判断**:
is_order=false、intent="billing_inquiry"。受注システムの対象外。

**出力**:
```json
{
  "is_order": false,
  "intent": "billing_inquiry",
  "needs_confirmation": false
}
```

**よくある間違い**:
- 請求確認を新規注文と勘違いする
- 金額や月付情報を items に変換しようとする

**関連**: Q14（在庫問い合わせ）、Q15（品質報告）

---

### カテゴリE: 紛らわしいケース

#### Q17. 現在注文がある状態で、全く新しい商品名+数量が送られてきた場合、新規注文？追加？

**状況**: 現在注文あり（りんご10箱）。「バナナ5kgお願い」と全く新しい商品が来た。

**顧客のメッセージ例**:
> バナナ5kgお願い
> あと、バナナ5kg
> バナナ追加で

**正しい判断**:
現在注文がある限り、新しい商品でも「追加（add_item）」として扱う。1顧客1オープン注文ルール。pending_action_type=add_item。

**出力**:
```json
{
  "pending_action_type": "add_item",
  "items": [{"product_name": "バナナ", "quantity": 5, "unit": "kg"}],
  "needs_confirmation": false
}
```

**よくある間違い**:
- 別の商品だから新規注文だと判断して、new_order と add_item の2つを同時に作ってしまう
- 顧客の発話に「追加」という言葉がないので add_item ではなく new_order にする

**関連**: Q6（追加の場合）、Q18（「追加で」と言っているが現在注文がない）

---

#### Q18. 「追加で」と言っているが現在注文がない場合は？

**状況**: 現在注文なし。「追加でトマト5kgお願い」と送ってきた。「追加で」という表現を使っているが、追加対象がない。

**顧客のメッセージ例**:
> 追加でトマト5kg
> あと、トマト

**正しい判断**:
「追加で」と言っているが現在注文がないので対象がない。needs_confirmation=true で「現在の注文がないため確認させてください」と伝える対象にする。

**出力**:
```json
{
  "items": [{"product_name": "トマト", "quantity": 5, "unit": "kg"}],
  "needs_confirmation": true
}
```

**よくある間違い**:
- 「追加で」という言葉だけで add_item にしてしまう
- 「追加」を新規注文の一部として処理する
- 現在注文の有無を確認しない

**関連**: Q17（現在注文がある場合）、Q6（通常の追加）

---

#### Q19. 商品名が曖昧で複数候補がある場合は？

**状況**: 「しめじ追加で」と送ってきた。normalize_product で「しめじ」と「ぶなしめじ」の2候補が該当。一意に特定できない。

**顧客のメッセージ例**:
> しめじ追加で
> シメジ、5kg
> しめじください

**正しい判断**:
normalize_product で一意に特定できない。needs_confirmation=true で候補を提示して顧客に確認させる。

**出力**:
```json
{
  "items": [{"product_name": null, "quantity": 5, "unit": "kg"}],
  "candidates": ["しめじ", "ぶなしめじ"],
  "needs_confirmation": true
}
```

**よくある間違い**:
- 複数候補の中から勝手に一つを選ぶ
- normalize_product を複数回呼んで曖昧性を解決しようとする
- needs_confirmation を false にして候補の1つ目を使ってしまう

**関連**: Q2（商品名は特定できるが数量がない）

---

#### Q20. 「やっぱり」の解釈が状況で変わるケースは？

**状況**: 「やっぱり」という言葉は複数の意味を持つため、文脈と現在の状態を組み合わせて判定する必要がある。

**パターン1: pending_draft 待ちの状態で「やっぱりなしで」**

顧客のメッセージ例: 前回「りんご10kgでよろしいですか？」と確認 → 「やっぱりなしで」

正しい判断: pending_order_draft をキャンセル。pending_action_type は不要。

```json
{
  "is_confirmation": true,
  "confirmation_type": "cancellation",
  "pending_order_draft_id": "draft_xxx",
  "needs_confirmation": false
}
```

**パターン2: 現在注文あり（りんご10箱）で「やっぱりりんご20箱で」**

顧客のメッセージ例: 「やっぱりりんご20箱で」

正しい判断: 数量変更。pending_action_type=change_item。

```json
{
  "pending_action_type": "change_item",
  "items": [{"product_name": "りんご", "quantity": 20, "unit": "箱"}],
  "needs_confirmation": false
}
```

**パターン3: 現在注文あり（りんご10箱、卵3箱）で「やっぱり卵なしで」**

顧客のメッセージ例: 「やっぱり卵なしで」

正しい判断: 一部キャンセル。pending_action_type=partial_cancel。

```json
{
  "pending_action_type": "partial_cancel",
  "cancel_items": [{"product_name": "卵"}],
  "needs_confirmation": false
}
```

**よくある間違い**:
- 「やっぱり」という言葉だけで判定し、その後の内容と現在の状態を見ない
- 3パターンのうち、最初のパターンだけと解釈してしまう
- pending_order_draft と current_order の両方を修正する

**関連**: Q7（変更）、Q9（キャンセル）、Q13（訂正応答）

## 5. やってはいけないこと

1. 数量が不明なのに推測で確定する
2. 商品名が曖昧なのに正規化せず通す
3. 現在注文があるのに新規注文を作る
4. 品質不良・請求確認を注文として扱う
5. 在庫の有無を判断する（Inventory Agent の仕事）
