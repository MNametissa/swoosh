"""Swoosh CLI - Main entry point."""

import typer
from rich.console import Console
from rich.panel import Panel
from typing import Optional
from pathlib import Path

from swoosh import __version__
from swoosh.modules import (
    init, hooks, config, check, clone,
    commit, release, deploy, sync, secrets, pr, origins, templates, auth
)

app = typer.Typer(
    name="swoosh",
    help="All-in-one CLI for Git workflow automation: init, commit, release, deploy, sync",
    rich_markup_mode="rich",
    no_args_is_help=True,
)

console = Console()


def version_callback(value: bool):
    if value:
        console.print(Panel(
            f"[bold blue]Swoosh[/] v{__version__}",
            subtitle="Git Workflow Automation"
        ))
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-v",
        callback=version_callback,
        is_eager=True,
        help="Show version"
    ),
):
    """Swoosh - All-in-one Git workflow automation."""
    pass


# ============================================================================
# INIT
# ============================================================================

@app.command("init")
def init_project(
    name: Optional[str] = typer.Argument(None, help="Project name"),
    here: bool = typer.Option(False, "--here", "-h", help="Initialize in current directory"),
    org: Optional[str] = typer.Option(None, "--org", "-o", help="Create in organization"),
    template: str = typer.Option("generic", "--template", "-t", help="CI template: node, python, rust, go, generic"),
    private: bool = typer.Option(False, "--private", "-p", help="Create private repository"),
    no_ci: bool = typer.Option(False, "--no-ci", help="Skip CI/CD setup"),
    no_autopush: bool = typer.Option(False, "--no-autopush", help="Skip auto-push hook"),
    multi_origin: bool = typer.Option(False, "--multi-origin", "-m", help="Enable multi-origin push"),
):
    """Initialize project with Git, GitHub repo, and CI/CD."""
    init.run(
        name=name,
        here=here,
        org=org,
        template=template,
        private=private,
        setup_ci=not no_ci,
        setup_autopush=not no_autopush,
        multi_origin=multi_origin,
    )


# ============================================================================
# COMMIT
# ============================================================================

@app.command("commit")
def commit_cmd(
    message: Optional[str] = typer.Argument(None, help="Commit message"),
    type_: Optional[str] = typer.Option(None, "--type", "-t", help="Commit type: feat, fix, docs, etc."),
    scope: Optional[str] = typer.Option(None, "--scope", "-s", help="Commit scope"),
    push: bool = typer.Option(False, "--push", "-p", help="Push after commit"),
    all_remotes: bool = typer.Option(False, "--all", "-a", help="Push to all remotes"),
):
    """Create a conventional commit."""
    if message and type_:
        commit.quick_commit(message, type_, push=push)
    else:
        commit.interactive_commit(
            commit_type=type_,
            scope=scope,
            message=message,
            push=push,
            all_remotes=all_remotes,
        )


# ============================================================================
# RELEASE
# ============================================================================

@app.command("release")
def release_cmd(
    bump: Optional[str] = typer.Argument(None, help="Bump type: major, minor, patch, alpha, beta, rc"),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Specific version"),
    prerelease: Optional[str] = typer.Option(None, "--pre", "-p", help="Pre-release type: alpha, beta, rc"),
    auto: bool = typer.Option(False, "--auto", "-a", help="Auto-detect bump type from commits"),
    no_changelog: bool = typer.Option(False, "--no-changelog", help="Skip changelog generation"),
    no_github: bool = typer.Option(False, "--no-github", help="Skip GitHub release"),
    no_push: bool = typer.Option(False, "--no-push", help="Skip push"),
):
    """Create a new release with version bump, changelog, and tag.

    Supports pre-releases: alpha, beta, rc
    Auto-detects breaking changes for major bumps.
    """
    release.create_release(
        bump_type=bump,
        version=version,
        prerelease=prerelease,
        auto=auto,
        skip_changelog=no_changelog,
        skip_github=no_github,
        push=not no_push,
    )


# ============================================================================
# DEPLOY
# ============================================================================

@app.command("deploy")
def deploy_cmd(
    target: Optional[str] = typer.Argument(None, help="Deploy target from swoosh.yaml"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be done"),
    skip_health: bool = typer.Option(False, "--skip-health", help="Skip health check"),
    list_: bool = typer.Option(False, "--list", "-l", help="List available targets"),
    releases: bool = typer.Option(False, "--releases", "-r", help="List releases for target"),
    rollback: bool = typer.Option(False, "--rollback", help="Rollback to previous release"),
):
    """Deploy to SSH/VPS server with rollback support.

    Features:
    - Release management (keeps N previous releases)
    - Health checks (HTTP, TCP, process, command)
    - Automatic rollback on failed health check
    """
    if list_:
        deploy.list_targets()
    elif releases:
        if not target:
            console.print("[red]Error:[/] Target required for --releases")
            raise typer.Exit(1)
        deploy.releases_list(target)
    elif rollback:
        if not target:
            console.print("[red]Error:[/] Target required for --rollback")
            raise typer.Exit(1)
        deploy.rollback(target)
    else:
        deploy.deploy(target=target, dry_run=dry_run, skip_health_check=skip_health)


# ============================================================================
# SYNC
# ============================================================================

@app.command("sync")
def sync_cmd(
    directory: Optional[str] = typer.Argument(None, help="Directory to sync"),
    status: bool = typer.Option(False, "--status", "-s", help="Show status only"),
    no_push: bool = typer.Option(False, "--no-push", help="Pull only, don't push"),
    upstream: bool = typer.Option(False, "--upstream", "-u", help="Sync with upstream (for forks)"),
):
    """Sync multiple repositories (pull + push)."""
    path = Path(directory) if directory else None

    if upstream:
        sync.sync_upstream(cwd=path)
    elif status:
        sync.status_all(directory=path)
    else:
        sync.sync_all(directory=path, push=not no_push)


# ============================================================================
# SECRETS
# ============================================================================

@app.command("secrets")
def secrets_cmd(
    action: str = typer.Argument("scan", help="Action: scan, add, list, hook"),
    name: Optional[str] = typer.Argument(None, help="Secret name (for add)"),
    staged: bool = typer.Option(False, "--staged", help="Scan staged files only"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Minimal output"),
):
    """Scan for secrets or manage GitHub secrets."""
    if action == "scan":
        findings = secrets.scan(staged_only=staged, quiet=quiet)
        if findings and not quiet:
            raise typer.Exit(1)
    elif action == "add":
        if not name:
            console.print("[red]Error:[/] Secret name required")
            raise typer.Exit(1)
        secrets.add_github_secret(name)
    elif action == "list":
        secrets.list_github_secrets()
    elif action == "hook":
        secrets.install_pre_commit_hook()
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        console.print("Use: scan, add, list, hook")


# ============================================================================
# PR
# ============================================================================

@app.command("pr")
def pr_cmd(
    title: Optional[str] = typer.Argument(None, help="PR title"),
    base: Optional[str] = typer.Option(None, "--base", "-b", help="Base branch"),
    draft: bool = typer.Option(False, "--draft", "-d", help="Create as draft"),
    list_: bool = typer.Option(False, "--list", "-l", help="List open PRs"),
):
    """Create or list pull requests."""
    if list_:
        pr.list_prs()
    else:
        pr.create_pr(title=title, base=base, draft=draft)


# ============================================================================
# ORIGIN (Multi-origin management)
# ============================================================================

@app.command("origin")
def origin_cmd(
    action: str = typer.Argument("list", help="Action: list, add, remove, push, status, mirror"),
    name: Optional[str] = typer.Argument(None, help="Remote name or repo name"),
    url: Optional[str] = typer.Option(None, "--url", "-u", help="Remote URL"),
    provider: Optional[str] = typer.Option(None, "--provider", "-p", help="Provider: github, gitlab, bitbucket, gitea"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Owner/organization/group"),
    host: Optional[str] = typer.Option(None, "--host", help="Host for self-hosted (GitLab, Gitea)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show more details"),
):
    """Manage multiple git remotes.

    Actions:
    - list: Show all configured remotes
    - add: Add a new remote
    - remove: Remove a remote
    - push: Push to all remotes
    - status: Check sync status of all remotes
    - mirror: Set up a mirror to another provider
    """
    if action == "list":
        origins.list_origins(verbose=verbose)
    elif action == "add":
        origins.add_origin(name=name, url=url, provider=provider, owner=owner, host=host)
    elif action == "remove":
        if not name:
            console.print("[red]Error:[/] Remote name required")
            raise typer.Exit(1)
        origins.remove_origin(name)
    elif action == "push":
        origins.push_all()
    elif action == "status":
        origins.status_all()
    elif action == "mirror":
        if not provider:
            console.print("[red]Error:[/] --provider required for mirror")
            console.print("Example: swoosh origin mirror --provider gitlab")
            raise typer.Exit(1)
        origins.setup_mirror(
            source_remote=name or "origin",
            target_provider=provider,
            target_owner=owner,
            target_host=host,
        )
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        console.print("Use: list, add, remove, push, status, mirror")


# ============================================================================
# HOOK
# ============================================================================

@app.command("hook")
def hook_cmd(
    action: str = typer.Argument(..., help="Action: install, remove, status"),
    multi_origin: bool = typer.Option(False, "--multi-origin", "-m", help="Enable multi-origin push"),
):
    """Manage auto-push git hooks."""
    if action == "install":
        hooks.install(multi_origin=multi_origin)
    elif action == "remove":
        hooks.remove()
    elif action == "status":
        hooks.status()
    elif action == "multi":
        hooks.enable_multi_origin()
    else:
        console.print(f"[red]Unknown action:[/] {action}")
        console.print("Use: install, remove, status")


# ============================================================================
# TEMPLATES
# ============================================================================

@app.command("templates")
def templates_cmd(
    action: str = typer.Argument("list", help="Action: list, show"),
    name: Optional[str] = typer.Argument(None, help="Template name"),
):
    """List or show CI/CD templates."""
    if action == "list":
        templates.list_templates()
    elif action == "show" and name:
        templates.show_template(name)
    else:
        templates.list_templates()


# ============================================================================
# CLONE
# ============================================================================

@app.command("clone")
def clone_cmd(
    name: Optional[str] = typer.Argument(None, help="Repository name or owner/repo"),
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Repository owner"),
    dest: Optional[str] = typer.Option(None, "--dest", "-d", help="Destination directory"),
    no_hook: bool = typer.Option(False, "--no-hook", help="Skip auto-push hook"),
):
    """Clone a repository from GitHub."""
    clone.clone_repo(
        name=name,
        owner=owner,
        dest=Path(dest) if dest else None,
        setup_hook=not no_hook,
    )


@app.command("clone-all")
def clone_all_cmd(
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="Clone from specific owner/org"),
    dest: Optional[str] = typer.Option(None, "--dest", "-d", help="Destination directory"),
    no_private: bool = typer.Option(False, "--no-private", help="Skip private repos"),
    no_hooks: bool = typer.Option(False, "--no-hooks", help="Skip hooks"),
):
    """Clone all your repositories."""
    clone.clone_all(
        owner=owner,
        dest_dir=Path(dest) if dest else None,
        include_private=not no_private,
        setup_hooks=not no_hooks,
    )


# ============================================================================
# REPOS & ORGS
# ============================================================================

@app.command("repos")
def repos_cmd(
    owner: Optional[str] = typer.Option(None, "--owner", "-o", help="List from specific owner"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of repos"),
):
    """List your GitHub repositories."""
    clone.list_repos(owner=owner, limit=limit)


@app.command("orgs")
def orgs_cmd():
    """List organizations you have access to."""
    from swoosh.modules.init import get_orgs
    from rich.table import Table

    orgs = get_orgs()
    if not orgs:
        console.print("[yellow]No organizations found or not authenticated.[/]")
        return

    table = Table(title="Organizations", show_header=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")

    for i, org in enumerate(orgs, 1):
        table.add_row(str(i), org)

    console.print(table)
    console.print()
    console.print("[dim]Use with:[/] swoosh init --org <name>")


# ============================================================================
# DOCTOR & CONFIG
# ============================================================================

@app.command("doctor")
def doctor_cmd():
    """Check system dependencies and configuration."""
    check.run_doctor()


@app.command("config")
def config_cmd(
    show: bool = typer.Option(False, "--show", "-s", help="Show current config"),
    github_user: Optional[str] = typer.Option(None, "--github-user", "-u", help="Set GitHub username"),
    template: Optional[str] = typer.Option(None, "--template", "-t", help="Set default template"),
):
    """Configure Swoosh defaults."""
    if show:
        config.show_config()
    elif github_user or template:
        config.update_config(github_user=github_user, default_template=template)
    else:
        config.interactive_config()


# ============================================================================
# AUTH
# ============================================================================

@app.command("auth")
def auth_cmd(
    method: Optional[str] = typer.Argument(None, help="Method: ssh, token, oauth, status, logout"),
    token: Optional[str] = typer.Option(None, "--token", "-t", help="Personal Access Token"),
    username: Optional[str] = typer.Option(None, "--name", "-n", help="Git username"),
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Git email"),
    ssh: bool = typer.Option(False, "--ssh", "-s", help="Use/generate SSH key"),
):
    """Authenticate with GitHub.

    Examples:
        swoosh auth            # Interactive setup
        swoosh auth --ssh      # Use SSH key
        swoosh auth --token    # Use Personal Access Token
        swoosh auth status     # Show current status
        swoosh auth logout     # Logout
    """
    if method == "status":
        auth.status()
        return

    if method == "logout":
        auth.logout()
        return

    # Default: start interactive login
    auth.login(
        method="ssh" if ssh else method,
        token=token,
        username=username,
        email=email,
        generate_key=ssh,
    )


if __name__ == "__main__":
    app()
