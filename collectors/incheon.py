"""인천일자리플랫폼 공공 채용정보(incheon.go.kr/jobs).

인천 지역 공공기관 공고가 모이는 곳이다. 인증키가 필요 없다.

이 게시판 검색은 제목·기관명만 훑어서, 제목에 직렬이 없으면 검색으로 못 찾는다.
대신 상세 페이지에 공고 본문 전문이 실려 있어서, 대학교직원신문과 같은 방식으로
본문을 열어 전산 관련 모집분야인지 확인한다. 한 번 확인한 글은 .cache 에 남긴다.

정보제공처가 나라일터·잡알리오인 공고가 많아 다른 수집처와 겹친다.
겹치는 건 교차 중복 제거로 한쪽만 남는다.

목록에 시작일이 없어 등록일은 비워 둔다(마감일만 쓴다).
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .base import Posting, request, squeeze

BASE = "https://www.incheon.go.kr"
LIST_URL = BASE + "/jobs/main/recruit/public/list.do"
VIEW_URL = BASE + "/jobs/main/recruit/public/view.do"
LABEL = "인천일자리플랫폼"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": LIST_URL,
}

CACHE_FILE = Path(".cache/incheon_detail.json")
_SN = re.compile(r"rcrut_info_sn=(\d+)")
_YMD = re.compile(r"(\d{4})-(\d{2})-(\d{2})")

DEFAULT_IT_WORDS = [
    "전산", "전자계산", "정보화", "정보통신", "정보시스템", "정보보안", "정보보호",
    "네트워크", "서버", "데이터베이스", "소프트웨어", "전산실", "IT", "ICT",
]
# 안내문에 흔히 섞이는 말. 이것만으로는 전산 공고로 보지 않는다
DEFAULT_IT_STOP = ["전산접수", "전산등록", "인터넷 접수", "온라인 접수",
                   "정보통신부", "과학기술정보통신부", "방송통신대",
                   "개인정보처리방침", "개인정보 처리방침", "개인정보처리", "개인정보 처리",
                   "개인정보보호법", "개인정보 보호법", "개인정보보호", "개인정보 보호",
                   "채용정보시스템", "정보보호법"]

# 본문이 끝나고 페이지 하단 링크가 시작되는 지점.
# 여기를 안 자르면 '채용정보시스템', '개인정보처리방침' 같은 링크에 전부 걸린다.
BODY_END = ["제 1유형", "이 페이지에서 제공하는", "자료관리담당자", "저작권보호정책"]


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


def _has_it(text: str, words, stops) -> bool:
    for s in stops:
        text = text.replace(s, "")
    for w in words:
        if w.lower() in ("it", "ict"):
            if re.search(rf"(?<![A-Za-z]){w}(?![A-Za-z])", text, re.I):
                return True
        elif w in text:
            return True
    return False


def _body_is_it(session, sn, title, words, stops, log, delay) -> bool:
    try:
        r = request(session, "GET", VIEW_URL, log, f"인천 상세 {sn}", tries=2,
                    delay=delay, params={"rcrut_info_sn": sn},
                    headers=HEADERS, timeout=40)
        text = BeautifulSoup(r.text, "lxml").get_text(" ", strip=True)
    except Exception as e:  # noqa: BLE001
        log(f"  인천 상세 {sn} 못 읽음: {type(e).__name__}")
        return False

    anchor = squeeze(title)[:14]
    i = text.find(anchor) if anchor else -1
    if i < 0:
        i = 0
    ends = [text.find(m, i) for m in BODY_END]
    ends = [e for e in ends if e > i]
    j = min(ends) if ends else i + 5000
    return _has_it(text[i:j], words, stops)


def fetch(cfg: dict, log) -> list[Posting]:
    max_pages = int(cfg.get("max_pages", 8))
    delay = float(cfg.get("delay", 1.2))
    check_detail = bool(cfg.get("check_detail", True))
    max_detail = int(cfg.get("max_detail", 40))
    words = cfg.get("it_words") or DEFAULT_IT_WORDS
    stops = cfg.get("it_stop_words") or DEFAULT_IT_STOP
    today = date.today().isoformat()

    session = requests.Session()
    rows = []
    seen: set[str] = set()

    for page in range(1, max_pages + 1):
        try:
            r = request(session, "GET", LIST_URL, log, f"인천일자리 {page}p",
                        delay=delay, headers=HEADERS, timeout=40,
                        params={"page": page, "srchSort": "regist_DESC"})
            soup = BeautifulSoup(r.text, "lxml")
        except Exception as e:  # noqa: BLE001
            log(f"인천일자리플랫폼 {page}p 실패: {type(e).__name__}")
            break

        links = soup.select(".pubPolicies_name a")
        if not links:
            break

        added = 0
        for a in links:
            m = _SN.search(a.get("href", "") or "")
            if not m:
                continue
            sn = m.group(1)
            if sn in seen:
                continue
            seen.add(sn)

            title = squeeze(a.get_text())
            if not title:
                continue

            tr = a.find_parent("tr")
            org, end = "", ""
            if tr:
                o = tr.select_one(".pubPolicies_org")
                org = squeeze(o.get_text()) if o else ""
                d = _YMD.search(tr.get_text(" ", strip=True))
                if d:
                    end = f"{d.group(1)}-{d.group(2)}-{d.group(3)}"

            rows.append({"sn": sn, "title": title, "org": org or "인천광역시", "end": end})
            added += 1

        if added == 0:
            break

    # 접수가 끝난 공고는 본문을 열 필요가 없다
    rows = [r for r in rows if not r["end"] or r["end"] >= today]

    cache = _load_cache()
    looked = 0
    out: list[Posting] = []

    for r in rows:
        is_it = _has_it(r["title"], words, stops)
        if not is_it and check_detail:
            if r["sn"] in cache:
                is_it = bool(cache[r["sn"]])
            elif looked < max_detail:
                looked += 1
                is_it = _body_is_it(session, r["sn"], r["title"], words, stops, log, delay)
                cache[r["sn"]] = is_it
        if not is_it:
            continue

        out.append(
            Posting(
                source="incheon",
                source_label=LABEL,
                org=r["org"],
                title=r["title"],
                url=f"{VIEW_URL}?rcrut_info_sn={r['sn']}",
                start_date="",              # 목록·상세에 시작일이 없다
                end_date=r["end"],
                region="인천",
                ncs="정보통신",
            )
        )

    _save_cache(cache)
    log(f"인천일자리플랫폼: 진행중 {len(rows)}건 중 전산 관련 {len(out)}건 (본문 확인 {looked}건)")
    return out
