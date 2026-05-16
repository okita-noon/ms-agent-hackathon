# 電話チャネル テスト手順書

## 概要

ACS (Azure Communication Services) Call Automation による電話チャネルのテスト方法を3段階で説明する。
実際の電話番号がなくてもテスト可能。

---

## 方法1: ユニットテスト（CI対応・最速）

ACS SDK を全てモックし、イベントハンドリングロジックを検証する。

```bash
# Docker で実行（推奨）
docker run --rm -v "$(pwd):/app" -w /app python:3.12-slim \
  sh -c "pip install -r requirements.txt -q && python -m pytest tests/test_phone_handler.py -v"

# ローカル Python 3.12 がある場合
pytest tests/test_phone_handler.py -v
```

### テストカバレッジ

| テストクラス | 内容 |
|---|---|
| `TestHandleIncomingCall` | 着信応答、CallState 作成、ACS未設定エラー |
| `TestHandleCallConnected` | 挨拶TTS再生、不明な通話の無視 |
| `TestHandleRecognizeCompleted` | 音声テキスト→Agent処理、セッション作成、Agent障害時フォールバック、空音声リトライ |
| `TestHandlePlayCompleted` | 未確定→再認識、確定→切断、最大ターン→切断 |
| `TestHandleRecognizeFailed` | リトライ、最大ターン到達時の終了 |
| `TestHandleCallDisconnected` | CallState削除、セッション更新 |
| `TestOrchestratorCallback` | `response_callback` がLINE送信の代わりに使われることを検証 |

---

## 方法2: シミュレーションスクリプト（統合テスト）

ローカルサーバーに模擬 CloudEvents を POST して、実際のAPIフローを検証する。
ACS SDK の呼び出し（`answer_call`, `play_media` 等）はサーバー側でエラーになるが、
イベントルーティング・セッション管理・Agent処理のフローは確認できる。

### 準備

```bash
# .env に最低限の環境変数を設定
export COSMOS_CONNECTION_STRING="..."
export SQL_CONNECTION_STRING="..."
export AZURE_OPENAI_ENDPOINT="https://ai-orderai-dev.openai.azure.com/"
export AZURE_OPENAI_KEY="..."
export ACS_CALLBACK_BASE_URL="http://localhost:8080"

# サーバー起動
uvicorn src.api.main:app --reload --port 8080
```

### 実行

```bash
# 基本（りんご10箱、バナナ20kg を1ターンで注文）
python tests/simulate_phone_call.py

# デプロイ済み環境に対して実行
python tests/simulate_phone_call.py \
  --base-url https://ca-api-orderai-dev.thankfulstone-903cb4eb.japaneast.azurecontainerapps.io

# 複数ターン（1ターン目で注文、2ターン目で追加）
python tests/simulate_phone_call.py --messages "りんご10箱" "バナナ20kgも追加で"

# 曖昧な注文（確認フロー発生）
python tests/simulate_phone_call.py --messages "いつものお願い"

# 異常数量（異常検知テスト）
python tests/simulate_phone_call.py --messages "トマト150kg"
```

### シミュレーションのイベント順序

```
[1] IncomingCall      → サーバーが answer_call 実行
[2] CallConnected     → 挨拶TTS再生
[3] PlayCompleted     → 音声認識開始
[4] RecognizeCompleted → Agent が注文処理、応答TTS再生
[5] PlayCompleted     → 注文確定なら切断、未確定なら再認識
[6] CallDisconnected  → セッション完了
```

### 確認ポイント

- サーバーログに `Incoming call from ...` が出る
- `Intake result:` にJSON形式の注文ドラフトが出る
- 注文確定時 `Created order ORD-xxx` が出る
- `Call disconnected: ..., turns=N` で通話終了

---

## 方法3: curl による個別イベント送信

特定のイベントだけテストしたい場合に使う。

```bash
BASE=http://localhost:8080

# IncomingCall
curl -s -X POST "$BASE/api/phone-webhook" \
  -H "Content-Type: application/json" \
  -d '[{
    "type": "Microsoft.Communication.IncomingCall",
    "data": {
      "from": {"phoneNumber": {"value": "+81312345678"}},
      "to": {"phoneNumber": {"value": "+81501234567"}},
      "incomingCallContext": "mock-context",
      "serverCallId": "mock-server-001"
    }
  }]'

# RecognizeCompleted（音声認識結果）
curl -s -X POST "$BASE/api/phone-webhook" \
  -H "Content-Type: application/json" \
  -d '[{
    "type": "Microsoft.Communication.RecognizeCompleted",
    "data": {
      "callConnectionId": "conn-001",
      "speechResult": {"speech": "りんご10箱お願いします"}
    }
  }]'

# EventGrid バリデーション（ACS設定時に必要）
curl -s -X POST "$BASE/api/phone-webhook" \
  -H "Content-Type: application/json" \
  -d '[{
    "type": "Microsoft.EventGrid.SubscriptionValidationEvent",
    "data": {"validationCode": "test-code-123"}
  }]'
```

---

## 方法4: 実電話テスト（E2E）

ACS 電話番号の取得後に実施。

### 前提条件
- ACS 電話番号が取得済み
- Event Grid サブスクリプションが設定済み
- Container Apps にデプロイ済み（または ngrok でローカル公開）

### ngrok でのローカルテスト

```bash
# ターミナル1: サーバー起動
uvicorn src.api.main:app --reload --port 8080

# ターミナル2: ngrok 起動
ngrok http 8080
# → https://xxxx.ngrok-free.app を取得

# .env を更新
ACS_CALLBACK_BASE_URL=https://xxxx.ngrok-free.app
```

Azure Portal で以下を設定:
1. ACS リソース → Events → Event Subscription 作成
2. Endpoint Type: Webhook
3. Endpoint URL: `https://xxxx.ngrok-free.app/api/phone-webhook`
4. Event Types: `Microsoft.Communication.IncomingCall`

設定後、ACS 電話番号に電話をかけるとフルフローが動作する。

### デプロイ環境でのテスト

Event Grid の Webhook URL を Container Apps のURLに設定:
```
https://ca-api-orderai-dev.thankfulstone-903cb4eb.japaneast.azurecontainerapps.io/api/phone-webhook
```

---

## トラブルシューティング

| 症状 | 原因 | 対処 |
|---|---|---|
| `acs_not_configured` | ACS接続文字列が未設定 | `.env` に `ACS_CONNECTION_STRING` を設定 |
| `unknown_call` | CallState が見つからない | IncomingCall を先に送信する（シミュレーション順序を確認） |
| Agent処理タイムアウト | OpenAI API が遅い | ログで `Intake result:` の出力時間を確認 |
| `end_silence_timeout` で認識失敗 | 無音検出が早すぎる | `phone_handler.py` の `end_silence_timeout_in_seconds` を調整（デフォルト5秒） |
| TTS が再生されない | Speech Service キーが無効 | Key Vault の `speech-service-key` を確認 |
