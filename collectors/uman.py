"""대학교직원신문(uman.kr) [직원]채용 게시판 — 4년제·전문대 교직원 채용.

사립대 공고가 모이는 거의 유일한 곳이다. 인증키가 필요 없다.
해외 IP 는 서버가 403 으로 막으므로 국내(NAS)에서만 동작한다.

목록에 마감일 칸이 없는 대신 제목 끝에 "(~09. 13(일) 17:00)" 처럼 적혀 있어서
거기서 마감일을 뽑아 쓴다. 못 뽑으면 상시로 취급한다.
"""

from __future__ import annotations

import re
from datetime import date

import requests
from bs4 import BeautifulSoup

from .base import Posting, request, squeeze

BASE = "https://www.uman.kr"
LIST_URL = BASE + "/board/index.html"
BOARD_ID = "talk4"          # [직원]채용
LABEL = "대학교직원신문"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": f"{LIST_URL}?id={BOARD_ID}",
}

_NO = re.compile(r"[?&]no=(\d+)")
# "~09. 13(일)" / "~26.09.02" / "~.08.31.(월)" / "~ 9. 3.(목)"
_DEADLINE = re.compile(r"~\s*\.?\s*(?:(\d{2})\s*[.\-]\s*)?(\d{1,2})\s*[.\-]\s*(\d{1,2})")
# 목록 등록일 칸: "2026-08-25" 또는 당일이면 "16:56:22"
_YMD = re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})")
_HMS = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")


def _posted(text, today: date) -> str:
    t = squeeze(text)
    m = _YMD.search(t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            return ""
    if _HMS.match(t):            # 시각만 있으면 오늘 올라온 글
        return today.isoformat()
    return ""


def _deadline(title: str, today: date) -> str:
    m = _DEADLINE.search(title)
    if not m:
        return ""
    yy, mo, dd = m.groups()
    try:
        mo, dd = int(mo), int(dd)
        if yy:
            return date(2000 + int(yy), mo, dd).isoformat()
        d = date(today.year, mo, dd)
        # 12월 공고에 1월 마감이 적힌 경우를 넘겨 준다
        if (d - today).days < -120:
            d = date(today.year + 1, mo, dd)
        return d.isoformat()
    except ValueError:
        return ""


def fetch(cfg: dict, log) -> list[Posting]:
    max_pages = int(cfg.get("max_pages", 4))
    delay = float(cfg.get("delay", 1.2))
    page_param = cfg.get("page_param", "page")
    today = date.today()

    session = requests.Session()
    seen: set[str] = set()
    first_of_prev_page = None
    out: list[Posting] = []

    for page in range(1, max_pages + 1):
        params = {"id": BOARD_ID}
        if page > 1:
            params[page_param] = page

        try:
            r = request(session, "GET", LIST_URL, log, f"대학교직원신문 {page}p",
                        delay=delay, params=params, headers=HEADERS, timeout=40)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.text, "lxml")
        except Exception as e:  # noqa: BLE001
            log(f"대학교직원신문 {page}p 조회 실패: {e}")
            break

        links = [a for a in soup.select("a[href]")
                 if BOARD_ID in a.get("href", "") and _NO.search(a.get("href", ""))]
        if not links:
            break

        # 페이지 파라미터가 안 먹으면 1페이지가 계속 나온다. 그때는 멈춘다.
        head = _NO.search(links[0].get("href", "")).group(1)
        if page > 1 and head == first_of_prev_page:
            log(f"대학교직원신문: {page}p 가 앞 페이지와 같아 중단 (페이지 파라미터 확인 필요)")
            break
        first_of_prev_page = head

        added = 0
        for a in links:
            no = _NO.search(a.get("href", "")).group(1)
            if no in seen:
                continue
            seen.add(no)

            title = squeeze(a.get_text())
            if not title:
                continue

            tr = a.find_parent("tr")
            tds = tr.select("td") if tr else []
            if len(tds) < 5:
                continue

            num = squeeze(tds[0].get_text())
            if num == "공지" and cfg.get("skip_notice", False):
                continue

            out.append(
                Posting(
                    source="uman",
                    source_label=LABEL,
                    org=squeeze(tds[2].get_text()),
                    title=title,
                    url=f"{LIST_URL}?id={BOARD_ID}&no={no}",
                    start_date=_posted(tds[4].get_text(), today),
                    end_date=_deadline(title, today),
                )
            )
            added += 1

        if added == 0:
            break

    log(f"대학교직원신문: {len(out)}건 수집")
    return out
