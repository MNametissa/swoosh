"""Release automation module for Swoosh."""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import questionary

from swoosh.modules.utils import (
    run_cmd, is_git_repo, get_version_from_file, set_version_in_file
)

console = Console()


def parse_version(version: str) -> tuple[int, int, int, str]:
    """Parse semver string to tuple (major, minor, patch, prerelease)."""
    # Match: 1.2.3, 1.2.3-alpha, 1.2.3-beta.1, 1.2.3-rc.2
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?", version)
    if match:
        prerelease = match.group(4) or ""
        return int(match.group(1)), int(match.group(2)), int(match.group(3)), prerelease
    return 0, 0, 0, ""


def bump_version(version: str, bump_type: str, prerelease: Optional[str] = None) -> str:
    """Bump version according to semver with pre-release support."""
    major, minor, patch, current_pre = parse_version(version)

    if bump_type == "major":
        base = f"{major + 1}.0.0"
    elif bump_type == "minor":
        base = f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        base = f"{major}.{minor}.{patch + 1}"
    elif bump_type == "prerelease":
        # Bump prerelease: alpha.1 -> alpha.2, or add -alpha.1
        if current_pre:
            # Try to bump the number in prerelease
            pre_match = re.match(r"([a-zA-Z]+)\.?(\d+)?", current_pre)
            if pre_match:
                pre_type = pre_match.group(1)
                pre_num = int(pre_match.group(2) or 0) + 1
                return f"{major}.{minor}.{patch}-{pre_type}.{pre_num}"
        # No current prerelease, add one
        pre_type = prerelease or "alpha"
        return f"{major}.{minor}.{patch}-{pre_type}.1"
    elif bump_type == "release":
        # Remove prerelease suffix
        return f"{major}.{minor}.{patch}"
    else:
        base = f"{major}.{minor}.{patch + 1}"

    # Add prerelease suffix if specified
    if prerelease:
        return f"{base}-{prerelease}.1"
    return base


def detect_breaking_changes(commits: list[dict]) -> bool:
    """Detect breaking changes from commit messages."""
    for commit in commits:
        msg = commit["message"].lower()
        # Conventional commits breaking change indicators
        if "!" in msg.split(":")[0] if ":" in msg else False:
            return True
        if "breaking change" in msg:
            return True
        if "breaking:" in msg:
            return True
    return False


def suggest_bump_type(commits: list[dict]) -> str:
    """Suggest version bump type based on commits."""
    has_breaking = detect_breaking_changes(commits)
    has_feat = any(c["message"].startswith("feat") for c in commits)
    has_fix = any(c["message"].startswith("fix") for c in commits)

    if has_breaking:
        return "major"
    elif has_feat:
        return "minor"
    elif has_fix:
        return "patch"
    return "patch"


def get_commits_since_tag(tag: str, cwd: Optional[Path] = None) -> list[dict]:
    """Get commits since a specific tag."""
    ok, output = run_cmd(
        ["git", "log", f"{tag}..HEAD", "--pretty=format:%H|%s|%an"],
        cwd=cwd
    )

    if not ok or not output:
        return []

    commits = []
    for line in output.split("\n"):
        if "|" in line:
            parts = line.split("|", 2)
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0][:8],
                    "message": parts[1],
                    "author": parts[2] if len(parts) > 2 else "Unknown"
                })

    return commits


def get_latest_tag(cwd: Optional[Path] = None) -> Optional[str]:
    """Get the latest version tag."""
    ok, output = run_cmd(
        ["git", "describe", "--tags", "--abbrev=0"],
        cwd=cwd
    )
    return output if ok else None


def generate_changelog(
    commits: list[dict],
    version: str,
    previous_version: Optional[str] = None
) -> str:
    """Generate changelog from commits."""
    date = datetime.now().strftime("%Y-%m-%d")

    lines = [f"## [{version}] - {date}", ""]

    # Group commits by type
    features = []
    fixes = []
    other = []

    for commit in commits:
        msg = commit["message"]
        if msg.startswith("feat"):
            features.append(commit)
        elif msg.startswith("fix"):
            fixes.append(commit)
        else:
            other.append(commit)

    if features:
        lines.append("### Features")
        for c in features:
            # Remove type prefix
            msg = re.sub(r"^feat(\([^)]+\))?:\s*", "", c["message"])
            lines.append(f"- {msg} ({c['hash']})")
        lines.append("")

    if fixes:
        lines.append("### Bug Fixes")
        for c in fixes:
            msg = re.sub(r"^fix(\([^)]+\))?:\s*", "", c["message"])
            lines.append(f"- {msg} ({c['hash']})")
        lines.append("")

    if other:
        lines.append("### Other Changes")
        for c in other:
            lines.append(f"- {c['message']} ({c['hash']})")
        lines.append("")

    return "\n".join(lines)


def update_changelog_file(
    changelog_content: str,
    cwd: Optional[Path] = None
):
    """Prepend new release to CHANGELOG.md."""
    if cwd is None:
        cwd = Path.cwd()

    changelog_file = cwd / "CHANGELOG.md"

    if changelog_file.exists():
        existing = changelog_file.read_text()
        # Insert after header
        if "# Changelog" in existing:
            parts = existing.split("# Changelog", 1)
            new_content = f"# Changelog\n\n{changelog_content}\n{parts[1].lstrip()}"
        else:
            new_content = f"# Changelog\n\n{changelog_content}\n{existing}"
    else:
        new_content = f"# Changelog\n\n{changelog_content}"

    changelog_file.write_text(new_content)


def create_release(
    bump_type: Optional[str] = None,
    version: Optional[str] = None,
    prerelease: Optional[str] = None,
    skip_changelog: bool = False,
    skip_github: bool = False,
    push: bool = True,
    auto: bool = False,
    cwd: Optional[Path] = None,
):
    """Create a new release."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    console.print()

    # Get current version
    current_version = get_version_from_file(cwd)
    latest_tag = get_latest_tag(cwd)

    if current_version:
        console.print(f"Current version: [cyan]{current_version}[/]")
    if latest_tag:
        console.print(f"Latest tag: [cyan]{latest_tag}[/]")

    # Get commits early for auto-detection
    commits = []
    if latest_tag:
        commits = get_commits_since_tag(latest_tag, cwd)

    # Auto-detect bump type from commits
    if auto and not bump_type and not version:
        bump_type = suggest_bump_type(commits)
        has_breaking = detect_breaking_changes(commits)
        console.print(f"\n[dim]Auto-detected:[/] {bump_type} bump" +
                     (" [red](breaking changes)[/]" if has_breaking else ""))

    console.print()

    # Determine new version
    if version:
        new_version = version.lstrip("v")
    elif bump_type:
        base = current_version or latest_tag or "0.0.0"
        new_version = bump_version(base.lstrip("v"), bump_type, prerelease)
    else:
        # Interactive
        base = current_version or latest_tag or "0.0.0"
        base_clean = base.lstrip("v")
        major, minor, patch, current_pre = parse_version(base_clean)

        # Show suggested bump
        suggested = suggest_bump_type(commits) if commits else "patch"

        choices = [
            f"patch ({base_clean} → {major}.{minor}.{patch + 1})" +
                (" [recommended]" if suggested == "patch" else ""),
            f"minor ({base_clean} → {major}.{minor + 1}.0)" +
                (" [recommended]" if suggested == "minor" else ""),
            f"major ({base_clean} → {major + 1}.0.0)" +
                (" [recommended]" if suggested == "major" else ""),
            f"alpha ({base_clean} → {major}.{minor}.{patch + 1}-alpha.1)",
            f"beta ({base_clean} → {major}.{minor}.{patch + 1}-beta.1)",
            f"rc ({base_clean} → {major}.{minor}.{patch + 1}-rc.1)",
            "custom",
        ]

        # If currently in prerelease, add option to release
        if current_pre:
            choices.insert(0, f"release ({base_clean} → {major}.{minor}.{patch})")

        selected = questionary.select(
            "Version bump:",
            choices=choices
        ).ask()

        if not selected:
            console.print("[yellow]Cancelled.[/]")
            return

        if selected.startswith("release"):
            bump_type = "release"
        elif "patch" in selected:
            bump_type = "patch"
        elif "minor" in selected:
            bump_type = "minor"
        elif "major" in selected:
            bump_type = "major"
        elif "alpha" in selected:
            bump_type = "patch"
            prerelease = "alpha"
        elif "beta" in selected:
            bump_type = "patch"
            prerelease = "beta"
        elif "rc" in selected:
            bump_type = "patch"
            prerelease = "rc"
        else:
            new_version = questionary.text(
                "New version:",
                validate=lambda x: re.match(r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$", x) is not None or "Invalid semver"
            ).ask()
            if not new_version:
                return

        if bump_type and not version:
            new_version = bump_version(base_clean, bump_type, prerelease)

    tag_name = f"v{new_version}"

    console.print(f"\nNew version: [green]{new_version}[/]")
    console.print(f"Tag: [green]{tag_name}[/]")

    # Get commits for changelog
    commits = []
    if latest_tag and not skip_changelog:
        commits = get_commits_since_tag(latest_tag, cwd)
        console.print(f"Commits since {latest_tag}: {len(commits)}")

    console.print()

    if not questionary.confirm("Proceed with release?", default=True).ask():
        console.print("[yellow]Cancelled.[/]")
        return

    # 1. Update version in files
    console.print("\n[dim]Updating version...[/]")
    if set_version_in_file(cwd, new_version):
        console.print(f"[green]✓[/] Updated version to {new_version}")
    else:
        console.print("[yellow]![/] No version file found to update")

    # 2. Generate changelog
    if not skip_changelog and commits:
        console.print("[dim]Generating changelog...[/]")
        changelog = generate_changelog(commits, new_version, latest_tag)
        update_changelog_file(changelog, cwd)
        console.print("[green]✓[/] Updated CHANGELOG.md")

    # 3. Commit changes
    console.print("[dim]Creating release commit...[/]")
    run_cmd(["git", "add", "-A"], cwd=cwd)
    ok, _ = run_cmd(["git", "commit", "-m", f"chore(release): {new_version}"], cwd=cwd)
    if ok:
        console.print(f"[green]✓[/] Created release commit")

    # 4. Create tag
    console.print("[dim]Creating tag...[/]")
    ok, output = run_cmd(["git", "tag", "-a", tag_name, "-m", f"Release {new_version}"], cwd=cwd)
    if ok:
        console.print(f"[green]✓[/] Created tag {tag_name}")
    else:
        console.print(f"[red]✗[/] Tag failed: {output}")
        return

    # 5. Push
    if push:
        console.print("[dim]Pushing...[/]")
        run_cmd(["git", "push"], cwd=cwd)
        run_cmd(["git", "push", "--tags"], cwd=cwd)
        console.print("[green]✓[/] Pushed to origin")

    # 6. Create GitHub release
    if not skip_github:
        console.print("[dim]Creating GitHub release...[/]")

        release_notes = ""
        if commits:
            release_notes = generate_changelog(commits, new_version, latest_tag)

        ok, output = run_cmd([
            "gh", "release", "create", tag_name,
            "--title", f"Release {new_version}",
            "--notes", release_notes or f"Release {new_version}"
        ], cwd=cwd)

        if ok:
            console.print(f"[green]✓[/] Created GitHub release")
        else:
            console.print(f"[yellow]![/] GitHub release failed: {output[:80]}")

    # Summary
    console.print()
    console.print(Panel(
        f"[green bold]Released {new_version}[/]\n\n"
        f"Tag: {tag_name}\n"
        f"Commits: {len(commits)}",
        expand=False
    ))
