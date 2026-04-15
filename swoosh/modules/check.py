"""System dependency checker."""

import shutil
import subprocess
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def check_command(cmd: str) -> tuple[bool, str]:
    """Check if a command exists and get its version."""
    path = shutil.which(cmd)
    if not path:
        return False, "Not found"

    try:
        if cmd == "git":
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip().replace("git version ", "")
        elif cmd == "gh":
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.split("\n")[0].replace("gh version ", "").split(" ")[0]
        elif cmd == "glab":
            result = subprocess.run(
                ["glab", "--version"],
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.split("\n")[0]
        else:
            version = "installed"
        return True, version
    except Exception as e:
        return True, f"installed (version check failed: {e})"


def check_gh_auth() -> tuple[bool, str]:
    """Check if gh CLI is authenticated."""
    try:
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n") + result.stderr.split("\n"):
                if "Logged in to" in line:
                    return True, line.strip()
            return True, "Authenticated"
        return False, "Not authenticated"
    except FileNotFoundError:
        return False, "gh CLI not installed"
    except Exception as e:
        return False, str(e)


def check_ssh() -> tuple[bool, str]:
    """Check if SSH is configured."""
    try:
        result = subprocess.run(
            ["ssh", "-T", "git@github.com"],
            capture_output=True, text=True, timeout=10
        )
        # GitHub returns exit code 1 but says "successfully authenticated"
        output = result.stdout + result.stderr
        if "successfully authenticated" in output.lower():
            return True, "GitHub SSH configured"
        elif "permission denied" in output.lower():
            return False, "SSH key not authorized"
        return False, "SSH not configured"
    except Exception:
        return False, "SSH check failed"


def check_git_config() -> dict[str, str]:
    """Check git global configuration."""
    config = {}
    for key in ["user.name", "user.email"]:
        try:
            result = subprocess.run(
                ["git", "config", "--global", key],
                capture_output=True, text=True, timeout=5
            )
            config[key] = result.stdout.strip() or "[not set]"
        except Exception:
            config[key] = "[error]"
    return config


def run_doctor():
    """Run full system check."""
    console.print()
    console.print(Panel("[bold blue]Swoosh Doctor[/] - System Check", expand=False))
    console.print()

    # Dependencies table
    table = Table(title="Dependencies", show_header=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    all_ok = True

    # Check git
    git_ok, git_version = check_command("git")
    table.add_row(
        "git",
        "[green]✓[/]" if git_ok else "[red]✗[/]",
        git_version
    )
    if not git_ok:
        all_ok = False

    # Check gh CLI
    gh_ok, gh_version = check_command("gh")
    table.add_row(
        "gh (GitHub CLI)",
        "[green]✓[/]" if gh_ok else "[red]✗[/]",
        gh_version
    )
    if not gh_ok:
        all_ok = False

    # Check glab (optional)
    glab_ok, glab_version = check_command("glab")
    table.add_row(
        "glab (GitLab CLI)",
        "[green]✓[/]" if glab_ok else "[dim]○[/]",
        glab_version if glab_ok else "Optional"
    )

    # Check gh auth
    auth_ok, auth_status = check_gh_auth()
    table.add_row(
        "GitHub Auth",
        "[green]✓[/]" if auth_ok else "[yellow]![/]",
        auth_status
    )

    # Check SSH
    ssh_ok, ssh_status = check_ssh()
    table.add_row(
        "SSH (GitHub)",
        "[green]✓[/]" if ssh_ok else "[dim]○[/]",
        ssh_status
    )

    console.print(table)
    console.print()

    # Git config table
    git_config = check_git_config()
    config_table = Table(title="Git Configuration", show_header=True)
    config_table.add_column("Setting", style="cyan")
    config_table.add_column("Value", style="white")

    for key, value in git_config.items():
        config_table.add_row(key, value)

    console.print(config_table)
    console.print()

    # Summary
    if all_ok and auth_ok:
        console.print("[green]✓ All checks passed![/] Swoosh is ready to use.")
    elif all_ok:
        console.print("[yellow]! Some optional checks failed.[/]")
        if not auth_ok:
            console.print("  Run [cyan]gh auth login[/] to authenticate with GitHub.")
    else:
        console.print("[red]✗ Some required dependencies are missing.[/]")
        if not git_ok:
            console.print("  Install git: https://git-scm.com/downloads")
        if not gh_ok:
            console.print("  Install gh CLI: https://cli.github.com/")

    console.print()
    return all_ok


def ensure_dependencies() -> bool:
    """Quick check that all dependencies are available. Returns True if OK."""
    git_ok, _ = check_command("git")
    gh_ok, _ = check_command("gh")
    auth_ok, _ = check_gh_auth()

    if not git_ok:
        console.print("[red]Error:[/] git is not installed.")
        return False
    if not gh_ok:
        console.print("[red]Error:[/] gh CLI is not installed.")
        return False
    if not auth_ok:
        console.print("[red]Error:[/] gh CLI is not authenticated. Run: gh auth login")
        return False

    return True
