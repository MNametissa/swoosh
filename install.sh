#!/usr/bin/env bash
set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info() { echo -e "${CYAN}$1${NC}"; }
success() { echo -e "${GREEN}$1${NC}"; }
warn() { echo -e "${YELLOW}$1${NC}"; }
error() { echo -e "${RED}$1${NC}"; exit 1; }

# Detect OS and package manager
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        if command -v brew &> /dev/null; then
            PKG="brew"
        else
            PKG="none"
        fi
    elif [[ -f /etc/debian_version ]]; then
        OS="debian"
        PKG="apt"
    elif [[ -f /etc/fedora-release ]]; then
        OS="fedora"
        PKG="dnf"
    elif [[ -f /etc/arch-release ]]; then
        OS="arch"
        PKG="pacman"
    elif [[ -f /etc/alpine-release ]]; then
        OS="alpine"
        PKG="apk"
    elif command -v apt-get &> /dev/null; then
        OS="debian"
        PKG="apt"
    elif command -v dnf &> /dev/null; then
        OS="fedora"
        PKG="dnf"
    elif command -v yum &> /dev/null; then
        OS="rhel"
        PKG="yum"
    elif command -v pacman &> /dev/null; then
        OS="arch"
        PKG="pacman"
    else
        OS="unknown"
        PKG="none"
    fi
}

# Install package based on OS
install_pkg() {
    local pkg="$1"
    local pkg_apt="${2:-$1}"
    local pkg_dnf="${3:-$1}"
    local pkg_brew="${4:-$1}"
    local pkg_pacman="${5:-$1}"

    info "Installing $pkg..."

    case "$PKG" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y "$pkg_apt"
            ;;
        dnf)
            sudo dnf install -y "$pkg_dnf"
            ;;
        yum)
            sudo yum install -y "$pkg_dnf"
            ;;
        pacman)
            sudo pacman -S --noconfirm "$pkg_pacman"
            ;;
        apk)
            sudo apk add "$pkg_apt"
            ;;
        brew)
            brew install "$pkg_brew"
            ;;
        *)
            warn "Cannot auto-install $pkg. Please install manually."
            return 1
            ;;
    esac
}

# Install Homebrew on macOS
install_homebrew() {
    if [[ "$OS" == "macos" ]] && ! command -v brew &> /dev/null; then
        info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add to path for this session
        if [[ -f /opt/homebrew/bin/brew ]]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [[ -f /usr/local/bin/brew ]]; then
            eval "$(/usr/local/bin/brew shellenv)"
        fi
        PKG="brew"
    fi
}

# Install GitHub CLI
install_gh() {
    if command -v gh &> /dev/null; then
        success "  gh: $(gh --version | head -1)"
        return 0
    fi

    info "Installing GitHub CLI..."

    case "$PKG" in
        apt)
            curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg
            sudo chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg
            echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
            sudo apt-get update -qq
            sudo apt-get install -y gh
            ;;
        dnf|yum)
            sudo dnf install -y 'dnf-command(config-manager)' 2>/dev/null || true
            sudo dnf config-manager --add-repo https://cli.github.com/packages/rpm/gh-cli.repo
            sudo dnf install -y gh
            ;;
        pacman)
            sudo pacman -S --noconfirm github-cli
            ;;
        brew)
            brew install gh
            ;;
        *)
            warn "Please install GitHub CLI manually: https://cli.github.com"
            return 1
            ;;
    esac

    success "  gh: installed"
}

# Install pipx
install_pipx() {
    if command -v pipx &> /dev/null; then
        return 0
    fi

    info "Installing pipx..."

    case "$PKG" in
        apt)
            sudo apt-get install -y pipx || python3 -m pip install --user pipx
            ;;
        dnf|yum)
            sudo dnf install -y pipx || python3 -m pip install --user pipx
            ;;
        pacman)
            sudo pacman -S --noconfirm python-pipx || python3 -m pip install --user pipx
            ;;
        brew)
            brew install pipx
            ;;
        *)
            python3 -m pip install --user pipx
            ;;
    esac

    # Ensure pipx path
    python3 -m pipx ensurepath 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
}

echo ""
echo "======================================"
echo "       Swoosh Installer"
echo "======================================"
echo ""

detect_os
info "Detected: $OS ($PKG)"
echo ""

# macOS: ensure Homebrew
if [[ "$OS" == "macos" ]]; then
    install_homebrew
fi

# 1. Python 3.10+
info "Checking Python..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &> /dev/null; then
        version=$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")
        major=$(echo "$version" | cut -d. -f1)
        minor=$(echo "$version" | cut -d. -f2)
        if [[ "$major" -ge 3 ]] && [[ "$minor" -ge 10 ]]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    info "Installing Python 3.12..."
    case "$PKG" in
        apt)
            sudo apt-get update -qq
            sudo apt-get install -y python3 python3-pip python3-venv
            ;;
        dnf|yum)
            sudo dnf install -y python3 python3-pip
            ;;
        pacman)
            sudo pacman -S --noconfirm python python-pip
            ;;
        brew)
            brew install python@3.12
            ;;
        *)
            error "Please install Python 3.10+ manually"
            ;;
    esac
    PYTHON="python3"
fi
success "  python: $($PYTHON --version)"

# 2. Git
info "Checking git..."
if command -v git &> /dev/null; then
    success "  git: $(git --version)"
else
    install_pkg "git"
    success "  git: installed"
fi

# 3. GitHub CLI
info "Checking GitHub CLI..."
install_gh

# 4. SSH
info "Checking SSH..."
if command -v ssh &> /dev/null; then
    success "  ssh: OK"
else
    install_pkg "openssh-client" "openssh-client" "openssh-clients" "openssh" "openssh"
    success "  ssh: installed"
fi

# 5. rsync
info "Checking rsync..."
if command -v rsync &> /dev/null; then
    success "  rsync: OK"
else
    install_pkg "rsync"
    success "  rsync: installed"
fi

echo ""

# 6. Install pipx
info "Setting up pipx..."
install_pipx
success "  pipx: OK"

# 7. Install swoosh
echo ""
info "Installing Swoosh..."

# Try PyPI first, fallback to GitHub
if pipx install swoosh-cli 2>/dev/null; then
    success "  swoosh: installed from PyPI"
else
    info "  Installing from GitHub..."
    pipx install git+https://github.com/MNametissa/swoosh.git
    success "  swoosh: installed from GitHub"
fi

# Ensure PATH
export PATH="$HOME/.local/bin:$PATH"

echo ""
echo "======================================"
success "  Swoosh installed successfully!"
echo "======================================"
echo ""

# Verify
if command -v swoosh &> /dev/null; then
    swoosh --version
else
    warn "Add to your shell profile:"
    echo '  export PATH="$HOME/.local/bin:$PATH"'
    echo ""
    echo "Then restart your terminal or run:"
    echo "  source ~/.bashrc  # or ~/.zshrc"
fi

echo ""
info "Next steps:"
echo "  1. Run: swoosh auth"
echo "  2. Run: swoosh doctor"
echo "  3. Run: swoosh init myproject"
echo ""

# Offer to run auth now
read -p "Run 'swoosh auth' now? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    swoosh auth
fi
