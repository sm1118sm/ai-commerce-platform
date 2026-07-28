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
- TextCNN 후보 검색과 쇼핑 신호 랭킹을 결합한 2단계 회원별 추천
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

추천 모델은 TextCNN 하나만 사용합니다. 학습된 약 124KB 모델을 NumPy로
추론하므로 무료 호스팅에서도 별도의 GPU나 무거운 딥러닝 런타임이
필요하지 않습니다.

## 데이터베이스

별도 설정 없이 실행하면 Docker의 로컬 MySQL을 사용합니다. 로컬과 배포
사이트가 같은 Aiven MySQL을 사용하게 하려면 Git에서 제외된 `.env`,
Streamlit Secrets와 Render Environment의 `DATABASE_URL`에 같은 Service
URI를 설정합니다.

```text
mysql://USER:URL_ENCODED_PASSWORD@HOST:PORT/defaultdb?ssl-mode=REQUIRED
```

비밀번호 원문은 저장하지 않습니다. `admin_user_overview` 뷰에서는 가입
이메일, 닉네임, 마스킹된 전화번호, 가입 시각만 확인할 수 있습니다.
실제 DB 주소·비밀번호·`.env`는 GitHub에 올리지 마세요.

### Aiven 회원 DB를 DBeaver에서 확인하기

Aiven 웹 화면의 **Connect → Users**는 쇼핑몰 회원 목록이 아니라 DB 접속
계정입니다. 실제 쇼핑몰 회원은 `defaultdb` 데이터베이스의 `users`
테이블에서 확인합니다.

1. [Aiven Console](https://console.aiven.io/)에서 MySQL 서비스를 선택한다.
2. **Overview → Quick connect**를 열어 `Host`, `Port`, `User`,
   `Password`를 확인한다.
3. 무료 [DBeaver Community](https://dbeaver.io/download/)를 설치하고
   실행한다.
4. 왼쪽 위 **새 데이터베이스 연결 → MySQL → Next**를 선택한다.
5. DBeaver 연결 화면에 다음 값을 입력한다.

   | DBeaver 입력란 | Aiven에서 넣을 값 |
   | --- | --- |
   | Server Host | `Host` |
   | Port | `Port` |
   | Database | `defaultdb` |
   | Username | `User` |
   | Password | `Password` |

6. **Test Connection**을 누른다. 드라이버 설치 안내가 나오면
   **Download**를 누르고, 연결 성공 후 **Finish**를 누른다.
7. 왼쪽 **Database Navigator → 연결한 MySQL → defaultdb → Tables →
   users**로 이동한다.
8. `users`를 마우스 오른쪽 버튼으로 누르고 **View Data → All Rows**를
   선택한다.

회원 목록에 필요한 항목만 안전하게 조회하려면 DBeaver의 SQL 편집기에서
다음을 실행합니다.

```sql
SELECT id, email, nickname, phone_number, status,
       created_at, last_login_at
FROM users
ORDER BY id DESC;
```

관련 데이터는 `user_preferences`(AI 추천 취향), `user_favorites`(찜),
`user_cart`(장바구니), `user_orders`와 `order_items`(주문),
`behavior_logs`(클릭·검색·구매 행동)에서 확인할 수 있습니다. 운영 DB에서는
의도하지 않은 `UPDATE`, `DELETE`, 테이블 삭제를 실행하지 마세요.

### Aiven DB 연결 오류 해결

다음 증상은 Aiven 무료 MySQL 서비스가 비활성화됐거나 Service URI가 변경된
경우 발생할 수 있습니다.

- `pymysql.err.InterfaceError` 또는 `OperationalError`
- `Name or service not known`
- 웹사이트에 `로그인 정보를 불러오는 중 데이터베이스 연결이 잠시
  끊겼습니다`라는 안내가 표시됨

해결 순서는 다음과 같습니다.

1. [Aiven Console](https://console.aiven.io/)에서 MySQL 서비스를 연다.
2. 서비스가 `POWERED OFF`이면 **Actions → Power on service**를 선택한다.
3. 상태가 `RUNNING`이 될 때까지 기다린다.
4. **Overview → Quick connect**에서 현재 Service URI를 확인한다.
5. URI가 변경됐다면 로컬 `.env`와 Streamlit의 **Settings → Secrets**에
   있는 `DATABASE_URL`을 새 URI로 교체한다.
6. Streamlit Secrets를 저장하고 **Reboot app**을 실행한다.
7. 웹사이트를 다시 열거나 오류 화면의 **다시 연결** 버튼을 누른다.

Aiven 무료 서비스는 활동이 적으면 자동으로 꺼질 수 있습니다. 전체 Service
URI에는 DB 비밀번호가 포함되므로 README, GitHub Issue, 채팅 또는 화면
캡처에 노출하지 마세요.

## 기술 구성

| 영역 | 기술 |
| --- | --- |
| 웹 | Streamlit, 반응형 CSS |
| 추천 | TextCNN Two-Tower 후보 검색, 하이브리드 랭킹, NumPy 추론 |
| 데이터 | MySQL 8.4, PyMySQL, pandas |
| 배포 | Streamlit Community Cloud, Render, GitHub Actions, Aiven |
| 품질 | unittest, MySQL/PostgreSQL CI 통합 테스트 |

## 테스트

```bash
python -m unittest discover -s tests -v
```

DB 통합 테스트에는 이름이 `_test`로 끝나는 별도 테스트 DB만 사용합니다.

## CNN 모델 다시 학습

상품 카탈로그를 변경한 뒤 다음 명령으로 TextCNN 모델 파일을 다시
학습할 수 있습니다.

```bash
python scripts/train_textcnn.py
```

모델은 상품명·카테고리·설명·태그·브랜드와 210개 쇼핑 의도를 입력받아
상품별 의미 특징을 학습합니다. 웹에서는 클릭 1점, 찜 4점, 장바구니 5점, 구매 8점으로 각
회원의 CNN 취향 벡터를 별도로 만들기 때문에 같은 화면에서도 사용자마다
추천 상품 순서가 달라집니다.

## 문서

- [배포 방법](docs/DEPLOYMENT.md)
- [다음 작업 체크리스트](docs/ROADMAP.md)
- [추천 모델 설계](docs/RECOMMENDER_DESIGN.md)
- [개인화 UI/UX 설계](docs/PERSONALIZED_UX_DESIGN.md)
- [작업 재개 가이드](docs/WORK_RESUME_GUIDE.md)
