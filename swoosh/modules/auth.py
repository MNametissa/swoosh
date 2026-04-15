"""GitHub authentication module for Swoosh."""

import os
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import questionary

from swoosh.modules.utils import run_cmd

console = Console()


def check_ssh_github() -> tuple[bool, str]:
    """Check if SSH to GitHub is configured and working."""
    try:
        result = subprocess.run(
            ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=5", "git@github.com"],
            capture_output=True,
            text=True,
            timeout=10
        )
        # GitHub returns exit code 1 but with success message
        output = result.stdout + result.stderr
        if "successfully authenticated" in output.lower():
            # Extract username
            import re
            match = re.search(r"Hi ([^!]+)!", output)
            username = match.group(1) if match else "unknown"
            return True, username
        return False, output
    except Exception as e:
        return False, str(e)


def check_gh_auth() -> tuple[bool, Optional[str]]:
    """Check if gh CLI is authenticated."""
    ok, output = run_cmd(["gh", "auth", "status"])
    if ok:
        # Extract username
        import re
        match = re.search(r"Logged in to github\.com.*account\s+(\S+)", output, re.IGNORECASE)
        if match:
            return True, match.group(1)
        match = re.search(r"Logged in to github\.com as (\S+)", output, re.IGNORECASE)
        if match:
            return True, match.group(1)
        return True, None
    return False, None


def get_git_config(key: str) -> Optional[str]:
    """Get git config value."""
    ok, output = run_cmd(["git", "config", "--global", "--get", key])
    return output.strip() if ok and output.strip() else None


def set_git_config(key: str, value: str) -> bool:
    """Set git config value."""
    ok, _ = run_cmd(["git", "config", "--global", key, value])
    return ok


def find_ssh_keys() -> list[Path]:
    """Find existing SSH keys."""
    ssh_dir = Path.home() / ".ssh"
    if not ssh_dir.exists():
        return []

    keys = []
    for pattern in ["id_ed25519", "id_rsa", "id_ecdsa", "id_dsa"]:
        key_file = ssh_dir / pattern
        if key_file.exists():
            keys.append(key_file)
    return keys


def generate_ssh_key(email: str) -> Optional[Path]:
    """Generate a new SSH key."""
    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)

    key_path = ssh_dir / "id_ed25519"

    if key_path.exists():
        if not questionary.confirm(f"SSH key exists at {key_path}. Overwrite?", default=False).ask():
            return key_path

    console.print("[dim]Generating SSH key...[/]")
    ok, output = run_cmd([
        "ssh-keygen", "-t", "ed25519", "-C", email, "-f", str(key_path), "-N", ""
    ])

    if ok:
        return key_path
    else:
        console.print(f"[red]Failed to generate key:[/] {output}")
        return None


def add_ssh_to_github(pub_key_path: Path, token: Optional[str] = None) -> bool:
    """Add SSH key to GitHub account."""
    pub_key = pub_key_path.with_suffix(".pub")
    if not pub_key.exists():
        pub_key = Path(str(pub_key_path) + ".pub")

    if not pub_key.exists():
        console.print(f"[red]Public key not found:[/] {pub_key}")
        return False

    key_content = pub_key.read_text().strip()

    # Use gh CLI if authenticated
    ok, _ = run_cmd(["gh", "auth", "status"])
    if ok:
        import socket
        hostname = socket.gethostname()
        title = f"swoosh-{hostname}"

        ok, output = run_cmd(["gh", "ssh-key", "add", str(pub_key), "--title", title])
        if ok:
            return True
        elif "already exists" in output.lower():
            console.print("[dim]SSH key already added to GitHub[/]")
            return True
        else:
            console.print(f"[yellow]Could not add key via gh:[/] {output}")

    # Manual instructions
    console.print()
    console.print(Panel(
        f"[bold]Add this SSH key to GitHub:[/]\n\n"
        f"1. Go to: https://github.com/settings/ssh/new\n"
        f"2. Title: swoosh-{os.uname().nodename if hasattr(os, 'uname') else 'key'}\n"
        f"3. Key:\n[dim]{key_content[:50]}...{key_content[-30:]}[/]",
        title="[cyan]Manual Step Required[/]",
        expand=False
    ))

    # Copy to clipboard if possible
    try:
        if os.name == 'posix':
            if os.path.exists("/usr/bin/xclip"):
                subprocess.run(["xclip", "-selection", "clipboard"], input=key_content.encode(), check=True)
                console.print("[green]Key copied to clipboard![/]")
            elif os.path.exists("/usr/bin/pbcopy"):
                subprocess.run(["pbcopy"], input=key_content.encode(), check=True)
                console.print("[green]Key copied to clipboard![/]")
    except:
        pass

    console.print()
    questionary.press_any_key_to_continue("Press Enter after adding the key to GitHub...").ask()

    return True


def auth_with_token(token: str) -> bool:
    """Authenticate gh CLI with a personal access token."""
    console.print("[dim]Authenticating with token...[/]")

    try:
        # gh auth login --with-token reads from stdin
        result = subprocess.run(
            ["gh", "auth", "login", "--with-token"],
            input=token,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return True
        else:
            console.print(f"[red]Auth failed:[/] {result.stderr}")
            return False
    except Exception as e:
        console.print(f"[red]Auth error:[/] {e}")
        return False


def auth_with_oauth() -> bool:
    """Authenticate using gh's OAuth device flow."""
    console.print("[dim]Starting OAuth authentication...[/]")

    try:
        # Interactive OAuth flow
        result = subprocess.run(
            ["gh", "auth", "login", "--web", "-h", "github.com", "-p", "https"],
            timeout=120
        )
        return result.returncode == 0
    except Exception as e:
        console.print(f"[red]OAuth error:[/] {e}")
        return False


def status():
    """Show current authentication status."""
    console.print()

    table = Table(title="Authentication Status", show_header=True)
    table.add_column("Method", style="cyan")
    table.add_column("Status", style="white")
    table.add_column("Details", style="dim")

    # Git config
    git_name = get_git_config("user.name")
    git_email = get_git_config("user.email")
    if git_name and git_email:
        table.add_row("Git Config", "[green]configured[/]", f"{git_name} <{git_email}>")
    elif git_name or git_email:
        table.add_row("Git Config", "[yellow]partial[/]", f"name={git_name}, email={git_email}")
    else:
        table.add_row("Git Config", "[red]not configured[/]", "Run: swoosh auth")

    # SSH
    ssh_ok, ssh_user = check_ssh_github()
    if ssh_ok:
        table.add_row("SSH (GitHub)", "[green]working[/]", f"user: {ssh_user}")
    else:
        keys = find_ssh_keys()
        if keys:
            table.add_row("SSH (GitHub)", "[yellow]key exists[/]", f"{keys[0].name} (not added to GitHub?)")
        else:
            table.add_row("SSH (GitHub)", "[red]no key[/]", "Run: swoosh auth --ssh")

    # gh CLI
    gh_ok, gh_user = check_gh_auth()
    if gh_ok:
        table.add_row("GitHub CLI", "[green]authenticated[/]", f"user: {gh_user or 'unknown'}")
    else:
        table.add_row("GitHub CLI", "[red]not authenticated[/]", "Run: swoosh auth")

    console.print(table)
    console.print()


def login(
    method: Optional[str] = None,
    token: Optional[str] = None,
    username: Optional[str] = None,
    email: Optional[str] = None,
    generate_key: bool = False,
):
    """Authenticate with GitHub."""
    console.print()
    console.print(Panel("GitHub Authentication", expand=False))
    console.print()

    # Step 1: Git config (username, email)
    current_name = get_git_config("user.name")
    current_email = get_git_config("user.email")

    if not current_name or not current_email:
        console.print("[bold]Git Configuration[/]")

        if not username:
            username = questionary.text(
                "Your name (for commits):",
                default=current_name or ""
            ).ask()

        if not email:
            email = questionary.text(
                "Your email (for commits):",
                default=current_email or ""
            ).ask()

        if username:
            set_git_config("user.name", username)
            console.print(f"[green]✓[/] Set user.name = {username}")

        if email:
            set_git_config("user.email", email)
            console.print(f"[green]✓[/] Set user.email = {email}")

        console.print()
    else:
        console.print(f"[dim]Git config: {current_name} <{current_email}>[/]")
        email = email or current_email

    # Step 2: Check current auth status
    ssh_ok, ssh_user = check_ssh_github()
    gh_ok, gh_user = check_gh_auth()

    if ssh_ok and gh_ok:
        console.print(f"[green]✓[/] Already authenticated as [cyan]{gh_user or ssh_user}[/]")
        return True

    # Step 3: Choose auth method
    if not method:
        choices = []

        if ssh_ok:
            choices.append("ssh (already working)")
        else:
            keys = find_ssh_keys()
            if keys:
                choices.append("ssh (use existing key)")
            choices.append("ssh (generate new key)")

        choices.append("token (Personal Access Token)")
        choices.append("oauth (browser login)")

        method = questionary.select(
            "Authentication method:",
            choices=choices
        ).ask()

        if not method:
            return False

    # Step 4: Authenticate
    if "ssh" in method.lower():
        keys = find_ssh_keys()

        if "generate" in method.lower() or generate_key or not keys:
            if not email:
                email = questionary.text("Email for SSH key:").ask()
            key_path = generate_ssh_key(email or "swoosh@local")
            if key_path:
                console.print(f"[green]✓[/] Generated SSH key: {key_path}")
                add_ssh_to_github(key_path)
        elif keys:
            console.print(f"[dim]Using existing key: {keys[0]}[/]")
            if not ssh_ok:
                add_ssh_to_github(keys[0])

        # Verify SSH works now
        ssh_ok, ssh_user = check_ssh_github()
        if ssh_ok:
            console.print(f"[green]✓[/] SSH authentication working ({ssh_user})")
        else:
            console.print("[yellow]![/] SSH not yet working. Key may need to be added to GitHub.")

        # Still need gh for API operations - use SSH for git
        if not gh_ok:
            console.print()
            console.print("[dim]Setting up GitHub CLI (for releases, PRs, etc.)...[/]")
            if token:
                auth_with_token(token)
            else:
                # Try OAuth as fallback
                auth_with_oauth()

    elif "token" in method.lower():
        if not token:
            token = questionary.password(
                "Personal Access Token (from https://github.com/settings/tokens):"
            ).ask()

        if token:
            if auth_with_token(token):
                console.print("[green]✓[/] Authenticated with token")
            else:
                return False

    elif "oauth" in method.lower():
        if auth_with_oauth():
            console.print("[green]✓[/] Authenticated via OAuth")
        else:
            return False

    # Final status
    console.print()
    gh_ok, gh_user = check_gh_auth()
    if gh_ok:
        console.print(Panel(
            f"[green bold]Authenticated as {gh_user}[/]\n\n"
            f"You're ready to use Swoosh!",
            expand=False
        ))
        return True
    else:
        console.print("[yellow]Authentication incomplete. Some features may not work.[/]")
        return False


def logout():
    """Logout from GitHub."""
    ok, _ = run_cmd(["gh", "auth", "logout", "-h", "github.com"])
    if ok:
        console.print("[green]✓[/] Logged out from GitHub")
    else:
        console.print("[yellow]Not logged in[/]")
