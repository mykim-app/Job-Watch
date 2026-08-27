"""잡알리오 — 공공데이터포털 '재정경제부_공공기관 채용정보 조회서비스'."""

from __future__ import annotations

import os
import time

import requests

from .base import Posting, parse_ymd, pick, squeeze

PATH = "/1051000/recruitment/list"
HOSTS = ["https://apis.data.go.kr", "http://apis.data.go.kr"]
LABEL = "잡알리오"


def _rows(payload) -> list:
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


def _get(params: dict, log):
    """https → http 순으로, 각 3회까지 시도한다."""
    last = None
    for base in HOSTS:
        for attempt in range(1, 4):
            try:
                r = requests.get(base + PATH, params=params, timeout=(60, 90))
                r.raise_for_status()
                if base.startswith("http://"):
                    log("  (https 실패로 http 로 붙었음)")
                return r
            except Exception as e:  # noqa: BLE001
                last = e
                kind = type(e).__name__
                log(f"  {base[:5]} 시도 {attempt}/3 실패: {kind}")
                time.sleep(attempt * 5)
    raise last


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
            r = _get(params, log)
        except Exception as e:  # noqa: BLE001
            log(f"잡알리오 {page}p 최종 실패: {e}")
            break

        try:
            data = r.json()
        except ValueError:
            log(f"잡알리오 {page}p 응답이 JSON 이 아님. 앞부분: {r.text[:200]}")
            break

        rows = _rows(data)
        if not rows:
            log(f"잡알리오 {page}p 목록 없음. 응답 앞부분: {str(data)[:200]}")
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
