# 빠른 설치 가이드

## 1. 클론 + 셋업 (원커맨드)

```bash
git clone https://github.com/JuneKunst/content-autopilot.git
cd content-autopilot
bash setup.sh
```

대화형으로 API 키를 물어봅니다. 없는 항목은 Enter로 스킵.

## 2. Ghost 키 발급

셋업 완료 후 Ghost Admin에 접속해서 키를 발급받아야 합니다:

1. http://localhost:2368/ghost/ 접속
2. 관리자 계정 생성
3. Settings → Integrations → Add custom integration
4. Admin API Key, Content API Key 복사
5. `.env` 파일에 입력:
   ```
   GHOST_ADMIN_KEY=복사한_Admin_키
   GHOST_CONTENT_KEY=복사한_Content_키
   ```
6. `make restart`

## 3. 테스트

```bash
make dry-run        # 수집+스코어링만 (발행 없이 테스트)
make run            # 실제 발행
make scheduler      # 자동 스케줄러 (매일 7/12/18시)
```

## 4. 전체 명령어

```bash
make help
```

```
  make setup           최초 설치
  make start           서비스 시작
  make stop            서비스 중지
  make restart         서비스 재시작
  make rebuild         코드 변경 후 재빌드
  make logs            앱 로그 보기
  make dry-run         드라이런
  make run             실제 파이프라인 실행
  make scheduler       자동 스케줄러 시작
  make ghost-setup     Ghost Admin 열기
  make install-browser Playwright 설치 (네이버/티스토리용)
  make backup          데이터 백업
  make update          최신 코드 pull + 재빌드
  make test            테스트 실행
  make shell           컨테이너 쉘 접속
```

## 5. 접속 주소

| 서비스 | URL |
|--------|-----|
| 대시보드 | http://localhost:8000/dashboard |
| Ghost 블로그 | http://localhost:2368 |
| Ghost Admin | http://localhost:2368/ghost/ |
| API 문서 | http://localhost:8000/docs |

대시보드 로그인: `admin` / `.env`의 `DASHBOARD_PASSWORD`

## 6. 나중에 키 추가하기

`.env` 파일을 열어서 원하는 항목만 수정 → `make restart`

```bash
# 예: WordPress 추가
WP_SITE_URL=https://my-site.com
WP_USERNAME=admin
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

키가 비어있는 채널은 자동 스킵됩니다.

## 7. 네이버/티스토리 사용 시

```bash
make install-browser   # Chromium 설치 (최초 1회)
```

`.env`에 계정 정보 입력 후 `make restart`.
첫 로그인 시 CAPTCHA가 뜨면 수동 로그인이 필요할 수 있습니다.

## 8. 다른 컴퓨터에서 접속

```bash
# 맥미니 IP 확인
ifconfig en0 | grep "inet "
```

같은 네트워크에서 `http://맥미니IP:8000/dashboard` 로 접속.
