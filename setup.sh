#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# Content Autopilot — 원커맨드 셋업
# 사용법: bash setup.sh
# ──────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
fail()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Content Autopilot — 초기 설정"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Docker 확인 ──
if ! command -v docker &>/dev/null; then
    fail "Docker가 설치되어 있지 않습니다.
    macOS: https://www.docker.com/products/docker-desktop/ 에서 설치
    Linux: curl -fsSL https://get.docker.com | sh"
fi

if ! docker info &>/dev/null; then
    fail "Docker가 실행 중이 아닙니다. Docker Desktop을 시작해주세요."
fi
ok "Docker 확인 완료"

# ── 2. .env 생성 ──
if [ -f .env ]; then
    warn ".env 파일이 이미 존재합니다. 덮어쓰지 않습니다."
    echo "    새로 만들려면: cp .env.example .env"
else
    cp .env.example .env
    ok ".env 파일 생성 완료"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  API 키 입력 (필수 항목만, 나머지는 나중에)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # OpenAI API Key (필수)
    read -rp "OpenAI API Key (sk-...): " OPENAI_KEY
    if [ -n "$OPENAI_KEY" ]; then
        sed -i.bak "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$OPENAI_KEY|" .env
        ok "OpenAI 키 설정 완료"
    else
        warn "OpenAI 키 미입력 — 나중에 .env 파일에서 직접 입력하세요"
    fi

    # Dashboard Password
    read -rp "대시보드 비밀번호 (기본: admin): " DASH_PW
    if [ -n "$DASH_PW" ]; then
        sed -i.bak "s|DASHBOARD_PASSWORD=.*|DASHBOARD_PASSWORD=$DASH_PW|" .env
    fi
    ok "대시보드 비밀번호 설정 완료"

    # Gemini (선택)
    read -rp "Gemini API Key (없으면 Enter): " GEMINI_KEY
    if [ -n "$GEMINI_KEY" ]; then
        sed -i.bak "s|GEMINI_API_KEY=.*|GEMINI_API_KEY=$GEMINI_KEY|" .env
        ok "Gemini 키 설정 완료"
    fi

    # Claude (선택)
    read -rp "Claude API Key (없으면 Enter): " CLAUDE_KEY
    if [ -n "$CLAUDE_KEY" ]; then
        sed -i.bak "s|CLAUDE_API_KEY=.*|CLAUDE_API_KEY=$CLAUDE_KEY|" .env
        ok "Claude 키 설정 완료"
    fi

    # GitHub Token (선택)
    read -rp "GitHub Token (없으면 Enter): " GH_TOKEN
    if [ -n "$GH_TOKEN" ]; then
        sed -i.bak "s|GITHUB_TOKEN=.*|GITHUB_TOKEN=$GH_TOKEN|" .env
        ok "GitHub 토큰 설정 완료"
    fi

    # YouTube API Key (선택)
    read -rp "YouTube API Key (없으면 Enter): " YT_KEY
    if [ -n "$YT_KEY" ]; then
        sed -i.bak "s|YOUTUBE_API_KEY=.*|YOUTUBE_API_KEY=$YT_KEY|" .env
        ok "YouTube 키 설정 완료"
    fi

    # Telegram (선택)
    read -rp "Telegram Bot Token (없으면 Enter): " TG_TOKEN
    if [ -n "$TG_TOKEN" ]; then
        sed -i.bak "s|TG_BOT_TOKEN=.*|TG_BOT_TOKEN=$TG_TOKEN|" .env
        read -rp "Telegram Channel ID (@channel): " TG_CH
        if [ -n "$TG_CH" ]; then
            sed -i.bak "s|TG_CHANNEL_ID=.*|TG_CHANNEL_ID=$TG_CH|" .env
        fi
        ok "Telegram 설정 완료"
    fi

    # Discord (선택)
    read -rp "Discord Webhook URL (없으면 Enter): " DISCORD_URL
    if [ -n "$DISCORD_URL" ]; then
        sed -i.bak "s|DISCORD_WEBHOOK_URL=.*|DISCORD_WEBHOOK_URL=$DISCORD_URL|" .env
        ok "Discord 설정 완료"
    fi

    # WordPress (선택)
    read -rp "WordPress 사이트 URL (없으면 Enter): " WP_URL
    if [ -n "$WP_URL" ]; then
        sed -i.bak "s|WP_SITE_URL=.*|WP_SITE_URL=$WP_URL|" .env
        read -rp "WordPress 사용자명: " WP_USER
        sed -i.bak "s|WP_USERNAME=.*|WP_USERNAME=$WP_USER|" .env
        read -rp "WordPress 앱 비밀번호: " WP_PASS
        sed -i.bak "s|WP_APP_PASSWORD=.*|WP_APP_PASSWORD=$WP_PASS|" .env
        ok "WordPress 설정 완료"
    fi

    # 임시 백업 파일 정리
    rm -f .env.bak

    echo ""
    ok "API 키 설정 완료!"
    echo "    나머지 키는 나중에 .env 파일에서 직접 수정 가능합니다."
    echo ""
fi

# ── 3. 데이터 디렉토리 ──
mkdir -p data
ok "데이터 디렉토리 생성"

# ── 4. Docker 빌드 + 실행 ──
echo ""
info "Docker 이미지 빌드 + 서비스 기동 중... (첫 실행 시 3-5분)"
docker compose up -d --build

# ── 5. 서비스 대기 ──
info "PostgreSQL 준비 대기 중..."
for i in $(seq 1 30); do
    if docker compose exec -T postgres pg_isready -U autopilot -d content_autopilot &>/dev/null; then
        break
    fi
    sleep 2
done
ok "PostgreSQL 준비 완료"

# ── 6. DB 마이그레이션 ──
info "데이터베이스 마이그레이션 실행 중..."
docker compose exec -T app alembic upgrade head 2>/dev/null || warn "마이그레이션 실패 — 나중에 수동으로: docker compose exec app alembic upgrade head"
ok "DB 마이그레이션 완료"

# ── 7. 결과 출력 ──
LOCAL_IP=$(ifconfig 2>/dev/null | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}' || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}설정 완료!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  대시보드    http://${LOCAL_IP}:8000/dashboard"
echo "  Ghost 블로그 http://${LOCAL_IP}:2368"
echo "  Ghost Admin  http://${LOCAL_IP}:2368/ghost/"
echo "  API 문서     http://${LOCAL_IP}:8000/docs"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  다음 단계"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  1. Ghost Admin 접속 → 계정 생성 → Admin API Key 발급"
echo "     http://${LOCAL_IP}:2368/ghost/"
echo ""
echo "  2. Ghost 키를 .env에 입력:"
echo "     GHOST_ADMIN_KEY=발급받은키"
echo "     GHOST_CONTENT_KEY=발급받은키"
echo ""
echo "  3. 앱 재시작: docker compose restart app"
echo ""
echo "  4. 테스트: make dry-run"
echo ""
echo "  5. 자동 스케줄러: make scheduler"
echo ""
