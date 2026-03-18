#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────
# OpenCode + Claude Code 환경 동기화 스크립트
#
# 현재 맥에서 실행 → 다른 맥으로 설정 내보내기/가져오기
#
# 사용법:
#   내보내기: bash scripts/sync-env.sh export
#   가져오기: bash scripts/sync-env.sh import
# ──────────────────────────────────────────────────────────

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}  OK${NC} $1"; }
warn()  { echo -e "${YELLOW}  !${NC} $1"; }
fail()  { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

BUNDLE_DIR="$HOME/opencode-env-bundle"
BUNDLE_TAR="$HOME/opencode-env-bundle.tar.gz"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPORT: 현재 컴퓨터에서 설정 내보내기
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
do_export() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  환경 설정 내보내기 (Export)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    rm -rf "$BUNDLE_DIR"
    mkdir -p "$BUNDLE_DIR"/{claude,opencode,sisyphus}

    # ── 1. Claude Code 설정 ──
    info "Claude Code 설정 복사 중..."

    # settings (모델 설정)
    [ -f ~/.claude/settings.json ] && cp ~/.claude/settings.json "$BUNDLE_DIR/claude/"
    ok "settings.json"

    # settings.local (권한 설정)
    [ -f ~/.claude/settings.local.json ] && cp ~/.claude/settings.local.json "$BUNDLE_DIR/claude/"
    ok "settings.local.json"

    # skills (사용자 스킬)
    if [ -d ~/.claude/skills ]; then
        cp -r ~/.claude/skills "$BUNDLE_DIR/claude/"
        ok "skills/ ($(find ~/.claude/skills -type f | wc -l | xargs) files)"
    fi

    # plugins
    if [ -d ~/.claude/plugins ]; then
        cp -r ~/.claude/plugins "$BUNDLE_DIR/claude/"
        ok "plugins/"
    fi

    # ── 2. OpenCode 설정 ──
    info "OpenCode 설정 복사 중..."

    # config
    if [ -d ~/.config/opencode ]; then
        cp ~/.config/opencode/opencode.json "$BUNDLE_DIR/opencode/" 2>/dev/null
        cp ~/.config/opencode/oh-my-opencode.json "$BUNDLE_DIR/opencode/" 2>/dev/null
        cp ~/.config/opencode/package.json "$BUNDLE_DIR/opencode/" 2>/dev/null
        ok "opencode config files"
    fi

    # auth (API 키 — 민감정보!)
    if [ -f ~/.local/share/opencode/auth.json ]; then
        cp ~/.local/share/opencode/auth.json "$BUNDLE_DIR/opencode/"
        ok "auth.json (API keys)"
    fi

    # model preference
    [ -f ~/.local/share/opencode/model.json ] && cp ~/.local/share/opencode/model.json "$BUNDLE_DIR/opencode/"

    # ── 3. Sisyphus 설정 (plans, notepads) ──
    info "Sisyphus 설정 복사 중..."
    if [ -d ~/.sisyphus ]; then
        cp -r ~/.sisyphus/plans "$BUNDLE_DIR/sisyphus/" 2>/dev/null
        cp -r ~/.sisyphus/notepads "$BUNDLE_DIR/sisyphus/" 2>/dev/null
        ok "plans + notepads"
    fi

    # ── 4. 번들 압축 ──
    info "번들 압축 중..."
    tar czf "$BUNDLE_TAR" -C "$HOME" "opencode-env-bundle"
    rm -rf "$BUNDLE_DIR"

    SIZE=$(du -h "$BUNDLE_TAR" | awk '{print $1}')
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  ${GREEN}내보내기 완료!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  번들 파일: $BUNDLE_TAR ($SIZE)"
    echo ""
    echo "  다른 컴퓨터로 전송 방법:"
    echo ""
    echo "  방법 1 — AirDrop:"
    echo "    Finder에서 $BUNDLE_TAR 파일을 AirDrop"
    echo ""
    echo "  방법 2 — scp:"
    echo "    scp $BUNDLE_TAR 사용자@맥미니IP:~/"
    echo ""
    echo "  방법 3 — USB:"
    echo "    USB에 $BUNDLE_TAR 복사"
    echo ""
    echo "  전송 후 맥미니에서:"
    echo "    bash scripts/sync-env.sh import"
    echo ""
    echo -e "  ${YELLOW}주의: 이 파일에는 API 키가 포함되어 있습니다.${NC}"
    echo "  전송 후 원본은 삭제하세요: rm $BUNDLE_TAR"
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# IMPORT: 다른 컴퓨터에서 설정 가져오기
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
do_import() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  환경 설정 가져오기 (Import)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ ! -f "$BUNDLE_TAR" ]; then
        fail "번들 파일을 찾을 수 없습니다: $BUNDLE_TAR
    홈 디렉토리에 opencode-env-bundle.tar.gz를 복사한 후 다시 실행하세요."
    fi

    info "번들 압축 해제 중..."
    tar xzf "$BUNDLE_TAR" -C "$HOME"

    # ── 1. Claude Code 설정 복원 ──
    info "Claude Code 설정 복원 중..."
    mkdir -p ~/.claude

    [ -f "$BUNDLE_DIR/claude/settings.json" ] && cp "$BUNDLE_DIR/claude/settings.json" ~/.claude/
    ok "settings.json"

    [ -f "$BUNDLE_DIR/claude/settings.local.json" ] && cp "$BUNDLE_DIR/claude/settings.local.json" ~/.claude/
    ok "settings.local.json"

    if [ -d "$BUNDLE_DIR/claude/skills" ]; then
        cp -r "$BUNDLE_DIR/claude/skills" ~/.claude/
        ok "skills/"
    fi

    if [ -d "$BUNDLE_DIR/claude/plugins" ]; then
        cp -r "$BUNDLE_DIR/claude/plugins" ~/.claude/
        ok "plugins/"
    fi

    # ── 2. OpenCode 설정 복원 ──
    info "OpenCode 설정 복원 중..."
    mkdir -p ~/.config/opencode
    mkdir -p ~/.local/share/opencode

    [ -f "$BUNDLE_DIR/opencode/opencode.json" ] && cp "$BUNDLE_DIR/opencode/opencode.json" ~/.config/opencode/
    [ -f "$BUNDLE_DIR/opencode/oh-my-opencode.json" ] && cp "$BUNDLE_DIR/opencode/oh-my-opencode.json" ~/.config/opencode/
    [ -f "$BUNDLE_DIR/opencode/package.json" ] && cp "$BUNDLE_DIR/opencode/package.json" ~/.config/opencode/
    ok "opencode config"

    if [ -f "$BUNDLE_DIR/opencode/auth.json" ]; then
        cp "$BUNDLE_DIR/opencode/auth.json" ~/.local/share/opencode/
        chmod 600 ~/.local/share/opencode/auth.json
        ok "auth.json (API keys)"
    fi

    [ -f "$BUNDLE_DIR/opencode/model.json" ] && cp "$BUNDLE_DIR/opencode/model.json" ~/.local/share/opencode/

    # ── 3. Sisyphus 복원 ──
    info "Sisyphus 설정 복원 중..."
    mkdir -p ~/.sisyphus
    [ -d "$BUNDLE_DIR/sisyphus/plans" ] && cp -r "$BUNDLE_DIR/sisyphus/plans" ~/.sisyphus/
    [ -d "$BUNDLE_DIR/sisyphus/notepads" ] && cp -r "$BUNDLE_DIR/sisyphus/notepads" ~/.sisyphus/
    ok "sisyphus plans + notepads"

    # ── 4. OpenCode 플러그인 설치 ──
    info "OpenCode 플러그인 설치 중..."
    if command -v opencode &>/dev/null; then
        (cd ~/.config/opencode && npm install 2>/dev/null) || warn "npm install 실패 — 수동으로: cd ~/.config/opencode && npm install"
        ok "oh-my-opencode 플러그인"
    else
        warn "opencode가 설치되어 있지 않습니다. 먼저 설치하세요."
    fi

    # ── 5. 정리 ──
    rm -rf "$BUNDLE_DIR"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  ${GREEN}가져오기 완료!${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  다음 단계:"
    echo ""
    echo "  1. Claude Code 로그인 (아직 안 했다면):"
    echo "     claude"
    echo ""
    echo "  2. OpenCode 로그인 (아직 안 했다면):"
    echo "     opencode"
    echo ""
    echo "  3. 번들 파일 삭제 (보안):"
    echo "     rm $BUNDLE_TAR"
    echo ""
}

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
case "${1:-}" in
    export)
        do_export
        ;;
    import)
        do_import
        ;;
    *)
        echo ""
        echo "사용법: bash $0 [export|import]"
        echo ""
        echo "  export  — 현재 컴퓨터의 설정을 번들 파일로 내보내기"
        echo "  import  — 번들 파일에서 설정 가져오기"
        echo ""
        echo "순서:"
        echo "  1. 현재 컴퓨터: bash $0 export"
        echo "  2. 번들 파일을 다른 컴퓨터로 전송 (AirDrop/scp/USB)"
        echo "  3. 다른 컴퓨터: bash $0 import"
        echo ""
        ;;
esac
