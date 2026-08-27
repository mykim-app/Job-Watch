"""사람인 채용정보 오픈API.

oapi.saramin.co.kr 에서 이용신청 → 승인 → 앱 등록 후 받은 키를 SARAMIN_ACCESS_KEY 로 넣는다.
호출 한도가 하루 500건이므로 키워드 수 × 페이지 수를 너무 늘리지 않는다.

사람인은 민간기업 공고가 대부분이라, 기관명이 공사·공단·재단·협회 …에 걸리는 것만 남긴다.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

from .base import Posting, parse_ymd, squeeze

ENDPOINT = "https://oapi.saramin.co.kr/job-search"
LABEL = "사람인"


KST = timezone(timedelta(hours=9))


def _date(value) -> str:
    """사람인은 'Wed, 27 Aug 2026 09:10:00 +0900' 또는 Unix timestamp 로 준다."""
    v = squeeze(value)
    if not v:
        return ""
    try:
        return parsedate_to_datetime(v).astimezone(KST).date().isoformat()
    except Exception:  # noqa: BLE001
        pass
    if v.isdigit() and len(v) >= 10:
        try:
            return datetime.fromtimestamp(int(v[:10]), KST).date().isoformat()
        except Exception:  # noqa: BLE001
            pass
    return parse_ymd(v)


def _dig(obj, *path):
    """중첩 dict 에서 값을 안전하게 꺼낸다."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return ""
        cur = cur.get(key)
    if isinstance(cur, dict):
        cur = cur.get("name") or cur.get("code") or ""
    return squeeze(cur)


def _jobs(payload) -> list:
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs")
    if isinstance(jobs, dict):
        job = jobs.get("job")
        if isinstance(job, list):
            return [j for j in job if isinstance(j, dict)]
        if isinstance(job, dict):
            return [job]
    if isinstance(jobs, list):
        return [j for j in jobs if isinstance(j, dict)]
    return []


def fetch(cfg: dict, log) -> list[Posting]:
    key = os.environ.get("SARAMIN_ACCESS_KEY", "").strip()
    if not key:
        log("사람인: SARAMIN_ACCESS_KEY 가 없어 건너뜀")
        return []

    count = min(int(cfg.get("count", 100)), 110)
    max_pages = int(cfg.get("max_pages", 2))
    since_days = int(cfg.get("since_days", 7))
    published_min = (date.today() - timedelta(days=since_days)).isoformat() + " 00:00:00"

    session = requests.Session()
    seen: set[str] = set()
    out: list[Posting] = []

    for kw in cfg.get("query_keywords", []):
        for page in range(max_pages):
            params = {
                "access-key": key,
                "keywords": kw,
                "count": count,
                "start": page,
                "sort": "pd",                       # 게시일 역순
                "fields": "posting-date,expiration-date",
                "published_min": published_min,
            }
            try:
                r = session.get(ENDPOINT, params=params, timeout=40,
                                headers={"Accept": "application/json"})
                r.raise_for_status()
                rows = _jobs(r.json())
            except Exception as e:  # noqa: BLE001
                log(f"사람인 '{kw}' {page + 1}p 조회 실패: {e}")
                break

            if not rows:
                break

            for row in rows:
                jid = squeeze(row.get("id"))
                if jid and jid in seen:
                    continue
                if jid:
                    seen.add(jid)

                title = _dig(row, "position", "title")
                if not title:
                    continue

                out.append(
                    Posting(
                        source="saramin",
                        source_label=LABEL,
                        org=_dig(row, "company", "detail", "name"),
                        title=title,
                        url=squeeze(row.get("url")),
                        start_date=_date(row.get("posting-date") or row.get("posting-timestamp")),
                        end_date=_date(row.get("expiration-date") or row.get("expiration-timestamp")),
                        hire_type=_dig(row, "position", "job-type"),
                        recruit_type=_dig(row, "position", "experience-level"),
                        region=_dig(row, "position", "location"),
                    )
                )

            if len(rows) < count:
                break

    log(f"사람인: {len(out)}건 수집 (기관명 필터 적용 전)")
    return out
