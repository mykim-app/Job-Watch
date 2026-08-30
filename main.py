#!/usr/bin/env python3
"""매일 09:00 실행 — 수집 → 필터 → 중복 제거 → 저장 → 메일."""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone

import yaml

import notify
import store
from collectors.base import Posting
from filters import is_public_org, match, match_open

KST = timezone(timedelta(hours=9))

# (config 의 sources 키, collectors 모듈명, 로그에 쓸 이름)
# 파일이 없거나 오류가 나도 그 출처만 건너뛰고 나머지는 계속 수집한다.
COLLECTORS = [
    ("alio", "alio", "잡알리오(API)"),
    ("alio_web", "alio_web", "잡알리오(웹)"),
    ("cleaneye", "cleaneye", "클린아이"),
    ("gojobs", "gojobs", "나라일터"),
    ("procollege", "procollege", "전문대학포털"),
    ("uman", "uman", "대학교직원신문"),
    ("saramin", "saramin", "사람인"),
    ("worknet", "worknet", "고용24"),
]


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


def main() -> int:
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    f = cfg.get("filters", {})
    sources = cfg.get("sources", {})
    now = datetime.now(KST)
    today = now.date().isoformat()
    cutoff = (now.date() - timedelta(days=int(cfg.get("lookback_days", 5)))).isoformat()

    print(f"[{now:%Y-%m-%d %H:%M} KST] 수집 시작")

    raw: list[Posting] = []
    failed: list[str] = []

    for key, module_name, label in COLLECTORS:
        conf = sources.get(key)
        if not (isinstance(conf, dict) and conf.get("enabled")):
            continue
        try:
            mod = importlib.import_module(f"collectors.{module_name}")
        except Exception as e:  # noqa: BLE001
            log(f"{label}: 수집기 파일을 못 읽어 건너뜀 — {type(e).__name__}: {e}")
            failed.append(label)
            continue
        try:
            raw += mod.fetch(conf, log)
        except Exception as e:  # noqa: BLE001
            log(f"{label}: 수집 중 오류로 건너뜀 — {type(e).__name__}: {e}")
            failed.append(label)

    for board in sources.get("html_boards", []) or []:
        if not board.get("enabled"):
            continue
        name = board.get("name", board.get("key", "게시판"))
        try:
            from collectors import html_board
            raw += html_board.fetch(board, log)
        except Exception as e:  # noqa: BLE001
            log(f"{name}: 수집 중 오류로 건너뜀 — {type(e).__name__}: {e}")
            failed.append(name)

    if not raw:
        print("수집된 공고가 0건입니다. 인증키와 설정을 확인하세요.")

    # ── 필터
    drop_closed = bool(cfg.get("drop_closed", True))
    closed = 0
    kept: list[dict] = []
    open_sources = f.get("open_sources") or {}

    for post in raw:
        ok, hits = match(post, f)
        rule = open_sources.get(post.source)
        if rule and not ok:
            # 전산·통신직이 아니어도 지정한 고용형태면 담는다 (대학교직원신문 등)
            ok, hits = match_open(post, f, rule)
        if not ok:
            continue
        # 사람인·고용24 는 민간기업이 대부분이라 기관명으로 한 번 더 거른다
        if post.source in ("saramin", "worknet") and not is_public_org(post, f):
            continue
        # 접수 시작일을 모르는 곳(HTML 게시판 등)은 날짜로 자르지 않는다
        if post.start_date and post.start_date < cutoff:
            continue
        # 접수가 이미 끝난 공고는 받지 않는다 (마감일이 없으면 상시채용으로 보고 남김)
        if drop_closed and post.end_date and post.end_date < today:
            closed += 1
            continue
        post.matched = hits
        kept.append(post.to_dict())

    print(f"전산·통신직 필터 통과: {len(kept)}건" + (f" (마감 지난 공고 {closed}건 제외)" if closed else ""))

    # ── 중복 제거 & 저장
    existing = store.load()
    merged, new_items, expired = store.merge(
        existing, kept, today, int(cfg.get("retention_days", 60)), drop_closed
    )
    if expired:
        print(f"보관 목록에서 마감된 공고 {expired}건 정리")
    merged["failed_sources"] = failed
    store.save(merged, now.strftime("%Y-%m-%d %H:%M"))

    print(f"신규 공고: {len(new_items)}건 / 보관 중: {len(merged['postings'])}건")
    for p in new_items:
        print(f"  + [{p.get('source_label')}] {p.get('org')} — {p.get('title')}")

    if failed:
        print(f"⚠ 수집 실패한 곳: {', '.join(failed)} (나머지는 정상 수집됨)")

    notify.send(new_items, today, os.environ.get("SITE_URL", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
