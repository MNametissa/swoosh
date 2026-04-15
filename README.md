# Swoosh

All-in-one CLI for Git workflow automation.

## Install

One command installs everything (Python, Git, GitHub CLI, SSH, rsync, swoosh):

**Linux/macOS:**
```bash
curl -fsSL https://raw.githubusercontent.com/MNametissa/swoosh/main/install.sh | bash
```

**Windows (PowerShell):**
```powershell
iwr -useb https://raw.githubusercontent.com/MNametissa/swoosh/main/install.ps1 | iex
```

The installer auto-detects your OS and package manager:
- **Linux**: apt, dnf, yum, pacman, apk
- **macOS**: Homebrew (installs if missing)
- **Windows**: winget, scoop, chocolatey

### Manual install

If you already have Python 3.10+ and dependencies:
```bash
pipx install swoosh-cli
# or
pip install swoosh-cli
```

### From source
```bash
pip install git+https://github.com/MNametissa/swoosh.git
```

## Commands

| Command | Description |
|---------|-------------|
| `swoosh auth` | Authenticate with GitHub (SSH, token, or OAuth) |
| `swoosh init` | Initialize project with Git, GitHub repo, CI/CD |
| `swoosh commit` | Create conventional commit |
| `swoosh release` | Version bump, changelog, tag, GitHub release |
| `swoosh deploy` | Deploy via SSH/rsync with rollback |
| `swoosh sync` | Sync multiple repositories |
| `swoosh secrets` | Scan for secrets, manage GitHub secrets |
| `swoosh pr` | Create/list pull requests |
| `swoosh origin` | Multi-origin management |
| `swoosh clone` | Clone repositories |
| `swoosh hook` | Manage auto-push hooks |
| `swoosh templates` | List CI/CD templates |
| `swoosh doctor` | Check dependencies |
| `swoosh config` | Configure defaults |

## Usage

### Authenticate with GitHub
```bash
# Interactive (recommended)
swoosh auth

# Check status
swoosh auth status

# Use SSH key
swoosh auth --ssh

# Use Personal Access Token
swoosh auth --token ghp_xxxxxxxxxxxx

# With git config
swoosh auth --name "Your Name" --email "you@example.com"
```

### Initialize a new project
```bash
# Create new project with Python CI template
swoosh init myproject --template python

# Initialize in current directory
swoosh init --here
```

### Commit with conventional format
```bash
# Interactive
swoosh commit

# Quick
swoosh commit "add user auth" --type feat --push
```

### Create a release
```bash
# Interactive with auto-detection
swoosh release --auto

# Specific bump
swoosh release minor

# Pre-release
swoosh release patch --pre beta
```

### Deploy to server
```yaml
# swoosh.yaml
deploy:
  production:
    host: user@server.com
    path: /var/www/app
    method: rsync
    build: npm run build
    restart: systemctl restart app
    health_check:
      type: http
      url: http://localhost:3000/health
```

```bash
swoosh deploy production
swoosh deploy --rollback production
```

### Multi-origin management
```bash
# List remotes
swoosh origin list

# Add GitLab mirror
swoosh origin mirror --provider gitlab

# Push to all remotes
swoosh origin push

# Check sync status
swoosh origin status
```

### Scan for secrets
```bash
swoosh secrets scan
swoosh secrets scan --staged
```

## CI/CD Templates

- `generic` - Basic linting
- `node` - Node.js with npm, testing, build
- `python` - Python with pytest, ruff
- `rust` - Rust with cargo, clippy
- `go` - Go with testing, build

```bash
swoosh templates list
swoosh templates show python
```

## Configuration

Global config: `~/.config/swoosh/config.yaml`
Project config: `swoosh.yaml`

```bash
swoosh config --show
swoosh config --github-user myuser
```

## License

MIT
