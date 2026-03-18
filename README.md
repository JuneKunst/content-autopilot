# Content Autopilot

해외 기술 콘텐츠를 자동 수집하고, AI로 요약/번역한 뒤, 한국어 블로그 포스트로 발행하는 파이프라인.

```
HN / Reddit / GitHub / RSS / YouTube
        ↓ 수집 + 중복제거 + 스코어링
    DeepSeek AI 요약 · 번역
        ↓ 페르소나 스타일링
Ghost 블로그 / Telegram / Discord / Mastodon / Bluesky
```

## 주요 기능

- **5개 소스 자동 수집** — Hacker News, Reddit, GitHub Trending, RSS/Atom, YouTube
- **AI 요약/번역** — DeepSeek V3로 영문 → 한국어 핵심 요약 (건당 ~$0.003)
- **페르소나 스타일링** — YAML로 정의한 블로거 톤/스타일로 자연스러운 한국어 포스트 생성
- **멀티채널 발행** — Ghost CMS + Telegram + Discord + Mastodon + Bluesky 동시 발행
- **스마트 스코어링** — 업보트, 속도, 댓글비율, 크로스플랫폼 등 6개 시그널 가중 점수
- **중복 제거** — URL 정규화 + 제목 유사도로 크로스플랫폼 중복 자동 제거
- **웹 대시보드** — htmx + Tailwind CSS, 빌드 스텝 없음
- **크론 스케줄러** — 하루 3회 자동 실행 (APScheduler)
- **Docker 원커맨드 배포** — `docker compose up -d`

## 빠른 시작

```bash
git clone https://github.com/JuneKunst/content-autopilot.git
cd content-autopilot

cp .env.example .env
# .env 편집: DEEPSEEK_API_KEY, GHOST_ADMIN_KEY, DASHBOARD_PASSWORD 입력

docker compose up -d
docker compose exec app alembic upgrade head
```

| 서비스 | URL |
|--------|-----|
| 대시보드 | http://localhost:8000/dashboard |
| Ghost 블로그 | http://localhost:2368 |
| Ghost Admin | http://localhost:2368/ghost/ |
| API 문서 | http://localhost:8000/docs |

## 최소 구성

API 키가 없는 소스는 자동 스킵됩니다. 이것만 있으면 동작합니다:

```bash
DEEPSEEK_API_KEY=sk-xxxx        # AI 요약/번역
GHOST_ADMIN_KEY=id:secret        # Ghost 발행 (localhost:2368/ghost 에서 발급)
DASHBOARD_PASSWORD=changeme      # 대시보드 로그인
```

→ HN + RSS만으로 수집 시작. Reddit/GitHub/YouTube는 각 API 키 추가 시 활성화.

## CLI

```bash
# 드라이런 (수집+스코어링만, 발행 안 함)
python -m content_autopilot.cli run-pipeline --dry-run

# 실제 실행
python -m content_autopilot.cli run-pipeline

# 스케줄러 시작 (매일 7시/12시/18시 자동 실행)
python -m content_autopilot.cli start-scheduler
```

실행 결과:
```
Status: success
Collected: 35 -> Deduped: 28 -> Scored: 3 -> Published: 3
```

## 설정 커스터마이징

모든 설정은 `config/` 디렉토리의 YAML 파일로 관리됩니다.

| 파일 | 용도 |
|------|------|
| `config/sources/hn.yaml` | HN 수집 설정 (min_score, fetch_count) |
| `config/sources/reddit.yaml` | Reddit 서브레딧 목록 |
| `config/sources/github.yaml` | GitHub 언어 필터, 최소 스타 수 |
| `config/sources/rss.yaml` | RSS 피드 URL 목록 |
| `config/sources/youtube.yaml` | YouTube 검색 쿼리, 일일 쿼터 |
| `config/scoring.yaml` | 스코어링 가중치, top_n 선별 수 |
| `config/schedule.yaml` | 크론 스케줄 (기본 7/12/18시) |
| `config/personas/default.yaml` | 페르소나 톤, 스타일 규칙, 금지 표현 |
| `config/personas/prompts/` | AI 프롬프트 템플릿 (요약, 스타일링) |
| `config/newsletter.yaml` | Ghost 뉴스레터 자동 발송 |
| `config/social.yaml` | Mastodon/Bluesky 크로스포스팅 |
| `config/monetization.yaml` | 광고/제휴 플레이스홀더 |

### 페르소나 예시

```yaml
# config/personas/default.yaml
tone: "친근하고 정보 전달력 있는 테크 블로거"
style_rules:
  - "첫 문장으로 핵심 정보 전달"
  - "개인 의견은 '제 생각엔~' 형태로 자연스럽게"
  - "전문용어는 한국어 병기 (예: LLM(대규모 언어 모델))"
forbidden_patterns:
  - "다음과 같습니다:"
  - "명시된 바와 같이"
target_length:
  recommended_chars: 700
```

## 아키텍처

```
src/content_autopilot/
├── collectors/          # HN, Reddit, GitHub, RSS, YouTube
├── processing/          # 중복제거, 스코어링, AI 요약, 페르소나 스타일링
├── publishers/          # Ghost, Telegram, Discord, Mastodon, Bluesky
├── orchestrator/        # 파이프라인 오케스트레이터 + APScheduler
├── ai/                  # DeepSeek API 클라이언트 + 프롬프트 로더
├── dashboard/           # FastAPI 라우터 + htmx 템플릿
├── common/              # 로거, 리트라이, 레이트리미터, HTTP 클라이언트
├── models/              # SQLAlchemy ORM (6 테이블)
└── schemas/             # Pydantic 데이터 모델 (9개)
```

### 데이터 흐름

```
[5개 소스] → RawItem → DedupService → ScoringEngine → top N
                                                        ↓
                                          Summarizer (DeepSeek API)
                                                        ↓
                                           Humanizer (DeepSeek API)
                                                        ↓
                                    Ghost / Telegram / Discord / SNS
```

## 기술 스택

| | |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 async, asyncpg |
| AI | DeepSeek V3 ($0.27/MTok input, $1.10/MTok output) |
| CMS | Ghost 5 (SQLite) |
| DB | PostgreSQL 15 |
| Frontend | htmx + Tailwind CSS CDN (빌드 불필요) |
| Scheduler | APScheduler |
| Deploy | Docker Compose |

## 월 운영 비용

| 항목 | 비용 |
|------|------|
| DeepSeek API | ~$1/월 (하루 9건 기준) |
| 서버 (VPS) | $5-10/월 |
| Ghost / PostgreSQL | $0 (셀프호스팅) |
| **합계** | **~$6-11/월** |

## 개발

```bash
# 로컬 설치
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 테스트 (215개)
python -m pytest tests/ -v

# 린트
ruff check src/
```

## 상세 가이드

API 키 발급, 채널 설정, 운영/백업, 문제 해결 등 상세 내용은 [GUIDE.md](GUIDE.md) 참조.

## License

MIT
