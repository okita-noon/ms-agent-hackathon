# CLAUDE.md

## プロジェクト概要
Microsoft Agent Hackathon 2026 参加プロジェクト（チーム: ASKNOI_AI木曜会）。
業務課題を解決するAgentic AIをAzure上で開発する。

## 締切
- 提出締切: 2026-06-01
- 審査期間: 2026-06-02 ~ 2026-06-18（この間デプロイ状態を維持）

## 技術要件（ハッカソンルール）
- 【必須】Azure実行基盤（App Service / Container Apps / Functions等）またはCopilot Studio
- 【必須】Microsoft AI技術1つ以上（Azure OpenAI / Semantic Kernel / AI Agent Service等）
- 【推奨】Cosmos DB, GitHub Copilot, Entra ID

## セキュリティ
- 秘密情報は `.env` で管理し、絶対にコミットしない
- pre-commit フックが `.githooks/` に設定済み
- 非エンジニアメンバーもいるため、SECURITY.md を参照すること
