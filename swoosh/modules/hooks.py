"""Git hooks management for auto-push and multi-origin."""

import os
import stat
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel

from swoosh.modules.utils import get_remotes

console = Console()

# Auto-push hook that supports multi-origin
POST_COMMIT_HOOK = '''#!/bin/bash
# Swoosh auto-push hook
# Automatically pushes commits to configured remotes

branch=$(git branch --show-current 2>/dev/null)
if [ -z "$branch" ]; then
    exit 0
fi

# Check for swoosh config for multi-origin
SWOOSH_MULTI_ORIGIN="${SWOOSH_MULTI_ORIGIN:-false}"

if [ "$SWOOSH_MULTI_ORIGIN" = "true" ]; then
    # Push to all remotes
    for remote in $(git remote); do
        if git rev-parse --abbrev-ref --symbolic-full-name "$remote/$branch" &>/dev/null 2>&1; then
            git push "$remote" "$branch" 2>/dev/null &
        else
            git push -u "$remote" "$branch" 2>/dev/null &
        fi
    done
else
    # Push to origin only
    if ! git remote get-url origin &>/dev/null; then
        exit 0
    fi

    if git rev-parse --abbrev-ref --symbolic-full-name @{u} &>/dev/null; then
        git push origin "$branch" 2>/dev/null &
    else
        git push -u origin "$branch" 2>/dev/null &
    fi
fi

# Disown background processes
disown 2>/dev/null

exit 0
'''

HOOK_MARKER = "# Swoosh auto-push hook"


def get_hooks_dir(project_dir: Optional[Path] = None) -> Optional[Path]:
    """Get the .git/hooks directory for a project."""
    if project_dir is None:
        project_dir = Path.cwd()

    git_dir = project_dir / ".git"
    if not git_dir.exists():
        return None

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    return hooks_dir


def is_installed(project_dir: Optional[Path] = None) -> bool:
    """Check if the auto-push hook is installed."""
    hooks_dir = get_hooks_dir(project_dir)
    if not hooks_dir:
        return False

    post_commit = hooks_dir / "post-commit"
    if not post_commit.exists():
        return False

    content = post_commit.read_text()
    return HOOK_MARKER in content


def install(
    project_dir: Optional[Path] = None,
    quiet: bool = False,
    multi_origin: bool = False
):
    """Install the auto-push post-commit hook."""
    if project_dir is None:
        project_dir = Path.cwd()

    hooks_dir = get_hooks_dir(project_dir)

    if not hooks_dir:
        if not quiet:
            console.print("[red]Error:[/] Not a git repository.")
            console.print(f"  Directory: {project_dir}")
        return False

    post_commit = hooks_dir / "post-commit"

    # Prepare hook content with multi-origin setting
    hook_content = POST_COMMIT_HOOK
    if multi_origin:
        hook_content = hook_content.replace(
            'SWOOSH_MULTI_ORIGIN="${SWOOSH_MULTI_ORIGIN:-false}"',
            'SWOOSH_MULTI_ORIGIN="${SWOOSH_MULTI_ORIGIN:-true}"'
        )

    # Check if hook already exists
    if post_commit.exists():
        content = post_commit.read_text()
        if HOOK_MARKER in content:
            if not quiet:
                console.print("[yellow]![/] Auto-push hook already installed.")
            return True

        # Append to existing hook
        if not quiet:
            console.print("[dim]Existing post-commit hook found, appending...[/]")
        new_content = content.rstrip() + "\n\n" + hook_content
        post_commit.write_text(new_content)
    else:
        post_commit.write_text(hook_content)

    # Make executable
    current_mode = post_commit.stat().st_mode
    post_commit.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    if not quiet:
        console.print("[green]✓[/] Auto-push hook installed.")
        console.print(f"  [dim]{post_commit}[/]")
        if multi_origin:
            remotes = get_remotes(project_dir)
            console.print(f"  Multi-origin: pushing to {len(remotes)} remote(s)")
        console.print()
        console.print("Every commit will now automatically push to origin.")

    return True


def remove(project_dir: Optional[Path] = None):
    """Remove the auto-push hook."""
    if project_dir is None:
        project_dir = Path.cwd()

    hooks_dir = get_hooks_dir(project_dir)

    if not hooks_dir:
        console.print("[red]Error:[/] Not a git repository.")
        return False

    post_commit = hooks_dir / "post-commit"

    if not post_commit.exists():
        console.print("[yellow]![/] No post-commit hook found.")
        return True

    content = post_commit.read_text()

    if HOOK_MARKER not in content:
        console.print("[yellow]![/] Auto-push hook not found in post-commit.")
        return True

    # Remove our hook section
    lines = content.split('\n')
    new_lines = []
    skip = False

    for line in lines:
        if HOOK_MARKER in line:
            skip = True
            continue
        if skip and line.startswith('#!/'):
            skip = False
        if not skip:
            new_lines.append(line)

    new_content = '\n'.join(new_lines).strip()

    if not new_content or new_content == "#!/bin/bash":
        post_commit.unlink()
        console.print("[green]✓[/] Auto-push hook removed.")
    else:
        post_commit.write_text(new_content + '\n')
        console.print("[green]✓[/] Auto-push hook removed (other hooks preserved).")

    return True


def status(project_dir: Optional[Path] = None):
    """Show hook status."""
    if project_dir is None:
        project_dir = Path.cwd()

    console.print()

    hooks_dir = get_hooks_dir(project_dir)

    if not hooks_dir:
        console.print(Panel(
            "[red]Not a git repository[/]\n\n"
            f"Directory: {project_dir}",
            title="Hook Status",
            expand=False
        ))
        return

    post_commit = hooks_dir / "post-commit"

    if not post_commit.exists():
        console.print(Panel(
            "[yellow]No post-commit hook[/]\n\n"
            "Auto-push is [red]disabled[/].\n\n"
            "Run [cyan]swoosh hook install[/] to enable.",
            title="Hook Status",
            expand=False
        ))
        return

    content = post_commit.read_text()

    if HOOK_MARKER in content:
        is_executable = os.access(post_commit, os.X_OK)
        multi_origin = 'SWOOSH_MULTI_ORIGIN:-true' in content

        remotes = get_remotes(project_dir)
        remote_list = ", ".join(r["name"] for r in remotes) if remotes else "none"

        console.print(Panel(
            f"[green]Auto-push hook installed[/]\n\n"
            f"Hook file: {post_commit}\n"
            f"Executable: {'[green]yes[/]' if is_executable else '[red]no[/]'}\n"
            f"Multi-origin: {'[cyan]yes[/]' if multi_origin else '[dim]no[/]'}\n"
            f"Remotes: {remote_list}\n\n"
            f"Every commit will automatically push.",
            title="Hook Status",
            expand=False
        ))

        if not is_executable:
            console.print()
            console.print("[yellow]Warning:[/] Hook is not executable.")
            console.print(f"  Run: chmod +x {post_commit}")
    else:
        console.print(Panel(
            "[yellow]Post-commit hook exists but no auto-push[/]\n\n"
            f"Hook file: {post_commit}\n\n"
            "Run [cyan]swoosh hook install[/] to add auto-push.",
            title="Hook Status",
            expand=False
        ))

    console.print()


def enable_multi_origin(project_dir: Optional[Path] = None):
    """Enable multi-origin push in existing hook."""
    if project_dir is None:
        project_dir = Path.cwd()

    hooks_dir = get_hooks_dir(project_dir)
    if not hooks_dir:
        console.print("[red]Error:[/] Not a git repository.")
        return

    post_commit = hooks_dir / "post-commit"

    if not post_commit.exists() or HOOK_MARKER not in post_commit.read_text():
        # Install with multi-origin
        install(project_dir, multi_origin=True)
        return

    content = post_commit.read_text()
    new_content = content.replace(
        'SWOOSH_MULTI_ORIGIN:-false',
        'SWOOSH_MULTI_ORIGIN:-true'
    )
    post_commit.write_text(new_content)

    remotes = get_remotes(project_dir)
    console.print(f"[green]✓[/] Multi-origin enabled for {len(remotes)} remote(s)")
