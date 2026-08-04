# StylePick AI 데이터베이스·앱 배포 절차

## 준비된 배포 구성

- `Dockerfile`: Python 3.12 기반 Streamlit 이미지
- `docker-compose.yml`: 로컬 앱과 MySQL 8 실행
- `render.yaml`: Render 웹 서비스 설정
- `scripts/streamlit_watchdog.py`: Streamlit 상태 확인·자동 resume 워커
- `database/mysql_schema.sql`: 로컬 Docker용 MySQL 8 스키마
- `database/postgres_schema.sql`: 선택 가능한 PostgreSQL 스키마
- `scripts/migrate_sqlite_to_mysql.py`: 기존 SQLite 데이터 이전
- `/_stcore/health`: 배포 상태 확인 경로

## 1. 로컬에서 MySQL 버전 확인

```bash
cp .env.example .env
docker compose up --build
```

브라우저에서 `http://localhost:8501`에 접속해 회원가입, 찜, 장바구니와 모의
주문까지 확인한다. 앱과 DB를 중지할 때는 다음 명령을 사용한다.

```bash
docker compose down
```

`mysql_data` 볼륨을 삭제하지 않는 한 데이터는 유지된다.

## 2. 운영 데이터베이스 준비

Aiven 같은 외부 관리형 MySQL을 준비하면 로컬 앱과 Render가 하나의 DB를
공유할 수 있다. 다음 정보를 확인한다.

- 호스트
- 포트(기본값 `3306`)
- 데이터베이스명
- 사용자명과 비밀번호
- 서비스가 요구하는 TLS 설정

접속 주소 형식:

```text
mysql://사용자명:비밀번호@호스트:포트/데이터베이스명?ssl-mode=REQUIRED
postgresql://사용자명:비밀번호@호스트:5432/데이터베이스명
```

비밀번호에 `@`, `:`, `/` 같은 문자가 있으면 URL 인코딩해야 한다.

## 3. Render 웹 서비스 배포

1. Render Dashboard에서 `New` → `Blueprint`를 선택한다.
2. GitHub의 StylePick AI 저장소를 연결한다.
3. 저장소 루트의 `render.yaml`을 적용한다.
4. `DATABASE_URL` Secret에 운영 PostgreSQL 또는 MySQL 접속 주소를 입력한다.
5. 배포 로그와 `/_stcore/health` 응답을 확인한다.

`render.yaml`의 `autoDeployTrigger: commit` 설정으로 GitHub `main`에 새
커밋이 병합될 때마다 Streamlit Docker 서비스가 자동으로 다시 배포된다.

Render 구성은 무료 플랜을 유지한다. Streamlit Community Cloud의 장기 30초
감시는 [무료 Cloudflare watchdog](CLOUDFLARE_WATCHDOG.md)이 담당한다. GitHub
Actions에도 동일한 복구 작업이 있지만 예약 실행은 지연되거나 비활성화될 수
있으므로 Cloudflare 배포 전 임시 안전 장치로만 사용한다.

MySQL을 선택하면 Render가 관리형 MySQL을 직접 생성하지 않으므로 외부
MySQL을 먼저 준비해야 한다. `DATABASE_URL`을 YAML이나 GitHub에 직접 넣지
않는다.

로컬에서도 같은 관리형 MySQL을 사용하려면 Git에서 제외된 `.env`에 동일한
`DATABASE_URL`을 저장하고 `docker compose up -d --build`를 실행한다.
Aiven 무료 서비스는 비활성 상태에서 자동으로 정지되므로 첫 접속이 평소보다
느릴 수 있다.

정지 상태 감지와 자동 복구 설정은
[Aiven MySQL 자동 복구](AIVEN_WATCHDOG.md)를 따른다.

## 4. 기존 SQLite 데이터를 옮길 경우

대상 MySQL에 회원 데이터가 없을 때 실행한다.

```bash
export DATABASE_URL='mysql://...'
python scripts/migrate_sqlite_to_mysql.py --sqlite data/stylepick.db
```

대상 MySQL에 회원 데이터가 있으면 안전을 위해 스크립트가 중단된다.

## 5. 배포 후 필수 확인

1. 신규 회원가입
2. 로그아웃 후 다시 로그인
3. 관심 카테고리와 예산 저장
4. 상품 상세 조회·검색·찜
5. 추천 결과 변화 확인
6. 장바구니와 모의 주문
7. 주문 내역 확인
8. 다른 회원으로 로그인해 데이터 격리 확인
9. 재배포 후 데이터 유지 확인

## 6. 운영 주의사항

- MySQL과 앱 서버는 가능하면 가까운 리전에 배치한다.
- 개발·테스트·운영 DB를 분리한다.
- 자동 백업과 복원 절차를 확인한다.
- 무료 DB의 중지·용량·접속 수 제한을 확인한다.
- 운영 DB에는 `STYLEPICK_TEST_DATABASE_URL`을 절대 지정하지 않는다.

공식 문서:

- [Render Blueprint YAML](https://render.com/docs/blueprint-spec)
- [Render Docker 배포](https://render.com/docs/docker)
- [MySQL 8.4 Reference Manual](https://dev.mysql.com/doc/refman/8.4/en/)
