"""Conventional commits module for Swoosh."""

from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
import questionary

from swoosh.modules.utils import run_cmd, is_git_repo

console = Console()

COMMIT_TYPES = {
    "feat": "A new feature",
    "fix": "A bug fix",
    "docs": "Documentation only changes",
    "style": "Code style changes (formatting, semicolons, etc)",
    "refactor": "Code change that neither fixes a bug nor adds a feature",
    "perf": "Performance improvement",
    "test": "Adding or updating tests",
    "build": "Build system or external dependencies",
    "ci": "CI configuration changes",
    "chore": "Other changes that don't modify src or test files",
    "revert": "Reverts a previous commit",
}


def get_staged_files(cwd: Optional[Path] = None) -> list[str]:
    """Get list of staged files."""
    ok, output = run_cmd(["git", "diff", "--cached", "--name-only"], cwd=cwd)
    if not ok or not output:
        return []
    return [f for f in output.split("\n") if f.strip()]


def get_changed_files(cwd: Optional[Path] = None) -> list[str]:
    """Get list of changed (unstaged) files."""
    ok, output = run_cmd(["git", "diff", "--name-only"], cwd=cwd)
    if not ok or not output:
        return []
    return [f for f in output.split("\n") if f.strip()]


def get_untracked_files(cwd: Optional[Path] = None) -> list[str]:
    """Get list of untracked files."""
    ok, output = run_cmd(["git", "ls-files", "--others", "--exclude-standard"], cwd=cwd)
    if not ok or not output:
        return []
    return [f for f in output.split("\n") if f.strip()]


def interactive_commit(
    commit_type: Optional[str] = None,
    scope: Optional[str] = None,
    message: Optional[str] = None,
    breaking: bool = False,
    body: Optional[str] = None,
    cwd: Optional[Path] = None,
    push: bool = False,
    all_remotes: bool = False,
):
    """Create a conventional commit interactively."""
    if cwd is None:
        cwd = Path.cwd()

    if not is_git_repo(cwd):
        console.print("[red]Error:[/] Not a git repository.")
        return

    console.print()

    # Check for staged files
    staged = get_staged_files(cwd)
    changed = get_changed_files(cwd)
    untracked = get_untracked_files(cwd)

    if not staged and not changed and not untracked:
        console.print("[yellow]Nothing to commit.[/]")
        return

    # Show status
    if staged:
        console.print(f"[green]Staged:[/] {len(staged)} file(s)")
    if changed:
        console.print(f"[yellow]Changed:[/] {len(changed)} file(s)")
    if untracked:
        console.print(f"[dim]Untracked:[/] {len(untracked)} file(s)")
    console.print()

    # Ask to stage files if nothing staged
    if not staged:
        if changed or untracked:
            stage_all = questionary.confirm(
                "No files staged. Stage all changes?",
                default=True
            ).ask()

            if stage_all:
                run_cmd(["git", "add", "-A"], cwd=cwd)
                staged = get_staged_files(cwd)
            else:
                # Let user select files
                all_files = changed + untracked
                selected = questionary.checkbox(
                    "Select files to stage:",
                    choices=all_files
                ).ask()

                if not selected:
                    console.print("[yellow]Cancelled.[/]")
                    return

                for f in selected:
                    run_cmd(["git", "add", f], cwd=cwd)
                staged = selected

    # Interactive commit type
    if not commit_type:
        choices = [
            questionary.Choice(f"{k}: {v}", value=k)
            for k, v in COMMIT_TYPES.items()
        ]
        commit_type = questionary.select(
            "Commit type:",
            choices=choices
        ).ask()

        if not commit_type:
            console.print("[yellow]Cancelled.[/]")
            return

    # Scope (optional)
    if scope is None:
        scope = questionary.text(
            "Scope (optional):",
            default=""
        ).ask()

    # Message
    if not message:
        message = questionary.text(
            "Commit message:",
            validate=lambda x: len(x) > 0 or "Message required"
        ).ask()

        if not message:
            console.print("[yellow]Cancelled.[/]")
            return

    # Breaking change
    if not breaking:
        breaking = questionary.confirm(
            "Breaking change?",
            default=False
        ).ask()

    # Body (optional)
    if body is None and questionary.confirm("Add body/description?", default=False).ask():
        body = questionary.text(
            "Body (longer description):",
            multiline=True
        ).ask()

    # Build commit message
    breaking_marker = "!" if breaking else ""

    if scope:
        full_message = f"{commit_type}({scope}){breaking_marker}: {message}"
    else:
        full_message = f"{commit_type}{breaking_marker}: {message}"

    if body:
        full_message += f"\n\n{body}"

    if breaking:
        full_message += "\n\nBREAKING CHANGE: This commit introduces breaking changes."

    # Show preview
    console.print()
    console.print(Panel(
        full_message,
        title="[blue]Commit Preview[/]",
        expand=False
    ))
    console.print()

    if not questionary.confirm("Create commit?", default=True).ask():
        console.print("[yellow]Cancelled.[/]")
        return

    # Create commit
    ok, output = run_cmd(["git", "commit", "-m", full_message], cwd=cwd)

    if ok:
        console.print("[green]✓[/] Commit created")

        # Push if requested
        if push:
            from swoosh.modules.origins import push_all, get_remotes

            if all_remotes:
                push_all(cwd=cwd)
            else:
                ok, _ = run_cmd(["git", "push"], cwd=cwd)
                if ok:
                    console.print("[green]✓[/] Pushed to origin")
                else:
                    console.print("[yellow]![/] Push failed (no upstream?)")
    else:
        console.print(f"[red]✗[/] Commit failed: {output}")


def quick_commit(
    message: str,
    commit_type: str = "chore",
    cwd: Optional[Path] = None,
    push: bool = True,
):
    """Quick commit without interaction."""
    if cwd is None:
        cwd = Path.cwd()

    # Stage all
    run_cmd(["git", "add", "-A"], cwd=cwd)

    # Build message
    full_message = f"{commit_type}: {message}"

    # Commit
    ok, output = run_cmd(["git", "commit", "-m", full_message], cwd=cwd)

    if ok:
        console.print(f"[green]✓[/] {full_message}")
        if push:
            run_cmd(["git", "push"], cwd=cwd)
    else:
        console.print(f"[red]✗[/] {output}")
