"""한국 기준 근무일 판정.

주말과 공휴일(설·추석 같은 음력 명절, 대체공휴일, 임시공휴일)을 제외한다.

공휴일 목록은 세 단계로 구한다.
 1) 공공데이터포털 '한국천문연구원_특일 정보' API — 가장 정확하고 임시공휴일까지 반영된다.
    HOLIDAY_SERVICE_KEY(없으면 ALIO_SERVICE_KEY)를 쓴다. 연 단위로 받아 .cache 에 둔다.
 2) holidays 파이썬 패키지 — 인증키가 없거나 API 가 안 될 때.
 3) 둘 다 안 되면 주말만 제외한다.

임시공휴일이 연중에 지정될 수 있어 캐시는 2주마다 다시 받는다.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

API = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"
CACHE_DIR = Path(".cache")
REFRESH_DAYS = 14


def _cache_path(year: int) -> Path:
    return CACHE_DIR / f"holidays_{year}.json"


def _from_api(year: int, key: str, log) -> set[str] | None:
    got: set[str] = set()
    session = requests.Session()
    for month in range(1, 13):
        params = {
            "serviceKey": key,
            "solYear": str(year),
            "solMonth": f"{month:02d}",
            "_type": "json",
            "numOfRows": "50",
        }
        try:
            r = session.get(API, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            log(f"  공휴일 API {year}-{month:02d} 실패: {type(e).__name__}")
            return None

        if "OpenAPI_ServiceResponse" in data:            # 인증 오류 등
            msg = (data["OpenAPI_ServiceResponse"].get("cmmMsgHeader") or {}).get("errMsg", "")
            log(f"  공휴일 API 오류: {msg}")
            return None

        body = (data.get("response") or {}).get("body") or {}
        items = (body.get("items") or {}).get("item")
        if items is None:
            continue
        if isinstance(items, dict):
            items = [items]
        for it in items:
            if str(it.get("isHoliday", "Y")).upper() != "Y":
                continue
            d = str(it.get("locdate", ""))
            if len(d) == 8:
                got.add(f"{d[:4]}-{d[4:6]}-{d[6:]}")
    return got


def _from_package(year: int, log) -> set[str] | None:
    try:
        import holidays as _h
    except ImportError:
        return None
    try:
        return {d.isoformat() for d in _h.KR(years=year).keys()}
    except Exception as e:  # noqa: BLE001
        log(f"  holidays 패키지 오류: {type(e).__name__}")
        return None


def holidays_for(year: int, log) -> set[str] | None:
    """해당 연도 공휴일 집합. 못 구하면 None."""
    path = _cache_path(year)
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            fetched = date.fromisoformat(cached.get("fetched", "1970-01-01"))
            if (date.today() - fetched).days < REFRESH_DAYS:
                return set(cached.get("days", []))
        except Exception:  # noqa: BLE001
            pass

    key = (os.environ.get("HOLIDAY_SERVICE_KEY")
           or os.environ.get("ALIO_SERVICE_KEY") or "").strip()

    days = _from_api(year, key, log) if key else None
    source = "특일정보 API"
    if days is None:
        days = _from_package(year, log)
        source = "holidays 패키지"
    if days is None:
        log("  공휴일 목록을 못 구해 주말만 제외합니다")
        return None

    log(f"  {year}년 공휴일 {len(days)}일 확인 ({source})")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(
            {"fetched": date.today().isoformat(), "source": source,
             "days": sorted(days)}, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return days


def is_workday(day: date, log) -> tuple[bool, str]:
    """(근무일인지, 사유)"""
    if day.weekday() >= 5:
        return False, "주말"
    days = holidays_for(day.year, log)
    if days and day.isoformat() in days:
        return False, "공휴일"
    return True, ""
