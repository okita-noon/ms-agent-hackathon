team_cases = '''    {
        "id": 15,
        "label": "既存注文への商品追加（文脈保持）",
        "customer_id": "C-002",
        "messages": [
            "バナナ10kgお願いします",
            "あとレモンも5個追加して",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
                ("バナナに言及", lambda r, d: "バナナ" in r, "バナナが確定"),
            ],
            [
                ("変更対象なしと返さない", lambda r, d: "変更対象" not in r, "追加が現在注文に紐付く"),
                ("レモンに言及", lambda r, d: "レモン" in r or "追加" in r or "承知" in r, "レモンが追加される"),
            ],
        ],
    },
    {
        "id": 16,
        "label": "キャンセル → 再注文（文脈保持）",
        "customer_id": "C-002",
        "messages": [
            "みかん10個お願いします",
            "キャンセル",
            "やっぱりみかん20個お願い",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
            ],
            [
                ("キャンセル受付", lambda r, d: "取消" in r or "キャンセル" in r or "承知" in r, "キャンセル受付メッセージ"),
            ],
            [
                ("再注文で受注確定", lambda r, d: d.get("order_saved") is True, "新規受注確定"),
                ("変更対象なしと返さない", lambda r, d: "変更対象" not in r, "前注文の復活にしない"),
            ],
        ],
    },
    {
        "id": 17,
        "label": "複数商品の一部数量変更（文脈保持）",
        "customer_id": "C-002",
        "messages": [
            "りんご5箱、バナナ10kg、みかん20個お願いします",
            "バナナだけ20kgに変更",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
            [
                ("変更対象なしと返さない", lambda r, d: "変更対象" not in r, "一部変更が現在注文に追従"),
                ("バナナに言及", lambda r, d: "バナナ" in r or "20" in r or "変更" in r or "承知" in r, "バナナ20kgへの変更"),
            ],
        ],
    },
    {
        "id": 18,
        "label": "単位mismatch / 不定貫",
        "customer_id": "C-002",
        "messages": [
            "バナナを3房お願いします",
        ],
        "checks": [
            [
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "単位ミスマッチで即確定しない"),
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "確認質問または自然な応答"),
            ],
        ],
    },
    {
        "id": 19,
        "label": "配送リードタイム超過",
        "customer_id": "C-001",
        "messages": [
            "りんご5箱、今日中にお願いします",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 20,
        "label": "休業日・営業日外指定",
        "customer_id": "C-002",
        "messages": [
            "バナナ10kg、日曜日にお願いします",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
                ("バナナに言及", lambda r, d: "バナナ" in r, "バナナが処理対象"),
            ],
        ],
    },
    {
        "id": 21,
        "label": "特殊対応メモ要求",
        "customer_id": "C-002",
        "messages": [
            "りんご5箱、アレルギー対応で個別包装お願いします",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 22,
        "label": "複数配送日まとめ注文",
        "customer_id": "C-002",
        "messages": [
            "明日にりんご5箱、明後日にバナナ10kg",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
                ("バナナに言及", lambda r, d: "バナナ" in r, "バナナが処理対象"),
            ],
        ],
    },
    {
        "id": 23,
        "label": "オープン注文ゼロ状態での照会",
        "customer_id": "C-002",
        "messages": [
            "今の注文って何？",
        ],
        "checks": [
            [
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "照会で新規注文を誤確定しない"),
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 24,
        "label": "確認待ち中の雑談（文脈保持）",
        "customer_id": "C-002",
        "messages": [
            "みかんちょうだい",
            "今日寒いね",
        ],
        "checks": [
            [
                ("確認質問あり（確定しない）", lambda r, d: d.get("order_saved") is not True, "数量確認でまだ確定しない"),
            ],
            [
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "雑談で誤確定しない"),
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 25,
        "label": "数量ゼロ / 負の数",
        "customer_id": "C-002",
        "messages": [
            "りんご0箱お願い",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 26,
        "label": "在庫ちょうど（境界値）",
        "customer_id": "C-002",
        "messages": [
            "スイカ30個お願いします",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "在庫ちょうどで受注確定"),
                ("在庫不足扱いにしない", lambda r, d: "不足" not in r and "よろしいですか" not in r, "代替数量提示にしない"),
            ],
        ],
    },
    {
        "id": 27,
        "label": "同一商品の重複指定",
        "customer_id": "C-002",
        "messages": [
            "りんご3箱、りんご2箱お願い",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
                ("りんごに言及", lambda r, d: "りんご" in r, "りんごが処理対象"),
            ],
        ],
    },
    {
        "id": 28,
        "label": "存在しない商品（正規化失敗）",
        "customer_id": "C-002",
        "messages": [
            "すいかバー10個お願いします",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 29,
        "label": "商品名と数量の対応曖昧",
        "customer_id": "C-002",
        "messages": [
            "りんご、バナナ10kg",
        ],
        "checks": [
            [
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "数量欠落で即確定しない"),
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 30,
        "label": "絵文字混じり",
        "customer_id": "C-002",
        "messages": [
            "🍎5箱お願いします🙏",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 31,
        "label": "長文の中の発注",
        "customer_id": "C-002",
        "messages": [
            "お疲れさまです。今日は寒いですが、明日のためにりんご5箱、バナナ10kg、もも2箱お願いできますか？よろしくお願いします",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
                ("バナナまたはももに言及", lambda r, d: "バナナ" in r or "もも" in r, "長文から商品が抽出される"),
            ],
        ],
    },
'''

src = open("scripts/line_qc/run.py", encoding="utf-8").read()

# "# ── チーム追加ケース（15〜31）" の直後に挿入
marker = "    # ── チーム追加ケース（15〜31） ───────────────────────────────────────────────\n"
insert_point = src.find(marker) + len(marker)
result = src[:insert_point] + team_cases + src[insert_point:]

open("scripts/line_qc/run.py", "w", encoding="utf-8").write(result)

import re
ids = sorted([int(m) for m in re.findall(r'"id":\s*(\d+),', result)])
dupes = [x for x in set(ids) if ids.count(x) > 1]
print(f"ケース数: {len(ids)}")
print(f"重複ID: {dupes}")
print(f"全ID: {ids}")
