# Content Autopilot - 사용 안내 가이드

> 해외 기술 콘텐츠를 자동 수집 → AI 요약/번역 → 한국어 블로그 포스트로 발행하는 자동화 파이프라인

---

## 목차

1. [시스템 개요](#1-시스템-개요)
2. [사전 준비](#2-사전-준비)
3. [설치 및 실행](#3-설치-및-실행)
4. [API 키 발급 가이드](#4-api-키-발급-가이드)
5. [환경 변수 설정](#5-환경-변수-설정)
6. [파이프라인 실행](#6-파이프라인-실행)
7. [웹 대시보드 사용법](#7-웹-대시보드-사용법)
8. [설정 파일 커스터마이징](#8-설정-파일-커스터마이징)
9. [발행 채널 설정](#9-발행-채널-설정)
10. [운영 가이드](#10-운영-가이드)
11. [문제 해결](#11-문제-해결)
12. [아키텍처 참조](#12-아키텍처-참조)

---

## 1. 시스템 개요

### 파이프라인 흐름

```
수집 → 중복 제거 → 스코어링 → AI 요약/번역 → 페르소나 스타일링 → 발행
```

| 단계 | 설명 |
|------|------|
| **수집** | HN, GitHub, RSS, YouTube에서 기술 콘텐츠 자동 수집 |
| **중복 제거** | URL 정규화 + 제목 유사도 비교로 크로스플랫폼 중복 제거 |
| **스코어링** | 업보트, 속도, 댓글 비율, 소스 권위도 등 6개 시그널 가중 점수 |
| **AI 요약** | OpenAI GPT-4o-mini로 영문 콘텐츠 → 한국어 요약 + 핵심 포인트 추출 (Gemini/Claude fallback) |
| **스타일링** | 페르소나 설정 기반 한국어 블로그 포스트로 변환 |
| **발행** | Ghost, WordPress, 네이버 블로그, 티스토리, Telegram, Discord, Mastodon, Bluesky 동시 발행 |

### 기술 스택

| 컴포넌트 | 기술 |
|----------|------|
| 백엔드 | Python 3.12, FastAPI, SQLAlchemy 2.0 async |
| AI | OpenAI GPT-4o-mini ($0.15/MTok) + Gemini Flash + Claude Haiku fallback |
| CMS | Ghost 5 (SQLite) |
| DB | PostgreSQL 15 |
| 프론트엔드 | htmx + Tailwind CSS (빌드 불필요) |
| 스케줄러 | APScheduler (크론 기반) |
| 배포 | Docker Compose |

### 월 운영 비용 (예상)

| 항목 | 비용 |
|------|------|
| DeepSeek API | ~$3-5/월 (하루 3회, 3건 발행 기준) |
| Ghost CMS | $0 (셀프호스팅) |
| 서버 | $5-10/월 (VPS 기준) |
| **합계** | **~$10-15/월** |

---

## 2. 사전 준비

### 필수 요구사항

- Docker & Docker Compose (v2+)
- Git

### 선택 요구사항 (로컬 개발용)

- Python 3.12+
- pip

---

## 3. 설치 및 실행

### 방법 1: Docker Compose (권장)

```bash
# 1. 프로젝트 클론
git clone <your-repo-url> content-autopilot
cd content-autopilot

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 입력 (아래 4, 5장 참조)

# 3. 전체 시스템 기동
docker compose up -d

# 4. 상태 확인
docker compose ps
# app (8000), ghost (2368), postgres (5432) 모두 healthy 확인

# 5. DB 마이그레이션 실행
docker compose exec app alembic upgrade head
```

기동 후 접근 주소:

| 서비스 | URL |
|--------|-----|
| 대시보드 | http://localhost:8000/dashboard |
| Ghost 블로그 | http://localhost:2368 |
| Ghost Admin | http://localhost:2368/ghost/ |
| API 문서 | http://localhost:8000/docs |

### 방법 2: 로컬 개발

```bash
# 1. 프로젝트 클론
git clone <your-repo-url> content-autopilot
cd content-autopilot

# 2. Python 가상환경
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 의존성 설치
pip install -e ".[dev]"

# 4. 환경 변수
cp .env.example .env
# .env 편집

# 5. PostgreSQL 실행 (Docker)
docker compose up -d postgres

# 6. DB 마이그레이션
alembic upgrade head

# 7. 앱 실행
uvicorn content_autopilot.app:app --host 0.0.0.0 --port 8000 --reload
```

---

## 4. API 키 발급 가이드

### 필수: OpenAI API 키

1. https://platform.openai.com/ 가입
2. API Keys 메뉴에서 키 생성
3. `.env`의 `OPENAI_API_KEY`에 입력

> GPT-4o-mini: $0.15/MTok input, $0.60/MTok output — 가장 가성비 좋은 모델

### 선택: Google Gemini API 키 (fallback 1)

1. https://aistudio.google.com/ 접속
2. Get API Key → Create API Key
3. `.env`의 `GEMINI_API_KEY`에 입력

### 선택: Anthropic Claude API 키 (fallback 2)

1. https://console.anthropic.com/ 가입
2. API Keys 메뉴에서 키 생성
3. `.env`의 `CLAUDE_API_KEY`에 입력

### 필수: Ghost Admin API 키

1. `docker compose up -d ghost` 실행
2. http://localhost:2368/ghost/ 접속하여 관리자 계정 생성
3. Settings → Integrations → Custom Integration 추가
4. **Admin API Key** 복사 (형식: `24자hex:64자hex`)
5. **Content API Key**도 복사
6. `.env`에 각각 입력

### 선택: Reddit API

1. https://www.reddit.com/prefs/apps 접속
2. "create another app" 클릭
3. 타입: **script** 선택
4. redirect uri: `http://localhost:8000`
5. 생성 후 client_id (앱 이름 아래 문자열)와 secret 복사

### 선택: YouTube Data API

1. https://console.cloud.google.com/apis/library 접속
2. "YouTube Data API v3" 검색 후 활성화
3. Credentials → Create API Key
4. 하루 10,000 유닛 무료 (검색 1회 = 100 유닛)

### 선택: GitHub Token

1. https://github.com/settings/tokens → Generate new token (classic)
2. scope: `public_repo` (읽기 전용)
3. 미설정 시 시간당 60회 제한 → 설정 시 5,000회

### 선택: Telegram Bot

1. @BotFather에게 `/newbot` 메시지 전송
2. 봇 이름과 username 입력
3. 받은 Bot Token 복사
4. 채널 생성 후 봇을 관리자로 추가
5. Channel ID: `@채널username` 또는 숫자 ID

### 선택: Discord Webhook

1. Discord 서버 → 채널 설정 → Integrations → Webhooks
2. "New Webhook" 생성
3. Webhook URL 복사

### 선택: Mastodon

1. 사용 중인 인스턴스 (예: mastodon.social) 로그인
2. Settings → Development → New Application
3. 권한: `write:statuses` 체크
4. Access Token 복사

### 선택: Bluesky

1. https://bsky.app Settings → App Passwords
2. "Add App Password" 클릭
3. 비밀번호 복사
4. Identifier = 본인 핸들 (예: `user.bsky.social`)

---

## 5. 환경 변수 설정

`.env` 파일 전체 구조:

```bash
# === 필수: AI API ===
OPENAI_API_KEY=sk-xxxx                # 메인 AI (GPT-4o-mini)
GEMINI_API_KEY=xxxx                   # fallback 1 (Gemini Flash)
CLAUDE_API_KEY=sk-ant-xxxx            # fallback 2 (Claude Haiku)

# === 필수: 인프라 ===
GHOST_URL=http://localhost:2368
GHOST_ADMIN_KEY=id:secret
GHOST_CONTENT_KEY=xxxx
DB_URL=postgresql+asyncpg://autopilot:autopilot@localhost:5432/content_autopilot
DASHBOARD_PASSWORD=your_strong_password_here

# === 블로그 발행 (선택) ===
WP_SITE_URL=https://your-wordpress-site.com
WP_USERNAME=admin
WP_APP_PASSWORD=xxxx xxxx xxxx xxxx xxxx xxxx
NAVER_ID=your_naver_id
NAVER_PASSWORD=your_naver_password
NAVER_BLOG_ID=your_blog_id
TISTORY_EMAIL=your_kakao_email
TISTORY_PASSWORD=your_kakao_password
TISTORY_BLOG_NAME=your_tistory_blog_name

# === 메시징 채널 (선택) ===
TG_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TG_CHANNEL_ID=@my_tech_channel
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/1234/abcdef

# === 수집 소스 (선택) ===
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
YOUTUBE_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxx

# === SNS 크로스포스팅 (선택) ===
MASTODON_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxx
MASTODON_INSTANCE=https://mastodon.social
BLUESKY_IDENTIFIER=myhandle.bsky.social
BLUESKY_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

> **Docker 환경 주의**: Docker 내부에서는 `DB_URL`의 호스트가 `postgres`입니다.
> `docker-compose.yml`에서 자동 오버라이드되므로 `.env`에는 로컬용 주소를 그대로 두면 됩니다.

### 최소 구성 (필수만)

API 키가 없는 수집 소스/발행 채널은 자동 스킵됩니다. 최소한 이것만 설정하면 동작합니다:

```bash
OPENAI_API_KEY=sk-xxxx             # AI 처리용 (필수)
GHOST_URL=http://localhost:2368    # 블로그 발행용
GHOST_ADMIN_KEY=id:secret          # Ghost API 인증
DASHBOARD_PASSWORD=your_password   # 대시보드 로그인
```

이 경우 HN + RSS만 수집하고 Ghost에만 발행합니다.
Gemini/Claude 키 추가 시 AI fallback 체인 활성화.
WordPress/네이버/티스토리 키 추가 시 해당 채널 자동 활성화.

---

## 6. 파이프라인 실행

### CLI 명령어

```bash
# 드라이런 (수집+스코어링만, 발행 안 함)
python -m content_autopilot.cli run-pipeline --dry-run

# 실제 실행 (수집 → 처리 → 발행)
python -m content_autopilot.cli run-pipeline

# 스케줄러 시작 (크론 기반 자동 실행)
python -m content_autopilot.cli start-scheduler

# 상태 확인
python -m content_autopilot.cli status
```

Docker 환경에서:

```bash
# 드라이런
docker compose exec app python -m content_autopilot.cli run-pipeline --dry-run

# 실제 실행
docker compose exec app python -m content_autopilot.cli run-pipeline

# 스케줄러
docker compose exec app python -m content_autopilot.cli start-scheduler
```

### 파이프라인 실행 결과 예시

```
Status: success
Collected: 35 -> Deduped: 28 -> Scored: 3 -> Published: 3
```

| 항목 | 설명 |
|------|------|
| Collected | 5개 소스에서 수집한 총 아이템 수 |
| Deduped | 중복 제거 후 남은 아이템 수 |
| Scored | 상위 N개 선별 (기본 top 3) |
| Published | 최종 발행 성공 건수 |

### 자동 스케줄

기본 설정 (`config/schedule.yaml`):

```yaml
schedules:
  - cron: "0 7 * * *"   # 매일 오전 7시 (KST)
  - cron: "0 12 * * *"  # 매일 오후 12시
  - cron: "0 18 * * *"  # 매일 오후 6시
timezone: "Asia/Seoul"
```

하루 3회 x 3건 = 최대 9건의 블로그 포스트가 자동 발행됩니다.

---

## 7. 웹 대시보드 사용법

### 접속

```
http://localhost:8000/dashboard
```

로그인: username `admin` / password `.env`의 `DASHBOARD_PASSWORD` 값

### 페이지 구성

| 페이지 | 경로 | 기능 |
|--------|------|------|
| 홈 | `/dashboard` | 오늘의 발행 현황, 최근 기사, 빠른 실행 버튼 |
| 기사 | `/dashboard/articles` | 발행된 기사 목록, 페이지네이션 |
| 파이프라인 | `/dashboard/pipeline` | 수동 실행, 드라이런, 실행 이력 |
| 소스 관리 | `/dashboard/sources` | 5개 소스 활성/비활성 토글, RSS 피드 추가 |
| 분석 | `/dashboard/analytics` | AI 비용, 채널별 발행 현황, 30초 자동 새로고침 |

### 주요 기능

**파이프라인 수동 실행**

1. `/dashboard/pipeline` 접속
2. "파이프라인 실행" 버튼 클릭 → 전체 파이프라인 실행
3. "드라이런" 버튼 → 수집+스코어링만 (발행 없이 테스트)

**소스 관리**

1. `/dashboard/sources` 접속
2. 각 소스(HN, Reddit, GitHub, RSS, YouTube) 활성/비활성 토글
3. "새 피드 추가" → RSS 피드 URL 입력으로 수집 소스 추가

**분석 모니터링**

- AI 토큰 사용량 + 예상 비용 실시간 표시
- 월 예산 $50 기준 80% 초과 시 경고 배너
- 채널별(Ghost, Telegram, Discord) 발행 성공/실패 현황
- 30초마다 자동 갱신

### REST API

API 문서는 http://localhost:8000/docs 에서 확인 가능합니다.

주요 엔드포인트:

```
GET  /api/dashboard/overview    오늘의 현황 통계
GET  /api/articles              기사 목록 (pagination)
GET  /api/articles/{id}         기사 상세
POST /api/pipeline/run          파이프라인 수동 실행
GET  /api/pipeline/runs         실행 이력
GET  /api/sources               소스 목록
PATCH /api/sources/{id}/toggle  소스 활성/비활성 토글
POST /api/sources               RSS 피드 추가
GET  /api/stats                 통계 (토큰, 비용, 구독자)
GET  /api/schedule              예약 발행 목록
GET  /health                    헬스체크
```

모든 API는 HTTP Basic Auth가 필요합니다.

---

## 8. 설정 파일 커스터마이징

### 수집 소스 설정

각 소스의 수집 파라미터는 `config/sources/` 아래 YAML로 관리됩니다:

**`config/sources/hn.yaml`** — Hacker News
```yaml
fetch_count: 30       # 상위 N개 스토리 조회
min_score: 10         # 최소 스코어 필터
excluded_domains:     # 제외할 도메인
  - "reddit.com"
  - "twitter.com"
```

**`config/sources/reddit.yaml`** — Reddit
```yaml
subreddits:           # 구독 서브레딧
  - technology
  - programming
  - MachineLearning
  - artificial
  - startups
  - worldnews
min_upvotes: 10       # 최소 업보트
```

**`config/sources/github.yaml`** — GitHub Trending
```yaml
min_stars: 50         # 최소 스타 수
languages:            # 관심 언어 필터
  - python
  - typescript
  - go
  - rust
  - ""                # 전체 언어
```

**`config/sources/rss.yaml`** — RSS/Blog 피드
```yaml
feeds:
  - url: "https://news.hada.io/rss"
    name: "geeknews"
    lang: "ko"                        # 한국어 소스 (번역 스킵)
  - url: "https://techcrunch.com/feed/"
    name: "techcrunch"
    lang: "en"
  - url: "https://feeds.arstechnica.com/arstechnica/index"
    name: "arstechnica"
    lang: "en"
  - url: "https://hnrss.org/frontpage"
    name: "hn_rss"
    lang: "en"
max_age_hours: 24     # 24시간 이내 기사만
```

> **RSS 피드 추가 방법**: feeds 리스트에 새 항목을 추가하거나, 대시보드 `/dashboard/sources`에서 URL 입력

**`config/sources/youtube.yaml`** — YouTube
```yaml
search_queries:        # 검색 쿼리
  - "AI technology 2024"
  - "programming tutorial"
  - "tech news"
region: KR             # 지역 (인기 영상 기준)
daily_quota_limit: 9500  # YouTube API 일일 한도 (10,000 중)
```

### 스코어링 설정

**`config/scoring.yaml`**

```yaml
weights:
  volume: 0.3           # 업보트 절대량 (log10)
  velocity: 0.2         # 시간당 업보트 속도
  comment_ratio: 0.1    # 댓글/업보트 비율
  cross_platform: 0.2   # 여러 소스에서 동시 등장 보너스
  source_authority: 0.1  # 소스별 가중치
  time_decay: 0.1       # 시간 경과 감쇠

source_authority:       # 소스별 권위도 (0-1)
  hn: 1.0
  reddit: 0.8
  github: 0.7
  youtube: 0.6
  rss: 0.5

time_decay:
  half_life_hours: 24   # 24시간마다 점수 반감

top_n: 3               # 파이프라인당 선별 건수
```

`top_n`을 올리면 한 번에 더 많은 기사를 발행합니다. AI 비용이 비례 증가합니다.

### 페르소나 설정

**`config/personas/default.yaml`**

이 파일이 AI가 글을 쓰는 "성격"을 결정합니다:

```yaml
name: "content-autopilot-default"
tone: "친근하고 정보 전달력 있는 테크 블로거"
language: "ko"

style_rules:
  - "반말과 존댓말 혼용 (제목은 강렬하고 짧게, 본문은 존댓말)"
  - "이모지 적절히 사용 (문단당 최대 1개)"
  - "첫 문장으로 핵심 정보 전달 (why this matters)"
  - "개인 의견은 '제 생각엔~', '솔직히 말하면~' 형태로 자연스럽게"
  - "3줄 이상 연속 나열 리스트 지양 (문단으로 풀어쓰기)"
  - "전문용어는 한국어 병기 (예: LLM(대규모 언어 모델))"

example_openings:      # AI가 참고하는 도입부 패턴
  - "솔직히 말하면, 이 소식 처음 봤을 때 좀 놀랐어요."
  - "오늘 공유할 내용, 개발자라면 한 번쯤은 겪어봤을 이야기예요."

forbidden_patterns:    # 절대 사용 금지 표현
  - "~입니다만"
  - "다음과 같습니다:"
  - "상기"
  - "명시된 바와 같이"
  - "본 문서에서"

target_length:
  min_chars: 400
  max_chars: 1200
  recommended_chars: 700
```

**페르소나 커스터마이징 팁**:
- `tone`을 바꾸면 전체 글의 분위기가 달라집니다
- `style_rules`에 자신만의 규칙을 추가하세요
- `forbidden_patterns`에 AI가 자주 쓰는 뻔한 표현을 추가하세요
- `example_openings`에 본인이 좋아하는 도입부 스타일을 추가하세요

### 프롬프트 템플릿

AI에게 전달되는 프롬프트는 `config/personas/prompts/`에 있습니다:

- `summarize.txt` — 요약/번역 프롬프트 (영문 → 한국어 핵심 추출)
- `humanize.txt` — 스타일링 프롬프트 (요약 → 블로그 포스트 변환)

직접 수정하여 AI의 출력 품질을 조절할 수 있습니다.

---

## 9. 발행 채널 설정

### Ghost 블로그 (기본)

Ghost는 Docker로 자동 기동됩니다. 최초 설정:

1. http://localhost:2368/ghost/ 접속
2. 관리자 계정 생성
3. Settings → Integrations → Custom Integration 추가
4. Admin API Key, Content API Key 복사 → `.env`에 입력

발행된 글은 http://localhost:2368 에서 확인됩니다.

**뉴스레터 자동 발송** (`config/newsletter.yaml`):
```yaml
enabled: false   # true로 변경하면 발행 시 자동으로 구독자에게 이메일
auto_send: false
```

### Telegram

1. `.env`에 `TG_BOT_TOKEN`과 `TG_CHANNEL_ID` 설정
2. 봇을 채널 관리자로 추가
3. 파이프라인 실행 시 자동으로 채널에 포스트 전송

전송 형식: 제목(볼드) + 요약 + 블로그 링크 + 출처 + 해시태그

### Discord

1. `.env`에 `DISCORD_WEBHOOK_URL` 설정
2. 파이프라인 실행 시 자동으로 Embed 메시지 전송

전송 형식: Discord Embed (제목, 설명, 태그, 출처 링크)

### Mastodon (`config/social.yaml`)

```yaml
channels:
  mastodon:
    enabled: true              # false → true
    instance: "https://mastodon.social"
```

`.env`에 `MASTODON_ACCESS_TOKEN` 설정 필요.

### Bluesky (`config/social.yaml`)

```yaml
channels:
  bluesky:
    enabled: true              # false → true
```

`.env`에 `BLUESKY_IDENTIFIER`와 `BLUESKY_APP_PASSWORD` 설정 필요.

> Mastodon/Bluesky는 `config/social.yaml`에서 `enabled: true`로 변경해야 활성화됩니다.

---

## 10. 운영 가이드

### 일일 운영

시스템은 자동으로 운영됩니다. 스케줄러가 하루 3회(오전 7시, 낮 12시, 오후 6시) 파이프라인을 실행합니다.

```bash
# 스케줄러를 백그라운드로 시작 (Docker)
docker compose exec -d app python -m content_autopilot.cli start-scheduler
```

### 모니터링 체크리스트

| 주기 | 확인 사항 | 방법 |
|------|-----------|------|
| 매일 | 발행 건수 | 대시보드 `/dashboard` |
| 매주 | AI 비용 | 대시보드 `/dashboard/analytics` |
| 매주 | 스코어링 분포 | 드라이런 후 결과 확인 |
| 매월 | API 한도 | YouTube quota, GitHub rate limit |

### 비용 관리

DeepSeek V3 비용 추정:

| 항목 | 토큰/건 | 비용/건 |
|------|---------|---------|
| 요약 (input) | ~2,000 | $0.0005 |
| 요약 (output) | ~500 | $0.0006 |
| 스타일링 (input) | ~1,500 | $0.0004 |
| 스타일링 (output) | ~1,000 | $0.0011 |
| **건당 합계** | | **~$0.003** |

하루 9건 × 30일 = 월 270건 × $0.003 = **~$0.81/월**

> 월 예산 $50의 2%도 안 됩니다. 비용 걱정 없이 운영 가능합니다.

### 백업

```bash
# Ghost 데이터 백업
docker compose exec ghost ghost backup

# PostgreSQL 백업
docker compose exec postgres pg_dump -U autopilot content_autopilot > backup.sql

# 전체 볼륨 백업
docker compose down
docker run --rm -v content-autopilot_ghost_data:/data -v $(pwd):/backup alpine tar czf /backup/ghost_backup.tar.gz /data
docker run --rm -v content-autopilot_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres_backup.tar.gz /data
docker compose up -d
```

### 로그 확인

```bash
# 앱 로그 (JSON 형식)
docker compose logs -f app

# Ghost 로그
docker compose logs -f ghost

# 특정 시간 이후 로그
docker compose logs --since 1h app
```

로그는 structlog JSON 포맷입니다:
```json
{"event": "pipeline_collected", "count": 35, "timestamp": "2026-03-18T10:00:00Z"}
{"event": "pipeline_published", "count": 3, "errors": 0, "timestamp": "2026-03-18T10:01:30Z"}
```

---

## 11. 문제 해결

### "No items collected"

**원인**: 모든 수집기가 빈 결과를 반환함

**해결**:
1. HN과 RSS는 API 키 불필요 → 네트워크 확인
2. Reddit/GitHub/YouTube는 API 키 필요 → `.env` 확인
3. `docker compose exec app python -c "from content_autopilot.collectors.hn import HNCollector; import asyncio; items = asyncio.run(HNCollector().collect()); print(len(items), 'items')"` 로 개별 테스트

### Ghost 발행 실패 (401 Unauthorized)

**원인**: Ghost Admin Key가 잘못되었거나 만료됨

**해결**:
1. Ghost Admin → Settings → Integrations 에서 키 재확인
2. 키 형식: `24자hex:64자hex` (콜론으로 구분)
3. `.env`의 `GHOST_ADMIN_KEY` 업데이트

### "AI error" / DeepSeek API 실패

**원인**: API 키 오류 또는 잔액 부족

**해결**:
1. https://platform.deepseek.com/ 에서 잔액 확인
2. `.env`의 `DEEPSEEK_API_KEY` 확인
3. 네트워크 방화벽이 `api.deepseek.com` 을 차단하는지 확인

### Docker 컨테이너가 안 뜸

```bash
# 상태 확인
docker compose ps

# 로그 확인
docker compose logs app

# 컨테이너 재시작
docker compose restart app

# 전체 재빌드
docker compose down && docker compose up -d --build
```

### PostgreSQL 연결 실패

```bash
# PostgreSQL 상태 확인
docker compose exec postgres pg_isready -U autopilot -d content_autopilot

# 직접 접속 테스트
docker compose exec postgres psql -U autopilot -d content_autopilot -c "SELECT 1;"
```

### 테스트 실행

```bash
# 전체 테스트
python -m pytest tests/ -v

# 특정 모듈 테스트
python -m pytest tests/collectors/ -v
python -m pytest tests/processing/ -v
python -m pytest tests/publishers/ -v
```

---

## 12. 아키텍처 참조

### 디렉토리 구조

```
content-autopilot/
├── src/content_autopilot/
│   ├── app.py                    # FastAPI 앱 엔트리포인트
│   ├── config.py                 # Pydantic Settings (환경 변수)
│   ├── cli.py                    # Typer CLI (run-pipeline, start-scheduler)
│   ├── db.py                     # SQLAlchemy async 엔진/세션
│   ├── models/                   # SQLAlchemy ORM 모델 (6개 테이블)
│   ├── schemas/                  # Pydantic 데이터 모델 (9개)
│   ├── collectors/               # 데이터 수집기
│   │   ├── hn.py                 #   Hacker News (Firebase API)
│   │   ├── reddit.py             #   Reddit (OAuth2 API)
│   │   ├── github.py             #   GitHub (Search API)
│   │   ├── rss.py                #   RSS/Atom 피드 (feedparser)
│   │   └── youtube.py            #   YouTube (Data API v3)
│   ├── processing/               # 데이터 처리
│   │   ├── dedup.py              #   중복 제거 (URL + 제목 유사도)
│   │   ├── scorer.py             #   스코어링 엔진 (6시그널 가중)
│   │   ├── summarizer.py         #   AI 요약/번역 (DeepSeek)
│   │   └── humanizer.py          #   페르소나 스타일링 (DeepSeek)
│   ├── publishers/               # 콘텐츠 발행
│   │   ├── ghost.py              #   Ghost CMS (JWT Auth)
│   │   ├── telegram.py           #   Telegram Bot API
│   │   ├── discord.py            #   Discord Webhook
│   │   └── social.py             #   Mastodon + Bluesky
│   ├── orchestrator/             # 오케스트레이션
│   │   ├── pipeline.py           #   파이프라인 (수집→발행 전체 흐름)
│   │   └── scheduler.py          #   APScheduler 크론 + 콘텐츠 큐
│   ├── ai/                       # AI 모듈
│   │   ├── client.py             #   DeepSeek async 클라이언트
│   │   ├── prompts.py            #   Jinja2 프롬프트 로더
│   │   └── pipeline.py           #   Protocol 인터페이스
│   ├── common/                   # 공통 유틸리티
│   │   ├── logger.py             #   structlog JSON 로거
│   │   ├── retry.py              #   tenacity 재시도 데코레이터
│   │   ├── rate_limiter.py       #   토큰 버킷 레이트 리미터
│   │   ├── config_loader.py      #   YAML 설정 로더
│   │   ├── http_client.py        #   공용 httpx 클라이언트
│   │   └── text_utils.py         #   HTML 스트립, 텍스트 유틸
│   └── dashboard/                # 웹 대시보드
│       ├── api.py                #   FastAPI 라우터 (19 엔드포인트)
│       ├── templates/            #   Jinja2 HTML 템플릿 (7개)
│       └── static/               #   정적 파일
├── config/                       # YAML 설정 파일
│   ├── sources/                  #   소스별 수집 설정 (5개)
│   ├── personas/                 #   페르소나 + 프롬프트 템플릿
│   ├── scoring.yaml              #   스코어링 가중치
│   ├── schedule.yaml             #   크론 스케줄
│   ├── newsletter.yaml           #   뉴스레터 설정
│   ├── monetization.yaml         #   수익화 설정
│   └── social.yaml               #   SNS 크로스포스팅 설정
├── alembic/                      # DB 마이그레이션
├── tests/                        # 테스트 (215개)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env.example
```

### 데이터 흐름

```
[HN API]─────┐
[Reddit API]──┤
[GitHub API]──┼──→ [RawItem] ──→ [DedupService] ──→ [ScoringEngine] ──→ top 3
[RSS Feeds]───┤                                          ↓
[YouTube API]─┘                                    [ScoredItem]
                                                         ↓
                                                   [Summarizer]
                                                   (DeepSeek API)
                                                         ↓
                                                   [SummaryResult]
                                                         ↓
                                                    [Humanizer]
                                                   (DeepSeek API)
                                                         ↓
                                                   [ArticleDraft]
                                                         ↓
                                          ┌──────────────┼──────────────┐
                                          ↓              ↓              ↓
                                    [Ghost CMS]    [Telegram]     [Discord]
                                          ↓              ↓              ↓
                                     블로그 포스트    채널 메시지    Embed 메시지
                                          │
                                          ├──→ [Mastodon] (선택)
                                          └──→ [Bluesky]  (선택)
```

### DB 스키마

| 테이블 | 설명 |
|--------|------|
| `sources` | 수집 소스 설정 |
| `raw_items` | 수집된 원본 아이템 |
| `scored_items` | 스코어링 결과 |
| `articles` | 생성된 기사 |
| `publications` | 발행 이력 |
| `pipeline_runs` | 파이프라인 실행 로그 |
