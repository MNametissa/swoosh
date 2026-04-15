"""Swoosh configuration management."""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import questionary

console = Console()

CONFIG_DIR = Path.home() / ".config" / "swoosh"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "github_user": None,
    "default_template": "generic",
    "default_private": False,
    "auto_push": True,
    "conventional_commits": True,
    "multi_origin": False,
}


def load_config() -> dict:
    """Load configuration from file."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                config = json.load(f)
                return {**DEFAULT_CONFIG, **config}
        except Exception:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """Save configuration to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def show_config():
    """Display current configuration."""
    config = load_config()

    console.print()
    table = Table(title="Swoosh Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Source", style="dim")

    source = "config file" if CONFIG_FILE.exists() else "default"

    for key, value in config.items():
        display_value = str(value) if value is not None else "[dim]not set[/]"
        table.add_row(key, display_value, source)

    console.print(table)
    console.print()
    console.print(f"[dim]Config file: {CONFIG_FILE}[/]")
    console.print()


def update_config(
    github_user: Optional[str] = None,
    default_template: Optional[str] = None,
    default_private: Optional[bool] = None,
    auto_push: Optional[bool] = None,
    conventional_commits: Optional[bool] = None,
    multi_origin: Optional[bool] = None,
):
    """Update specific configuration values."""
    config = load_config()

    if github_user is not None:
        config["github_user"] = github_user
        console.print(f"[green]✓[/] Set github_user = {github_user}")

    if default_template is not None:
        valid_templates = ["generic", "node", "python", "rust", "go"]
        if default_template not in valid_templates:
            console.print(f"[yellow]Warning:[/] Unknown template '{default_template}'")
        config["default_template"] = default_template
        console.print(f"[green]✓[/] Set default_template = {default_template}")

    if default_private is not None:
        config["default_private"] = default_private
        console.print(f"[green]✓[/] Set default_private = {default_private}")

    if auto_push is not None:
        config["auto_push"] = auto_push
        console.print(f"[green]✓[/] Set auto_push = {auto_push}")

    if conventional_commits is not None:
        config["conventional_commits"] = conventional_commits
        console.print(f"[green]✓[/] Set conventional_commits = {conventional_commits}")

    if multi_origin is not None:
        config["multi_origin"] = multi_origin
        console.print(f"[green]✓[/] Set multi_origin = {multi_origin}")

    save_config(config)
    console.print()
    console.print(f"[dim]Configuration saved to {CONFIG_FILE}[/]")


def interactive_config():
    """Interactive configuration wizard."""
    console.print()
    console.print(Panel("[bold blue]Swoosh Configuration Wizard[/]", expand=False))
    console.print()

    config = load_config()

    # GitHub username
    github_user = questionary.text(
        "GitHub username:",
        default=config.get("github_user") or "",
    ).ask()

    if github_user:
        config["github_user"] = github_user

    # Default template
    template = questionary.select(
        "Default CI template:",
        choices=["generic", "node", "python", "rust", "go"],
        default=config.get("default_template", "generic"),
    ).ask()

    if template:
        config["default_template"] = template

    # Default visibility
    private = questionary.confirm(
        "Create private repositories by default?",
        default=config.get("default_private", False),
    ).ask()

    if private is not None:
        config["default_private"] = private

    # Auto-push
    auto_push = questionary.confirm(
        "Enable auto-push on commit by default?",
        default=config.get("auto_push", True),
    ).ask()

    if auto_push is not None:
        config["auto_push"] = auto_push

    # Conventional commits
    conventional = questionary.confirm(
        "Use conventional commits by default?",
        default=config.get("conventional_commits", True),
    ).ask()

    if conventional is not None:
        config["conventional_commits"] = conventional

    save_config(config)

    console.print()
    console.print("[green]✓ Configuration saved![/]")
    console.print()
    show_config()
