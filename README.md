# StylePick AI

사용자의 관심사·검색·클릭·찜·장바구니·구매 행동을 학습해 상품과 추천
이유를 보여주는 설명 가능한 AI 이커머스 MVP입니다.

**공개 사이트:** [StylePick AI 실행하기](https://ai-commerce-platform-nbtk9sjwlwpfozv2wpqjfa.streamlit.app/)

**예비 사이트:** [Render에서 실행하기](https://ai-commerce-platform-5ovk.onrender.com/)

## 주요 기능

- 2030 타깃 상품 30개 검색, 필터, 상세 보기
- 이메일·닉네임·전화번호 중복을 차단하는 회원가입
- PBKDF2 비밀번호 해시, 로그인, 회원탈퇴
- 선택 시 새로고침과 재방문에도 유지되는 2시간 보안 로그인
- 회원별 찜, 장바구니, 모의 주문, 행동 로그
- TF-IDF/E5와 사용자 행동을 결합한 하이브리드 추천
- 추천 상품별 설명과 신규 사용자를 위한 콜드 스타트 추천
- 데스크톱·모바일 반응형 이커머스 UI
- 로컬 MySQL과 Aiven 관리형 MySQL 지원

> 결제와 주문은 포트폴리오 시연용이며 실제 결제는 발생하지 않습니다.

## 로컬에서 바로 실행

준비물은 [Git](https://git-scm.com/downloads)과
[Docker Desktop](https://www.docker.com/products/docker-desktop/)입니다.

```bash
git clone https://github.com/sm1118sm/ai-commerce-platform.git
cd ai-commerce-platform
docker compose up -d --build
```

- 쇼핑몰: `http://localhost:8501`
- 회원 DB 확인: `http://localhost:8081`
- 종료: `docker compose down`

무료 호스팅과 빠른 시작을 위해 기본 추천 모델은 TF-IDF입니다.
E5를 사용하려면 `.env.example`을 `.env`로 복사하고
`RECOMMENDER_BACKEND=e5`로 변경하세요.

## 데이터베이스

별도 설정 없이 실행하면 Docker의 로컬 MySQL을 사용합니다. 로컬과 Render가
같은 Aiven MySQL을 사용하게 하려면 Git에서 제외된 `.env`와 Render Secret의
`DATABASE_URL`에 같은 Service URI를 설정합니다.

```text
mysql://USER:URL_ENCODED_PASSWORD@HOST:PORT/defaultdb?ssl-mode=REQUIRED
```

비밀번호 원문은 저장하지 않습니다. `admin_user_overview` 뷰에서는 가입
이메일, 닉네임, 마스킹된 전화번호, 가입 시각만 확인할 수 있습니다.
실제 DB 주소·비밀번호·`.env`는 GitHub에 올리지 마세요.

## 기술 구성

| 영역 | 기술 |
| --- | --- |
| 웹 | Streamlit, 반응형 CSS |
| 추천 | Sentence Transformers E5, TF-IDF, 행동 가중치 |
| 데이터 | MySQL 8.4, PyMySQL, pandas |
| 배포 | Streamlit Community Cloud, Render, GitHub Actions, Aiven |
| 품질 | unittest, MySQL/PostgreSQL CI 통합 테스트 |

## 테스트

```bash
python -m unittest discover -s tests -v
```

DB 통합 테스트에는 이름이 `_test`로 끝나는 별도 테스트 DB만 사용합니다.

## 문서

- [배포 방법](docs/DEPLOYMENT.md)
- [다음 작업 체크리스트](docs/ROADMAP.md)
- [추천 모델 설계](docs/RECOMMENDER_DESIGN.md)
- [개인화 UI/UX 설계](docs/PERSONALIZED_UX_DESIGN.md)
- [작업 재개 가이드](docs/WORK_RESUME_GUIDE.md)
