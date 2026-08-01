# Aiven MySQL 자동 복구

운영 Aiven MySQL이 `POWEROFF` 상태가 되면 GitHub Actions가 이를 감지해 전원을
켜고 `RUNNING` 상태까지 기다린다. GitHub 예약 실행의 최소 간격은 5분이므로,
각 작업이 약 5분 동안 30초 간격으로 열 번 확인하도록 구성했다. 애플리케이션도
DB가 깨어나는 동안 지수 백오프로 연결을 재시도하며 연결 실패 원문 대신 복구
안내를 표시한다.

## GitHub 설정

저장소의 **Settings → Secrets and variables → Actions**에서 다음 값을 등록한다.

| 종류 | 이름 | 값 |
| --- | --- | --- |
| Secret | `AIVEN_TOKEN` | Aiven application user의 인증 토큰 |
| Variable | `AIVEN_PROJECT` | `stylepick-ai-commerce` |
| Variable | `AIVEN_SERVICE` | `mysql-138ce16` |

설정 후 **Actions → Aiven MySQL watchdog → Run workflow**를 한 번 수동 실행해
권한과 서비스 이름을 검증한다. 토큰은 개인 Owner 토큰보다 해당 서비스에 필요한
최소 권한만 가진 Aiven application user 토큰을 사용한다.

## 애플리케이션 재시도 설정

다음 환경 변수는 선택 사항이다. 지정하지 않아도 아래 기본값이 적용된다.

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `STYLEPICK_DB_CONNECT_ATTEMPTS` | `6` | 한 요청에서 연결을 시도할 최대 횟수 |
| `STYLEPICK_DB_RETRY_BASE_SECONDS` | `1` | 첫 재시도 대기 시간 |
| `STYLEPICK_DB_RETRY_MAX_SECONDS` | `8` | 재시도 간 최대 대기 시간 |

## 보장 범위

이 구성은 무료 서비스의 정지를 감지한 뒤 복구하는 장치다. GitHub Actions 예약
실행은 부하에 따라 지연될 수 있고, Aiven 자체 장애·네트워크 장애·잘못된 인증
정보까지 제거할 수는 없다. 중단 시간이 허용되지 않는 운영 서비스라면 자동
정지되지 않는 유료 Aiven 플랜과 별도의 가용성 구성이 필요하다.
