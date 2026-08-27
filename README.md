# 전산·통신직 채용 감시

공공기관·지방공기업·협회 채용공고를 **매일 아침 9시에 한 번** 훑어서,
전산·통신 분야 공고 중 **어제까지 없던 것만** 골라 웹페이지에 올리고 메일로 보냅니다.

- 실행: GitHub Actions (내 PC를 켜둘 필요 없음, 무료)
- 화면: GitHub Pages 정적 페이지
- 알림: 신규 공고가 1건이라도 있을 때만 메일 발송 (0건이면 안 보냄)

---

## 1. 준비물 — 인증키 2개

| 무엇 | 어디서 | 걸리는 시간 |
|---|---|---|
| 잡알리오 인증키 | [공공데이터포털](https://www.data.go.kr) → `재정경제부_공공기관 채용정보 조회서비스` 검색 → 활용신청 | 보통 즉시 승인 |
| 워크넷 인증키 | 워크넷(고용24) 오픈API 신청 | 1~2일 심사 |

- 잡알리오 키는 **일반 인증키(Decoding)** 값을 씁니다. Encoding 값을 넣으면 계속 오류가 납니다.
- 워크넷 키가 아직 없어도 잡알리오만으로 먼저 돌려볼 수 있습니다.

메일 발송은 Gmail 기준으로, 구글 계정 → 보안 → **앱 비밀번호**를 하나 만들어서 씁니다.
(평소 로그인 비밀번호를 넣으면 안 됩니다.)

---

## 2. 설치 (10분)

> 처음 설치하는 분은 **`설치가이드.md`** 를 보세요. 화면 하나하나 따라가는 버전입니다.

1. GitHub에서 **공개(Public) 저장소**를 하나 만들고 이 폴더를 통째로 올립니다.
   (무료 계정은 공개 저장소에서만 Pages를 쓸 수 있습니다. 인증키·비밀번호는
   아래 Secrets에 암호화 저장되므로 공개돼도 노출되지 않습니다.)
2. **Settings → Actions → General → Workflow permissions** 를
   `Read and write permissions` 로 바꾸고 저장합니다. (이걸 빼먹으면 결과 저장이 실패합니다.)
3. 저장소 **Settings → Pages** → Source를 `Deploy from a branch`, 폴더를 **`/docs`** 로 지정.
   몇 분 뒤 `https://<아이디>.github.io/<저장소이름>/` 주소가 생깁니다.
4. **Settings → Secrets and variables → Actions → New repository secret** 에서 아래를 등록합니다.

   | 이름 | 값 |
   |---|---|
   | `ALIO_SERVICE_KEY` | 잡알리오 인증키 |
   | `WORKNET_AUTH_KEY` | 워크넷 인증키 (없으면 생략) |
   | `SMTP_HOST` | `smtp.gmail.com` |
   | `SMTP_PORT` | `587` |
   | `SMTP_USER` | 보내는 구글 계정 주소 |
   | `SMTP_PASS` | 앱 비밀번호 |
   | `MAIL_TO` | 받을 주소 (쉼표로 여러 개 가능) |

   같은 화면의 **Variables** 탭에 `SITE_URL` 로 2번의 Pages 주소를 넣어두면
   메일 본문에 전체 목록 링크가 같이 나갑니다.
5. **Actions 탭 → daily-job-watch → Run workflow** 로 한 번 수동 실행해서 결과를 확인합니다.

이후로는 매일 09시에 알아서 돕니다.

> GitHub의 예약 실행은 서버가 붐비면 **5~20분 정도 늦게** 시작될 수 있습니다.
> 정확히 09시 00분에 도착해야 한다면 cron 을 `50 23 * * *`(08:50 KST) 정도로 당겨두면 됩니다.

---

## 3. 어떻게 걸러내는가

기관마다 붙이는 직종코드가 제각각이라 **코드만 믿으면 누락이 큽니다.**
그래서 공고 제목과 직무분류 글자를 직접 맞춰보는 방식을 주로 쓰고, NCS 분류는 보조로만 씁니다.

키워드는 `config.yaml` 에서 고칩니다.

```yaml
filters:
  include:   # 이 중 하나라도 걸리면 수집
    - 전산
    - 정보통신
    - 정보보안
  exclude:   # 위에 걸려도 이게 있으면 버림 (오탐 제거)
    - 통신원
    - 홍보
```

`exclude` 를 잘 쓰는 게 핵심입니다. 예를 들어 `통신` 만 넣으면 '통신원 모집', '통신판매'
같은 공고가 잔뜩 들어옵니다. 며칠 돌려보고 눈에 거슬리는 단어를 여기에 추가하면 됩니다.

워크넷은 민간기업 공고가 대부분이라, `public_org_patterns`(공사·공단·재단·협회·진흥원 …)
에 기관명이 걸리는 것만 남깁니다. 놓치는 기관이 보이면 이 목록에 단어를 추가하세요.

---

## 4. 중복 처리

- 같은 공고가 매일 API에 잡혀도, 한 번 본 것은 **처음 본 날짜**를 기억해두고 다시 신규로 치지 않습니다.
- 잡알리오와 워크넷에 **같은 공고가 동시에** 올라오면 한쪽만 신규로 처리합니다.
  (기관명 + 공고제목에서 공백·괄호·기호를 뗀 값으로 비교)
- 기록은 `docs/data/postings.json` 한 파일에 쌓이고, 60일이 지난 건은 자동으로 빠집니다.
- 처음부터 다시 보고 싶으면 이 파일을 `{"updated_at":"","postings":[]}` 로 되돌리면 됩니다.

---

## 5. API가 없는 게시판 추가하기

클린아이 잡플러스, 나라일터, 개별 협회 홈페이지처럼 API가 없는 곳은
목록 페이지를 직접 읽어옵니다. `config.yaml` 의 `html_boards` 에 주소와 위치를 적어주면 됩니다.

찾는 방법:

1. PC 크롬으로 그 사이트의 채용 목록 페이지를 엽니다.
2. 공고 한 줄 위에서 **마우스 오른쪽 → 검사**.
3. 그 줄 전체를 감싸는 태그(보통 `<tr>` 또는 `<li>`)에서 **오른쪽 → Copy → Copy selector**.
4. 복사된 값에서 맨 끝의 순번(`:nth-child(3)` 같은 부분)만 지우고 `item` 에 넣습니다.
5. 제목·기관명·날짜 칸도 같은 방법으로 `title`, `org`, `date` 에 넣고 `enabled: true` 로 바꿉니다.

```yaml
- name: 클린아이 잡플러스
  key: cleaneye
  enabled: true
  url: https://job.cleaneye.go.kr/...
  selectors:
    item:  "table.board tbody tr"
    title: "td.subject a"
    link:  "td.subject a"
    org:   "td.org"
    date:  "td.date"
  link_base: https://job.cleaneye.go.kr
```

selector 가 틀리면 그 게시판만 0건으로 조용히 넘어가고 로그에 사유가 남습니다.
나머지 수집은 정상적으로 계속됩니다.

---

## 6. 파일 구성

```
main.py                수집 → 필터 → 중복 제거 → 저장 → 메일
config.yaml            키워드·수집처 설정 (여기만 손보면 됨)
filters.py             전산·통신직 판별
store.py               중복 기억 / 보관 기간 관리
notify.py              메일 발송
collectors/
  alio.py              잡알리오 (공공데이터포털)
  worknet.py           워크넷 (고용24)
  html_board.py        API 없는 게시판 공용 수집기
  base.py              공통 자료구조
docs/
  index.html           웹페이지 (GitHub Pages가 이걸 띄움)
  data/postings.json   누적 데이터 (Actions가 매일 갱신)
.github/workflows/daily.yml   매일 09시 실행 설정
```

---

## 7. 로컬에서 시험 실행

```bash
pip install -r requirements.txt
export ALIO_SERVICE_KEY="발급받은키"
python main.py
```

메일 설정 없이 돌리면 수집·중복 제거까지만 하고 발송은 건너뜁니다.
`docs/data/postings.json` 이 채워졌는지 확인한 뒤,
`cd docs && python -m http.server 8000` 으로 화면을 미리 볼 수 있습니다.
