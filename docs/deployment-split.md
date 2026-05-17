# デプロイ分割設計

チーム開発時の待ち時間と影響範囲を小さくするため、デプロイ対象を API・Frontend・Docs の3系統に分ける。

## 方針

| 対象 | 配置先 | 主な担当 | トリガー |
|---|---|---|---|
| API | Azure Container Apps | エンジニア | `src/**`, `Dockerfile`, `requirements.txt` |
| Frontend | Azure Storage Static Website | 画面・文言担当 | `frontend/**` |
| Docs | GitHub Pages | ドキュメント・審査資料担当 | `docs/**`, `mkdocs.yml` |

## URL構成

| 種別 | URL |
|---|---|
| API | `https://ca-api-orderai-dev.thankfulstone-903cb4eb.japaneast.azurecontainerapps.io` |
| Frontend | `https://storderaidev.z11.web.core.windows.net/dashboard/` |
| Docs | GitHub Pages |

Frontend は `/dashboard/` 配下に配置し、既存の認証リダイレクトURIや画面導線を維持する。

## GitHub Actions

| Workflow | 役割 |
|---|---|
| `.github/workflows/deploy-api.yml` | APIイメージのビルド、ACR push、Container Apps更新、ヘルスチェック |
| `.github/workflows/deploy-frontend.yml` | React/Viteのlint・build、Storage Static Websiteへのアップロード |
| `.github/workflows/docs.yml` | MkDocs build、GitHub Pagesデプロイ |

## 環境変数

### API

| 変数 | 用途 |
|---|---|
| `FRONTEND_ORIGINS` | CORS許可オリジン。例: `https://storderaidev.z11.web.core.windows.net` |
| `FRONTEND_URL` | APIルートレスポンスなどで参照するFrontend URL |

### Frontend

| 変数 | 用途 |
|---|---|
| `VITE_API_BASE_URL` | APIのベースURL |
| `VITE_ENTRA_CLIENT_ID` | Microsoft Entra ID アプリケーションID |
| `VITE_ENTRA_TENANT_ID` | Microsoft Entra ID テナントID |

`VITE_ENTRA_CLIENT_ID` と `VITE_ENTRA_TENANT_ID` は GitHub Repository Variables として設定する。

## 注意点

- Frontendだけの修正では API コンテナを再デプロイしない。
- Docsだけの修正では API・Frontendを再デプロイしない。
- API と Frontend が別オリジンになるため、API側で `FRONTEND_ORIGINS` を設定する。
- Microsoft Entra ID のリダイレクトURIに Frontend URL `/dashboard/` を追加する。
