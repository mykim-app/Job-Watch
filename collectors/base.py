"""공고 1건을 나타내는 공통 구조와, 서로 다른 API 응답을 맞춰주는 도우미."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, asdict, field
from datetime import date, datetime

_WS = re.compile(r"[\s\u3000]+")
_PUNCT = re.compile(r"[\[\]()（）<>《》「」『』·ㆍ,.\-–—/\\'\"!?~*:;]")


def squeeze(text) -> str:
    if text is None:
        return ""
    return _WS.sub(" ", str(text)).strip()


def normalize_key(text) -> str:
    """중복 판정용 정규화 — 공백·괄호·기호 제거, 소문자."""
    t = squeeze(text).lower()
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
