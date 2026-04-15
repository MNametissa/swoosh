"""Release automation module for Swoosh."""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel
import questionary

from swoosh.modules.utils import (
    run_cmd, is_git_repo, get_version_from_file, set_version_in_file
)

console = Console()


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semver string to tuple."""
    match = re.match(r"v?(\d+)\.(\d+)\.(\d+)", version)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return 0, 0, 0


def bump_version(version: str, bump_type: str) -> str:
    """Bump version according to semver."""
    major, minor, patch = parse_version(version)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    else:  # patch
        return f"{major}.{minor}.{patch + 1}"


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
    skip_changelog: bool = False,
    skip_github: bool = False,
    push: bool = True,
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
    console.print()

    # Determine new version
    if version:
        new_version = version.lstrip("v")
    elif bump_type:
        base = current_version or latest_tag or "0.0.0"
        new_version = bump_version(base.lstrip("v"), bump_type)
    else:
        # Interactive
        base = current_version or latest_tag or "0.0.0"
        base_clean = base.lstrip("v")
        major, minor, patch = parse_version(base_clean)

        choices = [
            f"patch ({base_clean} → {major}.{minor}.{patch + 1})",
            f"minor ({base_clean} → {major}.{minor + 1}.0)",
            f"major ({base_clean} → {major + 1}.0.0)",
            "custom",
        ]

        selected = questionary.select(
            "Version bump:",
            choices=choices
        ).ask()

        if not selected:
            console.print("[yellow]Cancelled.[/]")
            return

        if "patch" in selected:
            bump_type = "patch"
        elif "minor" in selected:
            bump_type = "minor"
        elif "major" in selected:
            bump_type = "major"
        else:
            new_version = questionary.text(
                "New version:",
                validate=lambda x: re.match(r"^\d+\.\d+\.\d+$", x) is not None or "Invalid semver"
            ).ask()
            if not new_version:
                return

        if bump_type:
            new_version = bump_version(base_clean, bump_type)

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
