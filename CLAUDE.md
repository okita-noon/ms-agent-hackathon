# CLAUDE.md

@AGENTS.md

## Claude Code 固有の設定

### ワークフロー
- 実装前に該当する `docs/` 配下の設計ドキュメントを必ず読む
- Connector Interface を変更する場合、既存の全Adapterへの影響を確認する
- Agent（Plugin）からDB/APIを直接呼ばない。必ず Connector Interface 経由にする

### コミット
- pre-commit フック有効（`git config core.hooksPath .githooks`）
- `.env` や秘密情報を含むファイルは絶対にコミットしない

### テスト
- `pytest` で実行
- Connector のテストはインターフェースに対して書く（アダプタ実装に依存しない）
- Agent のテストは Semantic Kernel のモック機能を使用
