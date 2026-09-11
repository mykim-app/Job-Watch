"""전산·통신직 공고만 골라내는 필터.

직종코드는 기관마다 붙이는 기준이 제각각이라 누락이 크다.
그래서 제목·직무분류 텍스트 매칭을 주로 쓰고, NCS 분류는 보조로만 쓴다.

제외 단어는 두 갈래로 나뉜다.
 - exclude            : 무조건 제외 (합격자 발표, 조리·미화 등 직무 자체가 다른 것)
 - exclude_employment : 고용형태 때문에 제외. 단 같은 공고에 keep_employment
                        (정규직·무기계약직 등)가 함께 있으면 살린다.
                        "기간제 및 정규직 채용" 처럼 여러 형태를 한 공고에서
                        같이 뽑는 경우가 많기 때문이다.
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


def _blob(post: Posting) -> str:
    return " ".join(
        squeeze(x) for x in (post.title, post.ncs, post.recruit_type, post.hire_type)
    )


# 잡알리오는 여러 고용형태를 뽑는 공고를 '비정규직 외 1' 처럼 줄여 보여준다.
# 나머지 하나가 정규직일 수 있으므로, 이 표시가 있으면 제외하지 않는다.
_MULTI_EMP = re.compile(r"외\s*\d+")


# '비정규직' 안에는 '정규직'이 들어 있다. 이 글자가 앞에 붙으면 정규직으로 보지 않는다.
_NEGATION = "비준"


def _keep_spans(blob: str, keeps: list) -> list:
    """정규직 계열 표현이 나온 구간. '비'가 앞에 붙은 것은 빼고 찾는다."""
    spans = []
    for g in keeps:
        g = g.strip()
        if not g:
            continue
        for m in re.finditer(rf"(?<![{_NEGATION}]){re.escape(g)}", blob):
            spans.append((m.start(), m.end()))
    return spans


def excluded_reason(post: Posting, f: dict) -> str | None:
    """제외 사유. 제외 대상이 아니면 None."""
    blob = _blob(post)

    for bad in f.get("exclude", []):
        if _hit(blob, bad):
            return f"제외 단어 '{bad}'"

    keeps = f.get("keep_employment", [])
    spans = _keep_spans(blob, keeps)

    # 정규직 계열로 잡힌 구간은 지우고 고용형태 제외어를 찾는다.
    # ('무기계약직'을 '계약직'으로 잘못 잡는 것을 막는다)
    masked = list(blob)
    for a, b in spans:
        for i in range(a, b):
            masked[i] = " "
    masked = "".join(masked)

    emp_bad = [w for w in f.get("exclude_employment", []) if _hit(masked, w)]
    if emp_bad:
        if spans:
            return None            # 정규직도 같이 뽑는 공고라 살린다
        if f.get("keep_multi_employment", True) and _MULTI_EMP.search(squeeze(post.hire_type)):
            return None            # '비정규직 외 1' — 나머지가 정규직일 수 있다
        return f"고용형태 '{emp_bad[0]}'"

    return None


def match(post: Posting, f: dict) -> tuple[bool, list[str]]:
    """(수집할지, 걸린 키워드 목록)"""
    if excluded_reason(post, f):
        return False, []

    blob = _blob(post)
    hits = [kw for kw in f.get("include", []) if _hit(blob, kw)]
    for ncs_kw in f.get("ncs_keywords", []):
        if post.ncs and _hit(post.ncs, ncs_kw) and ncs_kw not in hits:
            hits.append(ncs_kw)

    return bool(hits), hits


def match_open(post: Posting, f: dict, keywords: list) -> tuple[bool, list[str]]:
    """직무(전산·통신)를 따지지 않고, 지정한 고용형태에 해당하면 수집한다.

    open_sources 설정을 쓰는 수집처에만 적용된다.
    """
    if excluded_reason(post, f):
        return False, []
    blob = _blob(post)
    hits = [kw for kw in keywords if _hit(blob, kw)]
    return bool(hits), hits


def is_public_org(post: Posting, f: dict) -> bool:
    """사람인·고용24·서울일자리포털처럼 민간이 섞여 오는 곳에만 쓴다."""
    org = squeeze(post.org)
    if not org:
        return False
    return any(p in org for p in f.get("public_org_patterns", []))
