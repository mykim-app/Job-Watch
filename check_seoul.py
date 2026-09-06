# 서울일자리포털 원본을 직접 세어 본다 (우리 필터와 무관)
import json, os, sys, urllib.request

KEY = os.environ.get("SEOUL_API_KEY", "").strip()
if not KEY:
    sys.exit("SEOUL_API_KEY 가 없습니다")

SVC = "recMntList"
IT = ["전산", "전자계산", "정보화", "정보통신", "정보시스템", "정보보안", "정보보호",
      "네트워크", "서버", "데이터베이스", "소프트웨어", "컴퓨터", "프로그래머",
      "홈페이지", "웹", "IT", "ICT", "디지털"]
PUB = ["공사", "공단", "재단", "협회", "진흥원", "연구원", "연구소", "공제회", "위원회",
       "조합", "의료원", "대학교", "대학", "교육청", "도서관", "문화원", "센터", "사업소",
       "관리원", "기술원", "평가원", "개발원", "정보원", "(재)", "(사)", "(학)",
       "재단법인", "사단법인", "학교법인", "테크노파크", "산학협력단", "학원", "학교"]

def call(a, b):
    url = f"http://openapi.seoul.go.kr:8088/{KEY}/json/{SVC}/{a}/{b}/"
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))

total = int(call(1, 1)[SVC]["list_total_count"])
print(f"전체 {total}건")

rows = []
for p in range(3):                       # 뒤에서부터 3000건
    end = total - p * 1000
    start = max(end - 999, 1)
    if end < 1:
        break
    rows += call(start, end)[SVC].get("row") or []
print(f"읽은 행 {len(rows)}건\n")

it = [r for r in rows
      if any(w in f"{r.get('TITLE','')} {r.get('JOBS_NM','')}" for w in IT)]
pub = [r for r in it if any(p in (r.get("COMPANY") or "") for p in PUB)]

print(f"전산 관련 낱말 포함 : {len(it)}건")
print(f"그중 공공·비영리 기관명 : {len(pub)}건\n")

print("── 공공·비영리 (있으면 우리 목록에 들어와야 할 후보)")
for r in pub[:20]:
    print(f"  [{(r.get('COMPANY') or '')[:20]}] {(r.get('TITLE') or '')[:40]}")
    print(f"      직종 {(r.get('JOBS_NM') or '')[:26]} · 고용형태 {(r.get('EMP_TP_NM') or '')[:30]} · 등록 {r.get('REG_DT')}")
if not pub:
    print("  없음")

print("\n── 전산 관련이지만 민간이라 빠지는 예시")
for r in [x for x in it if x not in pub][:10]:
    print(f"  [{(r.get('COMPANY') or '')[:20]}] {(r.get('TITLE') or '')[:40]}")
