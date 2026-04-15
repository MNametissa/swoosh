"""Utility functions for Swoosh."""

import subprocess
import json
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def run_cmd(
    cmd: list[str],
    cwd: Optional[Path] = None,
    capture: bool = True,
    timeout: int = 60
) -> tuple[bool, str]:
    """Run a command and return (success, output)."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            timeout=timeout
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output.strip()
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def get_current_branch(cwd: Optional[Path] = None) -> Optional[str]:
    """Get current git branch name."""
    ok, branch = run_cmd(["git", "branch", "--show-current"], cwd=cwd)
    return branch if ok else None


def get_remotes(cwd: Optional[Path] = None) -> list[dict]:
    """Get all configured remotes."""
    ok, output = run_cmd(["git", "remote", "-v"], cwd=cwd)
    if not ok:
        return []

    remotes = {}
    for line in output.split("\n"):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 2:
            name = parts[0]
            url = parts[1]
            if name not in remotes:
                remotes[name] = {"name": name, "url": url}

    return list(remotes.values())


def get_github_user() -> Optional[str]:
    """Get authenticated GitHub username."""
    ok, output = run_cmd(["gh", "api", "user", "--jq", ".login"])
    return output.strip() if ok else None


def is_git_repo(path: Optional[Path] = None) -> bool:
    """Check if path is a git repository."""
    if path is None:
        path = Path.cwd()
    return (path / ".git").exists()


def get_repo_root(path: Optional[Path] = None) -> Optional[Path]:
    """Get the root of the git repository."""
    ok, output = run_cmd(["git", "rev-parse", "--show-toplevel"], cwd=path)
    return Path(output) if ok else None


def load_swoosh_config(path: Optional[Path] = None) -> dict:
    """Load swoosh.yaml configuration."""
    import yaml

    if path is None:
        path = Path.cwd()

    config_file = path / "swoosh.yaml"
    if not config_file.exists():
        config_file = path / "swoosh.yml"

    if config_file.exists():
        with open(config_file) as f:
            return yaml.safe_load(f) or {}

    return {}


def get_version_from_file(path: Path) -> Optional[str]:
    """Extract version from package.json, Cargo.toml, or pyproject.toml."""
    import toml

    # package.json
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json) as f:
                data = json.load(f)
                return data.get("version")
        except:
            pass

    # Cargo.toml
    cargo = path / "Cargo.toml"
    if cargo.exists():
        try:
            data = toml.load(cargo)
            return data.get("package", {}).get("version")
        except:
            pass

    # pyproject.toml
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            data = toml.load(pyproject)
            return data.get("project", {}).get("version")
        except:
            pass

    return None


def set_version_in_file(path: Path, version: str) -> bool:
    """Update version in package.json, Cargo.toml, or pyproject.toml."""
    import toml

    # package.json
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json) as f:
                data = json.load(f)
            data["version"] = version
            with open(pkg_json, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            return True
        except:
            pass

    # Cargo.toml
    cargo = path / "Cargo.toml"
    if cargo.exists():
        try:
            content = cargo.read_text()
            import re
            new_content = re.sub(
                r'^version\s*=\s*"[^"]*"',
                f'version = "{version}"',
                content,
                flags=re.MULTILINE
            )
            cargo.write_text(new_content)
            return True
        except:
            pass

    # pyproject.toml
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            import re
            new_content = re.sub(
                r'^version\s*=\s*"[^"]*"',
                f'version = "{version}"',
                content,
                flags=re.MULTILINE
            )
            pyproject.write_text(new_content)
            return True
        except:
            pass

    return False
