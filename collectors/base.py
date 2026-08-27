"""공고 1건을 나타내는 공통 구조와, 서로 다른 API 응답을 맞춰주는 도우미."""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import date, datetime

_WS = re.compile(r"[\s\u3000]+")
_PUNCT = re.compile(r"[\[\]()（）<>《》「」『』·ㆍ,.\-–—/\\'\"!?~*:;]")


def squeeze(text) -> str:
    if text is None:
        return ""
    return _WS.sub(" ", str(text)).strip()


# 같은 기관이 수집처마다 다르게 적혀 있어 중복 판정이 어긋나는 것을 막는다
# 예: "한국중소벤처기업유통원" vs "주식회사한국중소벤처기업유통원"
# 괄호 표기까지 살아 있는 상태에서 먼저 떼어낸다.
# 기호를 지운 뒤에 처리하면 '(재)' 가 '재' 로 남아 '주택도시…' 같은 이름을 잘못 자른다.
_ORG_PREFIX = re.compile(
    r"^\s*(주식회사|유한회사|재단법인|사단법인|학교법인|특수법인|의료법인"
    r"|㈜|\(\s*주\s*\)|\(\s*재\s*\)|\(\s*사\s*\)|\(\s*학\s*\)|\(\s*의\s*\))\s*"
)


def normalize_key(text) -> str:
    """중복 판정용 정규화 — 법인 표기·공백·괄호·기호 제거, 소문자."""
    t = squeeze(text).lower()
    for _ in range(3):                       # 표기가 겹쳐 붙은 경우까지
        new = _ORG_PREFIX.sub("", t)
        if new == t:
            break
        t = new
    t = _PUNCT.sub("", t)
    return t.replace(" ", "")


def parse_ymd(value) -> str:
    """20260821 / 2026-08-21 / 2026.08.21 → 2026-08-21. 실패하면 빈 문자열."""
    s = squeeze(value)
    if not s:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        digits = digits[:8]
        try:
            return datetime.strptime(digits, "%Y%m%d").date().isoformat()
        except ValueError:
            return ""
    if len(digits) == 6:  # 260821
        try:
            return datetime.strptime(digits, "%y%m%d").date().isoformat()
        except ValueError:
            return ""
    return ""


def days_left(end_ymd: str, today: date | None = None) -> int | None:
    if not end_ymd:
        return None
    today = today or date.today()
    try:
        return (date.fromisoformat(end_ymd) - today).days
    except ValueError:
        return None


def pick(d: dict, *names, contains: tuple[str, ...] = ()) -> str:
    """응답 키 이름이 스펙과 조금 달라도 최대한 찾아낸다."""
    for n in names:
        if n in d and squeeze(d[n]):
            return squeeze(d[n])
    if contains:
        for k, v in d.items():
            lk = k.lower()
            if any(c.lower() in lk for c in contains) and squeeze(v):
                return squeeze(v)
    return ""


@dataclass
class Posting:
    source: str            # alio / worknet / cleaneye ...
    source_label: str      # 화면에 보이는 출처 이름
    org: str               # 기관명
    title: str             # 공고명
    url: str
    start_date: str = ""   # 접수 시작 (YYYY-MM-DD)
    end_date: str = ""     # 접수 마감
    hire_type: str = ""    # 정규직/공무직 등
    recruit_type: str = "" # 신입/경력/신입+경력
    region: str = ""
    ncs: str = ""
    matched: list = field(default_factory=list)   # 걸린 키워드
    first_seen: str = ""   # 우리 시스템이 처음 발견한 날

    @property
    def uid(self) -> str:
        raw = f"{self.source}|{normalize_key(self.org)}|{normalize_key(self.title)}|{self.start_date}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    @property
    def cross_uid(self) -> str:
        """출처가 달라도 같은 공고면 같은 값 — 교차 중복 제거용."""
        raw = f"{normalize_key(self.org)}|{normalize_key(self.title)}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["uid"] = self.uid
        d["cross_uid"] = self.cross_uid
        d["d_day"] = days_left(self.end_date)
        return d


def request(session, method: str, url: str, log, tag: str = "", tries: int = 3,
            delay: float = 1.2, **kw):
    """요청 사이에 간격을 두고, 실패하면 몇 번 더 시도한다.

    30일치처럼 페이지를 여러 장 넘길 때 서버가 503 을 돌려주는 일이 있어서
    잠깐 쉬었다가 다시 부른다. 마지막까지 실패하면 예외를 그대로 올린다.
    """
    last = None
    for attempt in range(1, tries + 1):
        try:
            r = session.request(method, url, **kw)
            r.raise_for_status()
            time.sleep(delay)
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < tries:
                wait = delay * attempt * 3
                if log and tag:
                    log(f"  {tag} 재시도 {attempt}/{tries - 1} ({type(e).__name__}, {wait:.0f}초 후)")
                time.sleep(wait)
    raise last
