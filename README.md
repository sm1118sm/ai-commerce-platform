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

## 로컬 실행

가장 간단한 방법은 Docker Compose로 앱과 MySQL을 함께 실행하는 것입니다.

```bash
docker compose up --build
```

브라우저에서 `http://localhost:8501`을 엽니다. MySQL 데이터는
`mysql_data` 볼륨에 저장되어 앱을 다시 시작해도 유지됩니다.

### MySQL 회원 데이터 확인

Docker Compose 실행 후 `http://localhost:8081`에서 Adminer를 엽니다.

- 시스템: `MySQL`
- 서버: `mysql`
- 사용자명·비밀번호·DB명: `.env`의 `MYSQL_USER`,
  `MYSQL_PASSWORD`, `MYSQL_DATABASE`

로그인 후 `admin_user_overview` 뷰를 선택하면 가입 이메일, 닉네임, 마스킹된
전화번호와 가입 시각을 확인할 수 있습니다. 비밀번호 원문은 저장하지 않으며
관리자 뷰에는 `HASHED`로만 표시됩니다.

앱만 직접 실행하려면 MySQL 8을 먼저 준비하고 `DATABASE_URL`을 설정합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='mysql://stylepick:비밀번호@localhost:3306/stylepick'
streamlit run app.py
```

로그인 화면에서 `데모 계정으로 바로 시작`을 누르면 별도 가입 없이 전체
기능을 시연할 수 있습니다.

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
