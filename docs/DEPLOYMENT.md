# StylePick AI HTTPS 배포 절차

## 준비된 배포 구성

- `Dockerfile`: Python 3.12 기반 Streamlit 이미지
- `render.yaml`: Render 웹 서비스와 PostgreSQL Blueprint
- `database/postgres_schema.sql`: 운영 DB 스키마
- `scripts/migrate_sqlite_to_postgres.py`: SQLite 데이터 이전
- `/_stcore/health`: 배포 상태 확인 경로

## 1. GitHub 저장소 만들기

GitHub에서 비어 있는 저장소를 만든 후 프로젝트 폴더에서 실행한다.

```bash
git remote add origin https://github.com/사용자명/stylepick-ai.git
git branch -M main
git push -u origin main
```

`data/stylepick.db`, `.env`, `.venv`는 `.gitignore`에 의해 업로드되지 않는다.

## 2. Render Blueprint 배포

1. Render Dashboard에 로그인한다.
2. `New` → `Blueprint`를 선택한다.
3. GitHub의 StylePick AI 저장소를 연결한다.
4. 저장소 루트의 `render.yaml`을 선택한다.
5. 웹 서비스와 PostgreSQL 생성 내용을 확인한다.
6. Blueprint를 적용한다.

`DATABASE_URL`은 Blueprint가 PostgreSQL의 내부 연결 주소를 웹 서비스에
자동 전달한다. 비밀번호를 YAML에 직접 넣지 않는다.

## 3. 최초 배포 확인

Render 로그에서 다음 항목을 확인한다.

```text
Successfully installed ...
Uvicorn server started ...
```

배포 주소에서 확인:

```text
https://stylepick-ai.onrender.com/_stcore/health
```

정상 응답:

```text
ok
```

실제 서비스 이름에 따라 주소의 앞부분은 달라질 수 있다.

## 4. SQLite 데이터를 옮길 경우

새 PostgreSQL이 비어 있을 때만 실행한다.

```bash
export DATABASE_URL='postgresql://...'
python scripts/migrate_sqlite_to_postgres.py \
  --sqlite data/stylepick.db
```

대상 PostgreSQL에 회원 데이터가 이미 있으면 스크립트가 자동 중단한다.

## 5. 배포 후 필수 시나리오

1. 신규 회원가입
2. 로그아웃 후 다시 로그인
3. 관심 카테고리와 예산 저장
4. 상품 상세 조회·검색·찜
5. 추천 결과 변화 확인
6. 장바구니와 모의 주문
7. 주문 내역 확인
8. 다른 회원으로 로그인해 데이터 격리 확인
9. 재배포 후 데이터 유지 확인

## 6. 무료 배포 제한

Render 무료 웹 서비스는 일정 시간 요청이 없으면 내려가며 첫 접속에 시간이
걸릴 수 있다. 로컬 SQLite 파일은 재시작 시 유실되므로 반드시 PostgreSQL을
사용한다.

무료 Render PostgreSQL은 30일 후 만료되고 백업 기능이 없다. 발표 일정이
30일 이상 남았다면 발표일에 맞춰 생성하거나, 유료 DB 또는 다른 관리형
PostgreSQL을 연결한다.

공식 문서:

- [Render Blueprint YAML](https://render.com/docs/blueprint-spec)
- [Render 무료 서비스 제한](https://render.com/docs/free)
- [Render Docker 배포](https://render.com/docs/docker)

## 7. 현재 외부 배포에 필요한 사용자 작업

자동으로 대신할 수 없는 항목은 두 가지다.

1. GitHub 저장소 URL 또는 GitHub 업로드 권한
2. Render 계정에서 GitHub 저장소 연결 및 Blueprint 생성 승인

이 두 연결이 완료되면 생성된 HTTPS URL에서 최종 시나리오를 검증하면 된다.

