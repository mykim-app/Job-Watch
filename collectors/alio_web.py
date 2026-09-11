"""잡알리오 웹사이트(job.alio.go.kr) 직접 조회.

공공데이터포털 API(apis.data.go.kr)가 막히는 환경을 위한 대체 경로다.
호스트가 다르고, 인증키가 필요 없다.

NCS 직무를 '정보통신(R600020)'으로 지정해 조회하므로,
제목에 '전산'이 없는 공고("○○공사 하반기 신입직원 채용" 등)도 잡힌다.

목록의 고용형태는 '비정규직 외 1' 처럼 줄여서 나온다. 나머지가 정규직인지
청년인턴인지 알 수 없으므로, 이 표시가 붙은 공고만 상세를 열어 실제 고용형태로
바꿔 넣는다. 한 번 확인한 공고는 .cache 에 남겨 다시 열지 않는다.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import Posting, request, squeeze

BASE = "https://job.alio.go.kr"
LIST_URL = BASE + "/recruit.do"
VIEW_URL = BASE + "/recruitview.do"
LABEL = "잡알리오"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL,
}

CACHE_FILE = Path(".cache/alio_employment.json")

_IDX = re.compile(r"idx=(\d+)")
_MULTI = re.compile(r"외\s*\d+")
# 상세 페이지의 "고용형태 비정규직,정규직 대체인력여부 ..." 구간
_EMP = re.compile(r"고용형태\s*(.*?)\s*(?:대체인력여부|근무지|급여정보)")
# "2026.08.27" 또는 "26.09.11 D-14"
_YMD4 = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_YMD2 = re.compile(r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def _date(text) -> str:
    t = squeeze(text)
    m = _YMD4.search(t)
    if m:
        y, mo, d = m.groups()
    else:
        m = _YMD2.search(t)
        if not m:
            return ""
        y, mo, d = m.groups()
        y = "20" + y
    try:
        return date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return ""


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if len(cache) > 4000:
            cache = dict(list(cache.items())[-2000:])
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _real_employment(session, idx, log, delay) -> str:
    """상세 페이지에서 실제 고용형태를 읽는다. 실패하면 빈 문자열."""
    try:
        r = request(session, "GET", VIEW_URL, log, f"잡알리오 상세 {idx}", tries=2,
                    delay=delay, params={"idx": idx}, headers=HEADERS, timeout=40)
        text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
    except Exception as e:  # noqa: BLE001
        log(f"  잡알리오 상세 {idx} 못 읽음: {type(e).__name__}")
        return ""
    m = _EMP.search(text)
    return squeeze(m.group(1))[:60] if m else ""


def fetch(cfg: dict, log) -> list[Posting]:
    max_pages = int(cfg.get("max_pages", 12))
    codes = cfg.get("ncs_codes") or ["R600020"]      # R600020 = 정보통신
    since_days = int(cfg.get("since_days", 30))
    delay = float(cfg.get("delay", 1.2))
    resolve_multi = bool(cfg.get("resolve_multi_employment", True))
    max_detail = int(cfg.get("max_detail", 30))

    today = date.today()
    s_date = (today - timedelta(days=since_days)).strftime("%Y.%m.%d")
    e_date = today.strftime("%Y.%m.%d")

    # 잡알리오는 같은 세션에서 조회를 반복하면 직전 조건을 기억한다. 매번 새 세션으로 시작한다.
    session = requests.Session()
    try:
        request(session, "GET", LIST_URL, log, "잡알리오(웹) 첫 접속",
                delay=delay, headers=HEADERS, timeout=40)
    except Exception as e:  # noqa: BLE001
        log(f"잡알리오(웹): 첫 접속 실패 — {e}")
        return []

    seen: set[str] = set()
    out: list[Posting] = []

    for page in range(1, max_pages + 1):
        data = [("pageNo", str(page)), ("s_date", s_date), ("e_date", e_date)]
        data += [("detail_code", c) for c in codes]

        try:
            r = request(session, "POST", LIST_URL, log, f"잡알리오(웹) {page}p",
                        delay=delay, headers=HEADERS, data=data, timeout=40)
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
        except Exception as e:  # noqa: BLE001
            log(f"잡알리오(웹) {page}p 조회 실패: {e}")
            break

        table = soup.select_one("table.type_03")
        rows = table.select("tbody tr") if table else []
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.select("td")
            if len(tds) < 8:
                continue

            link = tds[2].select_one("a")
            m = _IDX.search(link.get("href", "") if link else "")
            idx = m.group(1) if m else ""
            if idx and idx in seen:
                continue
            if idx:
                seen.add(idx)

            title = squeeze(tds[2].get_text())
            if not title:
                continue

            out.append(
                Posting(
                    source="alio",
                    source_label=LABEL,
                    org=squeeze(tds[3].get_text()),
                    title=title,
                    url=f"{VIEW_URL}?idx={idx}" if idx else "",
                    start_date=_date(tds[6].get_text()),
                    end_date=_date(tds[7].get_text()),
                    hire_type=squeeze(tds[5].get_text()),
                    region=squeeze(tds[4].get_text()).split("\n")[0],
                    ncs="정보통신",      # 분류가 확실하므로 키워드 필터를 통과시킨다
                )
            )
            added += 1

        if added == 0 or len(rows) < 10:
            break

    # ── '비정규직 외 1' 처럼 줄여 쓴 것은 상세를 열어 실제 고용형태로 바꾼다
    resolved = 0
    if resolve_multi:
        cache = _load_cache()
        for p in out:
            if not _MULTI.search(p.hire_type):
                continue
            idx = p.url.rsplit("idx=", 1)[-1]
            if not idx.isdigit():
                continue

            real = cache.get(idx)
            if real is None:
                if resolved >= max_detail:
                    continue
                resolved += 1
                real = _real_employment(session, idx, log, delay)
                cache[idx] = real
            if real:
                p.hire_type = real
        _save_cache(cache)

    log(f"잡알리오(웹): {len(out)}건 수집" +
        (f" (고용형태 확인 {resolved}건)" if resolved else ""))
    return out
