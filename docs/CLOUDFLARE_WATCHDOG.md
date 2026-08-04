# Streamlit 무료 30초 자동 복구

`cloudflare-watchdog`는 Cloudflare Workers 무료 플랜에서 매분 실행된다. 각 Cron
실행은 즉시 Streamlit 상태 확인·resume을 수행하고 30초 기다린 뒤 같은 요청을
한 번 더 수행한다. 따라서 사용자 PC와 브라우저가 꺼져 있어도 30초 간격으로
Streamlit Community Cloud의 inactivity shutdown을 예방한다.

## 최초 1회 배포

Cloudflare 무료 계정으로 로그인한 뒤 저장소 루트에서 실행한다.

```bash
cd cloudflare-watchdog
npm install
npx wrangler login
npm test
npm run deploy
```

배포 후 Cloudflare Dashboard의 **Workers & Pages →
stylepick-streamlit-watchdog → Triggers**에서 Cron `* * * * *`가 등록되었는지
확인한다. **Observability → Logs**에는 매분 `sequence: 1`, 30초 뒤
`sequence: 2` 로그가 남아야 한다.

## 보장 범위

- 하루 Worker 실행: 약 1,440회
- 하루 Streamlit status/resume 확인: 약 2,880회
- Cloudflare Workers 무료 플랜 한도: 하루 100,000회
- Cron 실행 최대 wall time은 15분이며, 이 Worker는 약 30초 동안 실행된다.

무료 서비스에는 SLA가 없으므로 1000일 동안 단 한 번의 지연도 없다고 보증할 수는
없다. Cloudflare 장애, Streamlit 정책/API 변경, 계정 정지에는 영향을 받는다.
GitHub Actions watchdog은 Cloudflare 배포 전과 일시 장애 시의 보조 장치로 둔다.
