"""서울 열린데이터광장 채용정보.

기본은 recMntList(OA-23047) — 고용24에서 받아온 서울·경기·인천 채용공고, 매일 1회 갱신.
GetJobInfo(OA-13341) 도 쓸 수 있게 필드 대응표를 같이 둔다.

인증키는 .env 의 SEOUL_API_KEY. 일반 인증키 하나면 서비스별 신청이 필요 없다.
요청 주소가 8088 포트라 방화벽에서 막히는 곳이 있다(국내 NAS 는 대개 열려 있다).

민간기업이 대부분이라 기관명 조건(public_org_patterns)으로 한 번 더 거른다.
공고 원문 주소를 주지 않으므로 링크는 비워 둔다.
"""

from __future__ import annotations

import os

import requests

from .base import Posting, parse_ymd, request, squeeze

HOST = "http://openapi.seoul.go.kr:8088"
LABEL = "서울일자리포털"

# END_INDEX - START_INDEX 가 999 를 넘을 수 없다 (열린데이터광장 공통 제한)
PAGE = 1000

# 서비스별 출력 필드 대응
FIELDS = {
    "recMntList": {                      # OA-23047 (고용24 원본, 서울·경기·인천)
        "org": "COMPANY", "title": "TITLE", "reg": "REG_DT", "close": "CLOSE_DT",
        "emp": "EMP_TP_NM", "career": "CAREER", "region": "REGION",
        "job": "JOBS_NM", "content": "JOB_CONT",
    },
    "GetJobInfo": {                      # OA-13341 (일자리플러스센터)
        "org": "CMPNY_NM", "title": "JO_SJ", "reg": "JO_REG_DT",
        "close": "RCEPT_CLOS_NM", "emp": "EMPLYM_STLE_CMMN_MM",
        "career": "CAREER_CND_NM", "region": "WORK_PARAR_BASS_ADRES_CN",
        "job": "JOBCODE_NM", "content": "",
    },
}

# 직무내용에서 찾을 전산 관련 말 (scan_job_content 를 켰을 때만 쓴다)
IT_WORDS = ["전산", "정보화", "정보통신", "정보시스템", "정보보안", "네트워크",
            "서버", "데이터베이스", "소프트웨어", "홈페이지", "전산실"]


def _unpack(payload, service: str):
    """(행 목록, 총건수, 오류메시지)"""
    if not isinstance(payload, dict):
        return [], 0, "응답 형식이 예상과 다름"

    body = payload.get(service)
    if body is None:
        res = payload.get("RESULT") or {}
        msg = f"{res.get('CODE', '')} {res.get('MESSAGE', '')}".strip()
        return [], 0, msg or "응답에 결과가 없음"

    res = body.get("RESULT") or {}
    code = squeeze(res.get("CODE"))
    if code and code != "INFO-000":
        return [], 0, f"{code} {squeeze(res.get('MESSAGE'))}"

    rows = body.get("row") or []
    if isinstance(rows, dict):
        rows = [rows]
    return rows, int(body.get("list_total_count") or 0), ""


def _call(session, key, service, start, end, log, tag, delay):
    url = f"{HOST}/{key}/json/{service}/{start}/{end}/"
    r = request(session, "GET", url, log, tag, delay=delay, timeout=60)
    return _unpack(r.json(), service)


def _newest_first(session, key, service, total, log, delay, f) -> bool:
    """목록이 최신순인지 확인한다. 앞뒤 5건의 등록일을 비교한다."""
    try:
        head, _, _ = _call(session, key, service, 1, 5, log, "정렬확인(앞)", delay)
        tail, _, _ = _call(session, key, service, max(total - 4, 1), total,
                           log, "정렬확인(뒤)", delay)
    except Exception:  # noqa: BLE001
        return True

    def newest(rows):
        ds = [parse_ymd(x.get(f["reg"])) for x in rows]
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

    service = cfg.get("service", "recMntList")
    f = FIELDS.get(service)
    if f is None:
        log(f"서울일자리포털: 모르는 서비스명 '{service}'")
        return []

    max_pages = int(cfg.get("max_pages", 3))
    delay = float(cfg.get("delay", 1.2))
    scan_content = bool(cfg.get("scan_job_content", False))
    session = requests.Session()

    try:
        _, total, err = _call(session, key, service, 1, 1, log, "건수확인", delay)
    except Exception as e:  # noqa: BLE001
        log(f"서울일자리포털 조회 실패: {type(e).__name__}: {e}")
        return []
    if err:
        log(f"서울일자리포털 응답 오류: {err}")
        return []

    newest_first = True
    if total > PAGE:
        newest_first = _newest_first(session, key, service, total, log, delay, f)
    log(f"  {service} 전체 {total}건 · {'최신순' if newest_first else '오래된순(뒤에서부터)'}")

    out: list[Posting] = []
    seen: set[str] = set()

    for page in range(max_pages):
        if newest_first:
            start = page * PAGE + 1
            end = start + PAGE - 1
            if start > total:
                break
        else:
            end = total - page * PAGE
            start = max(end - PAGE + 1, 1)
            if end < 1:
                break

        try:
            rows, _, err = _call(session, key, service, start, end,
                                 log, f"서울일자리포털 {page + 1}p", delay)
        except Exception as e:  # noqa: BLE001
            log(f"서울일자리포털 {page + 1}p 실패: {type(e).__name__}: {e}")
            break
        if err:
            log(f"서울일자리포털 응답 오류: {err}")
            break
        if not rows:
            break

        for row in rows:
            title = squeeze(row.get(f["title"]))
            org = squeeze(row.get(f["org"]))
            if not title:
                continue
            uniq = f"{org}|{title}|{squeeze(row.get(f['reg']))}"
            if uniq in seen:
                continue
            seen.add(uniq)

            job = squeeze(row.get(f["job"]))
            # 직무내용까지 훑을지 (기본 꺼둠 — 켜면 놓치는 건 줄지만 오탐이 는다)
            if scan_content and f["content"]:
                body = squeeze(row.get(f["content"]))
                if body and any(w in body for w in IT_WORDS):
                    job = (job + " 정보통신").strip()

            out.append(
                Posting(
                    source="seoul",
                    source_label=LABEL,
                    org=org,
                    title=title,
                    url="",                       # 원문 주소를 제공하지 않는다
                    start_date=parse_ymd(row.get(f["reg"])),
                    end_date=parse_ymd(row.get(f["close"])),
                    hire_type=squeeze(row.get(f["emp"])),
                    recruit_type=squeeze(row.get(f["career"])),
                    region=squeeze(row.get(f["region"]))[:20],
                    ncs=job,
                )
            )

        if len(rows) < PAGE:
            break
        if not newest_first and start <= 1:
            break

    log(f"서울일자리포털: {len(out)}건 수집 (기관명 필터 적용 전)")
    return out
