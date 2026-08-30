"""고용24(구 워크넷) 채용정보 오픈API.

옛 openapi.work.go.kr 주소는 폐지되고 www.work24.go.kr 로 옮겨졌다.
인증키는 고용24에서 '채용정보' 서비스를 신청해 발급받아야 하며,
.env 의 WORKNET_AUTH_KEY 로 넣는다. 코드에 직접 적지 말 것(저장소가 공개다).

응답 필드명이 이전(워크넷)과 달라질 수 있어 느슨하게 읽는다.
키가 승인되지 않으면 <error> 만 돌아오므로 그 내용을 로그에 남긴다.

민간기업이 대부분이라 기관명 조건(public_org_patterns)으로 한 번 더 거른다.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import requests

from .base import Posting, parse_ymd, pick, request, squeeze

ENDPOINT = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
LABEL = "고용24"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; job-watch/1.0)"}

# 목록 한 건을 담는 태그 후보 (서비스 개편으로 이름이 바뀔 수 있다)
ITEM_TAGS = {"wanted", "item", "empinfo", "dhsopeninfo", "row"}


def _parse(xml_text: str, log) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        log(f"  고용24: XML 로 못 읽음. 앞부분 → {squeeze(xml_text)[:160]}")
        return []

    err = root.find(".//error")
    if err is not None and squeeze(err.text):
        log(f"  고용24 응답 오류: {squeeze(err.text)}")
        return []

    rows = []
    for node in root.iter():
        if node.tag.lower() in ITEM_TAGS:
            row = {c.tag: (c.text or "") for c in node}
            if row:
                rows.append(row)

    if not rows:                      # 태그 이름이 바뀐 경우: 자식이 여럿인 반복 노드를 찾는다
        best, count = None, 0
        for node in root.iter():
            kids = list(node)
            if len(kids) >= 3 and all(len(list(k)) == 0 for k in kids):
                parent_tag = node.tag
                same = [n for n in root.iter() if n.tag == parent_tag]
                if len(same) > count:
                    best, count = same, len(same)
        if best and count > 1:
            log(f"  고용24: 목록 태그를 '{best[0].tag}' 로 추정")
            rows = [{c.tag: (c.text or "") for c in n} for n in best]

    return rows


def fetch(cfg: dict, log) -> list[Posting]:
    key = os.environ.get("WORKNET_AUTH_KEY", "").strip()
    if not key:
        log("고용24: WORKNET_AUTH_KEY 가 없어 건너뜀")
        return []

    display = int(cfg.get("display", 100))
    max_pages = int(cfg.get("max_pages", 2))
    delay = float(cfg.get("delay", 1.2))
    keywords = cfg.get("query_keywords") or [""]

    session = requests.Session()
    seen: set[str] = set()
    out: list[Posting] = []

    for kw in keywords:
        for page in range(1, max_pages + 1):
            params = {
                "authKey": key,
                "callTp": "L",
                "returnType": "XML",
                "startPage": page,
                "display": display,
            }
            if kw:
                params["keyword"] = kw

            try:
                r = request(session, "GET", ENDPOINT, log, f"고용24 '{kw}' {page}p",
                            delay=delay, params=params, headers=HEADERS, timeout=40)
                rows = _parse(r.text, log)
            except Exception as e:  # noqa: BLE001
                log(f"고용24 '{kw}' {page}p 조회 실패: {e}")
                break

            if not rows:
                break

            for row in rows:
                no = pick(row, "wantedAuthNo", contains=("authno",))
                if no and no in seen:
                    continue
                if no:
                    seen.add(no)

                title = pick(row, "title", "wantedTitle", contains=("title", "채용제목"))
                if not title:
                    continue

                out.append(
                    Posting(
                        source="worknet",
                        source_label=LABEL,
                        org=pick(row, "company", "coNm", contains=("company", "회사", "기업")),
                        title=title,
                        url=pick(row, "wantedInfoUrl", "wantedMobileInfoUrl", contains=("url",)),
                        start_date=parse_ymd(pick(row, "regDt", "regDate", contains=("regd",))),
                        end_date=parse_ymd(pick(row, "closeDt", contains=("close",))),
                        hire_type=pick(row, "empTpNm", contains=("emptp", "고용형태")),
                        recruit_type=pick(row, "career", contains=("career", "경력")),
                        region=pick(row, "region", contains=("region", "지역")),
                    )
                )

            if len(rows) < display:
                break

    log(f"고용24: {len(out)}건 수집 (기관명 필터 적용 전)")
    return out
