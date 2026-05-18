# CLAUDE.md

@AGENTS.md
@STATUS.md

## Claude Code 固有の設定

### 初回確認事項
- `STATUS.md` で現在の進捗と残タスクを確認する
- 実装前に該当する `docs/` 配下の設計ドキュメントを必ず読む

### ワークフロー
- Connector Interface を変更する場合、既存の全Adapterへの影響を確認する
- Agent（Plugin）からDB/APIを直接呼ばない。必ず `TenantContext.get_connector("I...名")` 経由
- 新しいPluginを追加したら `src/agents/orchestrator.py` の `_build_kernel()` に登録する
- 新しいAdapterを追加したら `src/connectors/adapters/registry.py` に登録する
- REST APIを追加したら `AGENTS.md` のAPIエンドポイント表を更新する

### デプロイ
- `main` ブランチへ push すると GitHub Actions で自動デプロイされる
- 手動デプロイ: `docker buildx build --platform linux/amd64` → ACR push → `az containerapp update`
- Container Apps の環境変数は `az containerapp update --set-env-vars` で設定済み
- 新しい環境変数を追加する場合は Container Apps にも設定すること

### コミット
- pre-commit フック有効（`git config core.hooksPath .githooks`）
- `.env` や秘密情報を含むファイルは絶対にコミットしない
- `infra/main.json` は ARM テンプレート出力なのでコミット不要

### テスト
- `pytest` で実行
- Connector のテストはインターフェースに対して書く（アダプタ実装に依存しない）
- Agent のテストは Semantic Kernel のモック機能を使用
- ダッシュボードは `https://ca-api-orderai-dev.thankfulstone-903cb4eb.japaneast.azurecontainerapps.io/dashboard/` で動作確認

### フロントエンド UI 変更時のルール（必須）
UI を変更したら **毎回** 以下を行うこと:
1. ローカルで dev server を起動してスクリーンショットを撮影する
2. 撮影したスクリーンショット画像をユーザーに提示してレビューしてもらう
