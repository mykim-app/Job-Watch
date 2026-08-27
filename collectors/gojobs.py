"""나라일터 — 공무원·공공기관 경력채용 공고.

일반 HTML 목록이라 그대로 읽는다. 인증키가 필요 없다.
목록이 10건씩만 나오므로 키워드별로 나눠서 조회한다.
"""

from __future__ import annotations

import re
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

from .base import Posting, parse_ymd, squeeze

BASE = "https://www.gojobs.go.kr"
LIST_URL = BASE + "/apmList.do"
VIEW_URL = BASE + "/apmView.do"
LABEL = "나라일터"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; job-watch/1.0)",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# javascript:fn_apmView('020', '302196') 에서 뒤 숫자가 공고 번호
_VIEW_ID = re.compile(r"fn_apmView\(\s*'[^']*'\s*,\s*'(\d+)'\s*\)")


def _list_table(soup: BeautifulSoup):
    """머리글에 '공고명' 이 있는 표를 찾는다."""
    for t in soup.select("table"):
        heads = " ".join(x.get_text(strip=True) for x in t.select("th"))
        if "공고명" in heads and t.select("tbody tr"):
            return t
    return None


def fetch(cfg: dict, log) -> list[Posting]:
    max_pages = int(cfg.get("max_pages", 3))
    keywords = cfg.get("query_keywords") or [""]
    session = requests.Session()

    seen: set[str] = set()
    out: list[Posting] = []

    for kw in keywords:
        for page in range(1, max_pages + 1):
            params = {
                "menuNo": "401",
                "mngrMenuYn": "N",
                "selMenuNo": "400",
                "pageIndex": page,
            }
            if kw:
                params["searchKeyword"] = kw

            try:
                r = session.get(LIST_URL, params=params, headers=HEADERS, timeout=40)
                r.raise_for_status()
                r.encoding = r.apparent_encoding or "utf-8"
                soup = BeautifulSoup(r.text, "lxml")
            except Exception as e:  # noqa: BLE001
                log(f"나라일터 '{kw}' {page}p 조회 실패: {e}")
                break

            table = _list_table(soup)
            if table is None:
                break

            rows = table.select("tbody tr")
            if not rows:
                break

            for tr in rows:
                tds = tr.select("td")
                if len(tds) < 5:
                    continue

                link = tds[1].select_one("a")
                title = squeeze(link.get_text()) if link else squeeze(tds[1].get_text())
                if not title:
                    continue

                url = ""
                if link:
                    m = _VIEW_ID.search(link.get("href", ""))
                    if m:
                        url = f"{VIEW_URL}?empmnsn={m.group(1)}"
                key = url or title
                if key in seen:
                    continue
                seen.add(key)

                out.append(
                    Posting(
                        source="gojobs",
                        source_label=LABEL,
                        org=squeeze(tds[2].get_text()),
                        title=title,
                        url=url,
                        start_date=parse_ymd(tds[3].get_text()),
                        end_date=parse_ymd(tds[4].get_text()),
                    )
                )

            if len(rows) < 10:
                break

    log(f"나라일터: {len(out)}건 수집")
    return out
