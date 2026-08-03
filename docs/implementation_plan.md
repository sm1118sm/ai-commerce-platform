# StylePick AI 일일 운영 리포트 구현 계획

## 승인 결정

승인 — 사용자가 2026-08-03에 제안된 주제로 진행을 요청함.

## 구현 범위

- MySQL/PostgreSQL 공통 읽기 전용 SQL 집계
- 날짜별 Markdown 보고서 생성
- 테스트 JSON 입력 지원
- 성공·실패 실행 로그
- Gmail SMTP를 통한 선택적 보고서 발송
- VPS `cron` 실행 절차와 자동 테스트

## 제외 범위

- Gmail 보고서 외 실제 게시·결제·삭제
- 운영 데이터 생성·수정
- 추천 CTR 및 검색별 구매 전환 추정
- Streamlit 관리자 대시보드

## 입력·결과 경로

- 테스트 입력: `data/daily_report_sample.json`
- 실행기: `scripts/generate_daily_report.py`
- 운영 실행 래퍼: `scripts/run_daily_report.sh`
- 결과: `reports/daily/{YYYY-MM-DD}.md`
- 로그: `logs/daily_report.log`
- 수신 주소: `STYLEPICK_REPORT_RECIPIENT` Secret

## 구현 순서

1. 날짜 범위의 회원·행동·주문·상품 데이터를 읽기 전용으로 집계한다.
2. 지표·간이 전환·주의 항목을 Markdown으로 렌더링한다.
3. 샘플 입력 CLI와 가짜 SMTP 테스트로 결과·로그·이메일 구성을 검증한다.

## 성공 증거

- `python -m unittest tests.test_daily_report -v` 성공
- 샘플 CLI 종료 상태 0
- 결과 파일과 `SUCCESS` 로그 존재
- 이메일 제목·본문·첨부파일·수신 주소 테스트 성공

## 위험 및 중단 조건

- `DATABASE_URL`이 없거나 DB 연결이 실패하면 파일을 생성하지 않고 종료 상태
  1과 `FAIL` 로그를 남긴다.
- 스키마의 필수 테이블·컬럼이 없으면 추측하거나 보정하지 않고 실패한다.
- 추천 노출·검색 주문 연결처럼 근거가 없는 지표는 보고서에서 명시적으로 제외한다.
- SMTP 설정이 없거나 인증이 실패하면 발송 성공으로 기록하지 않고 종료 상태 1과
  `FAIL` 로그를 남긴다.

## 추가 자율학습 항목

- 추천 노출·클릭 이벤트 계약
- 날짜 컬럼을 문자열에서 DB 시간 타입으로 이전하는 방법
- 운영 DB 읽기 전용 계정과 최소 권한 설정
