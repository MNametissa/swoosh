"""Clone repositories from GitHub."""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd
from swoosh.modules import hooks

console = Console()


def get_repos(limit: int = 50, owner: Optional[str] = None) -> list[dict]:
    """Fetch user's repositories from GitHub."""
    cmd = ["gh", "repo", "list"]

    if owner:
        cmd.append(owner)

    cmd.extend(["--limit", str(limit), "--json", "name,description,isPrivate,pushedAt,url"])

    ok, output = run_cmd(cmd)
    if not ok:
        return []

    try:
        return json.loads(output)
    except:
        return []


def list_repos(owner: Optional[str] = None, limit: int = 20):
    """List user's repositories."""
    console.print()

    with console.status("Fetching repositories..."):
        repos = get_repos(limit=limit, owner=owner)

    if not repos:
        console.print("[yellow]No repositories found or not authenticated.[/]")
        console.print("Run: gh auth login")
        return

    table = Table(title=f"Repositories{f' ({owner})' if owner else ''}", show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white", max_width=40)
    table.add_column("Private", style="yellow", width=7)

    for i, repo in enumerate(repos, 1):
        desc = repo.get("description") or ""
        if len(desc) > 40:
            desc = desc[:37] + "..."
        table.add_row(
            str(i),
            repo["name"],
            desc,
            "private" if repo.get("isPrivate") else ""
        )

    console.print(table)
    console.print()


def clone_repo(
    name: Optional[str] = None,
    owner: Optional[str] = None,
    dest: Optional[Path] = None,
    setup_hook: bool = True,
):
    """Clone a repository."""
    console.print()

    # If no name provided, show interactive picker
    if not name:
        with console.status("Fetching repositories..."):
            repos = get_repos(limit=30, owner=owner)

        if not repos:
            console.print("[red]No repositories found.[/]")
            return

        choices = [f"{r['name']}: {r.get('description', '')[:50]}" for r in repos]

        selected = questionary.select(
            "Select repository to clone:",
            choices=choices
        ).ask()

        if not selected:
            console.print("[yellow]Cancelled.[/]")
            return

        name = selected.split(":")[0].strip()

    # Build clone URL
    if "/" in name:
        repo_path = name
    elif owner:
        repo_path = f"{owner}/{name}"
    else:
        # Get current user
        ok, username = run_cmd(["gh", "api", "user", "--jq", ".login"])
        if ok:
            repo_path = f"{username.strip()}/{name}"
        else:
            repo_path = name

    # Destination directory
    if dest is None:
        dest = Path.cwd() / name.split("/")[-1]

    console.print(f"[cyan]Cloning {repo_path}...[/]")

    ok, output = run_cmd(["gh", "repo", "clone", repo_path, str(dest)])

    if ok:
        console.print(f"[green]✓[/] Cloned to {dest}")

        # Install auto-push hook
        if setup_hook:
            hooks.install(dest, quiet=True)
            console.print(f"[green]✓[/] Auto-push hook installed")

        console.print()
        console.print(f"  [cyan]cd {dest.name}[/]")
    else:
        console.print(f"[red]✗[/] Clone failed: {output}")

    console.print()


def clone_all(
    owner: Optional[str] = None,
    dest_dir: Optional[Path] = None,
    include_private: bool = True,
    setup_hooks: bool = True,
):
    """Clone all repositories."""
    console.print()

    with console.status("Fetching repositories..."):
        repos = get_repos(limit=100, owner=owner)

    if not repos:
        console.print("[red]No repositories found.[/]")
        return

    # Filter
    if not include_private:
        repos = [r for r in repos if not r.get("isPrivate")]

    console.print(f"Found [cyan]{len(repos)}[/] repositories.")

    if not questionary.confirm(f"Clone all {len(repos)} repos?", default=False).ask():
        console.print("[yellow]Cancelled.[/]")
        return

    dest_dir = dest_dir or Path.cwd()

    console.print()

    cloned = 0
    skipped = 0
    failed = 0

    for repo in repos:
        name = repo["name"]
        repo_dest = dest_dir / name

        if repo_dest.exists():
            console.print(f"[dim]○[/] {name} (exists)")
            skipped += 1
            continue

        ok, _ = run_cmd(["gh", "repo", "clone", repo["url"], str(repo_dest)])

        if ok:
            console.print(f"[green]✓[/] {name}")
            if setup_hooks:
                hooks.install(repo_dest, quiet=True)
            cloned += 1
        else:
            console.print(f"[red]✗[/] {name}")
            failed += 1

    console.print()
    console.print(Panel(
        f"[green]Cloned:[/] {cloned}  [dim]Skipped:[/] {skipped}  [red]Failed:[/] {failed}",
        expand=False
    ))
    console.print()
