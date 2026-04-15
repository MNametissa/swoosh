"""Secrets scanning and management for Swoosh."""

import re
import os
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, is_git_repo

console = Console()

# Common secret patterns
SECRET_PATTERNS = [
    # API Keys
    (r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", "API Key"),
    (r"(?i)(secret[_-]?key|secretkey)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", "Secret Key"),

    # AWS
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID"),
    (r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?", "AWS Secret"),

    # GitHub
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
    (r"ghu_[a-zA-Z0-9]{36}", "GitHub User Token"),
    (r"ghs_[a-zA-Z0-9]{36}", "GitHub Server Token"),
    (r"ghr_[a-zA-Z0-9]{36}", "GitHub Refresh Token"),

    # Database
    (r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]?([^\s'\"]{8,})['\"]?", "Password"),
    (r"(?i)postgres://[^\s]+", "PostgreSQL Connection String"),
    (r"(?i)mysql://[^\s]+", "MySQL Connection String"),
    (r"(?i)mongodb(\+srv)?://[^\s]+", "MongoDB Connection String"),

    # Private Keys
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "Private Key"),

    # JWT
    (r"eyJ[a-zA-Z0-9_-]*\.eyJ[a-zA-Z0-9_-]*\.[a-zA-Z0-9_-]*", "JWT Token"),

    # Generic
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+", "Bearer Token"),
    (r"(?i)(token|auth)\s*[=:]\s*['\"]?([a-zA-Z0-9_\-]{20,})['\"]?", "Generic Token"),
]

# Files to skip
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".woff", ".woff2", ".ttf", ".eot",
    ".mp3", ".mp4", ".wav", ".avi",
    ".zip", ".tar", ".gz", ".rar",
    ".pdf", ".doc", ".docx",
    ".pyc", ".pyo", ".so", ".dll",
    ".lock", ".sum",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", ".next", ".nuxt",
    "target", "coverage", ".pytest_cache",
}


def should_scan_file(path: Path) -> bool:
    """Check if file should be scanned."""
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return False

    # Skip large files
    try:
        if path.stat().st_size > 1_000_000:  # 1MB
            return False
    except:
        return False

    return True


def scan_file(file_path: Path) -> list[dict]:
    """Scan a single file for secrets."""
    findings = []

    try:
        content = file_path.read_text(errors="ignore")
    except Exception:
        return findings

    lines = content.split("\n")

    for line_num, line in enumerate(lines, 1):
        for pattern, secret_type in SECRET_PATTERNS:
            matches = re.finditer(pattern, line)
            for match in matches:
                # Skip obvious false positives
                matched_text = match.group(0)
                if any(fp in matched_text.lower() for fp in [
                    "example", "sample", "test", "dummy", "placeholder",
                    "your_", "xxx", "changeme", "<", "{{", "${",
                ]):
                    continue

                findings.append({
                    "file": str(file_path),
                    "line": line_num,
                    "type": secret_type,
                    "match": matched_text[:60] + "..." if len(matched_text) > 60 else matched_text,
                })

    return findings


def scan_directory(
    directory: Optional[Path] = None,
    staged_only: bool = False,
) -> list[dict]:
    """Scan directory for secrets."""
    if directory is None:
        directory = Path.cwd()

    findings = []

    if staged_only:
        # Only scan staged files
        ok, output = run_cmd(["git", "diff", "--cached", "--name-only"], cwd=directory)
        if ok and output:
            files = [directory / f for f in output.split("\n") if f.strip()]
        else:
            files = []
    else:
        # Scan all files
        files = []
        for root, dirs, filenames in os.walk(directory):
            # Skip directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            for filename in filenames:
                file_path = Path(root) / filename
                if should_scan_file(file_path):
                    files.append(file_path)

    for file_path in files:
        if file_path.exists():
            file_findings = scan_file(file_path)
            findings.extend(file_findings)

    return findings


def scan(
    directory: Optional[Path] = None,
    staged_only: bool = False,
    quiet: bool = False,
):
    """Scan for secrets and display results."""
    if directory is None:
        directory = Path.cwd()

    if not quiet:
        console.print()
        console.print(f"Scanning [cyan]{directory}[/] for secrets...")
        console.print()

    findings = scan_directory(directory, staged_only=staged_only)

    if not findings:
        if not quiet:
            console.print("[green]✓[/] No secrets found.")
        return []

    console.print(f"[yellow]⚠[/] Found [red]{len(findings)}[/] potential secret(s):\n")

    # Group by file
    by_file = {}
    for f in findings:
        file = f["file"]
        if file not in by_file:
            by_file[file] = []
        by_file[file].append(f)

    for file, file_findings in by_file.items():
        rel_path = Path(file).relative_to(directory) if directory else file
        console.print(f"[cyan]{rel_path}[/]")
        for f in file_findings:
            console.print(f"  [dim]:{f['line']}[/] [{f['type']}] {f['match']}")
        console.print()

    return findings


def add_github_secret(
    name: str,
    value: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Add a secret to GitHub repository."""
    if cwd is None:
        cwd = Path.cwd()

    if not value:
        value = questionary.password(
            f"Value for {name}:",
        ).ask()

        if not value:
            console.print("[yellow]Cancelled.[/]")
            return

    # Use gh CLI to set secret
    import subprocess
    process = subprocess.Popen(
        ["gh", "secret", "set", name],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        text=True
    )
    stdout, stderr = process.communicate(input=value)

    if process.returncode == 0:
        console.print(f"[green]✓[/] Secret '{name}' added to GitHub")
    else:
        console.print(f"[red]✗[/] Failed: {stderr}")


def list_github_secrets(cwd: Optional[Path] = None):
    """List GitHub repository secrets."""
    if cwd is None:
        cwd = Path.cwd()

    ok, output = run_cmd(["gh", "secret", "list"], cwd=cwd)

    if ok:
        console.print()
        if output:
            console.print("[bold]GitHub Secrets:[/]\n")
            console.print(output)
        else:
            console.print("[dim]No secrets configured.[/]")
    else:
        console.print(f"[red]Error:[/] {output}")


def install_pre_commit_hook(cwd: Optional[Path] = None):
    """Install pre-commit hook to scan for secrets."""
    if cwd is None:
        cwd = Path.cwd()

    hooks_dir = cwd / ".git" / "hooks"
    if not hooks_dir.exists():
        console.print("[red]Error:[/] Not a git repository.")
        return

    hook_content = '''#!/bin/bash
# Swoosh secrets scanner pre-commit hook

echo "Scanning for secrets..."

# Run swoosh secrets scan on staged files
swoosh secrets scan --staged --quiet

if [ $? -ne 0 ]; then
    echo ""
    echo "Commit blocked: potential secrets detected!"
    echo "Review the findings above and remove sensitive data."
    echo ""
    echo "To bypass this check (not recommended):"
    echo "  git commit --no-verify"
    echo ""
    exit 1
fi
'''

    pre_commit = hooks_dir / "pre-commit"

    if pre_commit.exists():
        content = pre_commit.read_text()
        if "Swoosh secrets scanner" in content:
            console.print("[yellow]Secrets scanner already installed.[/]")
            return

        # Append to existing hook
        new_content = content.rstrip() + "\n\n" + hook_content
        pre_commit.write_text(new_content)
    else:
        pre_commit.write_text(hook_content)

    # Make executable
    import stat
    current_mode = pre_commit.stat().st_mode
    pre_commit.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    console.print("[green]✓[/] Secrets scanner pre-commit hook installed.")
