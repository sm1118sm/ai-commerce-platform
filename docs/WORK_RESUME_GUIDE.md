# 작업 종료 및 재시작 안내

## 현재 프로젝트

- 프로젝트 폴더: `/home/lsm1118/personalized-commerce-ai`
- GitHub: `https://github.com/sm1118sm/ai-commerce-platform`
- 기본 브랜치: `main`
- 배포 앱: `https://ai-commerce-platform-5ovk.onrender.com`
- 운영 DB: 외부 관리형 MySQL 8 (`DATABASE_URL`은 Render 환경변수로만 관리)

## 노트북을 종료하기 전

WSL 터미널에서 다음 명령을 실행한다.

```bash
cd /home/lsm1118/personalized-commerce-ai
git status
git add .
git commit -m "작업 내용 설명"
git push origin main
```

`git status`에 `nothing to commit, working tree clean`이 표시되면 저장이
완료된 상태다. 실행 중인 Streamlit은 `Ctrl+C`로 종료하고 WSL에서 `exit`를
입력한다.

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
cd /home/lsm1118/personalized-commerce-ai
git pull origin main
git status
```

VS Code로 열려면 다음 명령을 실행한다.

```bash
code .
```

## 로컬 앱과 MySQL 실행

```bash
cd /home/lsm1118/personalized-commerce-ai
cp .env.example .env
docker compose up --build
```

브라우저에서 `http://localhost:8501`에 접속한다. 로컬 MySQL 데이터는 Docker
볼륨에 보관하며 운영 DB 비밀번호를 PC나 GitHub에 저장하지 않는다.

실행을 멈추려면 터미널에서 `Ctrl+C`를 누르고 다음 명령을 실행한다.

```bash
docker compose down
```

## 테스트 실행

```bash
cd /home/lsm1118/personalized-commerce-ai
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
- 작업 시작 전 `git pull origin main`, 종료 전 `git push origin main`을 실행한다.
- Render 배포는 `main` 브랜치에 푸시하면 자동으로 시작된다.
- Render 무료 서비스는 첫 접속에 약 50초가 걸릴 수 있다.
