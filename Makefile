# Content Autopilot — 주요 명령어
# 사용법: make [명령어]

.PHONY: setup start stop restart logs dry-run run scheduler status ghost-setup test lint clean help

# ── 초기 설정 ──
setup:                ## 최초 설치 (대화형 API 키 입력 + Docker 빌드 + DB 마이그레이션)
	@bash setup.sh

# ── 서비스 관리 ──
start:                ## 서비스 시작
	docker compose up -d
	@echo "✓ http://localhost:8000/dashboard"

stop:                 ## 서비스 중지
	docker compose down

restart:              ## 서비스 재시작
	docker compose restart app
	@echo "✓ 앱 재시작 완료"

rebuild:              ## 코드 변경 후 재빌드 + 시작
	docker compose up -d --build

logs:                 ## 앱 로그 보기 (Ctrl+C로 종료)
	docker compose logs -f app

logs-all:             ## 전체 로그 보기
	docker compose logs -f

# ── 파이프라인 ──
dry-run:              ## 드라이런 (수집+스코어링, 발행 안 함)
	docker compose exec app python -m content_autopilot.cli run-pipeline --dry-run

run:                  ## 실제 파이프라인 실행 (수집 → AI 처리 → 발행)
	docker compose exec app python -m content_autopilot.cli run-pipeline

scheduler:            ## 자동 스케줄러 시작 (매일 7/12/18시 실행, 백그라운드)
	docker compose exec -d app python -m content_autopilot.cli start-scheduler
	@echo "✓ 스케줄러 시작 (매일 07:00, 12:00, 18:00 KST)"

status:               ## 파이프라인 상태 확인
	docker compose exec app python -m content_autopilot.cli status

# ── Ghost 설정 ──
ghost-setup:          ## Ghost Admin 브라우저 열기
	@echo "Ghost Admin에서 계정 생성 후 Integration → Admin API Key 복사"
	@echo "복사한 키를 .env의 GHOST_ADMIN_KEY에 입력 후: make restart"
	@open http://localhost:2368/ghost/ 2>/dev/null || echo "→ http://localhost:2368/ghost/"

# ── 개발 ──
test:                 ## 테스트 실행
	docker compose exec app python -m pytest tests/ -q

lint:                 ## 린트 체크
	docker compose exec app python -m ruff check src/ --select E,F,W,I

migrate:              ## DB 마이그레이션 실행
	docker compose exec app alembic upgrade head

shell:                ## 앱 컨테이너 쉘 접속
	docker compose exec app bash

# ── Playwright (네이버/티스토리용) ──
install-browser:      ## Playwright Chromium 설치 (네이버/티스토리 발행 시 필요)
	docker compose exec app python -m playwright install chromium
	docker compose exec app python -m playwright install-deps
	@echo "✓ Chromium 설치 완료"

# ── 유지보수 ──
backup:               ## 데이터 백업 (Ghost + PostgreSQL)
	@mkdir -p backups
	docker compose exec -T postgres pg_dump -U autopilot content_autopilot > backups/db_$$(date +%Y%m%d).sql
	@echo "✓ DB 백업 → backups/db_$$(date +%Y%m%d).sql"

clean:                ## Docker 볼륨 포함 전체 정리 (데이터 삭제!)
	@echo "⚠️  Ghost, PostgreSQL 데이터가 모두 삭제됩니다!"
	@read -p "정말 삭제? (y/N): " confirm && [ "$$confirm" = "y" ] && docker compose down -v || echo "취소됨"

update:               ## 최신 코드 pull + 재빌드
	git pull
	docker compose up -d --build
	docker compose exec -T app alembic upgrade head
	@echo "✓ 업데이트 완료"

# ── 도움말 ──
help:                 ## 이 도움말 표시
	@echo ""
	@echo "Content Autopilot — 사용 가능한 명령어"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-16s %s\n", $$1, $$2}'
	@echo ""

.DEFAULT_GOAL := help
