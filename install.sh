#!/usr/bin/env bash
# AiSE - AI Support Engineer System
# Installation script for Debian/Ubuntu and RHEL/CentOS/Fedora/Amazon Linux
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── OS detection ──────────────────────────────────────────────────────────────
detect_os() {
    [ -f /etc/os-release ] || error "Cannot detect OS: /etc/os-release not found."
    . /etc/os-release
    OS_ID="${ID}"
    OS_ID_LIKE="${ID_LIKE:-}"

    if echo "${OS_ID} ${OS_ID_LIKE}" | grep -qiE "debian|ubuntu|mint|pop|kali|raspbian"; then
        PKG_FAMILY="debian"
        PKG_UPDATE="apt-get update -qq"
        PKG_INSTALL="apt-get install -y"
    elif echo "${OS_ID} ${OS_ID_LIKE}" | grep -qiE "rhel|centos|fedora|amzn|rocky|almalinux|ol"; then
        PKG_FAMILY="rpm"
        if command -v dnf &>/dev/null; then
            PKG_UPDATE="dnf check-update -q || true"
            PKG_INSTALL="dnf install -y"
        else
            PKG_UPDATE="yum check-update -q || true"
            PKG_INSTALL="yum install -y"
        fi
    else
        error "Unsupported OS: ${OS_ID}. Only Debian/Ubuntu and RHEL/CentOS/Fedora families are supported."
    fi

    info "Detected OS: ${OS_ID} (${PKG_FAMILY} family)"
}

# ── Privilege check ───────────────────────────────────────────────────────────
check_root() {
    if [ "$EUID" -ne 0 ]; then
        command -v sudo &>/dev/null || error "Run as root or install sudo."
        SUDO="sudo"
    else
        SUDO=""
    fi
}

# ── Generate secure random password ──────────────────────────────────────────
gen_password() {
    python3 -c "import secrets, string; \
        chars = string.ascii_letters + string.digits; \
        print(''.join(secrets.choice(chars) for _ in range(32)))"
}

# ── System dependencies ───────────────────────────────────────────────────────
install_system_deps() {
    info "Updating package index..."
    $SUDO $PKG_UPDATE

    info "Installing system dependencies..."
    if [ "$PKG_FAMILY" = "debian" ]; then
        $SUDO $PKG_INSTALL \
            curl wget git ca-certificates gnupg lsb-release \
            build-essential libssl-dev libffi-dev \
            python3.11 python3.11-dev python3.11-venv python3-pip \
            postgresql-client redis-tools \
            libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
            libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
            libxrandr2 libgbm1 libasound2
    else
        if echo "${OS_ID}" | grep -qiE "centos|rhel|rocky|almalinux|ol"; then
            $SUDO $PKG_INSTALL epel-release 2>/dev/null || true
        fi
        $SUDO $PKG_INSTALL \
            curl wget git ca-certificates \
            gcc gcc-c++ make openssl-devel libffi-devel \
            python3.11 python3.11-devel \
            postgresql redis \
            nss atk at-spi2-atk cups-libs libdrm libxkbcommon \
            libXcomposite libXdamage libXfixes libXrandr mesa-libgbm alsa-lib
    fi
    success "System dependencies installed."
}

# ── Docker ────────────────────────────────────────────────────────────────────
install_docker() {
    if command -v docker &>/dev/null; then
        success "Docker already installed: $(docker --version)"
    else
        info "Installing Docker..."
        if [ "$PKG_FAMILY" = "debian" ]; then
            $SUDO install -m 0755 -d /etc/apt/keyrings
            curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" \
                | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/${OS_ID} $(lsb_release -cs) stable" \
                | $SUDO tee /etc/apt/sources.list.d/docker.list > /dev/null
            $SUDO apt-get update -qq
            $SUDO $PKG_INSTALL docker-ce docker-ce-cli containerd.io docker-compose-plugin
        else
            $SUDO $PKG_INSTALL yum-utils 2>/dev/null || $SUDO $PKG_INSTALL dnf-plugins-core
            $SUDO yum-config-manager --add-repo \
                https://download.docker.com/linux/centos/docker-ce.repo 2>/dev/null \
                || $SUDO dnf config-manager --add-repo \
                https://download.docker.com/linux/centos/docker-ce.repo
            $SUDO $PKG_INSTALL docker-ce docker-ce-cli containerd.io docker-compose-plugin
        fi
        $SUDO systemctl enable --now docker
        success "Docker installed: $(docker --version)"
    fi

    # Add invoking user to docker group
    REAL_USER="${SUDO_USER:-${USER}}"
    if [ -n "$REAL_USER" ] && ! groups "$REAL_USER" 2>/dev/null | grep -q docker; then
        $SUDO usermod -aG docker "$REAL_USER"
        warn "User '${REAL_USER}' added to docker group — log out and back in for this to take effect."
    fi
}

# ── Poetry ────────────────────────────────────────────────────────────────────
install_poetry() {
    if command -v poetry &>/dev/null; then
        success "Poetry already installed: $(poetry --version)"
        return
    fi
    info "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="${HOME}/.local/bin:${PATH}"
    success "Poetry installed: $(poetry --version)"
}

# ── Generate .env with consistent credentials ─────────────────────────────────
setup_env() {
    if [ -f .env ]; then
        info ".env already exists — reading existing credentials."
        # Extract existing passwords so we don't overwrite them
        POSTGRES_PASS=$(grep -oP '(?<=postgresql://aise:)[^@]+' .env | head -1 || echo "")
        REDIS_PASS=$(grep -oP '(?<=redis://:)[^@]+' .env | head -1 || echo "")
        VAULT_KEY=$(grep -oP '(?<=CREDENTIAL_VAULT_KEY=)\S+' .env | head -1 || echo "")
        WEBHOOK_SECRET=$(grep -oP '(?<=WEBHOOK_SECRET=)\S+' .env | head -1 || echo "")
    else
        info "Creating .env from .env.example with generated credentials..."
        cp .env.example .env
        POSTGRES_PASS=""
        REDIS_PASS=""
        VAULT_KEY=""
        WEBHOOK_SECRET=""
    fi

    # Generate any missing secrets
    [ -z "$POSTGRES_PASS" ]   && POSTGRES_PASS=$(gen_password)
    [ -z "$REDIS_PASS" ]      && REDIS_PASS=$(gen_password)
    [ -z "$VAULT_KEY" ]       && VAULT_KEY=$(gen_password)
    [ -z "$WEBHOOK_SECRET" ]  && WEBHOOK_SECRET=$(gen_password)

    # Write all credential lines into .env (replace or append)
    set_env_var() {
        local key="$1" val="$2"
        if grep -q "^${key}=" .env 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${val}|" .env
        else
            echo "${key}=${val}" >> .env
        fi
    }

    set_env_var "POSTGRES_URL"    "postgresql://aise:${POSTGRES_PASS}@localhost:5432/aise"
    set_env_var "DATABASE_URL"    "postgresql://aise:${POSTGRES_PASS}@localhost:5432/aise"
    set_env_var "REDIS_URL"       "redis://:${REDIS_PASS}@localhost:6379/0"
    set_env_var "CREDENTIAL_VAULT_KEY" "${VAULT_KEY}"
    set_env_var "WEBHOOK_SECRET"  "${WEBHOOK_SECRET}"
    set_env_var "CHROMA_HOST"     "localhost"
    set_env_var "CHROMA_PORT"     "8000"

    success ".env configured with generated credentials."
}

# ── Sync credentials into docker-compose.yml ─────────────────────────────────
sync_docker_compose() {
    info "Syncing credentials into docker-compose.yml..."

    # PostgreSQL password
    sed -i "s|POSTGRES_PASSWORD:.*|POSTGRES_PASSWORD: ${POSTGRES_PASS}|g" docker-compose.yml
    # PostgreSQL URLs in aise-api and aise-worker services
    sed -i "s|postgresql://aise:[^@]*@|postgresql://aise:${POSTGRES_PASS}@|g" docker-compose.yml

    # Redis password — update the redis command and all REDIS_URL references
    sed -i "s|redis-server --appendonly yes|redis-server --appendonly yes --requirepass ${REDIS_PASS}|g" docker-compose.yml
    sed -i "s|redis://redis:[0-9]*/0|redis://:${REDIS_PASS}@redis:6379/0|g" docker-compose.yml
    # Handle case where redis URL has no password yet
    sed -i "s|redis://redis:6379/0|redis://:${REDIS_PASS}@redis:6379/0|g" docker-compose.yml

    success "docker-compose.yml updated with matching credentials."
}

# ── Python dependencies ───────────────────────────────────────────────────────
install_python_deps() {
    info "Installing Python dependencies via Poetry..."
    export PATH="${HOME}/.local/bin:${PATH}"
    poetry install --no-interaction
    success "Python dependencies installed."
}

# ── Playwright browsers ───────────────────────────────────────────────────────
install_playwright() {
    info "Installing Playwright chromium browser..."
    export PATH="${HOME}/.local/bin:${PATH}"
    poetry run playwright install chromium
    success "Playwright chromium installed."
}

# ── Start infrastructure services ────────────────────────────────────────────
start_services() {
    info "Starting infrastructure services (postgres, redis, chromadb)..."
    docker compose up -d postgres redis chromadb
    info "Waiting for services to become healthy..."
    local retries=30
    while [ $retries -gt 0 ]; do
        if docker compose ps | grep -E "postgres|redis|chromadb" | grep -qv "healthy\|running"; then
            sleep 2
            retries=$((retries - 1))
        else
            break
        fi
    done
    # Give a few extra seconds for postgres to finish init
    sleep 5
    success "Infrastructure services started."
}

# ── Verify services ───────────────────────────────────────────────────────────
verify_services() {
    info "Verifying service connectivity..."

    # PostgreSQL
    if docker compose exec -T postgres pg_isready -U aise -d aise &>/dev/null; then
        success "PostgreSQL: reachable"
    else
        warn "PostgreSQL: not yet ready (may still be initializing)"
    fi

    # Redis
    if docker compose exec -T redis redis-cli -a "${REDIS_PASS}" ping 2>/dev/null | grep -q PONG; then
        success "Redis: reachable"
    else
        warn "Redis: not yet ready"
    fi

    # ChromaDB
    if curl -sf http://localhost:8000/api/v1/heartbeat &>/dev/null; then
        success "ChromaDB: reachable"
    else
        warn "ChromaDB: not yet ready"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   AiSE - AI Support Engineer Installer   ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
    echo ""

    detect_os
    check_root
    install_system_deps
    install_docker
    install_poetry
    setup_env
    sync_docker_compose
    install_python_deps
    install_playwright
    start_services
    verify_services

    echo ""
    success "Installation complete."
    echo ""
    echo -e "  Generated credentials have been written to ${YELLOW}.env${NC} and ${YELLOW}docker-compose.yml${NC}."
    echo ""
    echo -e "  ${YELLOW}Required:${NC} Edit ${YELLOW}.env${NC} and set your LLM provider API key:"
    echo -e "    ${CYAN}ANTHROPIC_API_KEY${NC}  or  ${CYAN}OPENAI_API_KEY${NC}  or  ${CYAN}DEEPSEEK_API_KEY${NC}"
    echo ""
    echo -e "  Then run:"
    echo -e "    ${CYAN}poetry run aise ask \"Why is my EC2 instance unreachable?\"${NC}"
    echo ""
}

main "$@"
