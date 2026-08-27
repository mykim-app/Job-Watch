#!/usr/bin/env python3
"""매일 09:00 실행 — 수집 → 필터 → 중복 제거 → 저장 → 메일."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import yaml

import notify
import store
from collectors import alio, html_board, worknet
from collectors.base import Posting
from filters import is_public_org, match

KST = timezone(timedelta(hours=9))


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
    if sources.get("alio", {}).get("enabled"):
        raw += alio.fetch(sources["alio"], log)
    if sources.get("worknet", {}).get("enabled"):
        raw += worknet.fetch(sources["worknet"], log)
    for board in sources.get("html_boards", []) or []:
        if board.get("enabled"):
            raw += html_board.fetch(board, log)

    if not raw:
        print("수집된 공고가 0건입니다. 인증키와 설정을 확인하세요.")

    # ── 필터
    kept: list[dict] = []
    for post in raw:
        ok, hits = match(post, f)
        if not ok:
            continue
        if post.source == "worknet" and not is_public_org(post, f):
            continue
        # 접수 시작일을 모르는 곳(HTML 게시판 등)은 날짜로 자르지 않는다
        if post.start_date and post.start_date < cutoff:
            continue
        post.matched = hits
        kept.append(post.to_dict())

    print(f"전산·통신직 필터 통과: {len(kept)}건")

    # ── 중복 제거 & 저장
    existing = store.load()
    merged, new_items = store.merge(existing, kept, today, int(cfg.get("retention_days", 60)))
    store.save(merged, now.strftime("%Y-%m-%d %H:%M"))

    print(f"신규 공고: {len(new_items)}건 / 보관 중: {len(merged['postings'])}건")
    for p in new_items:
        print(f"  + [{p.get('source_label')}] {p.get('org')} — {p.get('title')}")

    notify.send(new_items, today, os.environ.get("SITE_URL", ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
