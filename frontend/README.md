# OrderAI Frontend

React + TypeScript + Vite のダッシュボードです。
API とは別成果物としてビルドし、Azure Storage Static Website のルートに配置します。

## Local development

```bash
npm ci
npm run dev
```

Vite dev server は `/api` を `http://localhost:8080` に proxy します。
ローカルの API 以外へ接続する場合は `.env.local` に設定します。

```bash
VITE_API_BASE_URL=https://ca-api-orderai-dev2.mangoground-6945bb56.japaneast.azurecontainerapps.io
VITE_ENTRA_CLIENT_ID=<client-id>
VITE_ENTRA_TENANT_ID=<tenant-id>
```

## Deployment

`.github/workflows/deploy-frontend.yml` が `frontend/**` の変更だけで起動します。
`npm run build` を実行した後、`storderaidev2` の Static Website ルートにアップロードします。

API URL は workflow の `VITE_API_BASE_URL`、Microsoft Entra ID 設定は GitHub Repository Variables の `VITE_ENTRA_CLIENT_ID` / `VITE_ENTRA_TENANT_ID` で渡します。
