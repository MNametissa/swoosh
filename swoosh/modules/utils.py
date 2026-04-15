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
    """Extract version from various project files."""
    import toml
    import re

    # package.json (Node.js)
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json) as f:
                data = json.load(f)
                return data.get("version")
        except:
            pass

    # Cargo.toml (Rust)
    cargo = path / "Cargo.toml"
    if cargo.exists():
        try:
            data = toml.load(cargo)
            return data.get("package", {}).get("version")
        except:
            pass

    # pyproject.toml (Python)
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            data = toml.load(pyproject)
            return data.get("project", {}).get("version")
        except:
            pass

    # setup.py (Python legacy)
    setup_py = path / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text()
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
        except:
            pass

    # composer.json (PHP)
    composer = path / "composer.json"
    if composer.exists():
        try:
            with open(composer) as f:
                data = json.load(f)
                return data.get("version")
        except:
            pass

    # pom.xml (Java/Maven)
    pom = path / "pom.xml"
    if pom.exists():
        try:
            content = pom.read_text()
            # Look for <version> in <project> (not in dependencies)
            match = re.search(r'<project[^>]*>.*?<version>([^<]+)</version>', content, re.DOTALL)
            if match:
                return match.group(1)
        except:
            pass

    # build.gradle / build.gradle.kts (Gradle)
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle = path / gradle_file
        if gradle.exists():
            try:
                content = gradle.read_text()
                match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
            except:
                pass

    # VERSION or version.txt (generic)
    for version_file in ["VERSION", "version.txt", "VERSION.txt"]:
        vf = path / version_file
        if vf.exists():
            try:
                return vf.read_text().strip()
            except:
                pass

    # go.mod (Go) - extract module version from git tags is complex, skip
    # pubspec.yaml (Dart/Flutter)
    pubspec = path / "pubspec.yaml"
    if pubspec.exists():
        try:
            import yaml
            with open(pubspec) as f:
                data = yaml.safe_load(f)
                return data.get("version")
        except:
            pass

    return None


def set_version_in_file(path: Path, version: str) -> bool:
    """Update version in various project files."""
    import toml
    import re

    updated = False

    # package.json (Node.js)
    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            with open(pkg_json) as f:
                data = json.load(f)
            data["version"] = version
            with open(pkg_json, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
            updated = True
        except:
            pass

    # Cargo.toml (Rust)
    cargo = path / "Cargo.toml"
    if cargo.exists():
        try:
            content = cargo.read_text()
            new_content = re.sub(
                r'^version\s*=\s*"[^"]*"',
                f'version = "{version}"',
                content,
                flags=re.MULTILINE
            )
            cargo.write_text(new_content)
            updated = True
        except:
            pass

    # pyproject.toml (Python)
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            new_content = re.sub(
                r'^version\s*=\s*"[^"]*"',
                f'version = "{version}"',
                content,
                flags=re.MULTILINE
            )
            pyproject.write_text(new_content)
            updated = True
        except:
            pass

    # setup.py (Python legacy)
    setup_py = path / "setup.py"
    if setup_py.exists():
        try:
            content = setup_py.read_text()
            new_content = re.sub(
                r'version\s*=\s*["\'][^"\']+["\']',
                f'version="{version}"',
                content
            )
            setup_py.write_text(new_content)
            updated = True
        except:
            pass

    # composer.json (PHP)
    composer = path / "composer.json"
    if composer.exists():
        try:
            with open(composer) as f:
                data = json.load(f)
            data["version"] = version
            with open(composer, "w") as f:
                json.dump(data, f, indent=4)
                f.write("\n")
            updated = True
        except:
            pass

    # pom.xml (Java/Maven) - update first <version> under <project>
    pom = path / "pom.xml"
    if pom.exists():
        try:
            content = pom.read_text()
            # Replace first version tag (project version, not dependency)
            new_content = re.sub(
                r'(<project[^>]*>.*?<version>)[^<]+(</version>)',
                rf'\g<1>{version}\g<2>',
                content,
                count=1,
                flags=re.DOTALL
            )
            pom.write_text(new_content)
            updated = True
        except:
            pass

    # build.gradle / build.gradle.kts (Gradle)
    for gradle_file in ["build.gradle", "build.gradle.kts"]:
        gradle = path / gradle_file
        if gradle.exists():
            try:
                content = gradle.read_text()
                new_content = re.sub(
                    r'version\s*=\s*["\'][^"\']+["\']',
                    f'version = "{version}"',
                    content
                )
                gradle.write_text(new_content)
                updated = True
            except:
                pass

    # VERSION or version.txt (generic)
    for version_file in ["VERSION", "version.txt", "VERSION.txt"]:
        vf = path / version_file
        if vf.exists():
            try:
                vf.write_text(version + "\n")
                updated = True
            except:
                pass

    # pubspec.yaml (Dart/Flutter)
    pubspec = path / "pubspec.yaml"
    if pubspec.exists():
        try:
            content = pubspec.read_text()
            new_content = re.sub(
                r'^version:\s*.+$',
                f'version: {version}',
                content,
                flags=re.MULTILINE
            )
            pubspec.write_text(new_content)
            updated = True
        except:
            pass

    return updated
