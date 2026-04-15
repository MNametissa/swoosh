"""Multi-origin management for Swoosh."""

from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, get_remotes, is_git_repo

console = Console()

# Known Git providers
PROVIDERS = {
    "github": {
        "name": "GitHub",
        "ssh": "git@github.com:{owner}/{repo}.git",
        "https": "https://github.com/{owner}/{repo}.git",
        "cli": "gh",
    },
    "gitlab": {
        "name": "GitLab",
        "ssh": "git@gitlab.com:{owner}/{repo}.git",
        "https": "https://gitlab.com/{owner}/{repo}.git",
        "cli": "glab",
    },
    "bitbucket": {
        "name": "Bitbucket",
        "ssh": "git@bitbucket.org:{owner}/{repo}.git",
        "https": "https://bitbucket.org/{owner}/{repo}.git",
        "cli": None,
    },
    "custom": {
        "name": "Custom",
        "ssh": None,
        "https": None,
        "cli": None,
    },
}


def detect_provider(url: str) -> Optional[str]:
    """Detect provider from remote URL."""
    url_lower = url.lower()
    if "github.com" in url_lower:
        return "github"
    elif "gitlab.com" in url_lower:
        return "gitlab"
    elif "bitbucket.org" in url_lower:
        return "bitbucket"
    return "custom"


def list_origins(cwd: Optional[Path] = None):
    """List all configured remotes."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    remotes = get_remotes(cwd)

    if not remotes:
        console.print("[yellow]No remotes configured.[/]")
        console.print("Use [cyan]swoosh origin add[/] to add one.")
        return

    console.print()
    table = Table(title="Git Remotes", show_header=True)
    table.add_column("Name", style="cyan")
    table.add_column("Provider", style="blue")
    table.add_column("URL", style="white")

    for remote in remotes:
        provider = detect_provider(remote["url"])
        provider_name = PROVIDERS.get(provider, {}).get("name", "Unknown")
        table.add_row(remote["name"], provider_name, remote["url"])

    console.print(table)
    console.print()


def add_origin(
    name: Optional[str] = None,
    url: Optional[str] = None,
    provider: Optional[str] = None,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Add a new remote origin."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    console.print()

    # Interactive mode
    if not name:
        name = questionary.text(
            "Remote name:",
            default="origin" if not get_remotes(cwd) else "",
            validate=lambda x: len(x) > 0 or "Name required"
        ).ask()
        if not name:
            return

    # Check if remote already exists
    remotes = get_remotes(cwd)
    if any(r["name"] == name for r in remotes):
        console.print(f"[yellow]Remote '{name}' already exists.[/]")
        if not questionary.confirm("Replace it?", default=False).ask():
            return
        run_cmd(["git", "remote", "remove", name], cwd=cwd)

    if not url:
        # Ask for provider
        if not provider:
            provider = questionary.select(
                "Provider:",
                choices=["github", "gitlab", "bitbucket", "custom"]
            ).ask()
            if not provider:
                return

        if provider == "custom":
            url = questionary.text(
                "Remote URL:",
                validate=lambda x: len(x) > 0 or "URL required"
            ).ask()
        else:
            if not owner:
                owner = questionary.text(
                    "Owner/Organization:",
                    validate=lambda x: len(x) > 0 or "Owner required"
                ).ask()
            if not repo:
                repo = questionary.text(
                    "Repository name:",
                    default=cwd.name,
                    validate=lambda x: len(x) > 0 or "Repo required"
                ).ask()

            if not owner or not repo:
                return

            # Build URL
            use_ssh = questionary.confirm("Use SSH?", default=True).ask()
            template = PROVIDERS[provider]["ssh" if use_ssh else "https"]
            url = template.format(owner=owner, repo=repo)

    if not url:
        return

    # Add remote
    ok, output = run_cmd(["git", "remote", "add", name, url], cwd=cwd)

    if ok:
        console.print(f"[green]✓[/] Added remote '{name}': {url}")
    else:
        console.print(f"[red]✗[/] Failed: {output}")


def remove_origin(name: str, cwd: Optional[Path] = None):
    """Remove a remote origin."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    ok, output = run_cmd(["git", "remote", "remove", name], cwd=cwd)

    if ok:
        console.print(f"[green]✓[/] Removed remote '{name}'")
    else:
        console.print(f"[red]✗[/] Failed: {output}")


def push_all(cwd: Optional[Path] = None, branch: Optional[str] = None):
    """Push to all remotes."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    remotes = get_remotes(cwd)

    if not remotes:
        console.print("[yellow]No remotes configured.[/]")
        return

    # Get current branch if not specified
    if not branch:
        ok, branch = run_cmd(["git", "branch", "--show-current"], cwd=cwd)
        if not ok or not branch:
            console.print("[red]Error:[/] Could not determine current branch.")
            return

    console.print(f"\nPushing [cyan]{branch}[/] to {len(remotes)} remote(s)...\n")

    success = 0
    failed = 0

    for remote in remotes:
        name = remote["name"]
        ok, output = run_cmd(["git", "push", name, branch], cwd=cwd, timeout=120)

        if ok:
            console.print(f"[green]✓[/] {name}")
            success += 1
        else:
            console.print(f"[red]✗[/] {name}: {output[:80]}")
            failed += 1

    console.print()
    console.print(Panel(
        f"[green]Success:[/] {success}  [red]Failed:[/] {failed}",
        expand=False
    ))


def sync_origin(name: str, cwd: Optional[Path] = None):
    """Sync (pull then push) with a specific remote."""
    if cwd is None:
        cwd = Path.cwd()

    ok, branch = run_cmd(["git", "branch", "--show-current"], cwd=cwd)
    if not ok:
        console.print("[red]Error:[/] Could not determine branch.")
        return

    console.print(f"Syncing with [cyan]{name}[/]...")

    # Pull
    ok, output = run_cmd(["git", "pull", name, branch, "--rebase"], cwd=cwd)
    if not ok:
        console.print(f"[red]✗[/] Pull failed: {output[:100]}")
        return

    # Push
    ok, output = run_cmd(["git", "push", name, branch], cwd=cwd)
    if ok:
        console.print(f"[green]✓[/] Synced with {name}")
    else:
        console.print(f"[red]✗[/] Push failed: {output[:100]}")
