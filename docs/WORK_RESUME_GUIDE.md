# 작업 종료 및 재시작 안내

## 현재 프로젝트

- 프로젝트 폴더: `/mnt/c/Users/sm222/Documents/Codex/2026-07-27/ai-commerce-platform`
- GitHub: `https://github.com/sm1118sm/ai-commerce-platform`
- 기본 브랜치: `main`
- 배포 앱: `https://ai-commerce-platform-5ovk.onrender.com`
- 운영 DB: Aiven MySQL 8.4 무료 플랜
- Aiven 프로젝트: `stylepick-ai-commerce`
- Aiven 서비스: `mysql-138ce16`
- DB 이름: `defaultdb`
- DB 비밀정보: 로컬 `.env`와 Render Secret에만 저장

## 2026-07-27까지 완료한 내용

- 2030 이용자를 위한 상품 30개와 이커머스형 홈 화면
- 데스크톱·모바일 반응형 UI, 상품 카드와 개인화 추천 진열 영역
- TF-IDF/E5 하이브리드 추천, 최근 행동·관심사·예산·인기도 반영
- 이메일·닉네임·전화번호 중복 차단과 안전한 비밀번호 해시
- 회원별 찜·장바구니·주문·행동 로그 분리, 회원탈퇴 연쇄 삭제
- MySQL/PostgreSQL DB 어댑터와 운영 오류 상세정보 숨김
- Aiven MySQL TLS 연결, 스키마 생성, 상품 30개 시드 검증
- Aiven에서 임시 회원 가입·로그인·중복 차단·탈퇴 실연결 검증
- 모든 GitHub 변경을 기능 브랜치 → PR → CI → `main` 병합으로 관리

- PR #6: 공용 Aiven MySQL 연결과 TLS 처리 병합 완료
- PR #7: 핵심 중심 README 개편 완료
- Render `DATABASE_URL`: Aiven Service URI로 설정 완료
- 최종 배포: `e159ee0`, Render 상태 `live`, MySQL 사전 점검과 HTTP 200 확인

## 노트북을 종료하기 전

WSL 터미널에서 다음 명령을 실행한다. 작업은 `main`이 아닌 기능 브랜치에서
진행한다.

```bash
cd /mnt/c/Users/sm222/Documents/Codex/2026-07-27/ai-commerce-platform
git status
git add .
git commit -m "작업 내용 설명"
git push -u origin 현재-기능-브랜치
```

GitHub에서 Pull Request를 만들고 자동 테스트가 통과한 뒤 `main`에
병합한다. `git status`에 `nothing to commit, working tree clean`이 표시되면
로컬 저장이 완료된 상태다.

PowerShell로 돌아온 다음 필요하면 WSL을 완전히 종료한다.

```powershell
wsl --shutdown
```

## PowerShell에서 다시 작업 시작

PowerShell을 열고 WSL에 접속한다.

```powershell
wsl
```

WSL 안에서 프로젝트로 이동하고 최신 코드를 받는다.

```bash
cd /mnt/c/Users/sm222/Documents/Codex/2026-07-27/ai-commerce-platform
git pull origin main
git switch -c feat/작업이름
git status
```

VS Code로 열려면 다음 명령을 실행한다.

```bash
code .
```

## 로컬 앱과 MySQL 실행

```bash
cd /mnt/c/Users/sm222/Documents/Codex/2026-07-27/ai-commerce-platform
docker compose up --build
```

브라우저에서 `http://localhost:8501`에 접속한다. 현재 PC의 Git 제외 `.env`에는
Aiven URI가 있으므로 로컬 앱과 Render가 같은 회원·행동·주문 데이터를 본다.
새 PC에서는 `.env.example`을 `.env`로 복사하면 로컬 Docker MySQL을 사용하며,
공용 Aiven을 사용하려면 URI를 별도로 안전하게 입력해야 한다.

실행을 멈추려면 터미널에서 `Ctrl+C`를 누르고 다음 명령을 실행한다.

```bash
docker compose down
```

## 테스트 실행

```bash
cd /mnt/c/Users/sm222/Documents/Codex/2026-07-27/ai-commerce-platform
source .venv/bin/activate
python -m unittest discover -s tests -v
```

## 새 PC 또는 프로젝트 폴더가 없을 때

PowerShell에서 WSL을 실행한 뒤 GitHub 저장소를 다시 복제한다.

```powershell
wsl
```

```bash
cd /home/lsm1118
git clone https://github.com/sm1118sm/ai-commerce-platform.git personalized-commerce-ai
cd personalized-commerce-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up --build
```

## 주의사항

- `DATABASE_URL`, DB 비밀번호, `.env` 파일은 채팅이나 GitHub에 올리지 않는다.
- Aiven Service URI의 비밀번호를 스크린샷에 노출하지 않는다.
- 작업 시작 전 `main`을 최신화하고 새 기능 브랜치를 만든다.
- 작업 종료 시 기능 브랜치를 push하고 PR과 CI를 거쳐 `main`에 병합한다.
- Render 배포는 PR이 `main`에 병합되면 자동으로 시작된다.
- Render 무료 서비스는 첫 접속에 약 50초가 걸릴 수 있다.
