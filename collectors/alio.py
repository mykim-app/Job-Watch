"""잡알리오 — 공공데이터포털 '재정경제부_공공기관 채용정보 조회서비스'.

data.go.kr 에서 활용신청 후 받은 일반 인증키(Decoding)를 ALIO_SERVICE_KEY 로 넣는다.
응답 필드명이 바뀌어도 되도록 pick() 으로 느슨하게 읽는다.
"""

from __future__ import annotations

import os
import requests

from .base import Posting, parse_ymd, pick, squeeze

ENDPOINT = "https://apis.data.go.kr/1051000/recruitment/list"
LABEL = "잡알리오"


def _rows(payload) -> list:
    """{'result': [...]} / {'response':{'body':{'items':[...]}}} 등 어떤 형태든 목록을 찾아낸다."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("result", "items", "item", "list", "data"):
        if key in payload:
            return _rows(payload[key])
    for key in ("response", "body", "resultList"):
        if key in payload:
            return _rows(payload[key])
    return []


def fetch(cfg: dict, log) -> list[Posting]:
    key = os.environ.get("ALIO_SERVICE_KEY", "").strip()
    if not key:
        log("잡알리오: ALIO_SERVICE_KEY 가 없어 건너뜀")
        return []

    out: list[Posting] = []
    max_pages = int(cfg.get("max_pages", 10))

    for page in range(1, max_pages + 1):
        params = {
            "serviceKey": key,
            "resultType": "json",
            "numOfRows": 100,
            "pageNo": page,
        }
        if cfg.get("ongoing_only", True):
            params["ongoingYn"] = "Y"

        try:
            r = requests.get(ENDPOINT, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
        except Exception as e:  # noqa: BLE001
            log(f"잡알리오 {page}p 조회 실패: {e}")
            break

        rows = _rows(data)
        if not rows:
            break

        for row in rows:
            title = pick(row, "recrutPbancTtl", "pbancTtl", contains=("ttl", "title", "공고"))
            if not title:
                continue
            out.append(
                Posting(
                    source="alio",
                    source_label=LABEL,
                    org=pick(row, "instNm", "pblntInstNm", contains=("instnm", "기관")),
                    title=title,
                    url=pick(row, "srcUrl", "url", contains=("url",)),
                    start_date=parse_ymd(pick(row, "pbancBgngYmd", contains=("bgng",))),
                    end_date=parse_ymd(pick(row, "pbancEndYmd", contains=("endymd",))),
                    hire_type=pick(row, "hireTypeNmLst", contains=("hiretype",)),
                    recruit_type=pick(row, "recrutSeNm", contains=("recrutse",)),
                    region=pick(row, "workRgnNmLst", contains=("rgn", "region")),
                    ncs=pick(row, "ncsCdNmLst", contains=("ncs",)),
                )
            )

        if len(rows) < 100:
            break

    log(f"잡알리오: {len(out)}건 수집")
    return out
