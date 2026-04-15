"""Secrets scanning and management for Swoosh."""

import re
import os
import math
import base64
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, is_git_repo, load_swoosh_config

console = Console()

# Secret patterns with confidence levels (high, medium, low)
SECRET_PATTERNS = [
    # AWS - High confidence (specific format)
    (r"AKIA[0-9A-Z]{16}", "AWS Access Key ID", "high"),
    (r"(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*['\"]?([a-zA-Z0-9/+=]{40})['\"]?", "AWS Secret", "high"),

    # GitHub - High confidence (specific prefixes)
    (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token", "high"),
    (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token", "high"),
    (r"ghu_[a-zA-Z0-9]{36}", "GitHub User Token", "high"),
    (r"ghs_[a-zA-Z0-9]{36}", "GitHub Server Token", "high"),
    (r"ghr_[a-zA-Z0-9]{36}", "GitHub Refresh Token", "high"),
    (r"github_pat_[a-zA-Z0-9_]{22,}", "GitHub Fine-grained Token", "high"),

    # GitLab
    (r"glpat-[a-zA-Z0-9\-_]{20,}", "GitLab Personal Access Token", "high"),

    # Slack
    (r"xox[baprs]-[0-9]{10,13}-[0-9]{10,13}[a-zA-Z0-9-]*", "Slack Token", "high"),

    # Stripe
    (r"sk_live_[a-zA-Z0-9]{24,}", "Stripe Secret Key", "high"),
    (r"rk_live_[a-zA-Z0-9]{24,}", "Stripe Restricted Key", "high"),

    # Twilio
    (r"SK[a-f0-9]{32}", "Twilio API Key", "high"),

    # SendGrid
    (r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}", "SendGrid API Key", "high"),

    # Private Keys - High confidence
    (r"-----BEGIN (RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----", "Private Key", "high"),
    (r"-----BEGIN ENCRYPTED PRIVATE KEY-----", "Encrypted Private Key", "high"),

    # Database connection strings - High confidence
    (r"(?i)postgres://[^\s'\"]+:[^\s'\"]+@[^\s'\"]+", "PostgreSQL Connection String", "high"),
    (r"(?i)mysql://[^\s'\"]+:[^\s'\"]+@[^\s'\"]+", "MySQL Connection String", "high"),
    (r"(?i)mongodb(\+srv)?://[^\s'\"]+:[^\s'\"]+@[^\s'\"]+", "MongoDB Connection String", "high"),
    (r"(?i)redis://[^\s'\"]+:[^\s'\"]+@[^\s'\"]+", "Redis Connection String", "high"),

    # JWT - Medium confidence (could be example)
    (r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}", "JWT Token", "medium"),

    # Generic API keys - Medium confidence
    (r"(?i)(api[_-]?key|apikey)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]", "API Key", "medium"),
    (r"(?i)(secret[_-]?key|secretkey)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]", "Secret Key", "medium"),
    (r"(?i)(access[_-]?token)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]", "Access Token", "medium"),

    # Password in config - Medium confidence
    (r"(?i)(password|passwd|pwd)\s*[=:]\s*['\"]([^\s'\"]{8,})['\"]", "Password", "medium"),

    # Bearer token - Low confidence (often in docs)
    (r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}", "Bearer Token", "low"),

    # Generic token assignment - Low confidence
    (r"(?i)(token|auth[_-]?token)\s*[=:]\s*['\"]([a-zA-Z0-9_\-]{20,})['\"]", "Generic Token", "low"),
]

# Files to skip
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".webm",
    ".zip", ".tar", ".gz", ".rar", ".7z", ".bz2",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".so", ".dll", ".exe", ".o", ".a",
    ".lock", ".sum", ".map",
    ".min.js", ".min.css", ".bundle.js",
}

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "vendor", "dist", "build", ".next", ".nuxt", ".output",
    "target", "coverage", ".pytest_cache", ".tox", ".nox",
    ".idea", ".vscode", ".vs",
    "public", "static", "assets",  # Usually contain built files
}

# Files that commonly contain example/template secrets
SKIP_FILES = {
    ".env.example", ".env.sample", ".env.template",
    "example.env", "sample.env",
    "docker-compose.example.yml", "docker-compose.sample.yml",
}

# Common false positive patterns
FALSE_POSITIVE_INDICATORS = [
    "example", "sample", "test", "dummy", "placeholder", "fake",
    "your_", "your-", "xxx", "changeme", "replace", "insert",
    "<your", "${", "{{", "}}", "%s", "TODO", "FIXME",
    "aaaaa", "bbbbb", "12345", "abcdef",
    "localhost", "127.0.0.1", "0.0.0.0",
]


def calculate_entropy(s: str) -> float:
    """Calculate Shannon entropy of a string."""
    if not s:
        return 0

    # Count character frequencies
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1

    length = len(s)
    entropy = 0

    for count in freq.values():
        p = count / length
        entropy -= p * math.log2(p)

    return entropy


def is_high_entropy(s: str, threshold: float = 3.5) -> bool:
    """Check if string has high entropy (likely random/secret)."""
    # Remove common prefixes/suffixes
    s = re.sub(r'^(sk_|pk_|api_|key_|token_|secret_)', '', s, flags=re.IGNORECASE)

    if len(s) < 16:
        return False

    return calculate_entropy(s) >= threshold


def is_likely_false_positive(text: str, line: str, file_path: str) -> bool:
    """Determine if a match is likely a false positive."""
    text_lower = text.lower()
    line_lower = line.lower()
    file_lower = str(file_path).lower()

    # Check for false positive indicators
    for indicator in FALSE_POSITIVE_INDICATORS:
        if indicator in text_lower or indicator in line_lower:
            return True

    # Skip if in documentation/readme
    if any(x in file_lower for x in ["readme", "doc", "example", "sample", "test", "mock", "fixture"]):
        return True

    # Skip if line is commented out
    stripped = line.strip()
    if stripped.startswith(("#", "//", "*", "/*", "<!--", ";", "'", "\"")):
        # But not if it's a shell script shebang
        if not stripped.startswith("#!"):
            return True

    # Skip environment variable references (not actual values)
    if re.search(r'\$\{?\w+\}?', text) or re.search(r'%\w+%', text):
        return True

    # Skip URL-like patterns without credentials
    if "://" in text and "@" not in text:
        return True

    return False


def load_ignore_patterns(cwd: Optional[Path] = None) -> list[str]:
    """Load ignore patterns from .swooshignore or swoosh.yaml."""
    if cwd is None:
        cwd = Path.cwd()

    patterns = []

    # Check .swooshignore
    ignore_file = cwd / ".swooshignore"
    if ignore_file.exists():
        for line in ignore_file.read_text().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)

    # Check swoosh.yaml
    config = load_swoosh_config(cwd)
    if "secrets" in config and "ignore" in config["secrets"]:
        patterns.extend(config["secrets"]["ignore"])

    return patterns


def should_scan_file(path: Path, ignore_patterns: list[str] = None) -> bool:
    """Check if file should be scanned."""
    if path.suffix.lower() in SKIP_EXTENSIONS:
        return False

    if path.name in SKIP_FILES:
        return False

    # Check ignore patterns
    if ignore_patterns:
        rel_path = str(path)
        for pattern in ignore_patterns:
            if re.search(pattern, rel_path):
                return False

    # Skip large files
    try:
        if path.stat().st_size > 500_000:  # 500KB
            return False
    except:
        return False

    # Skip binary files
    try:
        with open(path, 'rb') as f:
            chunk = f.read(1024)
            if b'\x00' in chunk:  # Contains null bytes = likely binary
                return False
    except:
        return False

    return True


def scan_file(file_path: Path, min_confidence: str = "medium") -> list[dict]:
    """Scan a single file for secrets."""
    findings = []

    confidence_levels = {"high": 3, "medium": 2, "low": 1}
    min_level = confidence_levels.get(min_confidence, 2)

    try:
        content = file_path.read_text(errors="ignore")
    except Exception:
        return findings

    lines = content.split("\n")

    for line_num, line in enumerate(lines, 1):
        for pattern, secret_type, confidence in SECRET_PATTERNS:
            # Skip if below minimum confidence
            if confidence_levels.get(confidence, 1) < min_level:
                continue

            matches = re.finditer(pattern, line)
            for match in matches:
                matched_text = match.group(0)

                # Skip false positives
                if is_likely_false_positive(matched_text, line, str(file_path)):
                    continue

                # For medium/low confidence, also check entropy
                if confidence in ("medium", "low"):
                    # Extract the actual secret value (usually in a capture group)
                    secret_value = match.group(2) if match.lastindex and match.lastindex >= 2 else matched_text
                    if not is_high_entropy(secret_value, threshold=3.0 if confidence == "low" else 2.5):
                        continue

                findings.append({
                    "file": str(file_path),
                    "line": line_num,
                    "type": secret_type,
                    "confidence": confidence,
                    "match": matched_text[:60] + "..." if len(matched_text) > 60 else matched_text,
                })

    return findings


def scan_directory(
    directory: Optional[Path] = None,
    staged_only: bool = False,
    min_confidence: str = "medium",
) -> list[dict]:
    """Scan directory for secrets."""
    if directory is None:
        directory = Path.cwd()

    ignore_patterns = load_ignore_patterns(directory)
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
                if should_scan_file(file_path, ignore_patterns):
                    files.append(file_path)

    for file_path in files:
        if file_path.exists():
            file_findings = scan_file(file_path, min_confidence)
            findings.extend(file_findings)

    return findings


def scan(
    directory: Optional[Path] = None,
    staged_only: bool = False,
    quiet: bool = False,
    min_confidence: str = "medium",
):
    """Scan for secrets and display results."""
    if directory is None:
        directory = Path.cwd()

    if not quiet:
        console.print()
        console.print(f"Scanning [cyan]{directory}[/] for secrets...")
        console.print(f"[dim]Minimum confidence: {min_confidence}[/]")
        console.print()

    findings = scan_directory(directory, staged_only=staged_only, min_confidence=min_confidence)

    if not findings:
        if not quiet:
            console.print("[green]✓[/] No secrets found.")
        return []

    # Sort by confidence (high first)
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda x: confidence_order.get(x["confidence"], 99))

    console.print(f"[yellow]⚠[/] Found [red]{len(findings)}[/] potential secret(s):\n")

    # Group by file
    by_file = {}
    for f in findings:
        file = f["file"]
        if file not in by_file:
            by_file[file] = []
        by_file[file].append(f)

    for file, file_findings in by_file.items():
        try:
            rel_path = Path(file).relative_to(directory)
        except ValueError:
            rel_path = file
        console.print(f"[cyan]{rel_path}[/]")
        for f in file_findings:
            conf_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(f["confidence"], "white")
            console.print(f"  [dim]:{f['line']}[/] [{conf_color}]{f['confidence']}[/{conf_color}] [{f['type']}] {f['match']}")
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


def encrypt_env_file(
    env_file: Optional[str] = None,
    output_file: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Encrypt .env file using age."""
    if cwd is None:
        cwd = Path.cwd()

    env_path = cwd / (env_file or ".env")

    if not env_path.exists():
        console.print(f"[red]Error:[/] {env_path} not found")
        return

    output_path = cwd / (output_file or ".env.enc")

    # Check if age is installed
    ok, _ = run_cmd(["which", "age"])
    if not ok:
        console.print("[red]Error:[/] 'age' not installed")
        console.print("Install: https://github.com/FiloSottile/age")
        console.print("  brew install age")
        console.print("  apt install age")
        return

    # Generate or use existing key
    key_file = cwd / ".age-key.txt"

    if not key_file.exists():
        console.print("[dim]Generating new age key...[/]")
        ok, output = run_cmd(["age-keygen", "-o", str(key_file)], cwd=cwd)
        if not ok:
            console.print(f"[red]Error:[/] Failed to generate key: {output}")
            return
        console.print(f"[green]✓[/] Key saved to {key_file}")
        console.print("[yellow]Warning:[/] Add .age-key.txt to .gitignore!")

    # Get public key from key file
    key_content = key_file.read_text()
    pub_key_match = re.search(r"public key: (age1[a-z0-9]+)", key_content)
    if not pub_key_match:
        console.print("[red]Error:[/] Could not extract public key")
        return

    pub_key = pub_key_match.group(1)

    # Encrypt
    ok, output = run_cmd([
        "age", "-r", pub_key, "-o", str(output_path), str(env_path)
    ], cwd=cwd)

    if ok:
        console.print(f"[green]✓[/] Encrypted to {output_path}")
        console.print(f"[dim]Decrypt with: age -d -i .age-key.txt {output_path}[/]")
    else:
        console.print(f"[red]Error:[/] {output}")


def decrypt_env_file(
    enc_file: Optional[str] = None,
    output_file: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Decrypt .env.enc file using age."""
    if cwd is None:
        cwd = Path.cwd()

    enc_path = cwd / (enc_file or ".env.enc")
    key_file = cwd / ".age-key.txt"

    if not enc_path.exists():
        console.print(f"[red]Error:[/] {enc_path} not found")
        return

    if not key_file.exists():
        console.print(f"[red]Error:[/] {key_file} not found")
        return

    output_path = cwd / (output_file or ".env")

    ok, output = run_cmd([
        "age", "-d", "-i", str(key_file), "-o", str(output_path), str(enc_path)
    ], cwd=cwd)

    if ok:
        console.print(f"[green]✓[/] Decrypted to {output_path}")
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

# Run swoosh secrets scan on staged files (high and medium confidence only)
swoosh secrets scan --staged --quiet

if [ $? -ne 0 ]; then
    echo ""
    echo "Commit blocked: potential secrets detected!"
    echo "Review the findings above and remove sensitive data."
    echo ""
    echo "If these are false positives, add patterns to .swooshignore"
    echo "or swoosh.yaml under secrets.ignore"
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
    console.print()
    console.print("[dim]To configure ignore patterns, create .swooshignore or add to swoosh.yaml:[/]")
    console.print("""
[dim]# .swooshignore
tests/.*
fixtures/.*

# or in swoosh.yaml
secrets:
  ignore:
    - "tests/.*"
    - "fixtures/.*"[/]
""")
