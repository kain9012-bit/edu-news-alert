"""수집 상태를 점검해 이상이 있을 때만 텔레그램으로 알린다.

게시판 주소가 바뀌어도 서버가 오류 없이 메인 화면을 돌려주는 곳이 있어,
수집이 조용히 0건이 되고도 며칠씩 모르고 지나가는 일이 있었다
(2026-09 전북교육소식 개편 때 나흘). 그래서 결과를 사람에게 밀어 준다.

점검 항목
  1. 오늘 수집이 돌았는지(status.json의 collectedAt)
  2. 목록이 0건인 기관(status.json의 emptySources)
  3. 수집 자체가 실패한 기관(runs[].status)
  4. 일정 기간 자료가 하나도 없는 기관(news.json 기준) — 1~3에 안 걸리는
     조용한 단절을 잡는다

이상이 없으면 아무것도 보내지 않는다. 매일 오는 알림은 이내 무시당하기 때문이다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

KST = timezone(timedelta(hours=9))
RAW_BASE = "https://raw.githubusercontent.com/kain9012-bit/edu-news-alert/main/public"
API_BASE = "https://api.telegram.org"
TIMEOUT = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="수집 상태 점검 후 이상 시 텔레그램 발송")
    parser.add_argument("--base-url", default=RAW_BASE, help="공개 데이터 주소")
    parser.add_argument(
        "--stale-days",
        type=int,
        default=10,
        help=(
            "이 기간 동안 자료가 없으면 이상으로 본다(일). 기본 10. "
            "연휴나 게시판이 조용한 시기에 헛경보가 나지 않을 만큼 넉넉히 잡았다. "
            "주소 변경처럼 급한 고장은 '목록 0건' 쪽에서 당일에 잡힌다."
        ),
    )
    parser.add_argument(
        "--always",
        action="store_true",
        help="이상이 없어도 결과를 보낸다(점검용)",
    )
    parser.add_argument("--dry-run", action="store_true", help="발송하지 않고 화면에만 출력")
    return parser.parse_args()


def fetch_json(url: str) -> Any:
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def today_kst() -> str:
    return datetime.now(KST).date().isoformat()


def check_run_freshness(status: dict[str, Any]) -> list[str]:
    collected = str(status.get("collectedAt") or "")[:10]
    if not collected:
        return ["수집 기록(collectedAt)이 없습니다."]
    if collected != today_kst():
        return [f"오늘 수집이 아직 안 돌았습니다. 마지막 수집 {collected}"]
    return []


def check_empty_and_failed(status: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    runs = status.get("runs") or []
    names = {str(r.get("sourceId")): str(r.get("source") or r.get("sourceId")) for r in runs}

    for source_id in status.get("emptySources") or []:
        problems.append(f"목록 0건 — {names.get(str(source_id), source_id)} (게시판 주소 변경 의심)")

    for run in runs:
        if run.get("status") == "failed":
            error = str(run.get("error") or "")[:80]
            problems.append(f"수집 실패 — {run.get('source')}: {error}")
        # 새로 받은 게 0건인 것 자체는 정상이다(이미 다 모았거나 새 글이 없는 날).
        # 목록에 있는 글을 '전부' 못 읽은 경우만 이상으로 본다.
        elif run.get("foundLinks") and run.get("detailFailures", 0) >= run["foundLinks"]:
            problems.append(
                f"상세 페이지를 전부 못 읽음 — {run.get('source')} (목록 {run['foundLinks']}건)"
            )
    return problems


def check_stale_sources(
    status: dict[str, Any], items: list[dict[str, Any]], stale_days: int
) -> list[str]:
    """기관별 최신 자료 날짜가 너무 오래됐는지 본다."""
    runs = status.get("runs") or []
    if not runs:
        return []
    latest: dict[str, str] = {}
    for item in items:
        source_id = str(item.get("sourceId") or "")
        date = str(item.get("date") or "")[:10]
        if source_id and date > latest.get(source_id, ""):
            latest[source_id] = date

    cutoff = (datetime.now(KST).date() - timedelta(days=stale_days)).isoformat()
    already = {str(s) for s in (status.get("emptySources") or [])}
    problems: list[str] = []
    for run in runs:
        source_id = str(run.get("sourceId"))
        if source_id in already:
            continue  # 위에서 이미 알렸다
        last = latest.get(source_id)
        if not last:
            problems.append(f"자료 없음 — {run.get('source')}")
        elif last < cutoff:
            problems.append(f"{stale_days}일 넘게 자료 없음 — {run.get('source')} (마지막 {last})")
    return problems


def build_message(problems: list[str], status: dict[str, Any]) -> str:
    stamp = datetime.now(KST).strftime("%-m월 %-d일 %H:%M")
    if not problems:
        return (
            f"✅ 교육동향 수집 정상 ({stamp})\n"
            f"수집 {status.get('total', '?')}건 · 기관 {len(status.get('runs') or [])}곳"
        )
    lines = [f"⚠️ 교육동향 수집 점검 ({stamp})", ""]
    lines += [f"• {p}" for p in problems]
    lines += [
        "",
        "게시판 주소가 바뀌었을 수 있습니다.",
        "https://github.com/kain9012-bit/edu-news-alert/actions",
    ]
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("TELEGRAM_BOT_TOKEN/CHAT_ID가 없어 발송을 건너뜁니다.", file=sys.stderr)
        return False
    response = requests.post(
        f"{API_BASE}/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"},
        timeout=TIMEOUT,
    )
    if not response.ok:
        print(f"텔레그램 발송 실패 {response.status_code}: {response.text[:200]}", file=sys.stderr)
        return False
    return True


def main() -> int:
    args = parse_args()
    base = args.base_url.rstrip("/")
    try:
        status = fetch_json(f"{base}/status.json")
        items = fetch_json(f"{base}/news.json")
    except Exception as exc:  # noqa: BLE001
        text = f"⚠️ 교육동향 수집 점검\n\n공개 데이터를 읽지 못했습니다: {type(exc).__name__} {exc}"
        print(text)
        if not args.dry_run:
            send_telegram(text)
        return 0

    problems = check_run_freshness(status)
    problems += check_empty_and_failed(status)
    problems += check_stale_sources(status, items, args.stale_days)

    message = build_message(problems, status)
    print(message)

    if problems or args.always:
        if args.dry_run:
            print("\n[dry-run] 발송하지 않음")
        else:
            send_telegram(message)
    else:
        print("\n이상 없음 — 발송하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
