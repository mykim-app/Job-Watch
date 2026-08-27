"""워크넷(고용24) 채용정보 오픈API.

work.go.kr 오픈API 에서 발급받은 인증키를 WORKNET_AUTH_KEY 로 넣는다.
잡알리오에 안 잡히는 협회·재단·출연기관 공고를 여기서 건진다.
XML 로 오므로 자식 태그를 통째로 dict 로 만들어 느슨하게 읽는다.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import requests

from .base import Posting, parse_ymd, pick, squeeze

ENDPOINT = "http://openapi.work.go.kr/opi/opi/opiaJobsrchList.do"
LABEL = "워크넷"


def _items(xml_text: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    items = []
    for node in root.iter():
        if node.tag.lower() in ("wanted", "item", "dhsopeninfo"):
            row = {c.tag: (c.text or "") for c in node}
            if row:
                items.append(row)
    return items


def fetch(cfg: dict, log) -> list[Posting]:
    key = os.environ.get("WORKNET_AUTH_KEY", "").strip()
    if not key:
        log("워크넷: WORKNET_AUTH_KEY 가 없어 건너뜀")
        return []

    display = int(cfg.get("display", 100))
    max_pages = int(cfg.get("max_pages", 3))
    seen_ids: set[str] = set()
    out: list[Posting] = []

    for kw in cfg.get("query_keywords", []):
        for page in range(1, max_pages + 1):
            params = {
                "authKey": key,
                "callTp": "L",
                "returnType": "XML",
                "startPage": page,
                "display": display,
                "keyword": kw,
                "sortOrderBy": "DESC",
            }
            try:
                r = requests.get(ENDPOINT, params=params, timeout=30)
                r.raise_for_status()
                rows = _items(r.text)
            except Exception as e:  # noqa: BLE001
                log(f"워크넷 '{kw}' {page}p 조회 실패: {e}")
                break

            if not rows:
                break

            for row in rows:
                auth_no = pick(row, "wantedAuthNo", contains=("authno",))
                if auth_no and auth_no in seen_ids:
                    continue
                if auth_no:
                    seen_ids.add(auth_no)

                title = pick(row, "title", contains=("title", "공고"))
                if not title:
                    continue

                out.append(
                    Posting(
                        source="worknet",
                        source_label=LABEL,
                        org=pick(row, "company", contains=("company", "회사", "기관")),
                        title=title,
                        url=pick(row, "wantedInfoUrl", "wantedMobileInfoUrl", contains=("url",)),
                        start_date=parse_ymd(pick(row, "regDt", "regDate", contains=("regd",))),
                        end_date=parse_ymd(pick(row, "closeDt", contains=("close",))),
                        hire_type=pick(row, "empTpNm", "holidayTpNm", contains=("emptp",)),
                        recruit_type=pick(row, "career", contains=("career",)),
                        region=pick(row, "region", contains=("region", "지역")),
                    )
                )

            if len(rows) < display:
                break

    log(f"워크넷: {len(out)}건 수집(중복 제거 전)")
    return out
