#!/usr/bin/env python3
"""Simulate a full phone call flow by sending mock ACS CloudEvents to /api/phone-webhook.

Usage:
    # Against local server
    python tests/simulate_phone_call.py

    # Against deployed server
    python tests/simulate_phone_call.py --base-url https://ca-api-orderai-dev.thankfulstone-903cb4eb.japaneast.azurecontainerapps.io

    # Custom caller/called numbers
    python tests/simulate_phone_call.py --caller +81312345678 --called +81501234567

    # Custom speech messages (multi-turn)
    python tests/simulate_phone_call.py --messages "りんご10箱" "バナナ20kg"

    # Single order, auto-confirmed
    python tests/simulate_phone_call.py --messages "りんご10箱、バナナ20kg"
"""

from __future__ import annotations

import argparse
import json
import time
import uuid

import httpx


def make_incoming_call_event(
    caller: str,
    called: str,
    server_call_id: str,
) -> dict:
    return {
        "type": "Microsoft.Communication.IncomingCall",
        "data": {
            "from": {"phoneNumber": {"value": caller}, "rawId": caller},
            "to": {"phoneNumber": {"value": called}, "rawId": called},
            "incomingCallContext": f"mock-context-{uuid.uuid4().hex[:8]}",
            "serverCallId": server_call_id,
        },
    }


def make_call_connected_event(call_connection_id: str) -> dict:
    return {
        "type": "Microsoft.Communication.CallConnected",
        "data": {"callConnectionId": call_connection_id},
    }


def make_recognize_completed_event(call_connection_id: str, speech: str) -> dict:
    return {
        "type": "Microsoft.Communication.RecognizeCompleted",
        "data": {
            "callConnectionId": call_connection_id,
            "speechResult": {"speech": speech},
        },
    }


def make_play_completed_event(call_connection_id: str) -> dict:
    return {
        "type": "Microsoft.Communication.PlayCompleted",
        "data": {"callConnectionId": call_connection_id},
    }


def make_call_disconnected_event(call_connection_id: str) -> dict:
    return {
        "type": "Microsoft.Communication.CallDisconnected",
        "data": {"callConnectionId": call_connection_id},
    }


def send_event(client: httpx.Client, base_url: str, event: dict) -> dict | None:
    url = f"{base_url}/api/phone-webhook"
    resp = client.post(url, json=[event], timeout=30)
    print(f"  → {resp.status_code}")
    if resp.status_code != 200:
        print(f"  ERROR: {resp.text}")
        return None
    try:
        return resp.json()
    except Exception:
        return None


def run_simulation(
    base_url: str,
    caller: str,
    called: str,
    messages: list[str],
    delay: float,
) -> None:
    server_call_id = f"server-call-{uuid.uuid4().hex[:8]}"
    call_connection_id = f"conn-sim-{uuid.uuid4().hex[:8]}"

    print(f"\n{'=' * 60}")
    print("Phone Call Simulation")
    print(f"  Server:  {base_url}")
    print(f"  Caller:  {caller}")
    print(f"  Called:  {called}")
    print(f"  Messages: {messages}")
    print(f"  Connection ID: {call_connection_id}")
    print(f"{'=' * 60}\n")

    with httpx.Client() as client:
        # 1. IncomingCall
        print("[1] IncomingCall")
        result = send_event(
            client,
            base_url,
            make_incoming_call_event(caller, called, server_call_id),
        )
        if result:
            print(f"     Result: {json.dumps(result, ensure_ascii=False)}")
        time.sleep(delay)

        # 2. CallConnected
        print("[2] CallConnected")
        send_event(client, base_url, make_call_connected_event(call_connection_id))
        time.sleep(delay)

        # 3. PlayCompleted (after greeting TTS)
        print("[3] PlayCompleted (greeting done)")
        send_event(client, base_url, make_play_completed_event(call_connection_id))
        time.sleep(delay)

        # 4. For each message: RecognizeCompleted → PlayCompleted
        for i, msg in enumerate(messages):
            turn = i + 1
            print(f'[{3 + turn * 2 - 1}] RecognizeCompleted (turn {turn}): "{msg}"')
            result = send_event(
                client,
                base_url,
                make_recognize_completed_event(call_connection_id, msg),
            )
            if result:
                print(f"     Result: {json.dumps(result, ensure_ascii=False)}")
            time.sleep(delay)

            print(f"[{3 + turn * 2}] PlayCompleted (response TTS done)")
            result = send_event(
                client,
                base_url,
                make_play_completed_event(call_connection_id),
            )
            if result:
                print(f"     Result: {json.dumps(result, ensure_ascii=False)}")
            time.sleep(delay)

        # 5. CallDisconnected
        print(f"[{3 + len(messages) * 2 + 1}] CallDisconnected")
        result = send_event(
            client,
            base_url,
            make_call_disconnected_event(call_connection_id),
        )
        if result:
            print(f"     Result: {json.dumps(result, ensure_ascii=False)}")

    print(f"\n{'=' * 60}")
    print("Simulation complete")
    print(f"{'=' * 60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate ACS phone call flow")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8080",
        help="API base URL (default: http://localhost:8080)",
    )
    parser.add_argument("--caller", default="+81312345678", help="Caller phone number")
    parser.add_argument(
        "--called", default="+81501234567", help="Called phone number (ACS)"
    )
    parser.add_argument(
        "--messages",
        nargs="+",
        default=["りんご10箱、バナナ20kg"],
        help="Speech messages to simulate (each = one recognize turn)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between events (default: 1.0)",
    )
    args = parser.parse_args()

    run_simulation(
        base_url=args.base_url.rstrip("/"),
        caller=args.caller,
        called=args.called,
        messages=args.messages,
        delay=args.delay,
    )


if __name__ == "__main__":
    main()
