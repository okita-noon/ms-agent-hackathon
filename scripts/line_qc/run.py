"""
LINE QC 自動実行スクリプト
Created: 2026-05-28
Updated: 2026-05-28 20:05

使い方:
    python scripts/line_qc/run.py
    python scripts/line_qc/run.py --verbose
    python scripts/line_qc/run.py --cases 1,3,5   # 指定ケースのみ
    python scripts/line_qc/run.py --base-url http://localhost:8080

出力:
    docs/line_QC.md の 4.X セクションに結果を追記する。
    scripts/line_qc/_logs/qc_YYYYMMDD_HHMMSS.json に全ログを出力する。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time

# Windows でのUTF-8出力を強制
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# ── 定数 ──────────────────────────────────────────────────────────────────────
JST = timezone(timedelta(hours=9))
REPO_ROOT = Path(__file__).resolve().parents[2]
QC_DOC = REPO_ROOT / "docs" / "line_QC.md"
LOGS_DIR = Path(__file__).resolve().parent / "_logs"
DEFAULT_BASE_URL = "https://ca-api-orderai-dev2.mangoground-6945bb56.japaneast.azurecontainerapps.io"
DEFAULT_ACCESS_CODE = "test"
DEFAULT_CUSTOMER_ID = "C-001"

# ── テストケース定義 ───────────────────────────────────────────────────────────
# 各ケース:
#   id          : ケースID（line_QC.md の 3.1 と対応）
#   label       : 観点名
#   customer_id : 使用顧客（Noneの場合はデフォルト C-001）
#   messages    : 送信メッセージのリスト
#   checks      : 各メッセージへの期待チェック関数リスト（response, result -> bool, reason）
TEST_CASES: list[dict[str, Any]] = [
    {
        "id": 1,
        "label": "通常注文（即確定）",
        "customer_id": "C-001",
        "messages": [
            "アボカド5個、マンゴー3個お願いします",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
                ("配送予定日あり", lambda r, d: "配送" in r or "お届け" in r or "月" in r or "日" in r, "配送予定日が含まれる"),
            ],
        ],
    },
    {
        "id": 2,
        "label": "数量不明の確認 → 回答で確定",
        "customer_id": "C-001",
        "messages": [
            "みかんちょうだい",
            "10個",
        ],
        "checks": [
            [
                ("確認質問あり", lambda r, d: d.get("order_saved") is not True, "order_savedでない（確認質問を返す）"),
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "まだ確定しない"),
            ],
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
                ("配送予定日あり", lambda r, d: "配送" in r or "お届け" in r or "月" in r, "配送予定日が含まれる"),
            ],
        ],
    },
    {
        "id": 3,
        "label": "誤発注の数量異常検知",
        "customer_id": "C-001",
        "messages": [
            "みかん1500個お願いします",
        ],
        "checks": [
            [
                ("即確定しない", lambda r, d: d.get("order_saved") is not True, "異常検知で確認質問"),
            ],
        ],
    },
    {
        "id": 4,
        "label": "在庫不足 → 代替数量で確定",
        "customer_id": "C-001",
        "messages": [
            "メロン50玉お願いします",
            "はい、お願いします",
        ],
        "checks": [
            [
                ("在庫不足を通知", lambda r, d: "在庫" in r or "受け付けられません" in r or "よろしいですか" in r, "在庫不足メッセージ"),
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "1通目はまだ確定しない"),
            ],
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "はい返答で受注確定"),
            ],
        ],
    },
    {
        "id": 5,
        "label": "「いつもの」注文（パターン学習）",
        "customer_id": "C-001",
        "messages": [
            "いつものお願い",
        ],
        "checks": [
            [
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 6,
        "label": "注文 → 変更（文脈保持）",
        "customer_id": "C-001",
        "messages": [
            "ぶどう5房お願いします",
            "6房に数量変更してください",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
            ],
            [
                ("変更対象なしと返さない", lambda r, d: "変更対象" not in r, "「変更対象の現在注文が見当たりません」が出ない"),
                ("6への変更言及", lambda r, d: "6" in r or "変更" in r or "承" in r, "6房への変更が反映"),
            ],
        ],
    },
    {
        "id": 7,
        "label": "注文 → キャンセル（文脈保持）",
        "customer_id": "C-001",
        "messages": [
            "みかん30個お願いします",
            "さっきの注文キャンセルしたい",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
            ],
            [
                ("変更対象なしと返さない", lambda r, d: "変更対象" not in r, "「変更対象なし」が出ない"),
                ("キャンセル受付", lambda r, d: "取消" in r or "キャンセル" in r or "承知" in r, "キャンセル受付メッセージ"),
            ],
        ],
    },
    {
        "id": 8,
        "label": "現在の注文の問い合わせ（文脈保持）",
        "customer_id": "C-001",
        "messages": [
            "レモン10個お願いします",
            "今の注文って何だっけ？",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
            ],
            [
                ("レモンに言及", lambda r, d: "レモン" in r, "レモンの情報が含まれる"),
                ("配送日が含まれる", lambda r, d: "配送" in r or "月" in r or "日" in r, "配送予定日がサマリに含まれる"),
                ("新規注文として処理しない", lambda r, d: d.get("order_saved") is not True, "2通目で新たなorder_savedが発生しない"),
            ],
        ],
    },
    {
        "id": 9,
        "label": "配送日・時間帯指定",
        "customer_id": "C-001",
        "messages": [
            "ぶどう3房、明後日の午前中に届けて",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
                ("配送または納品言及", lambda r, d: "配送" in r or "納品" in r or "お届け" in r or "月" in r or "日" in r, "配送日が含まれる"),
            ],
        ],
    },
    {
        "id": 10,
        "label": "在庫問い合わせ（受注しない）",
        "customer_id": "C-001",
        "messages": [
            "メロンって今ある？",
        ],
        "checks": [
            [
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "在庫照会のみで受注しない"),
                ("在庫情報を返す", lambda r, d: "メロン" in r or "在庫" in r or "玉" in r, "在庫情報が含まれる"),
            ],
        ],
    },
    {
        "id": 11,
        "label": "表記ゆれ・あいまい商品名",
        "customer_id": "C-001",
        "messages": [
            "レモン5個とキウイ10コ",
        ],
        "checks": [
            [
                ("レモン・キウイ両方に言及", lambda r, d: ("レモン" in r or "れもん" in r) and ("キウイ" in r or "きうい" in r), "正規化されて両商品が含まれる"),
                ("破綻しない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 12,
        "label": "雑談・無関係メッセージ",
        "customer_id": "C-001",
        "messages": [
            "おはよう！今日は天気いいね",
        ],
        "checks": [
            [
                ("受注確定しない", lambda r, d: d.get("order_saved") is not True, "雑談で受注確定しない"),
                ("エラーでない", lambda r, d: r != "" and "エラー" not in r, "応答が空でなくエラーでない"),
            ],
        ],
    },
    {
        "id": 13,
        "label": "複数注文の一部キャンセル（文脈保持）",
        "customer_id": "C-001",
        "messages": [
            "アボカド3個、マンゴー2個、ブルーベリー1箱お願いします",
            "そのうちマンゴーだけキャンセルして",
            "今の注文は？",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
            ],
            [
                ("全取消にしない", lambda r, d: "アボカド" in r or "ブルーベリー" in r or "取消" in r or "キャンセル" in r or "承知" in r, "マンゴーのみ取消・他は継続"),
            ],
            [
                ("アボカド・ブルーベリーが残る", lambda r, d: "アボカド" in r or "ブルーベリー" in r, "一部キャンセル後の残注文が正しい"),
            ],
        ],
    },
    {
        "id": 14,
        "label": "現在の注文状況の確認（単発照会）",
        "customer_id": "C-001",
        "messages": [
            "マンゴー3個、ブルーベリー1箱お願いします",
            "今の注文状況を教えて",
        ],
        "checks": [
            [
                ("受注確定", lambda r, d: d.get("order_saved") is True, "order_saved=True"),
            ],
            [
                ("マンゴー・ブルーベリーに言及", lambda r, d: "マンゴー" in r or "ブルーベリー" in r, "注文内容が含まれる"),
                ("新規注文として処理しない", lambda r, d: d.get("order_saved") is not True, "2通目で新たなorder_savedが発生しない"),
            ],
        ],
    },
]


# ── .env 読み込み ─────────────────────────────────────────────────────────────
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


# ── debug_log パース ──────────────────────────────────────────────────────────
def _parse_debug_log(debug_log: list[str]) -> tuple[str, str]:
    """debug_log から応答主体と経路を推定する。"""
    agent = "Orchestrator"
    route = "LLM生成"

    for line in debug_log:
        if "[判定] 現在注文の問い合わせ" in line:
            agent = "Orchestrator"
            route = "現在注文問い合わせテンプレート"
        elif "[判定] 在庫問い合わせ" in line:
            agent = "Inventory"
            route = "LLM生成"
        elif "[判定] 全注文取消" in line:
            agent = "Orchestrator"
            route = "テンプレート上書き"
        elif "[判定] 変更/取消要求だが現在注文なし" in line:
            agent = "Orchestrator"
            route = "テンプレート上書き"
        elif "[確定] ドラフト受注確定" in line:
            route = "テンプレート上書き"
        elif "[Intake] JSON抽出失敗" in line:
            agent = "Orchestrator"
            route = "フォールバック応答"
        elif "[パイプライン] マルチエージェント" in line:
            agent = "MultiAgent"
        elif "[パイプライン] シングルエージェント" in line:
            agent = "Orchestrator"

    # テンプレート返答の検出
    for line in debug_log:
        if "テンプレート" in line or "template" in line.lower():
            route = "テンプレート上書き"
            break

    return agent, route


# ── API クライアント ───────────────────────────────────────────────────────────
class LineTesterClient:
    def __init__(self, base_url: str, access_code: str, verbose: bool = False):
        self._base_url = base_url.rstrip("/")
        self._access_code = access_code
        self._verbose = verbose
        self._client: httpx.AsyncClient | None = None
        self._cookies: dict[str, str] = {}

    async def __aenter__(self) -> "LineTesterClient":
        self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        await self._unlock()
        self._customer_map = await self._fetch_customers()
        return self

    async def _fetch_customers(self) -> dict[str, str]:
        """customer_id -> customer_name のマップを取得する。"""
        url = f"{self._base_url}/api/line-tester/customers"
        resp = await self._client.get(url, cookies=self._cookies)
        data = resp.json()
        return {c["customer_id"]: c["customer_name"] for c in data.get("customers", []) if c["customer_id"]}

    def get_customer_name(self, customer_id: str) -> str | None:
        return self._customer_map.get(customer_id)

    async def __aexit__(self, *_: Any) -> None:
        if self._client:
            await self._client.aclose()

    async def _unlock(self) -> None:
        url = f"{self._base_url}/line-tester/unlock"
        resp = await self._client.post(url, json={"code": self._access_code})
        for cookie in resp.cookies.items():
            self._cookies[cookie[0]] = cookie[1]
        if self._verbose:
            print(f"  [unlock] status={resp.status_code}, cookies={list(self._cookies.keys())}")

    async def send_message(
        self,
        message: str,
        customer_id: str | None,
        customer_name: str | None,
        session_id: str,
        current_order_id: str | None,
        conversation_history: list[dict],
        pending_order_draft: dict | None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}/api/line-tester/message"
        payload = {
            "message": message,
            "customer_id": customer_id,
            "customer_name": customer_name,
            "session_id": session_id,
            "current_order_id": current_order_id,
            "conversation_history": conversation_history,
            "pending_order_draft": pending_order_draft,
        }
        resp = await self._client.post(url, json=payload, cookies=self._cookies)
        resp.raise_for_status()
        return resp.json()


# ── ケース実行 ────────────────────────────────────────────────────────────────
async def run_case(
    client: LineTesterClient,
    case: dict[str, Any],
    verbose: bool,
) -> dict[str, Any]:
    """1ケースを実行し、結果を返す。"""
    case_id = case["id"]
    label = case["label"]
    customer_id = case.get("customer_id", DEFAULT_CUSTOMER_ID)
    customer_name = client.get_customer_name(customer_id)
    messages = case["messages"]
    checks_per_msg = case["checks"]

    session_id = f"qc-case{case_id}-{int(time.time())}"
    current_order_id: str | None = None
    conversation_history: list[dict] = []
    pending_order_draft: dict | None = None

    msg_results: list[dict[str, Any]] = []

    for i, message in enumerate(messages):
        if verbose:
            print(f"    メッセージ{i+1}: {message!r}")

        result = await client.send_message(
            message=message,
            customer_id=customer_id,
            customer_name=customer_name,
            session_id=session_id,
            current_order_id=current_order_id,
            conversation_history=conversation_history,
            pending_order_draft=pending_order_draft,
        )

        response = result.get("response", "")
        debug_log: list[str] = result.get("debug_log", [])
        agent, route = _parse_debug_log(debug_log)

        # 業務状態
        order_id = result.get("order_id")
        new_current_order_id = result.get("current_order_id")
        order_cleared = result.get("current_order_cleared", False)
        order_saved = result.get("order_saved", False)

        # 状態を引き継ぐ
        conversation_history = result.get("conversation_history", conversation_history)
        pending_order_draft = result.get("pending_order_draft")
        if order_cleared:
            current_order_id = None
        elif new_current_order_id:
            current_order_id = new_current_order_id

        # チェック実行
        check_results: list[dict] = []
        checks = checks_per_msg[i] if i < len(checks_per_msg) else []
        all_ok = True
        for check_name, check_fn, check_desc in checks:
            try:
                ok = check_fn(response, result)
            except Exception:
                ok = False
            if not ok:
                all_ok = False
            check_results.append({"name": check_name, "ok": ok, "desc": check_desc})

        ai_judgment = "OK" if all_ok else "NG"

        if verbose:
            print(f"      応答主体={agent}, 経路={route}")
            print(f"      応答: {response[:80]!r}{'...' if len(response) > 80 else ''}")
            print(f"      判定: AI={ai_judgment}")

        msg_results.append(
            {
                "message": message,
                "response": response,
                "agent": agent,
                "route": route,
                "order_id": order_id,
                "current_order_id": current_order_id,
                "order_saved": order_saved,
                "pending_exists": pending_order_draft is not None,
                "debug_log": debug_log,
                "checks": check_results,
                "ai_judgment": ai_judgment,
            }
        )

    overall_ok = all(m["ai_judgment"] == "OK" for m in msg_results)
    return {
        "id": case_id,
        "label": label,
        "customer_id": customer_id,
        "messages": msg_results,
        "overall_ok": overall_ok,
    }


# ── Markdown 生成 ─────────────────────────────────────────────────────────────
def _build_section(
    section_no: str,
    now_jst: datetime,
    branch: str,
    max_pr: str,
    case_results: list[dict],
    log_filename: str = "",
) -> str:
    lines: list[str] = []
    n_cases = len(case_results)
    lines.append(f"### {section_no}. {now_jst.strftime('%Y-%m-%d')} 実施分（{n_cases}ケース）")
    lines.append("")
    lines.append(f"#### {section_no}.0. テスト実施メタ情報")
    lines.append(f"1. 実施日時 (JST): {now_jst.strftime('%Y-%m-%d %H:%M')}〜 頃")
    lines.append(f"2. 参照ブランチ: `{branch}`（ローカル確認時点）")
    lines.append(f"3. 当時点で `main` にマージ済みの最大PR番号: `{max_pr}`")
    lines.append(f"4. 詳細ログ: `scripts/line_qc/_logs/{log_filename}`")
    lines.append("5. 顧客No:")
    for cr in case_results:
        lines.append(f"   - {section_no}.{cr['id']}: `{cr['customer_id']}`")
    lines.append("")
    lines.append("")

    for cr in case_results:
        case_id = cr["id"]
        label = cr["label"]
        lines.append(f"#### {section_no}.{case_id}. ケース{case_id}: {label}")
        ng_msgs: list[str] = []

        for i, mr in enumerate(cr["messages"], 1):
            order_id_str = mr["order_id"] or "null"
            cur_order_str = mr["current_order_id"] or "null"
            pending_str = str(mr["pending_exists"]).lower()

            lines.append(f"{i}. 入力: `{mr['message']}`")
            lines.append(f"   - 応答主体: {mr['agent']}")
            lines.append(f"   - 経路: {mr['route']}")
            lines.append(f"   - 業務状態: `order_id={order_id_str} / current_order_id={cur_order_str} / pending_exists={pending_str}`")
            lines.append(f"   - 応答全文: `{mr['response']}`")
            lines.append(f"   - 判定: AI={mr['ai_judgment']} / 人=-")

            if mr["ai_judgment"] == "NG":
                ng_msgs.append(f"メッセージ{i}: " + ", ".join(
                    f"{c['name']}→NG" for c in mr["checks"] if not c["ok"]
                ))

        lines.append("")
        lines.append("所感:")
        if ng_msgs:
            for j, ng in enumerate(ng_msgs, 1):
                lines.append(f"{j}. {ng}")
        else:
            lines.append("1. 全チェックOK")
        lines.append("")

        if not cr["overall_ok"]:
            lines.append("理想応答（例）:")
            lines.append("1. （要確認）")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _update_toc(content: str, section_no: str, date_str: str, n_cases: int) -> str:
    """目次の「4. 実施結果ログ」配下に新しいエントリを追加する。"""
    anchor = section_no.replace(".", "") + f"-{date_str}-実施分{n_cases}ケース"
    new_entry = f"  - [{section_no}. {date_str} 実施分（{n_cases}ケース）](#{anchor})"

    # 「4.X. 次回テスト記録枠」の行の直前に挿入
    toc_marker = "  - [4."
    next_entry_marker = "  - [4." + section_no.split(".")[1] + ". 次回テスト記録枠"

    if next_entry_marker in content:
        return content.replace(next_entry_marker, new_entry + "\n" + next_entry_marker)

    # マーカーが見つからない場合は「5. 改善履歴」の直前に挿入
    fallback = "- [5. 改善履歴"
    return content.replace(fallback, new_entry + "\n" + fallback)


def _write_log(
    log_path: Path,
    now_jst: datetime,
    branch: str,
    max_pr: str,
    base_url: str,
    case_results: list[dict],
) -> None:
    """全ケースの詳細ログをJSONファイルに出力する。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    def _extract_debug(debug_log: list[str], tag: str) -> list[str]:
        return [l for l in debug_log if l.startswith(tag)]

    def _build_agent_flow(debug_log: list[str]) -> list[dict]:
        """debug_logからエージェント判断フローを時系列で整形する。"""
        flow = []
        # タグと対応するエージェント名のマッピング
        tag_map = [
            ("[顧客]", "System", "顧客情報の確認"),
            ("[顧客解決]", "System", "顧客解決経路の決定"),
            ("[分類]", "IntentClassifier", "意図分類"),
            ("[判定]", "Orchestrator", "ルール判定"),
            ("[ドラフト]", "System", "ドラフト確認"),
            ("[パイプライン]", "Orchestrator", "パイプライン選択"),
            ("[Intake]", "IntakeAgent", "注文解析"),
            ("[Exception]", "ExceptionAgent", "異常検知"),
            ("[在庫]", "InventoryCheck", "在庫確認"),
            ("[配送]", "DeliveryEstimator", "配送日推定"),
            ("[保存]", "OrderRepository", "受注保存"),
            ("[確定]", "OrderRepository", "受注確定"),
            ("[取消]", "OrderRepository", "注文キャンセル"),
            ("[セッション]", "SessionManager", "セッション状態"),
            ("[記憶注文]", "OrderMemoryService", "注文パターン照合"),
        ]
        for line in debug_log:
            for tag, agent, step in tag_map:
                if line.startswith(tag):
                    flow.append({"agent": agent, "step": step, "log": line})
                    break
        return flow

    payload = {
        "meta": {
            "timestamp_jst": now_jst.isoformat(),
            "branch": branch,
            "max_pr": max_pr,
            "base_url": base_url,
            "total_cases": len(case_results),
            "ok_count": sum(1 for c in case_results if c.get("overall_ok")),
            "ng_count": sum(1 for c in case_results if not c.get("overall_ok")),
        },
        "cases": [
            {
                "id": cr["id"],
                "label": cr["label"],
                "customer_id": cr["customer_id"],
                "overall_ok": cr.get("overall_ok", False),
                "messages": [
                    {
                        "seq": i + 1,
                        "input": mr["message"],
                        "response": mr["response"],
                        "agent": mr["agent"],
                        "route": mr["route"],
                        # 業務状態
                        "order_id": mr["order_id"],
                        "current_order_id": mr["current_order_id"],
                        "order_saved": mr["order_saved"],
                        "pending_exists": mr["pending_exists"],
                        # 判定
                        "ai_judgment": mr["ai_judgment"],
                        "checks": [
                            {"name": c["name"], "ok": c["ok"], "desc": c["desc"]}
                            for c in mr["checks"]
                        ],
                        # debug_log 全文
                        "debug_log": mr["debug_log"],
                        # debug_log から抽出したキー情報
                        "debug_顧客": _extract_debug(mr["debug_log"], "[顧客]"),
                        "debug_顧客解決": _extract_debug(mr["debug_log"], "[顧客解決]"),
                        "debug_分類": _extract_debug(mr["debug_log"], "[分類]"),
                        "debug_Intake": _extract_debug(mr["debug_log"], "[Intake]"),
                        "debug_在庫": _extract_debug(mr["debug_log"], "[在庫]"),
                        "debug_保存": _extract_debug(mr["debug_log"], "[保存]"),
                        "debug_セッション": _extract_debug(mr["debug_log"], "[セッション]"),
                        "debug_判定": _extract_debug(mr["debug_log"], "[判定]"),
                        "debug_ドラフト": _extract_debug(mr["debug_log"], "[ドラフト]"),
                        # needs_confirmation 関連を抽出
                        "needs_confirmation_logs": [
                            l for l in mr["debug_log"]
                            if "needs_confirmation" in l or "確認待ち" in l or "awaiting" in l
                        ],
                        # エージェント判断フロー（時系列）
                        "agent_flow": _build_agent_flow(mr["debug_log"]),
                    }
                    for i, mr in enumerate(cr.get("messages", []))
                ],
            }
            for cr in case_results
        ],
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_section_no(content: str) -> str:
    """line_QC.md の最後の 4.X を見て次の番号を返す。"""
    matches = re.findall(r"^### (4\.\d+)\.", content, re.MULTILINE)
    if not matches:
        return "4.1"
    last = max(int(m.split(".")[1]) for m in matches)
    return f"4.{last + 1}"


def _get_current_branch() -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _get_max_pr() -> str:
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--state", "merged", "--limit", "1", "--json", "number"],
            capture_output=True, text=True, cwd=str(REPO_ROOT)
        )
        data = json.loads(result.stdout)
        if data:
            return f"#{data[0]['number']}"
    except Exception:
        pass
    return "#?"


# ── メイン ────────────────────────────────────────────────────────────────────
async def main(args: argparse.Namespace) -> None:
    _load_dotenv(REPO_ROOT / ".env")

    base_url = args.base_url or os.environ.get("LINE_TESTER_BASE_URL", DEFAULT_BASE_URL)
    access_code = os.environ.get("LINE_TESTER_ACCESS_CODE", DEFAULT_ACCESS_CODE)
    verbose = args.verbose

    # 実行するケースを絞り込む
    cases = TEST_CASES
    if args.cases:
        ids = {int(x.strip()) for x in args.cases.split(",")}
        cases = [c for c in TEST_CASES if c["id"] in ids]

    # 顧客IDを上書き
    if args.customer:
        cases = [{**c, "customer_id": args.customer} for c in cases]

    print(f"LINE QC 開始: {len(cases)}ケース / base_url={base_url}")

    now_jst = datetime.now(JST)
    branch = _get_current_branch()
    max_pr = _get_max_pr()

    case_results: list[dict] = []
    async with LineTesterClient(base_url, access_code, verbose=verbose) as client:
        for case in cases:
            print(f"  ケース{case['id']}: {case['label']} ...", end=" ", flush=True)
            try:
                result = await run_case(client, case, verbose=verbose)
                status = "OK" if result["overall_ok"] else "NG"
                print(status)
                case_results.append(result)
            except Exception as e:
                print(f"ERROR: {e}")
                case_results.append({
                    "id": case["id"],
                    "label": case["label"],
                    "customer_id": case.get("customer_id", DEFAULT_CUSTOMER_ID),
                    "messages": [],
                    "overall_ok": False,
                    "error": str(e),
                })

    # ログファイル出力
    log_filename = f"qc_{now_jst.strftime('%Y%m%d_%H%M%S')}.json"
    log_path = LOGS_DIR / log_filename
    _write_log(log_path, now_jst, branch, max_pr, base_url, case_results)
    print(f"詳細ログ: {log_path}")

    # Markdown 更新
    qc_content = QC_DOC.read_text(encoding="utf-8")
    section_no = _next_section_no(qc_content)
    new_section = _build_section(section_no, now_jst, branch, max_pr, case_results, log_filename)

    # 「4.X. 次回テスト記録枠」の直前に挿入
    marker = f"### {section_no}. 次回テスト記録枠"
    if marker in qc_content:
        updated = qc_content.replace(marker, new_section + "\n" + marker)
    else:
        # マーカーが見つからない場合は末尾の「## 5.」の直前に挿入
        updated = re.sub(r"(## 5\.)", new_section + "\n\\1", qc_content, count=1)

    updated = _update_toc(updated, section_no, now_jst.strftime("%Y-%m-%d"), len(case_results))
    QC_DOC.write_text(updated, encoding="utf-8")
    print(f"\n結果を {QC_DOC} の {section_no} セクションに追記しましたわ。")

    # サマリ表示
    ok_count = sum(1 for r in case_results if r.get("overall_ok"))
    ng_count = len(case_results) - ok_count
    print(f"サマリ: {ok_count}OK / {ng_count}NG / {len(case_results)}件")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LINE QC 自動実行スクリプト")
    parser.add_argument("--base-url", default=None, help="APIのベースURL")
    parser.add_argument("--cases", default=None, help="実行するケースID（カンマ区切り）例: 1,3,5")
    parser.add_argument("--customer", default=None, help="全ケースで使用する顧客ID（例: C-011）")
    parser.add_argument("--verbose", action="store_true", help="詳細ログを表示")
    asyncio.run(main(parser.parse_args()))
