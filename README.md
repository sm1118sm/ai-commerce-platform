# StylePick AI

사용자의 관심사와 검색·클릭·찜·장바구니·구매 행동을 분석해 개인별 상품과
추천 이유를 보여주는 AI 이커머스 포트폴리오입니다.

## 바로가기

- [StylePick AI 실행하기](https://ai-commerce-platform-nbtk9sjwlwpfozv2wpqjfa.streamlit.app/)
- [최종 발표자료 보기 (PDF)](발표자료.pdf)
- [최종 발표자료 다운로드 (PPTX)](발표자료.pptx)

## 핵심 기능

- 이메일·닉네임 중복 확인과 비밀번호 규칙을 적용한 회원가입
- PBKDF2 해시 기반 비밀번호 저장과 로그인 유지
- 회원별 AI 추천 취향과 행동 데이터 저장
- TextCNN 기반 상품 추천과 상품별 추천 이유 제공
- 상품 검색·카테고리·가격 필터와 정렬
- 찜, 장바구니, 모의결제, 재고 차감, 주문 취소
- 프로필 및 주문 내역 관리
- 데스크톱·모바일 반응형 UI

## 추천 방식

TextCNN이 상품명·카테고리·설명·태그·브랜드의 의미 특징을 학습합니다.
사용자의 클릭, 찜, 장바구니, 구매 행동과 저장한 관심 카테고리·가격대를
함께 반영해 회원마다 다른 추천 순서를 제공합니다.

## 기술 구성

| 영역 | 기술 |
| --- | --- |
| 웹 | Python, Streamlit, 반응형 CSS |
| AI 추천 | TextCNN, NumPy 기반 추론 |
| 데이터베이스 | MySQL 8.4, Aiven, PyMySQL |
| 인증·보안 | PBKDF2 비밀번호 해시, 로그인 세션 |
| 배포·검증 | Streamlit Community Cloud, Docker, GitHub Actions |

## 로컬 실행

준비물은 [Git](https://git-scm.com/downloads)과
[Docker Desktop](https://www.docker.com/products/docker-desktop/)입니다.

```bash
git clone https://github.com/sm1118sm/ai-commerce-platform.git
cd ai-commerce-platform
docker compose up -d --build
```

- 쇼핑몰: `http://localhost:8501`
- 종료: `docker compose down`

## 운영 DB 자동 복구

운영 환경은 Aiven MySQL 무료 플랜을 사용한다. GitHub Actions watchdog이
5분 예약 주기 안에서 30초마다 서비스 상태를 확인하고, `POWEROFF` 상태면
자동으로 전원을 켠 뒤 `RUNNING`까지 기다린다.

앱은 MySQL이 시작되는 동안 연결을 지수 백오프로 재시도한다. 연결 실패가
계속되면 PyMySQL 원문 오류를 사용자에게 노출하지 않고 복구 안내를 표시한 뒤
새 연결로 자동 재실행한다.

설정과 보장 범위는 [Aiven MySQL 자동 복구](docs/AIVEN_WATCHDOG.md)를 참고한다.

## 일일 운영 리포트 자동화

전일의 회원·검색·상품 행동·모의 주문·재고를 읽기 전용으로 집계해
`reports/daily/YYYY-MM-DD.md`와 `logs/daily_report.log`를 생성한다.

테스트 입력으로 실행:

```bash
bash scripts/run_daily_report.sh \
  --date 2026-08-02 \
  --sample-json data/daily_report_sample.json
```

운영 DB로 전일 보고서 실행(`.env`의 `DATABASE_URL` 사용):

```bash
bash scripts/run_daily_report.sh
```

생성한 보고서를 `sm1118sm@gmail.com`으로 보내려면 Google 계정에서 2단계
인증과 앱 비밀번호를 만든 뒤, Git에서 제외된 `.env`에 다음 값을 설정한다.
일반 Google 계정 비밀번호는 사용하지 않는다.

```dotenv
STYLEPICK_REPORT_RECIPIENT=sm1118sm@gmail.com
STYLEPICK_SMTP_USERNAME=sm1118sm@gmail.com
STYLEPICK_SMTP_APP_PASSWORD=발급받은_16자리_앱_비밀번호
```

수동 발송:

```bash
bash scripts/run_daily_report.sh --send-email
```

운영 자동 발송은 `.github/workflows/daily-operations-report.yml`이 GitHub
Actions에서 한국 시간 매일 오전 9시에 실행한다. PC가 꺼져 있어도 동작하며
`DATABASE_URL`, `STYLEPICK_SMTP_USERNAME`, `STYLEPICK_SMTP_APP_PASSWORD`는
GitHub Actions Secret으로만 관리한다. 생성된 보고서와 로그는 Actions 실행의
artifact로 7일 동안 보관한다.

VPS `cron`을 대신 사용하려면 `crontab -e`에 프로젝트의 실제 절대 경로로 다음
한 줄을 등록한다.

```cron
0 9 * * * /usr/bin/bash /absolute/path/ai-commerce-platform/scripts/run_daily_report.sh --send-email
```

보고서 생성은 성공했지만 SMTP 인증이나 발송이 실패하면 종료 코드 1과 `FAIL`
로그를 남긴다. 비밀번호와 DB 접속 주소는 로그에 기록하지 않는다.

설계와 안전 범위는 [프로젝트 원페이지](docs/project_one_pager.md)를 참고한다.

## 상세 문서

- [배포 방법](docs/DEPLOYMENT.md)
- [추천 모델 설계](docs/RECOMMENDER_DESIGN.md)
- [개인화 UI/UX 설계](docs/PERSONALIZED_UX_DESIGN.md)

> 결제와 주문은 포트폴리오 시연용이며 실제 결제는 발생하지 않습니다.
