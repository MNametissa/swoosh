"""SSH/VPS deployment module for Swoosh."""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary

from swoosh.modules.utils import run_cmd, load_swoosh_config, is_git_repo

console = Console()

# Default number of releases to keep
DEFAULT_KEEP_RELEASES = 5


def get_deploy_targets(cwd: Optional[Path] = None) -> dict:
    """Get deploy targets from swoosh.yaml."""
    config = load_swoosh_config(cwd)
    return config.get("deploy", {})


def run_ssh_command(
    host: str,
    command: str,
    timeout: int = 300
) -> tuple[bool, str]:
    """Run a command on remote host via SSH."""
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10", host, command]
    return run_cmd(ssh_cmd, timeout=timeout)


def rsync_to_remote(
    local_path: str,
    host: str,
    remote_path: str,
    exclude: list[str] = None
) -> tuple[bool, str]:
    """Rsync files to remote server."""
    cmd = [
        "rsync", "-avz", "--delete",
        "-e", "ssh -o StrictHostKeyChecking=accept-new"
    ]

    exclude = exclude or [".git", "node_modules", "__pycache__", ".env"]
    for pattern in exclude:
        cmd.extend(["--exclude", pattern])

    cmd.extend([f"{local_path}/", f"{host}:{remote_path}/"])

    return run_cmd(cmd, timeout=600)


def health_check(
    host: str,
    health_config: dict,
    timeout: int = 30
) -> tuple[bool, str]:
    """Run health check on deployed application."""
    check_type = health_config.get("type", "http")

    if check_type == "http":
        url = health_config.get("url", "http://localhost")
        expected_status = health_config.get("status", 200)

        # Use curl on remote
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' --max-time {timeout} {url}"
        ok, output = run_ssh_command(host, cmd, timeout=timeout + 10)

        if ok:
            try:
                status_code = int(output.strip())
                if status_code == expected_status:
                    return True, f"HTTP {status_code} OK"
                else:
                    return False, f"Expected {expected_status}, got {status_code}"
            except ValueError:
                return False, f"Invalid response: {output}"
        return False, output

    elif check_type == "tcp":
        port = health_config.get("port", 80)
        host_target = health_config.get("host", "localhost")

        cmd = f"nc -z -w{timeout} {host_target} {port} && echo 'OK' || echo 'FAIL'"
        ok, output = run_ssh_command(host, cmd, timeout=timeout + 10)

        if ok and "OK" in output:
            return True, f"TCP port {port} open"
        return False, f"TCP port {port} not responding"

    elif check_type == "command":
        command = health_config.get("command")
        if not command:
            return False, "No health check command specified"

        ok, output = run_ssh_command(host, command, timeout=timeout)
        return ok, output[:100] if output else "OK"

    elif check_type == "process":
        process_name = health_config.get("process")
        if not process_name:
            return False, "No process name specified"

        cmd = f"pgrep -f '{process_name}' > /dev/null && echo 'running' || echo 'not running'"
        ok, output = run_ssh_command(host, cmd, timeout=timeout)

        if ok and "running" in output:
            return True, f"Process '{process_name}' running"
        return False, f"Process '{process_name}' not found"

    return False, f"Unknown health check type: {check_type}"


def create_release_dir(
    host: str,
    base_path: str,
    keep_releases: int = DEFAULT_KEEP_RELEASES
) -> tuple[bool, str]:
    """Create timestamped release directory and symlink."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    releases_dir = f"{base_path}/releases"
    release_path = f"{releases_dir}/{timestamp}"
    current_link = f"{base_path}/current"

    # Create releases directory if not exists
    cmd = f"""
        mkdir -p {releases_dir} && \
        mkdir -p {release_path} && \
        echo "{release_path}"
    """
    ok, output = run_ssh_command(host, cmd)

    if not ok:
        return False, output

    return True, release_path


def link_current_release(
    host: str,
    base_path: str,
    release_path: str
) -> tuple[bool, str]:
    """Create/update symlink to current release."""
    current_link = f"{base_path}/current"

    cmd = f"ln -sfn {release_path} {current_link}"
    return run_ssh_command(host, cmd)


def cleanup_old_releases(
    host: str,
    base_path: str,
    keep: int = DEFAULT_KEEP_RELEASES
) -> tuple[bool, str]:
    """Remove old releases, keeping the most recent ones."""
    releases_dir = f"{base_path}/releases"

    # List releases, sort by name (timestamp), remove old ones
    cmd = f"""
        cd {releases_dir} && \
        ls -1d */ 2>/dev/null | head -n -{keep} | xargs -r rm -rf
    """
    return run_ssh_command(host, cmd)


def get_releases(
    host: str,
    base_path: str
) -> list[str]:
    """Get list of available releases."""
    releases_dir = f"{base_path}/releases"

    cmd = f"ls -1t {releases_dir} 2>/dev/null || echo ''"
    ok, output = run_ssh_command(host, cmd)

    if ok and output:
        return [r.strip() for r in output.split("\n") if r.strip()]
    return []


def get_current_release(
    host: str,
    base_path: str
) -> Optional[str]:
    """Get current release name."""
    current_link = f"{base_path}/current"

    cmd = f"readlink {current_link} 2>/dev/null | xargs basename"
    ok, output = run_ssh_command(host, cmd)

    if ok and output.strip():
        return output.strip()
    return None


def deploy_target(
    target_name: str,
    target_config: dict,
    cwd: Optional[Path] = None,
    dry_run: bool = False,
    skip_health_check: bool = False,
):
    """Deploy to a specific target with release management."""
    if cwd is None:
        cwd = Path.cwd()

    host = target_config.get("host")
    path = target_config.get("path")
    build_cmd = target_config.get("build")
    pre_deploy = target_config.get("pre_deploy")
    post_deploy = target_config.get("post_deploy")
    restart_cmd = target_config.get("restart")
    method = target_config.get("method", "rsync")
    keep_releases = target_config.get("keep_releases", DEFAULT_KEEP_RELEASES)
    health = target_config.get("health_check", None)
    use_releases = target_config.get("releases", True)  # Enable release dirs by default

    if not host or not path:
        console.print(f"[red]Error:[/] Target '{target_name}' missing host or path.")
        return False

    console.print()
    console.print(Panel(
        f"[bold]Target:[/] {target_name}\n"
        f"[bold]Host:[/] {host}\n"
        f"[bold]Path:[/] {path}\n"
        f"[bold]Method:[/] {method}\n"
        f"[bold]Releases:[/] {'enabled' if use_releases else 'disabled'}\n"
        f"[bold]Health check:[/] {'configured' if health else 'none'}",
        title="[blue]Deploy[/]",
        expand=False
    ))
    console.print()

    if dry_run:
        console.print("[yellow]Dry run - no changes will be made.[/]")
        return True

    release_path = path  # Default to direct deploy

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        # 1. Local build
        if build_cmd:
            task = progress.add_task("Running local build...", total=None)
            ok, output = run_cmd(build_cmd.split(), cwd=cwd, timeout=300)
            if ok:
                progress.update(task, description="[green]✓[/] Build complete")
            else:
                progress.update(task, description=f"[red]✗[/] Build failed")
                console.print(output)
                return False
            progress.remove_task(task)

        # 2. Create release directory (if using releases)
        if use_releases:
            task = progress.add_task("Creating release directory...", total=None)
            ok, release_path = create_release_dir(host, path, keep_releases)
            if ok:
                progress.update(task, description=f"[green]✓[/] Release: {release_path.split('/')[-1]}")
            else:
                progress.update(task, description=f"[red]✗[/] Failed to create release dir")
                console.print(release_path)
                return False
            progress.remove_task(task)

        # 3. Pre-deploy (remote)
        if pre_deploy:
            task = progress.add_task("Running pre-deploy...", total=None)
            ok, output = run_ssh_command(host, f"cd {path} && {pre_deploy}")
            if ok:
                progress.update(task, description="[green]✓[/] Pre-deploy complete")
            else:
                progress.update(task, description=f"[yellow]![/] Pre-deploy warning")
            progress.remove_task(task)

        # 4. Deploy files
        task = progress.add_task(f"Deploying via {method}...", total=None)

        deploy_path = release_path if use_releases else path

        if method == "rsync":
            ok, output = rsync_to_remote(str(cwd), host, deploy_path)
        elif method == "git":
            if use_releases:
                ok, output = run_ssh_command(host, f"cd {deploy_path} && git clone --depth 1 . .")
            else:
                ok, output = run_ssh_command(host, f"cd {path} && git pull origin main")
        elif method == "docker":
            docker_cmd = target_config.get("docker_cmd", "docker compose up -d --build")
            ok, output = run_ssh_command(host, f"cd {deploy_path} && {docker_cmd}")
        else:
            ok, output = False, f"Unknown method: {method}"

        if ok:
            progress.update(task, description=f"[green]✓[/] Deployed via {method}")
        else:
            progress.update(task, description=f"[red]✗[/] Deploy failed")
            console.print(output)
            return False
        progress.remove_task(task)

        # 5. Link current release
        if use_releases:
            task = progress.add_task("Linking current release...", total=None)
            ok, output = link_current_release(host, path, release_path)
            if ok:
                progress.update(task, description="[green]✓[/] Linked current → release")
            else:
                progress.update(task, description=f"[red]✗[/] Link failed")
                return False
            progress.remove_task(task)

        # 6. Post-deploy (remote)
        if post_deploy:
            task = progress.add_task("Running post-deploy...", total=None)
            work_dir = f"{path}/current" if use_releases else path
            ok, output = run_ssh_command(host, f"cd {work_dir} && {post_deploy}")
            if ok:
                progress.update(task, description="[green]✓[/] Post-deploy complete")
            else:
                progress.update(task, description=f"[yellow]![/] Post-deploy warning")
            progress.remove_task(task)

        # 7. Restart service
        if restart_cmd:
            task = progress.add_task("Restarting service...", total=None)
            ok, output = run_ssh_command(host, restart_cmd)
            if ok:
                progress.update(task, description="[green]✓[/] Service restarted")
            else:
                progress.update(task, description=f"[yellow]![/] Restart warning")
            progress.remove_task(task)

        # 8. Health check
        if health and not skip_health_check:
            task = progress.add_task("Running health check...", total=None)

            # Wait a moment for service to start
            import time
            time.sleep(health.get("delay", 3))

            retries = health.get("retries", 3)
            retry_delay = health.get("retry_delay", 5)

            for attempt in range(retries):
                ok, msg = health_check(host, health)
                if ok:
                    progress.update(task, description=f"[green]✓[/] Health check passed: {msg}")
                    break
                else:
                    if attempt < retries - 1:
                        progress.update(task, description=f"[yellow]Retry {attempt + 1}/{retries}...[/]")
                        time.sleep(retry_delay)
            else:
                progress.update(task, description=f"[red]✗[/] Health check failed: {msg}")
                console.print()
                console.print("[yellow]Warning:[/] Health check failed. Consider rolling back:")
                console.print(f"  [cyan]swoosh deploy rollback {target_name}[/]")
                return False

            progress.remove_task(task)

        # 9. Cleanup old releases
        if use_releases:
            task = progress.add_task("Cleaning old releases...", total=None)
            cleanup_old_releases(host, path, keep_releases)
            progress.update(task, description=f"[green]✓[/] Keeping {keep_releases} releases")
            progress.remove_task(task)

    console.print()
    console.print(f"[green bold]✓ Deployed to {target_name}[/]")
    return True


def rollback(
    target: str,
    release: Optional[str] = None,
    cwd: Optional[Path] = None,
):
    """Rollback to a previous release."""
    if cwd is None:
        cwd = Path.cwd()

    targets = get_deploy_targets(cwd)

    if target not in targets:
        console.print(f"[red]Error:[/] Unknown target '{target}'")
        return False

    config = targets[target]
    host = config.get("host")
    path = config.get("path")
    restart_cmd = config.get("restart")

    if not host or not path:
        console.print("[red]Error:[/] Invalid target configuration")
        return False

    # Get available releases
    releases = get_releases(host, path)
    current = get_current_release(host, path)

    if not releases:
        console.print("[yellow]No releases found.[/]")
        return False

    console.print()
    console.print(f"Current release: [cyan]{current}[/]")
    console.print(f"Available releases: {len(releases)}")
    console.print()

    # Select release
    if not release:
        # Filter out current release
        available = [r for r in releases if r != current]

        if not available:
            console.print("[yellow]No previous releases to rollback to.[/]")
            return False

        release = questionary.select(
            "Select release to rollback to:",
            choices=available
        ).ask()

        if not release:
            console.print("[yellow]Cancelled.[/]")
            return False

    if release not in releases:
        console.print(f"[red]Error:[/] Release '{release}' not found")
        return False

    # Confirm
    if not questionary.confirm(
        f"Rollback {target} to {release}?",
        default=False
    ).ask():
        console.print("[yellow]Cancelled.[/]")
        return False

    console.print()

    # Perform rollback
    release_path = f"{path}/releases/{release}"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:

        task = progress.add_task("Rolling back...", total=None)
        ok, output = link_current_release(host, path, release_path)

        if ok:
            progress.update(task, description=f"[green]✓[/] Rolled back to {release}")
        else:
            progress.update(task, description=f"[red]✗[/] Rollback failed")
            console.print(output)
            return False
        progress.remove_task(task)

        # Restart if configured
        if restart_cmd:
            task = progress.add_task("Restarting service...", total=None)
            ok, output = run_ssh_command(host, restart_cmd)
            if ok:
                progress.update(task, description="[green]✓[/] Service restarted")
            else:
                progress.update(task, description=f"[yellow]![/] Restart warning")
            progress.remove_task(task)

    console.print()
    console.print(f"[green bold]✓ Rolled back to {release}[/]")
    return True


def releases_list(
    target: str,
    cwd: Optional[Path] = None,
):
    """List releases for a target."""
    if cwd is None:
        cwd = Path.cwd()

    targets = get_deploy_targets(cwd)

    if target not in targets:
        console.print(f"[red]Error:[/] Unknown target '{target}'")
        return

    config = targets[target]
    host = config.get("host")
    path = config.get("path")

    releases = get_releases(host, path)
    current = get_current_release(host, path)

    if not releases:
        console.print("[yellow]No releases found.[/]")
        return

    console.print()
    table = Table(title=f"Releases for {target}", show_header=True)
    table.add_column("Release", style="cyan")
    table.add_column("Status", style="white")

    for rel in releases:
        status = "[green]current[/]" if rel == current else ""
        table.add_row(rel, status)

    console.print(table)
    console.print()


def deploy(
    target: Optional[str] = None,
    dry_run: bool = False,
    skip_health_check: bool = False,
    cwd: Optional[Path] = None,
):
    """Deploy to a target environment."""
    if cwd is None:
        cwd = Path.cwd()

    targets = get_deploy_targets(cwd)

    if not targets:
        console.print("[yellow]No deploy targets configured.[/]")
        console.print("\nCreate [cyan]swoosh.yaml[/] with deploy config:")
        console.print("""
[dim]deploy:
  production:
    host: user@server.com
    path: /var/www/app
    method: rsync
    build: npm run build
    restart: systemctl restart app
    releases: true
    keep_releases: 5
    health_check:
      type: http
      url: http://localhost:3000/health
      status: 200
      retries: 3
  staging:
    host: user@staging.com
    path: /var/www/staging[/]
""")
        return

    # Select target
    if not target:
        if len(targets) == 1:
            target = list(targets.keys())[0]
        else:
            target = questionary.select(
                "Deploy target:",
                choices=list(targets.keys())
            ).ask()

            if not target:
                console.print("[yellow]Cancelled.[/]")
                return

    if target not in targets:
        console.print(f"[red]Error:[/] Unknown target '{target}'")
        console.print(f"Available: {', '.join(targets.keys())}")
        return

    # Confirm
    if not dry_run:
        if not questionary.confirm(
            f"Deploy to {target}?",
            default=False
        ).ask():
            console.print("[yellow]Cancelled.[/]")
            return

    deploy_target(target, targets[target], cwd, dry_run, skip_health_check)


def list_targets(cwd: Optional[Path] = None):
    """List configured deploy targets."""
    targets = get_deploy_targets(cwd)

    if not targets:
        console.print("[yellow]No deploy targets configured.[/]")
        return

    console.print()
    for name, config in targets.items():
        health = config.get("health_check")
        health_str = f"{health.get('type', 'http')} → {health.get('url', health.get('port', 'N/A'))}" if health else "None"

        console.print(Panel(
            f"[bold]Host:[/] {config.get('host', 'N/A')}\n"
            f"[bold]Path:[/] {config.get('path', 'N/A')}\n"
            f"[bold]Method:[/] {config.get('method', 'rsync')}\n"
            f"[bold]Build:[/] {config.get('build', 'None')}\n"
            f"[bold]Restart:[/] {config.get('restart', 'None')}\n"
            f"[bold]Releases:[/] {config.get('keep_releases', DEFAULT_KEEP_RELEASES)}\n"
            f"[bold]Health:[/] {health_str}",
            title=f"[cyan]{name}[/]",
            expand=False
        ))
    console.print()
