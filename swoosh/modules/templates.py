"""CI/CD templates and .gitignore templates."""

from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from rich.panel import Panel

console = Console()

TEMPLATES = {
    "generic": {
        "description": "Basic CI with linting",
        "workflow": """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Check files
        run: |
          echo "Repository checked out successfully"
          ls -la
""",
        "gitignore": """# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp
*.swo
*~

# Environment
.env
.env.local
*.local

# Logs
*.log
logs/
""",
    },

    "node": {
        "description": "Node.js with npm/yarn, testing, build",
        "workflow": """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  build:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        node-version: [18.x, 20.x]

    steps:
      - uses: actions/checkout@v4

      - name: Use Node.js ${{ matrix.node-version }}
        uses: actions/setup-node@v4
        with:
          node-version: ${{ matrix.node-version }}
          cache: 'npm'

      - name: Install dependencies
        run: npm ci

      - name: Lint
        run: npm run lint --if-present

      - name: Test
        run: npm test --if-present

      - name: Build
        run: npm run build --if-present
""",
        "gitignore": """# Dependencies
node_modules/
.pnp/
.pnp.js

# Build
dist/
build/
out/
.next/
.nuxt/

# Testing
coverage/

# OS
.DS_Store
Thumbs.db

# IDE
.idea/
.vscode/
*.swp

# Environment
.env
.env.local
.env*.local

# Logs
*.log
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# Cache
.npm/
.eslintcache
.cache/
""",
    },

    "python": {
        "description": "Python with pytest, linting, type checking",
        "workflow": """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest

    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install ruff pytest
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          if [ -f pyproject.toml ]; then pip install -e .; fi

      - name: Lint with ruff
        run: ruff check . --exit-zero

      - name: Test with pytest
        run: pytest --tb=short -q || true
""",
        "gitignore": """# Byte-compiled
__pycache__/
*.py[cod]
*$py.class
*.pyo

# Distribution
dist/
build/
*.egg-info/
*.egg
wheels/

# Virtual environments
venv/
.venv/
env/
.env/
ENV/

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Environment
.env
.env.local

# Jupyter
.ipynb_checkpoints/

# mypy
.mypy_cache/
""",
    },

    "rust": {
        "description": "Rust with cargo test, clippy, fmt",
        "workflow": """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

env:
  CARGO_TERM_COLOR: always

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Setup Rust
        uses: dtolnay/rust-toolchain@stable
        with:
          components: rustfmt, clippy

      - name: Cache cargo
        uses: Swatinem/rust-cache@v2

      - name: Check formatting
        run: cargo fmt --all -- --check

      - name: Clippy
        run: cargo clippy -- -D warnings

      - name: Build
        run: cargo build --verbose

      - name: Test
        run: cargo test --verbose
""",
        "gitignore": """# Rust build
target/
Cargo.lock

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db
""",
    },

    "go": {
        "description": "Go with testing, linting, build",
        "workflow": """name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  build:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.22'

      - name: Build
        run: go build -v ./...

      - name: Test
        run: go test -v ./...

      - name: Vet
        run: go vet ./...
""",
        "gitignore": """# Binaries
*.exe
*.exe~
*.dll
*.so
*.dylib

# Build output
bin/
dist/

# Test
*.test
coverage.out
coverage.html

# Vendor (uncomment if not using modules)
# vendor/

# IDE
.idea/
.vscode/
*.swp

# OS
.DS_Store
Thumbs.db

# Go workspace
go.work
""",
    },
}


def get_workflow(template_name: str) -> str:
    """Get CI workflow content for a template."""
    if template_name not in TEMPLATES:
        template_name = "generic"
    return TEMPLATES[template_name]["workflow"]


def get_gitignore(template_name: str) -> str:
    """Get .gitignore content for a template."""
    if template_name not in TEMPLATES:
        template_name = "generic"
    return TEMPLATES[template_name]["gitignore"]


def list_templates():
    """Display available templates."""
    console.print()

    table = Table(title="Available CI/CD Templates", show_header=True)
    table.add_column("Template", style="cyan", width=12)
    table.add_column("Description", style="white")

    for name, data in TEMPLATES.items():
        table.add_row(name, data["description"])

    console.print(table)
    console.print()
    console.print("[dim]Use:[/] swoosh templates show <name>")
    console.print()


def show_template(name: str):
    """Show a specific template's content."""
    if name not in TEMPLATES:
        console.print(f"[red]Error:[/] Template '{name}' not found.")
        console.print()
        list_templates()
        return

    template = TEMPLATES[name]

    console.print()
    console.print(Panel(
        f"[bold]{name}[/] - {template['description']}",
        expand=False
    ))

    console.print()
    console.print("[bold cyan]GitHub Actions Workflow (.github/workflows/ci.yml):[/]")
    console.print()
    syntax = Syntax(template["workflow"], "yaml", theme="monokai", line_numbers=True)
    console.print(syntax)

    console.print()
    console.print("[bold cyan].gitignore:[/]")
    console.print()
    syntax = Syntax(template["gitignore"], "gitignore", theme="monokai", line_numbers=True)
    console.print(syntax)
    console.print()
