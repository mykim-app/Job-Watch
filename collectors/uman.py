"""대학교직원신문(uman.kr) [직원]채용 게시판 — 4년제·전문대 교직원 채용.

사립대 공고가 모이는 거의 유일한 곳이다. 인증키가 필요 없다.
해외 IP 는 서버가 403 으로 막으므로 국내(NAS)에서만 동작한다.

목록에 마감일 칸이 없는 대신 제목 끝에 "(~09. 13(일) 17:00)" 처럼 적혀 있어서
거기서 마감일을 뽑아 쓴다. 못 뽑으면 상시로 취급한다.

제목에 직종이 안 드러나는 공고가 많다("○○대학교 정규직원 채용 공고").
그래서 제목에 전산 관련 말이 없으면 상세 본문을 열어 모집분야를 확인한다.
한 번 확인한 글은 .cache 에 적어두고 다시 열지 않는다.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import Posting, dedupe_title, request, squeeze

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

CACHE_FILE = Path(".cache/uman_detail.json")

# 상세 본문에서 찾을 전산 관련 말
DEFAULT_IT_WORDS = [
    "전산", "전자계산", "정보화", "정보통신", "정보시스템", "정보보안", "정보보호",
    "네트워크", "서버", "데이터베이스", "소프트웨어", "홈페이지", "웹개발",
    "시스템 운영", "시스템운영", "전산실", "정보전산", "IT", "ICT",
]
# 본문에 이게 있으면 전산 공고로 보지 않는다 (안내문에 흔히 섞이는 말)
DEFAULT_IT_STOP = ["전산접수", "전산등록", "인터넷 접수", "온라인 접수"]


def _load_cache() -> dict:
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_cache(cache: dict) -> None:
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        if len(cache) > 4000:                       # 너무 커지면 최근 것만 남긴다
            cache = dict(list(cache.items())[-2000:])
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _body_is_it(session, no: str, title: str, words, stops, log, delay) -> bool:
    """상세 본문에 전산 관련 모집분야가 있는지 본다."""
    try:
        r = request(session, "GET", LIST_URL, log, f"대학교직원신문 상세 {no}",
                    delay=delay, params={"id": BOARD_ID, "no": no},
                    headers=HEADERS, timeout=40, tries=2)
        r.encoding = "euc-kr"
        text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
    except Exception as e:  # noqa: BLE001
        log(f"  상세 {no} 못 읽음: {type(e).__name__}")
        return False

    # 좌측 메뉴·머리말을 피해 본문 시작점부터 본다.
    # 목록 제목에는 마감일이 붙어 있어 본문과 다르므로 떼어내고 찾는다.
    anchor = squeeze(dedupe_title(title))[:14]
    i = text.find(anchor) if anchor else -1
    if i < 0:
        i = text.rfind("[직원]채용")        # 게시판 제목줄 = 본문 영역 시작
    body = text[i:i + 4000] if i > 0 else text[:4000]

    for stop in stops:
        body = body.replace(stop, "")
    low = body.lower()
    for w in words:
        if w.lower() in ("it", "ict"):
            if re.search(rf"(?<![A-Za-z]){w}(?![A-Za-z])", body, re.I):
                return True
        elif w.lower() in low:
            return True
    return False


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
    check_detail = bool(cfg.get("check_detail", True))
    detail_days = int(cfg.get("detail_days", 45))
    max_detail = int(cfg.get("max_detail", 40))
    words = cfg.get("it_words") or DEFAULT_IT_WORDS
    stops = cfg.get("it_stop_words") or DEFAULT_IT_STOP
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

    if not check_detail:
        log(f"대학교직원신문: {len(out)}건 수집 (본문 확인 안 함)")
        return out

    # 제목에 전산 관련 말이 이미 있으면 본문을 열 필요가 없다
    cache = _load_cache()
    cutoff = (today - timedelta(days=detail_days)).isoformat()
    looked = hit = 0

    for p in out:
        blob = p.title
        if any(w.lower() in blob.lower() for w in words):
            p.ncs = "정보통신"
            hit += 1
            continue
        if p.start_date and p.start_date < cutoff:
            continue

        no = p.url.rsplit("no=", 1)[-1]
        if no in cache:
            if cache[no]:
                p.ncs = "정보통신"
                hit += 1
            continue
        if looked >= max_detail:
            continue

        looked += 1
        found = _body_is_it(session, no, p.title, words, stops, log, delay)
        cache[no] = found
        if found:
            p.ncs = "정보통신"
            hit += 1

    _save_cache(cache)
    log(f"대학교직원신문: {len(out)}건 중 전산 관련 {hit}건 (본문 확인 {looked}건)")
    return [p for p in out if p.ncs == "정보통신"]
