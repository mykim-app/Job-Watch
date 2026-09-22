"""이미 본 공고를 기억해서, 다음 날엔 신규만 남기는 저장소.

docs/data/postings.json 한 파일에 전부 담는다.
NAS 가 매일 이 파일을 갱신해서 GitHub 에 커밋한다.

자가 복구:
 1) 같은 공고(uid)가 오늘도 다시 수집되면, 마감일 등 필드가 통째로
    새 값으로 덮어써진다. 수집기 쪽 파싱 버그를 고쳤다면 그 공고가
    다음에 다시 수집되는 순간 저장된 값도 저절로 바로잡힌다.
 2) 다만 사이트 목록에서 밀려나 아예 재수집이 안 되면 위 방법으로는
    못 고친다. 그래서 "마지막으로 확인된 날(last_confirmed)"을 같이
    기록해두고, 마감일이 비어 있는(=상시채용으로 취급되는) 공고가
    OPEN_ENDED_GRACE_DAYS 이상 재확인되지 않으면 더는 목록에 없는
    것으로 보고 화면에서 정리한다. 파싱 실패로 마감일이 빈 채 영구히
    남는 것을 막기 위한 안전장치다.
    마감일이 정상적으로 찍힌 공고는 이 규칙과 무관하다 — 그쪽은 실제
    마감일이 지나야만 빠진다.
 3) 화면에 보이는 D-day 는 저장 당시 값이 아니라, 매번 오늘 날짜
    기준으로 다시 계산해서 저장한다. 며칠째 재수집이 안 된 공고라도
    D-day 표시는 항상 정확하다.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

DATA_FILE = Path("docs/data/postings.json")

# 마감일 없이(=상시채용 취급) 이 기간 이상 재확인 안 되면 화면에서 정리한다.
# 대부분의 수집처가 매번 사이트의 현재 목록을 그대로 훑으므로, 계속 안 잡힌다는 건
# 실제로 사이트에서 내려갔다는 뜻일 가능성이 높다. 다만 하루이틀 안 잡힌 것만으로
# 지우면 페이지 수 제한 등으로 인한 일시적 누락까지 지울 수 있어 넉넉히 잡는다.
OPEN_ENDED_GRACE_DAYS = 14


def load() -> dict:
    if not DATA_FILE.exists():
        return {"updated_at": "", "postings": []}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated_at": "", "postings": []}


def _recalc_dday(p: dict, today_d: date) -> None:
    end = p.get("end_date")
    if not end:
        p["d_day"] = None
        return
    try:
        p["d_day"] = (date.fromisoformat(end) - today_d).days
    except ValueError:
        p["d_day"] = None


def merge(existing: dict, fresh: list[dict], today: str, retention_days: int,
          drop_closed: bool = True) -> tuple[dict, list[dict], int]:
    """기존 데이터에 오늘 수집분을 합치고, (전체, 오늘 신규, 정리된 건수) 를 돌려준다."""
    by_uid = {p["uid"]: p for p in existing.get("postings", [])}
    known_cross = {p.get("cross_uid") for p in by_uid.values()}
    fresh_uids = {item["uid"] for item in fresh}

    new_items: list[dict] = []
    for item in fresh:
        item["last_confirmed"] = today

        if item["uid"] in by_uid:
            # 이미 아는 공고 — 필드를 통째로 새 값으로 덮어쓴다.
            # (파싱 버그를 고친 뒤 이 공고가 다시 수집되면 여기서 저절로 바로잡힌다)
            kept = by_uid[item["uid"]]
            item["first_seen"] = kept.get("first_seen", today)
            by_uid[item["uid"]] = item
            continue

        if item.get("cross_uid") in known_cross:
            # 다른 출처에서 이미 본 같은 공고 (예: 잡알리오 + 나라일터 동시 게재)
            item["first_seen"] = today
            item["duplicate_of_other_source"] = True
            by_uid[item["uid"]] = item
            continue

        item["first_seen"] = today
        by_uid[item["uid"]] = item
        known_cross.add(item.get("cross_uid"))
        new_items.append(item)

    # 오늘 재수집되지 않은 기존 기록은 last_confirmed 를 그대로 둔다
    # (한 번도 기록된 적 없으면 first_seen 으로 채워 넣는다 — 옛 데이터 호환용)
    for uid, p in by_uid.items():
        if uid not in fresh_uids and not p.get("last_confirmed"):
            p["last_confirmed"] = p.get("first_seen", today)

    cutoff = (date.fromisoformat(today) - timedelta(days=retention_days)).isoformat()
    postings = [p for p in by_uid.values() if p.get("first_seen", today) >= cutoff]

    # 여러 수집처에서 들어온 같은 공고는 하나만 남긴다.
    # 먼저 발견한 쪽을 본체로 두고 나머지는 표시만 해서 화면에서 뺀다
    # (기록은 남겨야 나중에 다시 신규로 잡히지 않는다).
    primary: dict[str, dict] = {}
    for p in sorted(postings, key=lambda x: (x.get("first_seen", ""), x.get("source", ""))):
        c = p.get("cross_uid")
        if not c:
            continue
        if c in primary and primary[c] is not p:
            p["duplicate_of_other_source"] = True
        else:
            primary[c] = p
            p.pop("duplicate_of_other_source", None)

    today_d = date.fromisoformat(today)
    removed = 0

    if drop_closed:
        before = len(postings)
        # 마감일이 실제로 지난 공고는 뺀다 (마감 당일까지는 남긴다)
        postings = [p for p in postings if not (p.get("end_date") and p["end_date"] < today)]
        removed += before - len(postings)

        # 마감일이 비어 있는(=상시채용 취급) 공고가 오래 재확인 안 되면 정리한다.
        # 실제 상시채용이면 사이트가 계속 보여줄 테니 매번 재확인되어 안 지워진다.
        def _stale(p: dict) -> bool:
            if p.get("end_date"):
                return False
            lc = p.get("last_confirmed") or p.get("first_seen") or today
            try:
                gone = (today_d - date.fromisoformat(lc)).days
            except ValueError:
                return False
            return gone > OPEN_ENDED_GRACE_DAYS

        before = len(postings)
        postings = [p for p in postings if not _stale(p)]
        removed += before - len(postings)

    for p in postings:
        _recalc_dday(p, today_d)

    postings.sort(key=lambda p: (p.get("first_seen", ""), p.get("org", "")), reverse=True)

    return {"updated_at": "", "postings": postings}, new_items, removed


def save(payload: dict, updated_at: str) -> None:
    payload["updated_at"] = updated_at
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8"
    )
