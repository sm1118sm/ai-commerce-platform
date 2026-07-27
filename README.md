# StylePick AI

사용자의 관심 카테고리, 찜한 상품, 예산을 분석해 상품과 추천 이유를
보여주는 설명 가능한 AI 이커머스 MVP입니다.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sm1118sm/ai-commerce-platform)

## 핵심 기능

- 30개 상품 탐색, 검색, 카테고리·가격 필터
- 회원가입·로그인·로그아웃과 회원별 데이터 분리
- 이메일·닉네임·전화번호 중복 가입 차단과 비밀번호 확인 회원탈퇴
- 상품 상세 모달, 찜, 장바구니
- 클릭·검색·찜·장바구니·구매 행동 로그
- TF-IDF 콘텐츠와 최근 행동·트렌드를 결합한 하이브리드 추천
- 추천 상품별 자연어 추천 이유
- 데이터가 없는 사용자를 위한 콜드 스타트 추천
- 실제 결제가 발생하지 않는 모의 주문 완료
- MySQL 8 기반 회원·상품·재고·주문 트랜잭션
- 로컬 MySQL·외부 관리형 MySQL·PostgreSQL을 지원하는 DB 어댑터

## 누구나 실행하는 가장 쉬운 방법

준비물은 다음 두 가지뿐입니다.

- [Git](https://git-scm.com/downloads)
- Docker Compose가 포함된 [Docker Desktop](https://www.docker.com/products/docker-desktop/)

저장소를 받은 뒤 루트 폴더에서 아래 명령을 실행합니다. 별도의 MySQL 설치나
`.env` 파일 없이도 로컬 개발용 기본값으로 실행됩니다.

```bash
git clone https://github.com/sm1118sm/ai-commerce-platform.git
cd ai-commerce-platform
docker compose up -d --build
```

첫 실행은 PyTorch와 E5 한국어 추천 모델을 내려받아 이미지를 만들기 때문에
인터넷 환경과 PC 성능에 따라 수 분 이상 걸릴 수 있습니다. 빌드가 끝나면
다음 주소를 사용합니다.

| 서비스 | 주소 | 용도 |
| --- | --- | --- |
| StylePick AI | `http://localhost:8501` | 쇼핑몰·회원가입·AI 추천 |
| Adminer | `http://localhost:8081` | MySQL 데이터 확인 |
| MySQL | `localhost:3306` | 앱 데이터베이스 |

정상 실행 확인:

```bash
docker compose ps
curl http://localhost:8501/_stcore/health
```

헬스체크가 `ok`를 반환하면 준비가 끝난 것입니다. 로그인 화면의
`데모 계정으로 바로 시작`을 누르면 별도 가입 없이 전체 기능을 시연할 수
있습니다.

로그 보기와 종료:

```bash
docker compose logs -f app
docker compose down
```

MySQL 데이터는 `mysql_data` 볼륨에 저장되므로 `docker compose down` 이후에도
유지됩니다. 모든 로컬 회원·주문 데이터를 정말 초기화할 때만 다음 명령을
사용하세요.

```bash
docker compose down --volumes
```

이 명령은 복구하기 어려운 데이터 삭제 작업입니다.

### 선택 사항: 로컬 설정 변경

기본 포트와 개발용 계정으로 실행할 때는 `.env`가 필요하지 않습니다.
비밀번호나 추천 백엔드를 바꾸려는 경우에만 예시 파일을 복사합니다.

```bash
cp .env.example .env
```

`.env`에는 비밀값이 들어가므로 GitHub에 커밋하지 않습니다. `DATABASE_URL`을
비워두면 로컬 Docker MySQL을 사용합니다. Aiven Service URI를 넣으면 로컬
앱과 Render가 같은 관리형 MySQL을 사용하므로 어느 주소에서 가입해도 동일한
회원·행동·장바구니·주문 데이터가 보입니다.

```dotenv
DATABASE_URL=mysql://avnadmin:URL인코딩된비밀번호@호스트:포트/defaultdb?ssl-mode=REQUIRED
```

Render에는 같은 값을 웹 서비스의 Secret 환경변수로 등록합니다. 실제 URI나
비밀번호는 `.env.example`, 문서, GitHub 이슈 또는 PR에 기록하지 않습니다.

### MySQL 회원 데이터 확인

Docker Compose 실행 후 `http://localhost:8081`에서 Adminer를 엽니다.

- 시스템: `MySQL`
- 서버: `mysql`
- 사용자명: `stylepick`
- 비밀번호: `stylepick_dev_password`
- 데이터베이스: `stylepick`

`.env`를 만들었다면 위 값 대신 해당 파일의 `MYSQL_USER`,
`MYSQL_PASSWORD`, `MYSQL_DATABASE`를 사용합니다.

로그인 후 `admin_user_overview` 뷰를 선택하면 가입 이메일, 닉네임, 마스킹된
전화번호와 가입 시각을 확인할 수 있습니다. 비밀번호 원문은 저장하지 않으며
관리자 뷰에는 `HASHED`로만 표시됩니다.

### Docker 없이 직접 실행

Python 3.12와 MySQL 8이 이미 설치된 환경에서만 이 방법을 사용합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='mysql://stylepick:비밀번호@localhost:3306/stylepick'
streamlit run app.py
```

Windows PowerShell에서는 가상환경 활성화와 환경변수를 다음처럼 설정합니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "mysql://stylepick:비밀번호@localhost:3306/stylepick"
streamlit run app.py
```

### 실행 문제 해결

- `docker` 명령을 찾지 못함: Docker Desktop을 설치하고 다시 터미널을 엽니다.
- WSL에서 Docker 연결 오류: Docker Desktop의 WSL Integration을 활성화합니다.
- `8501`, `8081`, `3306` 포트 충돌: 해당 포트를 사용하는 기존 프로그램이나
  컨테이너를 중지합니다.
- 앱이 아직 열리지 않음: `docker compose ps`에서 MySQL이 `healthy`인지 보고
  `docker compose logs -f app`으로 모델 로딩 상태를 확인합니다.
- 메모리 부족: Docker Desktop에 충분한 메모리를 할당하거나 `.env`에서
  `RECOMMENDER_BACKEND=tfidf`로 바꿔 가벼운 추천 모델로 실행합니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

MySQL 통합 테스트까지 실행하려면 이름이 `_test`로 끝나는 별도 DB를 만든 후
접속 주소를 지정합니다.

```bash
export STYLEPICK_TEST_DATABASE_URL='mysql://stylepick:비밀번호@localhost:3306/stylepick_test'
python -m unittest discover -s tests -v
```

상세한 기획, 알고리즘, 3일 일정, 시연 및 발표 자료는
[`docs/CAPSTONE_GUIDE.md`](docs/CAPSTONE_GUIDE.md)를 참고하세요.

실제 사용자에게 공개하기 전에 필요한 데이터베이스 이전, 보안, 배포,
모니터링, 추천 평가 작업은
[`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md)에 정리되어
있습니다.

Render와 외부 관리형 MySQL을 이용한 HTTPS 배포 방법은
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)를 참고하세요.
