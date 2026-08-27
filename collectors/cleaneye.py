"""클린아이 잡플러스 — 지방공기업·지자체 출자출연기관 채용공고.

화면은 자바스크립트로 그려지지만, 목록 자체는 JSON 으로 내려온다. 인증키가 필요 없다.

수집 방식이 두 갈래다.
 1) 모집분야를 '정보통신'으로 지정해 조회 — 제목에 '전산'이 없어도 잡힌다.
    (예: "○○도시공사 제6차 기간제근로자 채용 공고" 안에 전산직이 섞여 있는 경우)
    분류가 확실하므로 키워드 필터를 자동 통과시킨다.
 2) 전체 목록도 최근 몇 페이지 훑는다 — 모집분야를 엉뚱하게 등록한 공고를 건지기 위함.
    이쪽은 제목 키워드로 한 번 더 거른다.
"""

from __future__ import annotations

import requests

from .base import Posting, parse_ymd, squeeze

BASE = "https://job.cleaneye.go.kr"
LIST_URL = BASE + "/user/selectYpRecruitment.do"
CODE_URL = BASE + "/common/selectAdminCode.do"
VIEW_URL = BASE + "/user/ypCareersData.do"
LABEL = "클린아이"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; job-watch/1.0)",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": BASE + "/user/ypRecruitment.do",
}

# 코드표를 못 받아왔을 때 쓰는 예비값
FALLBACK = {
    "sido": {
        "007001": "서울", "007002": "부산", "007003": "대구", "007004": "인천",
        "007006": "대전", "007007": "울산", "007017": "세종", "007008": "경기",
        "007009": "강원", "007010": "충북", "007011": "충남", "007012": "전북",
        "007013": "전남·광주", "007014": "경북", "007015": "경남", "007016": "제주",
    },
    "employ": {"703001": "신입", "703002": "경력", "703003": "신입+경력"},
    "jobtype": {
        "702001": "일반정규직", "702002": "무기계약직", "702003": "기간제",
        "702004": "전문계약직", "702005": "인턴", "702006": "일반계약직",
        "702007": "비상임",
    },
}

CODE_SETS = {"sido": "T000008", "employ": "P000004", "jobtype": "P000003"}


def _codes(session: requests.Session) -> dict:
    """지역·채용구분·고용형태 코드표를 받아온다. 실패하면 예비값을 쓴다."""
    out = {}
    for name, dtl in CODE_SETS.items():
        try:
            r = session.post(CODE_URL, headers=HEADERS, timeout=30,
                             data={"gubun": "2", "dtlCd": dtl})
            r.raise_for_status()
            rows = r.json().get("data") or []
            table = {x["code"]: squeeze(x["codenm"]) for x in rows if x.get("code")}
            out[name] = table or FALLBACK[name]
        except Exception:  # noqa: BLE001
            out[name] = FALLBACK[name]
    return out


def _to_posting(row: dict, code: dict, ncs: str) -> Posting | None:
    title = squeeze(row.get("entTitle"))
    if not title:
        return None

    year = squeeze(row.get("empyear"))
    ent = squeeze(row.get("ypEntId"))
    seq = squeeze(row.get("entSeq"))
    url = ""
    if year and ent and seq:
        url = f"{VIEW_URL}?empyear={year}&ypEntId={ent}&entSeq={seq}"

    return Posting(
        source="cleaneye",
        source_label=LABEL,
        org=squeeze(row.get("entName")),
        title=title,
        url=url,
        start_date=parse_ymd(row.get("pubDate")),
        end_date=parse_ymd(row.get("pubEndDate")),
        hire_type=code["jobtype"].get(squeeze(row.get("jobType")), ""),
        recruit_type=code["employ"].get(squeeze(row.get("employGb")), ""),
        region=code["sido"].get(squeeze(row.get("sidoCd")), ""),
        ncs=ncs,
    )


def _pages(session, log, extra: dict, max_pages: int, code: dict, ncs: str, tag: str):
    got = []
    for page in range(1, max_pages + 1):
        data = dict(extra)
        data["pageIndex"] = page
        try:
            r = session.post(LIST_URL, headers=HEADERS, timeout=40, data=data)
            r.raise_for_status()
            rows = r.json().get("list") or []
        except Exception as e:  # noqa: BLE001
            log(f"클린아이 {tag} {page}p 조회 실패: {e}")
            break

        if not rows:
            break
        for row in rows:
            p = _to_posting(row, code, ncs)
            if p:
                got.append(p)
        if len(rows) < 10:
            break
    return got


def fetch(cfg: dict, log) -> list[Posting]:
    session = requests.Session()
    code = _codes(session)

    # 1) 모집분야 = 정보통신(700020) 으로 지정해 조회
    field_codes = cfg.get("recruit_field_codes") or ["700020"]
    field_pages = int(cfg.get("field_pages", 4))
    picked = []
    for fc in field_codes:
        picked += _pages(session, log, {"entRecruitList[]": fc},
                         field_pages, code, "정보통신", f"분야{fc}")

    # 2) 전체 목록도 최근 몇 페이지 훑기
    scan_pages = int(cfg.get("scan_pages", 5))
    scanned = _pages(session, log, {}, scan_pages, code, "", "전체") if scan_pages else []

    merged: dict[str, Posting] = {}
    for p in picked + scanned:
        key = p.url or (p.org + p.title)
        merged.setdefault(key, p)

    out = list(merged.values())
    log(f"클린아이: {len(out)}건 수집 (정보통신 분야 {len(picked)}건 포함)")
    return out
