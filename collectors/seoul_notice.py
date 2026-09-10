"""서울특별시 채용공고 게시판(seoul.go.kr/news/news_employ.do).

서울시 본청·산하기관·투자출연기관 공고가 모이는 곳이다. 인증키가 필요 없다.

이 게시판 검색은 **첨부 공고문 본문까지 훑는다.** 그래서 제목에 직렬이 안 드러나는
"서울교통공사 9호선운영부문 공개채용" 같은 공고도 '통신'으로 검색된다.
클린아이는 기관이 모집분야를 비워두면 알 길이 없는데, 여기가 그 구멍을 메운다.

검색으로 찾은 것이므로 걸린 키워드를 직무 칸에 넣어 필터를 통과시킨다.
대신 본문 어딘가에 낱말이 스쳐 지나간 공고도 딸려 오므로,
제외 규칙(합격자 발표·임기제·계약직 등)이 그대로 적용된다.
"""

from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from .base import Posting, parse_ymd, request, squeeze

BASE = "https://www.seoul.go.kr"
LIST_URL = BASE + "/news/news_employ.do"
BBS_NO = "166"
LABEL = "서울시 채용공고"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL,
}

_NTT = re.compile(r"fnTbbsView\(\s*'(\d+)'\s*\)")


def fetch(cfg: dict, log) -> list[Posting]:
    keywords = cfg.get("query_keywords") or ["전산", "정보통신", "정보보안", "정보화", "통신"]
    max_pages = int(cfg.get("max_pages", 2))
    delay = float(cfg.get("delay", 1.2))
    bbs_no = str(cfg.get("bbs_no", BBS_NO))

    session = requests.Session()
    seen: set[str] = set()
    out: list[Posting] = []

    for kw in keywords:
        for page in range(1, max_pages + 1):
            params = {"srchText": kw, "curPage": page}
            try:
                r = request(session, "GET", LIST_URL, log, f"서울시공고 '{kw}' {page}p",
                            delay=delay, params=params, headers=HEADERS, timeout=40)
                soup = BeautifulSoup(r.text, "lxml")
            except Exception as e:  # noqa: BLE001
                log(f"서울시 채용공고 '{kw}' {page}p 실패: {type(e).__name__}")
                break

            table = soup.select_one("table.sib-lst-type-basic")
            rows = table.select("tbody tr") if table else []
            if not rows:
                break

            added = 0
            for tr in rows:
                tds = tr.select("td")
                if len(tds) < 5:
                    continue
                link = tds[1].select_one("a")
                if link is None:
                    continue

                m = _NTT.search(link.get("href", "") or "")
                ntt = m.group(1) if m else ""
                if ntt and ntt in seen:
                    continue
                if ntt:
                    seen.add(ntt)

                title = squeeze(link.get_text())
                if not title:
                    continue

                dept = squeeze(tds[2].get_text())
                out.append(
                    Posting(
                        source="seoul_notice",
                        source_label=LABEL,
                        org=dept or "서울특별시",
                        title=title,
                        url=f"{LIST_URL}?bbsNo={bbs_no}&nttNo={ntt}" if ntt else LIST_URL,
                        start_date=parse_ymd(tds[3].get_text()),
                        end_date=parse_ymd(tds[4].get_text()),
                        region="서울",
                        ncs=kw,          # 검색으로 걸린 낱말을 직무 칸에 넣는다
                    )
                )
                added += 1

            if added == 0 or len(rows) < 10:
                break

    log(f"서울시 채용공고: {len(out)}건 수집")
    return out
