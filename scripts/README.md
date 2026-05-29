# scripts/

運用・開発・QC作業用のスクリプト集。

## 一覧

| スクリプト | 用途 | 対象ストア |
|---|---|---|
| `add_stock/run.py` | 在庫リセット・補充 | Azure SQL |
| `check_stock/run.py` | 在庫チェック・自動補正（`line_qc/run.py` から自動呼び出し） | Azure SQL |
| `line_qc/run.py` | LINE QC 自動実行（事前に在庫チェック・補正を自動実行） | LINE Tester API |
| `seed_orders.py` | デモ受注データ投入 | Cosmos DB |
| `seed_users.py` | デモユーザー投入 | Azure SQL |
| `fix_order_dates_jst.py` | 受注日をJST基準に補正 | Cosmos DB |
| `sync_products_to_search.py` | 商品マスタを AI Search に同期 | Azure SQL → AI Search |
| `new_agent_worktree.sh` | AI エージェント用 git worktree 作成 | ローカル git |

---

## add_stock/run.py — 在庫リセット・補充

テスト前に在庫をデフォルト値に戻す。`DEFAULT_STOCK` でデフォルト値を定義済み。

```bash
# デフォルト設定でリセット（QCテスト前の標準手順）
python scripts/add_stock/run.py

# 全商品を一括で指定数量に設定
python scripts/add_stock/run.py --qty 500

# 特定商品だけ指定数量に更新
python scripts/add_stock/run.py --product P-008 --qty 50

# dry-run（SQL確認のみ・実行しない）
python scripts/add_stock/run.py --dry-run
```

**デフォルト在庫設定**

`check_stock/expected_stock.json` の `min` 値が使われる。設定変更は `expected_stock.json` を編集すること。

| 商品ID | 商品名 | min | max | 備考 |
|---|---|---|---|---|
| P-001 | りんご | 0 | 0 | 欠品テスト用（ケース16）。常に0を維持 |
| P-002 | バナナ | 500 | 1000 | 通常注文用 |
| P-003 | みかん | 500 | 1000 | 通常注文用 |
| P-004 | ぶどう | 500 | 1000 | 通常注文用 |
| P-005 | もも | 500 | 1000 | 通常注文用 |
| P-006 | いちご | 500 | 1000 | 通常注文用 |
| P-007 | メロン | 20 | 20 | 在庫不足テスト用（ケース30: 50個注文→不足→3個で確定） |
| P-008 | スイカ | 30 | 30 | 在庫不足テスト用（ケース4: 50個注文→不足→代替確定） |
| P-009 | 梨 | 10 | 10 | 在庫超過テスト用（ケース35: 100個注文→超過で確定しない） |
| P-010 | マンゴー | 500 | 1000 | 通常注文用 |
| P-011 | キウイ | 500 | 1000 | 通常注文用 |
| P-012 | さくらんぼ | 20 | 30 | 在庫問い合わせテスト用（ケース10） |
| P-013 | いちじく | 500 | 1000 | 通常注文用 |
| P-014 | レモン | 500 | 1000 | 通常注文用 |
| P-015 | アボカド | 500 | 1000 | 通常注文用 |
| P-016 | にんにく | 500 | 1000 | 通常注文用 |
| P-017 | ブルーベリー | 500 | 1000 | 通常注文用 |

**必要な環境変数**（`.env` または `az login` 済みの場合は Key Vault から自動取得）

```
SQL_CONNECTION_STRING=...
```

---

## check_stock/run.py — 在庫チェック・自動補正

`check_stock/expected_stock.json` の min/max と現在の在庫を比較し、範囲外の商品を自動補正する。
`line_qc/run.py` 実行時に自動で呼び出される。

```bash
# チェックのみ（補正しない）
python scripts/check_stock/run.py --dry-run

# チェック＋自動補正
python scripts/check_stock/run.py
```

期待在庫の変更は `check_stock/expected_stock.json` を編集すること。

---

## line_qc/run.py — LINE QC 自動実行

`docs/line_QC.md` の全40ケースを LINE Tester API に対して自動実行し、結果を `docs/line_QC.md` の `4.X` セクションに追記する。詳細ログは `scripts/line_qc/_logs/qc_YYYYMMDD_HHMMSS.json` に保存。

```bash
# 全40ケース実行（QC前に add_stock/run.py で在庫リセット推奨）
python scripts/line_qc/run.py

# 詳細ログ付きで実行
python scripts/line_qc/run.py --verbose

# 指定ケースのみ実行
python scripts/line_qc/run.py --cases 1,3,5

# ローカル環境に向ける
python scripts/line_qc/run.py --base-url http://localhost:8080

# 顧客を全ケース統一指定
python scripts/line_qc/run.py --customer C-001
```

**必要な環境変数**

```
LINE_TESTER_BASE_URL=https://...  # 省略時は dev2 環境
LINE_TESTER_ACCESS_CODE=test      # 省略時は "test"
```

**QCの標準手順**

1. `python scripts/add_stock/run.py` で在庫リセット
2. `python scripts/line_qc/run.py --verbose` で全ケース実行
3. `docs/line_QC.md` の最新 `4.X` セクションで結果確認
4. NG があれば `docs/line_QC.md` の「次回対応事項」と Issue #155 にコメント

---

## seed_orders.py — デモ受注データ投入

Cosmos DB にデモ受注データを投入する。デフォルトは `infra/seed/cosmos-orders-20260523-demo.json`。

```bash
# デフォルトのシードファイルで投入
python scripts/seed_orders.py

# ファイル指定
python scripts/seed_orders.py --file infra/seed/cosmos-orders-20260523-demo.json

# dry-run（件数確認のみ）
python scripts/seed_orders.py --dry-run

# 接続先のコンテナを変更
python scripts/seed_orders.py --database orderai --container orders
```

**必要な環境変数**

```
COSMOS_CONNECTION_STRING=...
```

---

## seed_users.py — デモユーザー投入

Azure SQL にデモユーザー（U-001〜U-004）を投入する。

```bash
DEMO_PASSWORD=yourpassword python scripts/seed_users.py
```

**必要な環境変数**

```
SQL_CONNECTION_STRING=...
DEMO_PASSWORD=...  # デモユーザーの共通パスワード（必須）
```

---

## fix_order_dates_jst.py — 受注日 JST 補正

Container Apps の UTC 環境で作成された受注の `order_date` / `delivery_date` / `preparation_date` を JST 基準に補正する。`--apply` なしは dry-run。

```bash
# dry-run（差分確認のみ）
python scripts/fix_order_dates_jst.py

# 実際に補正を適用
python scripts/fix_order_dates_jst.py --apply

# 期間を絞って実行
python scripts/fix_order_dates_jst.py --created-from 2026-05-01 --created-to 2026-05-31 --apply

# 配送日は補正せず受注日だけ直す
python scripts/fix_order_dates_jst.py --keep-delivery-dates --apply
```

**必要な環境変数**

```
COSMOS_CONNECTION_STRING=...
```

---

## sync_products_to_search.py — AI Search 同期

Azure SQL の `products` テーブル（`product_aliases` も含む）を AI Search の `products` インデックスに一括アップロードする。インデックスは事前に作成が必要。

```bash
# T-001（デフォルト）を同期
python scripts/sync_products_to_search.py

# テナント指定
python scripts/sync_products_to_search.py --tenant-id T-002
```

**インデックス事前作成**

```bash
az rest --method PUT \
  --url "https://<service>.search.windows.net/indexes/products?api-version=2023-11-01" \
  --headers "Content-Type=application/json" "api-key=<key>" \
  --body @infra/search/products-index.json
```

**必要な環境変数**

```
SQL_CONNECTION_STRING=...
AI_SEARCH_ENDPOINT=https://search-orderai-dev.search.windows.net
AI_SEARCH_KEY=...
```

---

## new_agent_worktree.sh — AI エージェント用 worktree 作成

AI エージェント（codex / claude）が独立した git worktree で作業するためのブランチ・worktree を一括作成する。

```bash
# codex 用 worktree を作成
scripts/new_agent_worktree.sh codex login-copy-update

# claude 用 worktree を作成（ベースブランチ指定あり）
scripts/new_agent_worktree.sh claude exception-modal origin/main
```

作成先:
- `.codex/worktrees/<task-slug>` → ブランチ `codex/<task-slug>`
- `.claude/worktrees/<task-slug>` → ブランチ `claude/<task-slug>`
