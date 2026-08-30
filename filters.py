"""전산·통신직 공고만 골라내는 필터.

직종코드는 기관마다 붙이는 기준이 제각각이라 누락이 크다.
그래서 제목·직무분류 텍스트 매칭을 주로 쓰고, NCS 분류는 보조로만 쓴다.
"""

from __future__ import annotations

import re

from collectors.base import Posting, squeeze

# 'IT', 'AI' 처럼 짧은 영문은 단어 경계를 봐야 오탐이 없다 (예: DIGITAL 안의 IT)
_SHORT_EN = {"it", "ai", "ict", "dx", "os", "db"}


def _hit(haystack: str, needle: str) -> bool:
    n = needle.strip()
    if not n:
        return False
    if n.lower() in _SHORT_EN:
        return re.search(rf"(?<![A-Za-z]){re.escape(n)}(?![A-Za-z])", haystack, re.I) is not None
    return n.lower() in haystack.lower()


def match(post: Posting, f: dict) -> tuple[bool, list[str]]:
    """(수집할지, 걸린 키워드 목록)"""
    blob = " ".join(
        squeeze(x) for x in (post.title, post.ncs, post.recruit_type, post.hire_type)
    )

    for bad in f.get("exclude", []):
        if _hit(blob, bad):
            return False, []

    hits = [kw for kw in f.get("include", []) if _hit(blob, kw)]
    for ncs_kw in f.get("ncs_keywords", []):
        if post.ncs and _hit(post.ncs, ncs_kw) and ncs_kw not in hits:
            hits.append(ncs_kw)

    return bool(hits), hits


def match_open(post: Posting, f: dict, keywords: list) -> tuple[bool, list[str]]:
    """직무(전산·통신)를 따지지 않고, 지정한 고용형태에 해당하면 수집한다.

    대학교직원신문처럼 '이 게시판은 정규직이면 다 보고 싶다' 는 수집처에 쓴다.
    제외 단어(계약직·인턴·임기제 등)는 그대로 적용된다.
    """
    blob = " ".join(
        squeeze(x) for x in (post.title, post.ncs, post.recruit_type, post.hire_type)
    )

    for bad in f.get("exclude", []):
        if _hit(blob, bad):
            return False, []

    hits = [kw for kw in keywords if _hit(blob, kw)]
    return bool(hits), hits


def is_public_org(post: Posting, f: dict) -> bool:
    """워크넷처럼 민간이 섞여 들어오는 출처에만 적용."""
    org = squeeze(post.org)
    if not org:
        return False
    return any(p in org for p in f.get("public_org_patterns", []))
