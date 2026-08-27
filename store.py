"""이미 본 공고를 기억해서, 다음 날엔 신규만 남기는 저장소.

docs/data/postings.json 한 파일에 전부 담는다.
GitHub Actions 가 매일 이 파일을 갱신해서 커밋한다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

DATA_FILE = Path("docs/data/postings.json")


def load() -> dict:
    if not DATA_FILE.exists():
        return {"updated_at": "", "postings": []}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated_at": "", "postings": []}


def merge(existing: dict, fresh: list[dict], today: str, retention_days: int) -> tuple[dict, list[dict]]:
    """기존 데이터에 오늘 수집분을 합치고, (전체, 오늘 신규) 를 돌려준다."""
    by_uid = {p["uid"]: p for p in existing.get("postings", [])}
    known_cross = {p.get("cross_uid") for p in by_uid.values()}

    new_items: list[dict] = []
    for item in fresh:
        if item["uid"] in by_uid:
            # 이미 아는 공고 — 마감일 등만 최신화하고 신규로는 안 친다
            kept = by_uid[item["uid"]]
            item["first_seen"] = kept.get("first_seen", today)
            by_uid[item["uid"]] = item
            continue

        if item.get("cross_uid") in known_cross:
            # 다른 출처에서 이미 본 같은 공고 (예: 잡알리오 + 워크넷 동시 게재)
            item["first_seen"] = today
            item["duplicate_of_other_source"] = True
            by_uid[item["uid"]] = item
            continue

        item["first_seen"] = today
        by_uid[item["uid"]] = item
        known_cross.add(item.get("cross_uid"))
        new_items.append(item)

    cutoff = (date.fromisoformat(today) - timedelta(days=retention_days)).isoformat()
    postings = [p for p in by_uid.values() if p.get("first_seen", today) >= cutoff]
    postings.sort(key=lambda p: (p.get("first_seen", ""), p.get("org", "")), reverse=True)

    return {"updated_at": "", "postings": postings}, new_items


def save(payload: dict, updated_at: str) -> None:
    payload["updated_at"] = updated_at
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
