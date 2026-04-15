"""SSH/VPS deployment module for Swoosh."""

import os
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
import questionary

from swoosh.modules.utils import run_cmd, load_swoosh_config, is_git_repo

console = Console()


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
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=accept-new", host, command]
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


def deploy_target(
    target_name: str,
    target_config: dict,
    cwd: Optional[Path] = None,
    dry_run: bool = False,
):
    """Deploy to a specific target."""
    if cwd is None:
        cwd = Path.cwd()

    host = target_config.get("host")
    path = target_config.get("path")
    build_cmd = target_config.get("build")
    pre_deploy = target_config.get("pre_deploy")
    post_deploy = target_config.get("post_deploy")
    restart_cmd = target_config.get("restart")
    method = target_config.get("method", "rsync")  # rsync, git, docker

    if not host or not path:
        console.print(f"[red]Error:[/] Target '{target_name}' missing host or path.")
        return False

    console.print()
    console.print(Panel(
        f"[bold]Target:[/] {target_name}\n"
        f"[bold]Host:[/] {host}\n"
        f"[bold]Path:[/] {path}\n"
        f"[bold]Method:[/] {method}",
        title="[blue]Deploy[/]",
        expand=False
    ))
    console.print()

    if dry_run:
        console.print("[yellow]Dry run - no changes will be made.[/]")
        return True

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

        # 2. Pre-deploy (remote)
        if pre_deploy:
            task = progress.add_task("Running pre-deploy...", total=None)
            ok, output = run_ssh_command(host, f"cd {path} && {pre_deploy}")
            if ok:
                progress.update(task, description="[green]✓[/] Pre-deploy complete")
            else:
                progress.update(task, description=f"[yellow]![/] Pre-deploy warning")
            progress.remove_task(task)

        # 3. Deploy
        task = progress.add_task(f"Deploying via {method}...", total=None)

        if method == "rsync":
            ok, output = rsync_to_remote(str(cwd), host, path)
        elif method == "git":
            ok, output = run_ssh_command(host, f"cd {path} && git pull origin main")
        elif method == "docker":
            docker_cmd = target_config.get("docker_cmd", "docker compose up -d --build")
            ok, output = run_ssh_command(host, f"cd {path} && {docker_cmd}")
        else:
            ok, output = False, f"Unknown method: {method}"

        if ok:
            progress.update(task, description=f"[green]✓[/] Deployed via {method}")
        else:
            progress.update(task, description=f"[red]✗[/] Deploy failed")
            console.print(output)
            return False
        progress.remove_task(task)

        # 4. Post-deploy (remote)
        if post_deploy:
            task = progress.add_task("Running post-deploy...", total=None)
            ok, output = run_ssh_command(host, f"cd {path} && {post_deploy}")
            if ok:
                progress.update(task, description="[green]✓[/] Post-deploy complete")
            else:
                progress.update(task, description=f"[yellow]![/] Post-deploy warning")
            progress.remove_task(task)

        # 5. Restart service
        if restart_cmd:
            task = progress.add_task("Restarting service...", total=None)
            ok, output = run_ssh_command(host, restart_cmd)
            if ok:
                progress.update(task, description="[green]✓[/] Service restarted")
            else:
                progress.update(task, description=f"[yellow]![/] Restart warning")
            progress.remove_task(task)

    console.print()
    console.print(f"[green bold]✓ Deployed to {target_name}[/]")
    return True


def deploy(
    target: Optional[str] = None,
    dry_run: bool = False,
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

    deploy_target(target, targets[target], cwd, dry_run)


def list_targets(cwd: Optional[Path] = None):
    """List configured deploy targets."""
    targets = get_deploy_targets(cwd)

    if not targets:
        console.print("[yellow]No deploy targets configured.[/]")
        return

    console.print()
    for name, config in targets.items():
        console.print(Panel(
            f"[bold]Host:[/] {config.get('host', 'N/A')}\n"
            f"[bold]Path:[/] {config.get('path', 'N/A')}\n"
            f"[bold]Method:[/] {config.get('method', 'rsync')}\n"
            f"[bold]Build:[/] {config.get('build', 'None')}\n"
            f"[bold]Restart:[/] {config.get('restart', 'None')}",
            title=f"[cyan]{name}[/]",
            expand=False
        ))
    console.print()
