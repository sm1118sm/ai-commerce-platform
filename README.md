# StylePick AI

사용자의 관심 카테고리, 찜한 상품, 예산을 분석해 상품과 추천 이유를
보여주는 설명 가능한 AI 이커머스 MVP입니다.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/sm1118sm/ai-commerce-platform)

## 핵심 기능

- 30개 상품 탐색, 검색, 카테고리·가격 필터
- 회원가입·로그인·로그아웃과 회원별 데이터 분리
- 상품 상세 모달, 찜, 장바구니
- 클릭·검색·찜·장바구니·구매 행동 로그
- TF-IDF 콘텐츠와 최근 행동·트렌드를 결합한 하이브리드 추천
- 추천 상품별 자연어 추천 이유
- 데이터가 없는 사용자를 위한 콜드 스타트 추천
- 실제 결제가 발생하지 않는 모의 주문 완료
- SQLite 기반 회원·상품·재고·주문 트랜잭션

## 로컬 실행

Python 3.11 또는 3.12를 권장합니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

브라우저에서 `http://localhost:8501`을 엽니다.

첫 실행 시 `data/stylepick.db`가 자동 생성됩니다. 새로고침하거나 앱을
재시작해도 프로필, 찜, 장바구니, 모의 주문 내역이 유지됩니다.

로그인 화면에서 `데모 계정으로 바로 시작`을 누르면 별도 가입 없이 전체
기능을 시연할 수 있습니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

## Docker

```bash
docker build -t stylepick-ai .
docker run --rm -p 8501:8501 stylepick-ai
```

상세한 기획, 알고리즘, 3일 일정, 시연 및 발표 자료는
[`docs/CAPSTONE_GUIDE.md`](docs/CAPSTONE_GUIDE.md)를 참고하세요.

실제 사용자에게 공개하기 전에 필요한 데이터베이스 이전, 보안, 배포,
모니터링, 추천 평가 작업은
[`docs/PRODUCTION_READINESS.md`](docs/PRODUCTION_READINESS.md)에 정리되어
있습니다.

Render와 PostgreSQL을 이용한 HTTPS 배포 명령은
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)를 참고하세요.
