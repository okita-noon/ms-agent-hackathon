# Microsoft Agent Hackathon 2026

**チーム: AINOK_AI木曜会**

## セットアップ

```bash
git clone <このリポジトリのURL>
cd ms-agent-hackathon
git config core.hooksPath .githooks
cp .env.example .env
# .env に自分のAPIキー等を記入
```

セキュリティルールは [SECURITY.md](SECURITY.md) を必ず読んでください。


## Azureのセットアップ
- Azureについて、
    1. claude codeで使うには、Azure CLIをインストール（claude codeに指示）
    2. claude codeに手伝ってもらってazure cliにログインする（windows ではコマンドプロンプトで「az login」からログイン）
    3. Azureでサインインしているメールアドレスをおきたさん
    に共有
    4. おきたさんが承認後、招待メールの「Accept invitation」を押して承認
    5. Azure Portalにログイン → [https://portal.azure.com](https://portal.azure.com/)
    6. 右上のアカウントアイコン →「ディレクトリの切り替え」で、それっぽいテナント（ディレクトリ？）を選ぶ
    7. homeの左ペインのメニュー「Microsoft Entra ID」→概要
    8. 「テナントID」をclaude codeに共有（これは機密じゃないので共有OK）
    9. claude codeに「Azure CLIにログインして」と伝える。
    10. urlとデバイスコードが出るので、作業に従う
    11. claude codeからazureが見れるか確認し、OKをもらったらAzureの設定完了
    