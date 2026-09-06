#!/bin/bash
# NAS 작업 스케줄러가 도커 컨테이너 안에서 실행하는 스크립트.
# 로그는 /app/logs 아래에 주 단위 파일로 쌓이고, 1년이 지난 파일은 스스로 지운다.

cd /app || exit 1
export HOME=/app
export TZ="${TZ:-Asia/Seoul}"

LOG_DIR=/app/logs
# 로그와 공고 데이터를 같은 기간만큼 보관한다 (.env 의 KEEP_DAYS 로 조절)
KEEP_DAYS="${KEEP_DAYS:-365}"
mkdir -p "$LOG_DIR"

# ISO 기준 주 (월요일 시작). 예: 2026-W36
LOG="$LOG_DIR/$(date +%G-W%V).log"

# 이 아래 모든 출력은 이번 주 로그 파일로 들어간다
exec >> "$LOG" 2>&1

echo ""
echo "═════════ $(date '+%Y-%m-%d %H:%M:%S') 시작 ═════════"

git config --global --add safe.directory /app

if [ ! -d .venv ]; then
  echo "가상환경을 처음 만드는 중 (1~2분)"
  python -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

git pull --rebase -q

.venv/bin/python main.py
RC=$?

git add docs/data/postings.json
if git diff --staged --quiet; then
  echo "저장할 변경 없음"
else
  git -c user.name=job-watch -c user.email=job-watch@nas \
      commit -q -m "공고 갱신 $(date '+%Y-%m-%d %H:%M')"
  if git push -q; then
    echo "GitHub 반영 완료"
  else
    echo "GitHub 반영 실패 (다음 실행 때 다시 시도)"
  fi
fi

# 1년 지난 주간 로그 정리
DELETED=$(find "$LOG_DIR" -maxdepth 1 -name '*.log' -type f -mtime +"$KEEP_DAYS" -print -delete 2>/dev/null | wc -l)
if [ "$DELETED" -gt 0 ]; then
  echo "오래된 로그 ${DELETED}개 삭제 (보관 ${KEEP_DAYS}일)"
fi

echo "───────── $(date '+%H:%M:%S') 끝 (종료코드 $RC)"
exit $RC
