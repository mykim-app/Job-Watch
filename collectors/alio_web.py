"""잡알리오 웹사이트(job.alio.go.kr) 직접 조회.

공공데이터포털 API(apis.data.go.kr)가 막히는 환경을 위한 대체 경로다.
호스트가 다르고, 인증키가 필요 없다.

NCS 직무를 '정보통신(R600020)'으로 지정해 조회하므로,
제목에 '전산'이 없는 공고("○○공사 하반기 신입직원 채용" 등)도 잡힌다.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

BASE = "https://job.alio.go.kr"
LIST_URL = BASE + "/recruit.do"
VIEW_URL = BASE + "/recruitview.do"
LABEL = "잡알리오"

from .base import Posting, squeeze  # noqa: E402

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL,
}

_IDX = re.compile(r"idx=(\d+)")
# "2026.08.27" 또는 "26.09.11 D-14" 두 가지가 섞여 나온다
_YMD = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_YMD2 = re.compile(r"(\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})")


def _date(text) -> str:
    t = squeeze(text)
    m = _YMD.search(t)
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


def fetch(cfg: dict, log) -> list[Posting]:
    max_pages = int(cfg.get("max_pages", 5))
    codes = cfg.get("ncs_codes") or ["R600020"]      # R600020 = 정보통신
    since_days = int(cfg.get("since_days", 14))

    today = date.today()
    s_date = (today - timedelta(days=since_days)).strftime("%Y.%m.%d")
    e_date = today.strftime("%Y.%m.%d")

    session = requests.Session()
    try:
        session.get(LIST_URL, headers=HEADERS, timeout=40).raise_for_status()
    except Exception as e:  # noqa: BLE001
        log(f"잡알리오(웹): 첫 접속 실패 — {e}")
        return []

    seen: set[str] = set()
    out: list[Posting] = []

    for page in range(1, max_pages + 1):
        data = [("pageNo", str(page)), ("s_date", s_date), ("e_date", e_date)]
        data += [("detail_code", c) for c in codes]

        try:
            r = session.post(LIST_URL, headers=HEADERS, data=data, timeout=40)
            r.raise_for_status()
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
            href = link.get("href", "") if link else ""
            m = _IDX.search(href)
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
                    ncs="정보통신",          # 분류가 확실하므로 키워드 필터를 통과시킨다
                )
            )
            added += 1

        if added == 0 or len(rows) < 10:
            break

    log(f"잡알리오(웹): {len(out)}건 수집")
    return out
