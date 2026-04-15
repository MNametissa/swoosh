"""Pull Request creation module for Swoosh."""

import re
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, is_git_repo, get_current_branch

console = Console()

# Map commit types to GitHub labels
TYPE_TO_LABEL = {
    "feat": "enhancement",
    "fix": "bug",
    "docs": "documentation",
    "perf": "performance",
    "test": "testing",
    "ci": "ci/cd",
    "build": "build",
    "refactor": "refactor",
    "style": "style",
    "chore": "chore",
}


def get_commits_for_pr(base_branch: str, cwd: Optional[Path] = None) -> list[dict]:
    """Get commits between base branch and HEAD."""
    ok, output = run_cmd(
        ["git", "log", f"{base_branch}..HEAD", "--pretty=format:%H|%s"],
        cwd=cwd
    )

    if not ok or not output:
        return []

    commits = []
    for line in output.split("\n"):
        if "|" in line:
            hash_val, message = line.split("|", 1)
            commits.append({
                "hash": hash_val[:8],
                "message": message,
            })

    return commits


def detect_labels_from_commits(commits: list[dict]) -> list[str]:
    """Detect appropriate labels from commit messages."""
    labels = set()

    for commit in commits:
        msg = commit["message"].lower()

        for prefix, label in TYPE_TO_LABEL.items():
            if msg.startswith(prefix):
                labels.add(label)
                break

        # Special cases
        if "breaking" in msg:
            labels.add("breaking-change")
        if "wip" in msg or "work in progress" in msg:
            labels.add("work-in-progress")

    return list(labels)


def generate_pr_body(commits: list[dict], branch: str) -> str:
    """Generate PR description from commits."""
    lines = ["## Summary", ""]

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
        for c in features:
            clean_msg = re.sub(r"^feat(\([^)]+\))?:\s*", "", c["message"])
            lines.append(f"- {clean_msg}")

    if fixes:
        for c in fixes:
            clean_msg = re.sub(r"^fix(\([^)]+\))?:\s*", "", c["message"])
            lines.append(f"- {clean_msg}")

    if other and not features and not fixes:
        for c in other[:5]:  # Limit to 5
            lines.append(f"- {c['message']}")

    lines.extend([
        "",
        "## Test Plan",
        "",
        "- [ ] Tests pass locally",
        "- [ ] Manual testing completed",
        "",
    ])

    return "\n".join(lines)


def create_pr(
    title: Optional[str] = None,
    body: Optional[str] = None,
    base: Optional[str] = None,
    draft: bool = False,
    labels: Optional[list[str]] = None,
    reviewers: Optional[list[str]] = None,
    cwd: Optional[Path] = None,
):
    """Create a pull request."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    console.print()

    # Get current branch
    branch = get_current_branch(cwd)
    if not branch:
        console.print("[red]Error:[/] Could not determine current branch.")
        return

    console.print(f"Branch: [cyan]{branch}[/]")

    # Determine base branch
    if not base:
        # Try to detect default branch
        ok, default = run_cmd(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
            cwd=cwd
        )
        base = default.strip() if ok and default else "main"

    console.print(f"Base: [cyan]{base}[/]")

    # Check if branch is pushed
    ok, _ = run_cmd(["git", "rev-parse", f"origin/{branch}"], cwd=cwd)
    if not ok:
        console.print("\n[yellow]Branch not pushed to origin.[/]")
        if questionary.confirm("Push now?", default=True).ask():
            ok, _ = run_cmd(["git", "push", "-u", "origin", branch], cwd=cwd)
            if ok:
                console.print("[green]✓[/] Pushed to origin")
            else:
                console.print("[red]✗[/] Push failed")
                return
        else:
            return

    # Get commits for context
    commits = get_commits_for_pr(base, cwd)
    console.print(f"Commits: [cyan]{len(commits)}[/]")
    console.print()

    # Generate title from branch or commits
    if not title:
        # Try to generate from branch name
        suggested = branch.replace("-", " ").replace("_", " ")
        suggested = re.sub(r"^(feat|fix|chore|docs)/", "", suggested)
        suggested = suggested.title()

        title = questionary.text(
            "PR Title:",
            default=suggested,
            validate=lambda x: len(x) > 0 or "Title required"
        ).ask()

        if not title:
            console.print("[yellow]Cancelled.[/]")
            return

    # Generate body
    if not body:
        auto_body = generate_pr_body(commits, branch)

        if questionary.confirm("Edit PR description?", default=False).ask():
            body = questionary.text(
                "Description:",
                default=auto_body,
                multiline=True
            ).ask()
        else:
            body = auto_body

    # Detect labels
    if labels is None:
        auto_labels = detect_labels_from_commits(commits)
        if auto_labels:
            console.print(f"Detected labels: [cyan]{', '.join(auto_labels)}[/]")
            if questionary.confirm("Apply these labels?", default=True).ask():
                labels = auto_labels

    # Draft?
    if not draft:
        draft = questionary.confirm("Create as draft?", default=False).ask()

    # Build command
    cmd = ["gh", "pr", "create", "--title", title, "--body", body, "--base", base]

    if draft:
        cmd.append("--draft")

    if labels:
        for label in labels:
            cmd.extend(["--label", label])

    if reviewers:
        for reviewer in reviewers:
            cmd.extend(["--reviewer", reviewer])

    # Preview
    console.print()
    console.print(Panel(
        f"[bold]Title:[/] {title}\n"
        f"[bold]Base:[/] {base} ← {branch}\n"
        f"[bold]Labels:[/] {', '.join(labels) if labels else 'None'}\n"
        f"[bold]Draft:[/] {'Yes' if draft else 'No'}",
        title="[blue]PR Preview[/]",
        expand=False
    ))
    console.print()

    if not questionary.confirm("Create PR?", default=True).ask():
        console.print("[yellow]Cancelled.[/]")
        return

    # Create PR
    ok, output = run_cmd(cmd, cwd=cwd)

    if ok:
        # Extract URL from output
        url_match = re.search(r"https://github\.com/[^\s]+", output)
        url = url_match.group(0) if url_match else output

        console.print(f"[green]✓[/] PR created: {url}")
    else:
        console.print(f"[red]✗[/] Failed: {output}")


def list_prs(cwd: Optional[Path] = None, state: str = "open"):
    """List pull requests."""
    if cwd is None:
        cwd = Path.cwd()

    ok, output = run_cmd([
        "gh", "pr", "list",
        "--state", state,
        "--json", "number,title,author,state,isDraft",
    ], cwd=cwd)

    if not ok:
        console.print(f"[red]Error:[/] {output}")
        return

    import json
    try:
        prs = json.loads(output)
    except:
        prs = []

    if not prs:
        console.print(f"[dim]No {state} pull requests.[/]")
        return

    console.print()
    for pr in prs:
        status = "[yellow]draft[/]" if pr.get("isDraft") else "[green]open[/]"
        console.print(
            f"[cyan]#{pr['number']}[/] {pr['title']} "
            f"[dim]by {pr['author']['login']}[/] {status}"
        )
    console.print()
