"""Multi-repo sync module for Swoosh."""

import os
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, is_git_repo, get_current_branch, get_remotes

console = Console()


def get_repo_status(repo_path: Path) -> dict:
    """Get status of a git repository."""
    if not is_git_repo(repo_path):
        return {"status": "not_git", "path": repo_path}

    result = {
        "path": repo_path,
        "name": repo_path.name,
        "status": "ok",
        "branch": None,
        "ahead": 0,
        "behind": 0,
        "dirty": False,
        "conflicts": False,
    }

    # Get branch
    result["branch"] = get_current_branch(repo_path)

    # Check for uncommitted changes
    ok, output = run_cmd(["git", "status", "--porcelain"], cwd=repo_path)
    if ok and output:
        result["dirty"] = True
        if any(line.startswith("UU") for line in output.split("\n")):
            result["conflicts"] = True

    # Check ahead/behind
    ok, output = run_cmd(
        ["git", "rev-list", "--left-right", "--count", "@{upstream}...HEAD"],
        cwd=repo_path
    )
    if ok and output:
        parts = output.split()
        if len(parts) == 2:
            result["behind"] = int(parts[0])
            result["ahead"] = int(parts[1])

    return result


def find_repos(directory: Path, max_depth: int = 2) -> list[Path]:
    """Find git repositories in a directory."""
    repos = []

    if is_git_repo(directory):
        repos.append(directory)
        return repos

    for root, dirs, _ in os.walk(directory):
        # Calculate depth
        depth = len(Path(root).relative_to(directory).parts)
        if depth > max_depth:
            dirs.clear()
            continue

        # Skip hidden directories
        dirs[:] = [d for d in dirs if not d.startswith(".")]

        if ".git" in dirs:
            repos.append(Path(root))
            dirs.clear()  # Don't descend further

    return sorted(repos)


def sync_repo(repo_path: Path, push: bool = True) -> dict:
    """Sync a single repository (pull + push)."""
    result = {
        "path": repo_path,
        "name": repo_path.name,
        "status": "ok",
        "action": None,
        "error": None,
    }

    status = get_repo_status(repo_path)

    if status.get("conflicts"):
        result["status"] = "conflict"
        result["error"] = "Has merge conflicts"
        return result

    if status.get("dirty"):
        result["status"] = "dirty"
        result["action"] = "skipped (uncommitted changes)"
        return result

    # Fetch
    ok, output = run_cmd(["git", "fetch", "--all"], cwd=repo_path, timeout=60)
    if not ok:
        result["status"] = "error"
        result["error"] = "Fetch failed"
        return result

    # Pull if behind
    if status.get("behind", 0) > 0:
        ok, output = run_cmd(["git", "pull", "--rebase"], cwd=repo_path, timeout=120)
        if ok:
            result["action"] = f"pulled {status['behind']} commit(s)"
        else:
            result["status"] = "error"
            result["error"] = "Pull failed"
            return result

    # Push if ahead
    if push and status.get("ahead", 0) > 0:
        ok, output = run_cmd(["git", "push"], cwd=repo_path, timeout=60)
        if ok:
            if result["action"]:
                result["action"] += f", pushed {status['ahead']} commit(s)"
            else:
                result["action"] = f"pushed {status['ahead']} commit(s)"
        else:
            result["status"] = "warning"
            result["error"] = "Push failed"

    if not result["action"]:
        result["action"] = "up to date"

    return result


def sync_all(
    directory: Optional[Path] = None,
    push: bool = True,
    max_depth: int = 2,
):
    """Sync all repositories in a directory."""
    if directory is None:
        directory = Path.cwd()

    console.print()
    console.print(f"Scanning [cyan]{directory}[/] for repositories...")

    repos = find_repos(directory, max_depth)

    if not repos:
        console.print("[yellow]No git repositories found.[/]")
        return

    console.print(f"Found [cyan]{len(repos)}[/] repositories.\n")

    results = []

    for repo in repos:
        console.print(f"[dim]Syncing {repo.name}...[/]", end=" ")
        result = sync_repo(repo, push=push)
        results.append(result)

        if result["status"] == "ok":
            console.print(f"[green]✓[/] {result['action']}")
        elif result["status"] == "dirty":
            console.print(f"[yellow]○[/] {result['action']}")
        elif result["status"] == "conflict":
            console.print(f"[red]✗[/] {result['error']}")
        elif result["status"] == "warning":
            console.print(f"[yellow]![/] {result['action']} ({result['error']})")
        else:
            console.print(f"[red]✗[/] {result['error']}")

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    dirty = sum(1 for r in results if r["status"] == "dirty")
    errors = sum(1 for r in results if r["status"] in ("error", "conflict"))

    console.print()
    console.print(Panel(
        f"[green]Synced:[/] {ok}  [yellow]Skipped:[/] {dirty}  [red]Errors:[/] {errors}",
        expand=False
    ))


def status_all(
    directory: Optional[Path] = None,
    max_depth: int = 2,
):
    """Show status of all repositories."""
    if directory is None:
        directory = Path.cwd()

    repos = find_repos(directory, max_depth)

    if not repos:
        console.print("[yellow]No git repositories found.[/]")
        return

    console.print()

    table = Table(title=f"Repositories in {directory}", show_header=True)
    table.add_column("Repository", style="cyan")
    table.add_column("Branch", style="blue")
    table.add_column("Status", style="white")
    table.add_column("Ahead", style="green", justify="right")
    table.add_column("Behind", style="yellow", justify="right")

    for repo in repos:
        status = get_repo_status(repo)

        if status.get("conflicts"):
            status_str = "[red]conflicts[/]"
        elif status.get("dirty"):
            status_str = "[yellow]dirty[/]"
        else:
            status_str = "[green]clean[/]"

        table.add_row(
            status["name"],
            status.get("branch") or "-",
            status_str,
            str(status.get("ahead", 0)),
            str(status.get("behind", 0)),
        )

    console.print(table)
    console.print()


def sync_upstream(cwd: Optional[Path] = None):
    """Sync fork with upstream repository."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    remotes = get_remotes(cwd)
    remote_names = [r["name"] for r in remotes]

    if "upstream" not in remote_names:
        console.print("[yellow]No 'upstream' remote found.[/]")
        console.print("Add it with: [cyan]git remote add upstream <url>[/]")
        return

    branch = get_current_branch(cwd)

    console.print(f"Syncing [cyan]{branch}[/] with upstream...")

    # Fetch upstream
    ok, _ = run_cmd(["git", "fetch", "upstream"], cwd=cwd)
    if not ok:
        console.print("[red]✗[/] Failed to fetch upstream")
        return

    # Merge upstream
    ok, output = run_cmd(["git", "merge", f"upstream/{branch}"], cwd=cwd)
    if ok:
        console.print(f"[green]✓[/] Merged upstream/{branch}")

        # Push to origin
        ok, _ = run_cmd(["git", "push", "origin", branch], cwd=cwd)
        if ok:
            console.print(f"[green]✓[/] Pushed to origin/{branch}")
    else:
        console.print(f"[red]✗[/] Merge failed: {output[:100]}")
