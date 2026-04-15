"""Multi-origin management for Swoosh.

Supports: GitHub, GitLab (cloud + self-hosted), Bitbucket, Gitea, custom Git servers.
"""

import re
import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, get_remotes, is_git_repo, load_swoosh_config

console = Console()

# Known Git providers with their configurations
PROVIDERS = {
    "github": {
        "name": "GitHub",
        "domain": "github.com",
        "ssh": "git@github.com:{owner}/{repo}.git",
        "https": "https://github.com/{owner}/{repo}.git",
        "cli": "gh",
        "api": "https://api.github.com",
        "create_cmd": ["gh", "repo", "create", "{owner}/{repo}", "--{visibility}"],
        "visibility_options": ["public", "private"],
    },
    "gitlab": {
        "name": "GitLab",
        "domain": "gitlab.com",
        "ssh": "git@gitlab.com:{owner}/{repo}.git",
        "https": "https://gitlab.com/{owner}/{repo}.git",
        "cli": "glab",
        "api": "https://gitlab.com/api/v4",
        "create_cmd": ["glab", "repo", "create", "{repo}", "--group", "{owner}", "--{visibility}"],
        "visibility_options": ["public", "private", "internal"],
    },
    "bitbucket": {
        "name": "Bitbucket",
        "domain": "bitbucket.org",
        "ssh": "git@bitbucket.org:{owner}/{repo}.git",
        "https": "https://bitbucket.org/{owner}/{repo}.git",
        "cli": None,  # No official CLI, use API
        "api": "https://api.bitbucket.org/2.0",
        "visibility_options": ["public", "private"],
    },
    "gitea": {
        "name": "Gitea",
        "domain": None,  # Self-hosted
        "ssh": "git@{host}:{owner}/{repo}.git",
        "https": "https://{host}/{owner}/{repo}.git",
        "cli": None,
        "api": "https://{host}/api/v1",
        "visibility_options": ["public", "private"],
    },
    "custom": {
        "name": "Custom",
        "domain": None,
        "ssh": None,
        "https": None,
        "cli": None,
    },
}


def detect_provider(url: str) -> tuple[str, Optional[str]]:
    """Detect provider and host from remote URL.

    Returns (provider_key, host) where host is None for known cloud providers.
    """
    url_lower = url.lower()

    # Cloud providers
    if "github.com" in url_lower:
        return "github", None
    elif "gitlab.com" in url_lower:
        return "gitlab", None
    elif "bitbucket.org" in url_lower:
        return "bitbucket", None

    # Extract host for self-hosted detection
    host_match = re.search(r'[@/]([^/:]+)[:/]', url)
    host = host_match.group(1) if host_match else None

    # Known self-hosted patterns
    if host:
        # GitLab self-hosted often has "gitlab" in hostname
        if "gitlab" in host.lower():
            return "gitlab", host
        # Gitea instances
        if "gitea" in host.lower() or "git." in host.lower():
            return "gitea", host

    return "custom", host


def parse_remote_url(url: str) -> dict:
    """Parse a git remote URL into components."""
    result = {
        "url": url,
        "provider": "custom",
        "host": None,
        "owner": None,
        "repo": None,
        "protocol": "unknown",
    }

    provider, host = detect_provider(url)
    result["provider"] = provider
    result["host"] = host or PROVIDERS.get(provider, {}).get("domain")

    # SSH format: git@host:owner/repo.git
    ssh_match = re.match(r'git@([^:]+):([^/]+)/(.+?)(?:\.git)?$', url)
    if ssh_match:
        result["host"] = ssh_match.group(1)
        result["owner"] = ssh_match.group(2)
        result["repo"] = ssh_match.group(3)
        result["protocol"] = "ssh"
        return result

    # HTTPS format: https://host/owner/repo.git
    https_match = re.match(r'https?://([^/]+)/([^/]+)/(.+?)(?:\.git)?$', url)
    if https_match:
        result["host"] = https_match.group(1)
        result["owner"] = https_match.group(2)
        result["repo"] = https_match.group(3)
        result["protocol"] = "https"
        return result

    return result


def check_cli_available(provider: str) -> bool:
    """Check if provider CLI is available."""
    cli = PROVIDERS.get(provider, {}).get("cli")
    if not cli:
        return False
    ok, _ = run_cmd(["which", cli])
    return ok


def get_authenticated_user(provider: str) -> Optional[str]:
    """Get the authenticated username for a provider."""
    if provider == "github":
        ok, output = run_cmd(["gh", "api", "user", "--jq", ".login"])
        return output.strip() if ok else None
    elif provider == "gitlab":
        ok, output = run_cmd(["glab", "api", "user", "--jq", ".username"])
        return output.strip() if ok else None
    elif provider == "bitbucket":
        # Check for Bitbucket credentials in git config or netrc
        ok, output = run_cmd(["git", "config", "--get", "bitbucket.user"])
        return output.strip() if ok else None
    return None


def list_origins(cwd: Optional[Path] = None, verbose: bool = False):
    """List all configured remotes with provider info."""
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
    table.add_column("Owner/Repo", style="green")
    table.add_column("URL", style="dim")

    for remote in remotes:
        parsed = parse_remote_url(remote["url"])
        provider_name = PROVIDERS.get(parsed["provider"], {}).get("name", "Unknown")

        # For self-hosted, show host
        if parsed["provider"] in ["gitea", "custom"] or parsed["host"] not in [None, "github.com", "gitlab.com", "bitbucket.org"]:
            provider_name = f"{provider_name} ({parsed['host']})" if parsed["host"] else provider_name

        owner_repo = f"{parsed['owner']}/{parsed['repo']}" if parsed["owner"] and parsed["repo"] else "-"
        table.add_row(remote["name"], provider_name, owner_repo, remote["url"])

    console.print(table)

    # Show CLI availability
    if verbose:
        console.print()
        providers_used = set(parse_remote_url(r["url"])["provider"] for r in remotes)
        for p in providers_used:
            if p != "custom":
                cli = PROVIDERS.get(p, {}).get("cli")
                if cli:
                    available = check_cli_available(p)
                    status = "[green]✓[/]" if available else "[red]✗[/]"
                    console.print(f"  {status} {PROVIDERS[p]['name']} CLI ({cli})")

    console.print()


def add_origin(
    name: Optional[str] = None,
    url: Optional[str] = None,
    provider: Optional[str] = None,
    owner: Optional[str] = None,
    repo: Optional[str] = None,
    host: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Add a new remote origin with full provider support."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    console.print()

    # Interactive mode
    if not name:
        existing = get_remotes(cwd)
        default_name = "origin" if not existing else ""

        # Suggest name based on provider
        if provider and provider != "custom":
            default_name = provider if any(r["name"] == "origin" for r in existing) else "origin"

        name = questionary.text(
            "Remote name:",
            default=default_name,
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
                choices=[
                    "github (GitHub.com)",
                    "gitlab (GitLab.com)",
                    "gitlab-self (Self-hosted GitLab)",
                    "bitbucket (Bitbucket.org)",
                    "gitea (Self-hosted Gitea)",
                    "custom (Any Git URL)",
                ]
            ).ask()
            if not provider:
                return
            provider = provider.split()[0]  # Extract key

        # Handle self-hosted providers
        if provider in ["gitlab-self", "gitea"] or (provider == "gitlab" and host):
            if not host:
                host = questionary.text(
                    "Host (e.g., gitlab.mycompany.com):",
                    validate=lambda x: len(x) > 0 or "Host required"
                ).ask()
                if not host:
                    return
            provider = "gitlab" if provider == "gitlab-self" else "gitea"

        if provider == "custom":
            url = questionary.text(
                "Remote URL:",
                validate=lambda x: len(x) > 0 or "URL required"
            ).ask()
        else:
            # Get owner
            if not owner:
                # Try to get authenticated user as default
                default_owner = get_authenticated_user(provider) or ""

                owner_label = {
                    "github": "Owner/Organization",
                    "gitlab": "Group/Username",
                    "bitbucket": "Workspace",
                    "gitea": "Owner/Organization",
                }.get(provider, "Owner")

                owner = questionary.text(
                    f"{owner_label}:",
                    default=default_owner,
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
            template_key = "ssh" if use_ssh else "https"
            template = PROVIDERS[provider][template_key]

            if host:
                url = template.format(host=host, owner=owner, repo=repo)
            else:
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


def create_repo(
    provider: str,
    name: str,
    owner: Optional[str] = None,
    visibility: str = "private",
    description: str = "",
    host: Optional[str] = None,
    cwd: Optional[Path] = None,
) -> bool:
    """Create a repository on a provider.

    Supports: GitHub (gh), GitLab (glab), Bitbucket (API).
    """
    if cwd is None:
        cwd = Path.cwd()

    console.print(f"\n[dim]Creating {visibility} repo '{name}' on {PROVIDERS.get(provider, {}).get('name', provider)}...[/]")

    if provider == "github":
        if not check_cli_available("github"):
            console.print("[red]Error:[/] GitHub CLI (gh) not found. Install: https://cli.github.com")
            return False

        repo_path = f"{owner}/{name}" if owner else name
        cmd = ["gh", "repo", "create", repo_path, f"--{visibility}"]
        if description:
            cmd.extend(["--description", description])

        ok, output = run_cmd(cmd, cwd=cwd, timeout=60)
        if ok:
            console.print(f"[green]✓[/] Created GitHub repo: {repo_path}")
            return True
        else:
            console.print(f"[red]✗[/] Failed: {output}")
            return False

    elif provider == "gitlab":
        if not check_cli_available("gitlab"):
            console.print("[red]Error:[/] GitLab CLI (glab) not found. Install: https://gitlab.com/gitlab-org/cli")
            return False

        cmd = ["glab", "repo", "create", name, f"--{visibility}"]
        if owner:
            cmd.extend(["--group", owner])
        if description:
            cmd.extend(["--description", description])

        ok, output = run_cmd(cmd, cwd=cwd, timeout=60)
        if ok:
            console.print(f"[green]✓[/] Created GitLab repo: {owner}/{name}" if owner else f"[green]✓[/] Created GitLab repo: {name}")
            return True
        else:
            console.print(f"[red]✗[/] Failed: {output}")
            return False

    elif provider == "bitbucket":
        # Bitbucket uses REST API
        console.print("[yellow]![/] Bitbucket repo creation requires API token.")
        console.print("Set BITBUCKET_TOKEN environment variable or use: https://bitbucket.org/repo/create")
        return False

    elif provider == "gitea":
        if not host:
            console.print("[red]Error:[/] Host required for Gitea")
            return False

        console.print(f"[yellow]![/] Create repo manually at: https://{host}/repo/create")
        return False

    else:
        console.print(f"[red]Error:[/] Unsupported provider: {provider}")
        return False


def setup_mirror(
    source_remote: str = "origin",
    target_provider: str = "gitlab",
    target_owner: Optional[str] = None,
    target_repo: Optional[str] = None,
    target_host: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Set up a mirror to another provider.

    This creates the repo on the target and adds it as a remote.
    """
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    console.print()

    # Get source info
    remotes = get_remotes(cwd)
    source = next((r for r in remotes if r["name"] == source_remote), None)

    if not source:
        console.print(f"[red]Error:[/] Remote '{source_remote}' not found.")
        return

    source_info = parse_remote_url(source["url"])
    repo_name = target_repo or source_info["repo"] or cwd.name

    if not target_owner:
        target_owner = get_authenticated_user(target_provider)
        if not target_owner:
            target_owner = questionary.text(
                f"{PROVIDERS.get(target_provider, {}).get('name', target_provider)} owner/group:"
            ).ask()

    if not target_owner:
        return

    console.print(f"Setting up mirror: {source_remote} → {target_provider}")

    # Create repo on target provider
    created = create_repo(
        provider=target_provider,
        name=repo_name,
        owner=target_owner,
        visibility="private",
        host=target_host,
        cwd=cwd,
    )

    if not created:
        if not questionary.confirm("Continue adding remote anyway?", default=False).ask():
            return

    # Add as remote
    remote_name = target_provider
    if any(r["name"] == remote_name for r in remotes):
        remote_name = f"{target_provider}-mirror"

    # Build URL
    use_ssh = "git@" in source["url"]
    template = PROVIDERS[target_provider]["ssh" if use_ssh else "https"]
    if target_host:
        url = template.format(host=target_host, owner=target_owner, repo=repo_name)
    else:
        url = template.format(owner=target_owner, repo=repo_name)

    ok, _ = run_cmd(["git", "remote", "add", remote_name, url], cwd=cwd)
    if ok:
        console.print(f"[green]✓[/] Added remote '{remote_name}': {url}")

        # Push to mirror
        if questionary.confirm("Push to mirror now?", default=True).ask():
            ok, branch = run_cmd(["git", "branch", "--show-current"], cwd=cwd)
            if ok:
                run_cmd(["git", "push", "-u", remote_name, branch], cwd=cwd)
                console.print(f"[green]✓[/] Pushed to {remote_name}")
    else:
        console.print(f"[red]✗[/] Failed to add remote")


def status_all(cwd: Optional[Path] = None):
    """Check status of all remotes (sync state)."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    remotes = get_remotes(cwd)

    if not remotes:
        console.print("[yellow]No remotes configured.[/]")
        return

    ok, branch = run_cmd(["git", "branch", "--show-current"], cwd=cwd)
    if not ok:
        console.print("[red]Error:[/] Could not determine branch.")
        return

    console.print(f"\n[dim]Checking remotes for branch '{branch}'...[/]\n")

    # Fetch all remotes first
    run_cmd(["git", "fetch", "--all", "-q"], cwd=cwd, timeout=60)

    table = Table(title="Remote Status", show_header=True)
    table.add_column("Remote", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Behind", style="yellow")
    table.add_column("Ahead", style="green")

    for remote in remotes:
        name = remote["name"]
        ref = f"{name}/{branch}"

        # Check if remote branch exists
        ok, _ = run_cmd(["git", "rev-parse", "--verify", ref], cwd=cwd)
        if not ok:
            table.add_row(name, "[dim]no branch[/]", "-", "-")
            continue

        # Get ahead/behind counts
        ok, output = run_cmd(
            ["git", "rev-list", "--left-right", "--count", f"{ref}...HEAD"],
            cwd=cwd
        )

        if ok and output:
            parts = output.split()
            if len(parts) == 2:
                behind, ahead = parts
                if behind == "0" and ahead == "0":
                    status = "[green]synced[/]"
                elif behind != "0" and ahead != "0":
                    status = "[yellow]diverged[/]"
                elif behind != "0":
                    status = "[yellow]behind[/]"
                else:
                    status = "[blue]ahead[/]"
                table.add_row(name, status, behind, ahead)
            else:
                table.add_row(name, "[dim]unknown[/]", "-", "-")
        else:
            table.add_row(name, "[red]error[/]", "-", "-")

    console.print(table)
    console.print()


def clone_from_provider(
    provider: str,
    repo: str,
    owner: Optional[str] = None,
    dest: Optional[Path] = None,
    host: Optional[str] = None,
):
    """Clone a repository from any supported provider."""
    if not owner:
        owner = get_authenticated_user(provider)
        if not owner:
            owner = questionary.text(f"{PROVIDERS.get(provider, {}).get('name', provider)} owner:").ask()

    if not owner:
        return

    # Build URL
    template = PROVIDERS.get(provider, {}).get("ssh")
    if not template:
        console.print(f"[red]Error:[/] Unknown provider: {provider}")
        return

    if host:
        url = template.format(host=host, owner=owner, repo=repo)
    else:
        url = template.format(owner=owner, repo=repo)

    dest_path = dest or Path.cwd() / repo

    console.print(f"\nCloning {owner}/{repo} from {PROVIDERS.get(provider, {}).get('name', provider)}...")

    ok, output = run_cmd(["git", "clone", url, str(dest_path)], timeout=300)

    if ok:
        console.print(f"[green]✓[/] Cloned to {dest_path}")
    else:
        console.print(f"[red]✗[/] Clone failed: {output[:100]}")
