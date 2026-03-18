#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────
# 새 맥 개발환경 전체 셋업 (Homebrew + Docker + Node + OpenCode + Claude)
#
# 사용법: bash scripts/mac-setup.sh
# ──────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}  OK${NC} $1"; }
warn()  { echo -e "${YELLOW}  !${NC} $1"; }

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  맥 개발환경 전체 셋업"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── 1. Homebrew ──
if ! command -v brew &>/dev/null; then
    info "Homebrew 설치 중..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Apple Silicon 경로 추가
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
    ok "Homebrew"
else
    ok "Homebrew (이미 설치됨)"
fi

# ── 2. Git ──
if ! command -v git &>/dev/null; then
    info "Git 설치 중..."
    brew install git
    ok "Git"
else
    ok "Git (이미 설치됨)"
fi

# ── 3. Node.js ──
if ! command -v node &>/dev/null; then
    info "Node.js 설치 중..."
    brew install node
    ok "Node.js $(node --version)"
else
    ok "Node.js $(node --version) (이미 설치됨)"
fi

# ── 4. Docker ──
if ! command -v docker &>/dev/null; then
    info "Docker Desktop 설치 중..."
    brew install --cask docker
    warn "Docker Desktop을 실행해주세요 (Applications에서)"
    warn "Docker가 시작된 후 이 스크립트를 다시 실행하세요."
    open -a Docker
    exit 0
else
    ok "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
fi

# Docker 실행 확인
if ! docker info &>/dev/null; then
    warn "Docker가 실행 중이 아닙니다. Docker Desktop을 시작해주세요."
    open -a Docker
    echo "Docker 시작 대기 중..."
    for i in $(seq 1 30); do
        sleep 2
        if docker info &>/dev/null; then
            break
        fi
    done
    if ! docker info &>/dev/null; then
        warn "Docker가 아직 시작되지 않았습니다. Docker 시작 후 다시 실행해주세요."
        exit 1
    fi
fi
ok "Docker 실행 중"

# ── 5. Python (pyenv) ──
if ! command -v python3 &>/dev/null || [[ "$(python3 --version 2>&1)" != *"3.12"* && "$(python3 --version 2>&1)" != *"3.13"* ]]; then
    info "Python 3.12 설치 중..."
    brew install python@3.12
    ok "Python 3.12"
else
    ok "Python $(python3 --version | awk '{print $2}') (이미 설치됨)"
fi

# ── 6. Claude Code ──
if ! command -v claude &>/dev/null; then
    info "Claude Code (CLI) 설치 중..."
    npm install -g @anthropic-ai/claude-code
    ok "Claude Code"
else
    ok "Claude Code (이미 설치됨)"
fi

# ── 7. OpenCode ──
if ! command -v opencode &>/dev/null; then
    info "OpenCode 설치 중..."
    npm install -g opencode
    ok "OpenCode"
else
    ok "OpenCode (이미 설치됨)"
fi

# ── 8. oh-my-opencode 플러그인 ──
info "oh-my-opencode 플러그인 설치 중..."
mkdir -p ~/.config/opencode
if [ ! -f ~/.config/opencode/package.json ]; then
    echo '{"dependencies":{"@opencode-ai/plugin":"latest"}}' > ~/.config/opencode/package.json
fi
(cd ~/.config/opencode && npm install 2>/dev/null) || warn "플러그인 설치 실패"
ok "oh-my-opencode"

# ── 9. 환경 번들 가져오기 ──
BUNDLE_TAR="$HOME/opencode-env-bundle.tar.gz"
SYNC_SCRIPT="$HOME/.cache/content-autopilot-sync-env.sh"

if [ -f "$BUNDLE_TAR" ]; then
    echo ""
    info "환경 번들 발견! 설정을 가져옵니다..."

    mkdir -p "$(dirname "$SYNC_SCRIPT")"
    curl -fsSL "https://raw.githubusercontent.com/JuneKunst/content-autopilot/main/scripts/sync-env.sh" \
        -o "$SYNC_SCRIPT"
    chmod +x "$SYNC_SCRIPT"
    bash "$SYNC_SCRIPT" import
    rm -f "$SYNC_SCRIPT"
else
    echo ""
    warn "환경 번들이 없습니다 ($BUNDLE_TAR)"
    echo "    기존 컴퓨터에서 실행:"
    echo "      cd content-autopilot"
    echo "      bash scripts/sync-env.sh export"
    echo "    번들 파일을 이 컴퓨터 홈(~/)에 복사 후 다시 실행하세요."
fi

# ── 10. GitHub CLI ──
if ! command -v gh &>/dev/null; then
    info "GitHub CLI 설치 중..."
    brew install gh
    ok "GitHub CLI"
else
    ok "GitHub CLI (이미 설치됨)"
fi

# ── 결과 ──
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}개발환경 셋업 완료!${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  설치된 도구:"
echo "    brew     $(brew --version 2>/dev/null | head -1 || echo 'N/A')"
echo "    git      $(git --version 2>/dev/null | awk '{print $3}' || echo 'N/A')"
echo "    node     $(node --version 2>/dev/null || echo 'N/A')"
echo "    python   $(python3 --version 2>/dev/null | awk '{print $2}' || echo 'N/A')"
echo "    docker   $(docker --version 2>/dev/null | awk '{print $3}' | tr -d ',' || echo 'N/A')"
echo "    claude   $(claude --version 2>/dev/null || echo 'N/A')"
echo "    opencode $(opencode --version 2>/dev/null || echo 'N/A')"
echo "    gh       $(gh --version 2>/dev/null | head -1 | awk '{print $3}' || echo 'N/A')"
echo ""
echo "  다음 단계:"
echo "    1. gh auth login              # GitHub 로그인"
echo "    2. claude                      # Claude Code 로그인"
echo "    3. opencode                    # OpenCode 로그인"
echo "    4. git clone https://github.com/JuneKunst/content-autopilot.git"
echo "    5. cd content-autopilot && bash setup.sh"
echo ""
