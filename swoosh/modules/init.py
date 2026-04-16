"""Project initialization module."""

import os
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary

from swoosh.modules.check import ensure_dependencies
from swoosh.modules.config import load_config
from swoosh.modules import hooks
from swoosh.modules import templates
from swoosh.modules.utils import run_cmd

console = Console()


def get_orgs() -> list[str]:
    """Get list of organizations user has access to."""
    ok, output = run_cmd(["gh", "api", "user/orgs", "--jq", ".[].login"])
    if ok and output.strip():
        return [org.strip() for org in output.strip().split("\n") if org.strip()]
    return []


def run(
    name: Optional[str],
    here: bool,
    template: str,
    private: bool,
    setup_ci: bool,
    setup_autopush: bool,
    multi_origin: bool = False,
    org: Optional[str] = None,
):
    """Initialize a new project."""
    console.print()

    # Check dependencies first
    if not ensure_dependencies():
        console.print()
        console.print("[dim]Run [cyan]swoosh doctor[/cyan] for more details.[/]")
        return

    config = load_config()

    # Determine project directory
    if here:
        project_dir = Path.cwd()
        project_name = project_dir.name
    elif name:
        project_dir = Path.cwd() / name
        project_name = name
    else:
        # Interactive mode
        project_name = questionary.text(
            "Project name:",
            validate=lambda x: len(x) > 0 or "Name required"
        ).ask()

        if not project_name:
            console.print("[yellow]Cancelled.[/]")
            return

        project_dir = Path.cwd() / project_name

    # Check if directory exists
    if not here and project_dir.exists():
        if not questionary.confirm(
            f"Directory '{project_name}' already exists. Continue?",
            default=False
        ).ask():
            console.print("[yellow]Cancelled.[/]")
            return

    # Interactive options if not specified via CLI
    if not here and not name:
        # Ask for org
        if not org:
            orgs = get_orgs()
            if orgs:
                org_choices = ["(personal account)"] + orgs
                org_choice = questionary.select(
                    "Create in:",
                    choices=org_choices,
                    default="(personal account)"
                ).ask()
                if org_choice and org_choice != "(personal account)":
                    org = org_choice

        template = questionary.select(
            "CI template:",
            choices=["generic", "node", "python", "rust", "go"],
            default=config.get("default_template", "generic")
        ).ask() or template

        private = questionary.confirm(
            "Private repository?",
            default=config.get("default_private", False)
        ).ask()

    # Build repo path (org/name or just name)
    repo_full_name = f"{org}/{project_name}" if org else project_name

    console.print()
    console.print(Panel(
        f"[bold]Project:[/] {project_name}\n"
        f"[bold]Owner:[/] {org or '(personal)'}\n"
        f"[bold]Directory:[/] {project_dir}\n"
        f"[bold]Template:[/] {template}\n"
        f"[bold]Visibility:[/] {'private' if private else 'public'}",
        title="[blue]Swoosh Init[/]",
        expand=False
    ))
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 1. Create directory
        task = progress.add_task("Creating project directory...", total=None)
        if not here:
            project_dir.mkdir(parents=True, exist_ok=True)
        progress.update(task, description="[green]✓[/] Project directory ready")
        progress.remove_task(task)

        # 2. Initialize git
        task = progress.add_task("Initializing git repository...", total=None)
        git_dir = project_dir / ".git"
        if git_dir.exists():
            progress.update(task, description="[green]✓[/] Git repository exists")
        else:
            ok, output = run_cmd(["git", "init"], cwd=project_dir)
            if ok:
                progress.update(task, description="[green]✓[/] Git repository initialized")
            else:
                progress.update(task, description=f"[red]✗[/] Git init failed: {output}")
                return
        progress.remove_task(task)

        # 3. Create .gitignore if not exists
        task = progress.add_task("Creating .gitignore...", total=None)
        gitignore = project_dir / ".gitignore"
        if not gitignore.exists():
            gitignore_content = templates.get_gitignore(template)
            gitignore.write_text(gitignore_content)
            progress.update(task, description="[green]✓[/] Created .gitignore")
        else:
            progress.update(task, description="[green]✓[/] .gitignore exists")
        progress.remove_task(task)

        # 4. Setup CI/CD
        if setup_ci:
            task = progress.add_task("Setting up CI/CD...", total=None)
            workflows_dir = project_dir / ".github" / "workflows"
            workflows_dir.mkdir(parents=True, exist_ok=True)

            ci_content = templates.get_workflow(template)
            ci_file = workflows_dir / "ci.yml"
            ci_file.write_text(ci_content)
            progress.update(task, description="[green]✓[/] CI/CD workflow created")
            progress.remove_task(task)

        # 5. Create GitHub repository
        task = progress.add_task("Creating GitHub repository...", total=None)
        visibility = "--private" if private else "--public"

        # Check if remote already exists
        ok, output = run_cmd(["git", "remote", "get-url", "origin"], cwd=project_dir)
        if ok:
            progress.update(task, description=f"[green]✓[/] Remote exists: {output}")
        else:
            ok, output = run_cmd(
                ["gh", "repo", "create", repo_full_name, visibility, "--source", str(project_dir), "--push"],
                cwd=project_dir
            )
            if ok:
                progress.update(task, description=f"[green]✓[/] GitHub repository created: {repo_full_name}")
            else:
                # Try without --push
                ok2, output2 = run_cmd(
                    ["gh", "repo", "create", repo_full_name, visibility, "--source", str(project_dir)],
                    cwd=project_dir
                )
                if ok2:
                    progress.update(task, description=f"[green]✓[/] GitHub repository created: {repo_full_name}")
                else:
                    progress.update(task, description=f"[yellow]![/] GitHub repo issue: {output2[:80]}")
        progress.remove_task(task)

        # 6. Initial commit
        task = progress.add_task("Creating initial commit...", total=None)

        ok, _ = run_cmd(["git", "rev-parse", "HEAD"], cwd=project_dir)
        if not ok:
            run_cmd(["git", "add", "-A"], cwd=project_dir)
            ok, output = run_cmd(
                ["git", "commit", "-m", "init"],
                cwd=project_dir
            )
            if ok:
                progress.update(task, description="[green]✓[/] Initial commit created")
            else:
                progress.update(task, description="[dim]○[/] No files to commit")
        else:
            progress.update(task, description="[green]✓[/] Commits exist")
        progress.remove_task(task)

        # 7. Push to remote
        task = progress.add_task("Pushing to GitHub...", total=None)
        ok, output = run_cmd(["git", "push", "-u", "origin", "main"], cwd=project_dir)
        if not ok:
            ok, output = run_cmd(["git", "push", "-u", "origin", "master"], cwd=project_dir)

        if ok:
            progress.update(task, description="[green]✓[/] Pushed to GitHub")
        else:
            progress.update(task, description="[yellow]![/] Push pending")
        progress.remove_task(task)

        # 8. Install auto-push hook
        if setup_autopush:
            task = progress.add_task("Installing auto-push hook...", total=None)
            hooks.install(project_dir, quiet=True, multi_origin=multi_origin)
            progress.update(task, description="[green]✓[/] Auto-push hook installed")
            progress.remove_task(task)

    # Summary
    console.print()
    console.print(Panel(
        f"[green bold]Project initialized![/]\n\n"
        f"  [cyan]cd {project_name}[/]\n\n"
        f"Every commit will auto-push to GitHub.",
        expand=False
    ))
    console.print()
