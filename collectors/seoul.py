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


def _call(session, key, start, end, log, tag, delay):
    url = f"{HOST}/{key}/json/{SERVICE}/{start}/{end}/"
    r = request(session, "GET", url, log, tag, delay=delay, timeout=60)
    return _rows(r.json())


def _newest_first(session, key, total, log, delay) -> bool:
    """목록이 최신순인지 확인한다.

    전체가 2만 건이 넘는데 앞에서부터 읽으면 오래된 공고만 가져오게 된다.
    앞뒤 5건씩 등록일을 비교해 어느 쪽이 최신인지 본다.
    """
    try:
        head, _, _ = _call(session, key, 1, 5, log, "서울일자리포털 정렬확인(앞)", delay)
        tail, _, _ = _call(session, key, max(total - 4, 1), total,
                           log, "서울일자리포털 정렬확인(뒤)", delay)
    except Exception:  # noqa: BLE001
        return True

    def newest(rows):
        ds = [parse_ymd(x.get("JO_REG_DT")) for x in rows]
        ds = [d for d in ds if d]
        return max(ds) if ds else ""

    h, t = newest(head), newest(tail)
    if not h or not t:
        return True
    log(f"  등록일 앞 {h} / 뒤 {t}")
    return h >= t


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

    # 총 건수부터 확인하고, 최신 공고가 어느 쪽에 있는지 판단한다
    try:
        _, total, err = _call(session, key, 1, 1, log, "서울일자리포털 건수확인", delay)
    except Exception as e:  # noqa: BLE001
        log(f"서울일자리포털 조회 실패: {type(e).__name__}: {e}")
        return []
    if err:
        log(f"서울일자리포털 응답 오류: {err}")
        return []

    newest_first = _newest_first(session, key, total, log, delay) if total > PAGE else True
    log(f"  전체 {total}건 · {'최신순' if newest_first else '오래된순(뒤에서부터 읽음)'}")

    for page in range(max_pages):
        if newest_first:
            start = page * PAGE + 1
            end = start + PAGE - 1
        else:
            end = total - page * PAGE
            start = max(end - PAGE + 1, 1)
            if end < 1:
                break

        try:
            rows, _, err = _call(session, key, start, end,
                                 log, f"서울일자리포털 {page + 1}p", delay)
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

        if len(rows) < PAGE or start <= 1:
            break

    log(f"서울일자리포털: {len(out)}건 수집 (기관명 필터 적용 전)")
    return out
