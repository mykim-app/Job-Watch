"""서울 열린데이터광장 — 서울시 일자리포털 채용 정보(GetJobInfo).

인증키는 열린데이터광장에서 발급받아 .env 의 SEOUL_API_KEY 로 넣는다.
요청 주소가 8088 포트라 방화벽에서 막히는 곳이 있다(국내 NAS 는 대개 열려 있다).

민간 중소기업 구인이 대부분이라, 기관명 조건(public_org_patterns)으로 한 번 더 거른다.
공고 원문 주소를 주지 않으므로 링크는 비워 둔다.
"""

from __future__ import annotations

import os

import requests

from .base import Posting, parse_ymd, request, squeeze

HOST = "http://openapi.seoul.go.kr:8088"
SERVICE = "GetJobInfo"
LABEL = "서울일자리포털"

# 한 번 호출에 최대 1000행
PAGE = 1000


def _rows(payload) -> tuple[list, int, str]:
    """(행 목록, 총건수, 오류메시지)"""
    if not isinstance(payload, dict):
        return [], 0, "응답 형식이 예상과 다름"

    # {"GetJobInfo": {...}} 또는 {"RESULT": {...}}
    body = payload.get(SERVICE)
    if body is None:
        res = payload.get("RESULT") or {}
        return [], 0, f"{res.get('CODE', '')} {res.get('MESSAGE', '')}".strip()

    res = body.get("RESULT") or {}
    code = squeeze(res.get("CODE"))
    if code and code != "INFO-000":
        return [], 0, f"{code} {squeeze(res.get('MESSAGE'))}"

    rows = body.get("row") or []
    if isinstance(rows, dict):
        rows = [rows]
    return rows, int(body.get("list_total_count") or 0), ""


def fetch(cfg: dict, log) -> list[Posting]:
    key = os.environ.get("SEOUL_API_KEY", "").strip()
    if not key:
        log("서울일자리포털: SEOUL_API_KEY 가 없어 건너뜀")
        return []

    max_pages = int(cfg.get("max_pages", 3))
    delay = float(cfg.get("delay", 1.2))
    session = requests.Session()

    out: list[Posting] = []
    seen: set[str] = set()

    for page in range(max_pages):
        start = page * PAGE + 1
        end = start + PAGE - 1
        url = f"{HOST}/{key}/json/{SERVICE}/{start}/{end}/"

        try:
            r = request(session, "GET", url, log, f"서울일자리포털 {page + 1}p",
                        delay=delay, timeout=60)
            rows, total, err = _rows(r.json())
        except Exception as e:  # noqa: BLE001
            log(f"서울일자리포털 {page + 1}p 조회 실패: {type(e).__name__}: {e}")
            break

        if err:
            log(f"서울일자리포털 응답 오류: {err}")
            break
        if not rows:
            break

        for row in rows:
            no = squeeze(row.get("JO_REQST_NO")) or squeeze(row.get("JO_REGIST_NO"))
            if no and no in seen:
                continue
            if no:
                seen.add(no)

            title = squeeze(row.get("JO_SJ"))
            if not title:
                continue

            # 모집직종코드명을 직무 칸에 넣어 키워드 판정에 쓰이게 한다
            job = squeeze(row.get("JOBCODE_NM"))

            out.append(
                Posting(
                    source="seoul",
                    source_label=LABEL,
                    org=squeeze(row.get("CMPNY_NM")),
                    title=title,
                    url="",                       # 원문 주소를 제공하지 않는다
                    start_date=parse_ymd(row.get("JO_REG_DT")),
                    end_date=parse_ymd(row.get("RCEPT_CLOS_NM")),
                    hire_type=squeeze(row.get("EMPLYM_STLE_CMMN_MM")),
                    recruit_type=squeeze(row.get("CAREER_CND_NM")),
                    region=squeeze(row.get("WORK_PARAR_BASS_ADRES_CN"))[:20],
                    ncs=job,
                )
            )

        if page == 0:
            log(f"  서울일자리포털 전체 {total}건")
        if len(rows) < PAGE:
            break

    log(f"서울일자리포털: {len(out)}건 수집 (기관명 필터 적용 전)")
    return out
