"""Supabase 일시정지 방지용 하루 1회 확인.

- 모니터링이 하루 3번(09/13/17시) 돌지만, Supabase 확인은 그날 처음 성공한 1번만 한다.
  (성공하면 같은 날 나머지 실행에서는 건너뜀 / 실패하면 다음 실행에서 다시 시도)
- 키는 코드에 넣지 않는다. .env 의 SUPABASE_ANON_KEY 에서 읽는다 (저장소가 공개이므로).
- 이 단계가 실패해도 공고 수집·게시에는 영향이 없다(항상 종료코드 0).

.env 항목
  SUPABASE_ANON_KEY=...        (필수. 없으면 이 단계는 건너뜀)
  SUPABASE_URL=...             (선택. 기본값: 아래 DEFAULT_URL)
  SUPABASE_PING_TABLE=...      (선택. 읽기 권한이 있는 테이블 이름. 지정하면 실제 DB 조회를 한다)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_URL = "https://vewmmndhipvazzmttzzr.supabase.co"
STATE = Path(os.environ.get("KEEPALIVE_STATE", ".cache/supabase_ping.json"))
KST = timezone(timedelta(hours=9))


def _load_dotenv(path: str = ".env") -> None:
    """docker --env-file 로 이미 들어오지만, 직접 실행할 때를 위해 .env 도 읽는다."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _get(url: str, key: str, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"apikey": key, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(300).decode("utf-8", "ignore")
    except urllib.error.HTTPError as e:
        return e.code, e.read(300).decode("utf-8", "ignore")
    except Exception as e:  # 네트워크 오류 등
        return 0, f"{type(e).__name__}: {e}"


def _read_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_state(d: dict) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"  Supabase 확인: 상태 저장 실패 ({e})")


def run() -> bool:
    _load_dotenv()
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not key:
        print("  Supabase 확인: SUPABASE_ANON_KEY 가 없어 건너뜀")
        return False

    today = datetime.now(KST).strftime("%Y-%m-%d")
    st = _read_state()
    if st.get("date") == today and st.get("ok"):
        print(f"  Supabase 확인: 오늘({today}) 이미 확인함 — 건너뜀")
        return True

    base = (os.environ.get("SUPABASE_URL") or DEFAULT_URL).rstrip("/")
    table = os.environ.get("SUPABASE_PING_TABLE", "").strip()
    if table:
        targets = [f"{base}/rest/v1/{urllib.parse.quote(table)}?select=*&limit=1"]
    else:
        targets = [f"{base}/auth/v1/health", f"{base}/rest/v1/"]

    ok, last = False, (0, "")
    for url in targets:
        code, body = _get(url, key)
        last = (code, body)
        path = url.replace(base, "")
        if 200 <= code < 300:
            print(f"  Supabase 확인: 정상 (HTTP {code}, {path.split('?')[0]})")
            ok = True
            break
        print(f"  Supabase 확인: 응답 HTTP {code} ({path.split('?')[0]}) {body[:120]!r}")

    if not ok:
        if last[0] == 404 and table:
            print("  → 테이블 이름(SUPABASE_PING_TABLE)을 다시 확인해 주세요.")
        elif last[0] in (401, 403):
            print("  → SUPABASE_ANON_KEY 가 올바른지 확인해 주세요.")
        print("  → 다음 실행 때 다시 시도합니다.")
    elif not table:
        print("  (참고) SUPABASE_PING_TABLE 을 지정하면 실제 DB 조회로 더 확실히 유지됩니다.")

    _write_state({"date": today, "ok": ok, "status": last[0],
                  "at": datetime.now(KST).isoformat(timespec="seconds")})
    return ok


if __name__ == "__main__":
    try:
        run()
    except Exception as e:  # 어떤 경우에도 본 작업을 막지 않는다
        print(f"  Supabase 확인: 건너뜀 ({type(e).__name__}: {e})")
    sys.exit(0)
