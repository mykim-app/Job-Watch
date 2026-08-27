"""전문대학포털(procollege.kr) 교직원채용 게시판 — 전문대학 직원 채용.

채용구분을 '직원(bTmp3=2)'으로 좁혀서 조회한다. 교수 초빙 공고는 제외된다.
인증키가 필요 없다.

전산직 공고 자체가 드문 곳이라 수확은 적지만, 요청이 하루 한두 번이라 부담이 없다.
마감일을 목록에 안 주므로 end_date 는 비워 둔다(상시로 취급되어 보관 기간까지 남는다).
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .base import Posting, parse_ymd, request, squeeze

BASE = "https://www.procollege.kr"
LIST_URL = BASE + "/web/board/8321.do"
LABEL = "전문대학포털"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL,
}

_IDX = re.compile(r"fn_goView\(\s*'(\d+)'\s*\)")


def fetch(cfg: dict, log) -> list[Posting]:
    page_unit = int(cfg.get("page_unit", 50))
    max_pages = int(cfg.get("max_pages", 1))
    delay = float(cfg.get("delay", 1.2))

    session = requests.Session()
    seen: set[str] = set()
    out: list[Posting] = []

    for page in range(1, max_pages + 1):
        data = {
            "bTmp3": "2",          # 1=교수, 2=직원
            "pageUnit": str(page_unit),
            "pageIndex": str(page),
        }
        try:
            r = request(session, "POST", LIST_URL, log, f"전문대학포털 {page}p",
                        delay=delay, headers=HEADERS, data=data, timeout=40)
            r.encoding = r.apparent_encoding or "utf-8"
            soup = BeautifulSoup(r.text, "lxml")
        except Exception as e:  # noqa: BLE001
            log(f"전문대학포털 {page}p 조회 실패: {e}")
            break

        table = soup.select_one("table.tb01")
        rows = table.select("tbody tr") if table else []
        if not rows:
            break

        added = 0
        for tr in rows:
            tds = tr.select("td")
            if len(tds) < 7:
                continue

            link = tds[4].select_one("a")
            if link is None:
                continue
            m = _IDX.search(link.get("onclick", "") or "")
            idx = m.group(1) if m else ""
            if idx and idx in seen:
                continue
            if idx:
                seen.add(idx)

            title = squeeze(link.get_text())
            if not title:
                continue

            out.append(
                Posting(
                    source="procollege",
                    source_label=LABEL,
                    org=squeeze(tds[3].get_text()),
                    title=title,
                    url=f"{LIST_URL}?mode=view&idx={idx}&pageUnit={page_unit}" if idx else "",
                    start_date=parse_ymd(tds[6].get_text()),
                    region=squeeze(tds[2].get_text()),
                    hire_type="직원",
                )
            )
            added += 1

        if added == 0 or len(rows) < page_unit:
            break

    log(f"전문대학포털: {len(out)}건 수집")
    return out
