"""
Typer CLI for pwm.

This is the user-facing command surface. All behavior should match the
descriptions and contracts in SPEC.md and the spirit of the project
(educational, conservative crypto, pleasant but safe UX).

Run with `pwm` after `pip install -e .`
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print as rprint

from . import __version__
from .vault import Vault, get_default_vault_path
from .generator import generate_password
from .clipboard import copy_to_clipboard
from .crypto import VaultDecryptionError


app = typer.Typer(
    name="pwm",
    help="Local-first password manager. Single encrypted vault (Argon2id + AES-GCM). Educational project.",
    add_completion=True,
    rich_markup_mode="rich",
)
console = Console()


def _get_vault(vault_path: Optional[Path]) -> Vault:
    return Vault(vault_path)


def _prompt_master(prompt: str = "Master password: ") -> str:
    """Hidden prompt for the master password."""
    pw = getpass.getpass(prompt)
    if not pw:
        rprint("[red]Master password cannot be empty.[/red]")
        raise typer.Exit(code=1)
    return pw


def _prompt_new_master() -> str:
    pw1 = getpass.getpass("New master password: ")
    pw2 = getpass.getpass("Confirm new master password: ")
    if not pw1:
        rprint("[red]Master password cannot be empty.[/red]")
        raise typer.Exit(code=1)
    if pw1 != pw2:
        rprint("[red]Passwords do not match.[/red]")
        raise typer.Exit(code=1)
    return pw1


def _require_vault_exists(v: Vault) -> None:
    if not v.exists():
        rprint("[red]No vault found.[/red]")
        rprint("Run [bold]pwm init[/bold] to create one.")
        raise typer.Exit(code=1)


def _unlock(v: Vault, master: str | None = None) -> None:
    if v.is_unlocked():
        return
    if master is None:
        master = _prompt_master()
    try:
        with console.status("[bold green]Unlocking vault (Argon2 KDF running)..."):
            v.unlock(master)
    except VaultDecryptionError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    except FileNotFoundError:
        rprint("[red]Vault file not found.[/red]")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------
# Global options
# ---------------------------------------------------------------------

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    vault_path: Optional[Path] = typer.Option(
        None,
        "--vault-path",
        "-p",
        help="Override the default vault location (useful for testing or multiple vaults).",
        exists=False,
        file_okay=True,
        dir_okay=False,
        resolve_path=True,
    ),
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        help="Show version and exit.",
        is_eager=True,
    ),
):
    if version:
        rprint(f"pwm {__version__}")
        raise typer.Exit()

    # Store the chosen path on the context so commands can retrieve it
    ctx.obj = {"vault_path": vault_path}


def _get_vault_from_ctx(ctx: typer.Context) -> Vault:
    vault_path = ctx.obj.get("vault_path") if ctx.obj else None
    return _get_vault(vault_path)


# ---------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------

@app.command()
def init(ctx: typer.Context):
    """Initialize a new vault (set master password)."""
    v = _get_vault_from_ctx(ctx)
    if v.exists():
        rprint("[red]Vault already exists.[/red] Use [bold]pwm change-master[/bold] if you want to change it.")
        raise typer.Exit(code=1)

    rprint("[yellow]This will create a new encrypted vault.[/yellow]")
    master = _prompt_new_master()

    try:
        v.create(master)
    except Exception as e:
        rprint(f"[red]Failed to create vault: {e}[/red]")
        raise typer.Exit(code=1)

    path = v.vault_path
    rprint(f"[green]Vault created successfully at[/green] {path}")
    rprint("[bold yellow]IMPORTANT:[/bold yellow] Back up this file regularly. It is the only copy of your data.")


@app.command()
def generate(
    ctx: typer.Context,
    length: int = typer.Option(20, "--length", "-l", min=4, help="Password length"),
    no_upper: bool = typer.Option(False, "--no-upper", help="Exclude uppercase letters"),
    no_lower: bool = typer.Option(False, "--no-lower", help="Exclude lowercase letters"),
    no_digits: bool = typer.Option(False, "--no-digits", help="Exclude digits"),
    no_symbols: bool = typer.Option(False, "--no-symbols", help="Exclude symbols"),
    symbols: str = typer.Option(None, "--symbols", help="Custom symbol characters"),
    exclude: str = typer.Option(None, "--exclude", help="Characters to exclude (e.g. ambiguous ones)"),
    copy: bool = typer.Option(False, "--copy", "-c", help="Also copy the generated password to clipboard"),
):
    """Generate a strong customizable password (uses cryptographically secure randomness)."""
    pw = generate_password(
        length=length,
        use_upper=not no_upper,
        use_lower=not no_lower,
        use_digits=not no_digits,
        use_symbols=not no_symbols,
        symbols=symbols or "!@#$%^&*()_+-=[]{}|;:,.<>?",
        exclude=exclude or "0O1lI|`'\"\\",
    )

    rprint(f"[bold green]{pw}[/bold green]")

    if copy:
        copy_to_clipboard(pw)
        rprint("[dim]Copied to clipboard.[/dim]")
        rprint("[yellow]Remember: clipboard contents can be read by other processes.[/yellow]")


@app.command()
def add(
    ctx: typer.Context,
    label: str = typer.Option(..., "--label", "-l", help="Human label for the entry (e.g. Gmail, Netflix)"),
    username: Optional[str] = typer.Option(None, "--username", "-u"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Provide password directly (insecure in shell history)"),
    generate: bool = typer.Option(False, "--generate", "-g", help="Generate a strong password instead of prompting"),
    url: Optional[str] = typer.Option(None, "--url"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Repeatable tag (e.g. --tag work --tag email)"),
    show_password: bool = typer.Option(False, "--show-password", help="Show the password after adding (not recommended)"),
):
    """Add a new credential entry."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)

    master = _prompt_master()
    _unlock(v, master)

    if password and generate:
        rprint("[red]Cannot use both --password and --generate.[/red]")
        raise typer.Exit(1)

    if generate:
        pw = generate_password()
    elif password:
        pw = password
    else:
        pw = getpass.getpass("Password (leave empty to generate): ").strip()
        if not pw:
            pw = generate_password()
            rprint("[dim]Generated a strong password for you.[/dim]")

    try:
        entry = v.add(
            label=label,
            username=username,
            password=pw,
            url=url,
            notes=notes,
            tags=tag,
        )
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    rprint(f"[green]Added entry[/green] [bold]{label}[/bold]")
    if show_password:
        rprint(f"Password: [bold red]{entry.password}[/bold red]")
    else:
        rprint("[dim](password hidden — use `pwm copy` or `pwm get --show-password`)[/dim]")


@app.command("list")
def list_entries(
    ctx: typer.Context,
    show: bool = typer.Option(False, "--show", "--show-password", help="Show passwords in the table (dangerous)"),
    tag: Optional[str] = typer.Option(None, "--tag", help="Filter to entries containing this tag"),
):
    """List all entries (passwords hidden by default)."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)
    _unlock(v)

    entries = v.list_all()
    if tag:
        entries = [e for e in entries if tag in e.tags]

    if not entries:
        rprint("[dim]No entries.[/dim]")
        return

    table = Table(title="pwm vault", show_header=True, header_style="bold")
    table.add_column("Label", style="cyan")
    table.add_column("Username")
    table.add_column("URL")
    table.add_column("Tags")
    table.add_column("Updated")
    if show:
        table.add_column("Password", style="red")

    for e in sorted(entries, key=lambda x: x.label.lower()):
        row = [
            e.label,
            e.username or "",
            e.url or "",
            ", ".join(e.tags),
            e.updated_at,
        ]
        if show:
            row.append(e.password)
        table.add_row(*row)

    console.print(table)
    if show:
        rprint("[bold red]WARNING: passwords were displayed in plaintext.[/bold red]")


@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search term (matches label, username, url, notes, tags)"),
    show: bool = typer.Option(False, "--show", "--show-password"),
):
    """Search entries (case-insensitive)."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)
    _unlock(v)

    results = v.search(query)
    if not results:
        rprint(f"[dim]No matches for[/dim] '{query}'")
        return

    table = Table(title=f"Search results for '{query}'")
    table.add_column("Label", style="cyan")
    table.add_column("Username")
    if show:
        table.add_column("Password", style="red")

    for e in sorted(results, key=lambda x: x.label.lower()):
        row = [e.label, e.username or ""]
        if show:
            row.append(e.password)
        table.add_row(*row)

    console.print(table)


@app.command()
def get(
    ctx: typer.Context,
    label: Optional[str] = typer.Argument(
        None, help="Exact label of the entry (positional or use --label/-l)"
    ),
    label_opt: Optional[str] = typer.Option(None, "--label", "-l", help="Exact label of the entry"),
    show_password: bool = typer.Option(False, "--show-password", "-s"),
):
    """Show details for one entry."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)
    _unlock(v)

    target = label or label_opt
    if not target:
        rprint("[red]A label is required (provide it as a positional argument or with --label / -l).[/red]")
        raise typer.Exit(1)

    e = v.get(target)
    if e is None:
        rprint(f"[red]No entry with label '{target}'.[/red]")
        raise typer.Exit(1)

    rprint(f"[bold cyan]{e.label}[/bold cyan]")
    if e.username:
        rprint(f"Username: {e.username}")
    if e.url:
        rprint(f"URL:     {e.url}")
    if e.tags:
        rprint(f"Tags:    {', '.join(e.tags)}")
    if e.notes:
        rprint(f"Notes:   {e.notes}")
    rprint(f"Created: {e.created_at}")
    rprint(f"Updated: {e.updated_at}")

    if show_password:
        rprint(f"Password: [bold red]{e.password}[/bold red]")
    else:
        rprint("[dim]Password hidden. Use --show-password or `pwm copy`.[/dim]")


@app.command()
def copy(
    ctx: typer.Context,
    label: Optional[str] = typer.Argument(
        None, help="Exact label whose password to copy (positional or use --label/-l)"
    ),
    label_opt: Optional[str] = typer.Option(None, "--label", "-l", help="Exact label whose password to copy"),
):
    """Copy the password for an entry to the clipboard."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)
    _unlock(v)

    target = label or label_opt
    if not target:
        rprint("[red]A label is required (provide it as a positional argument or with --label / -l).[/red]")
        raise typer.Exit(1)

    e = v.get(target)
    if e is None:
        rprint(f"[red]No entry with label '{target}'.[/red]")
        raise typer.Exit(1)

    copy_to_clipboard(e.password)
    rprint(f"[green]Password for[/green] [bold]{target}[/bold] [green]copied to clipboard.[/green]")
    rprint("[yellow]Clipboard is readable by other processes and may be stored in history (Win+V on Windows).[/yellow]")


@app.command()
def delete(
    ctx: typer.Context,
    label: Optional[str] = typer.Argument(
        None, help="Exact label to delete (positional or use --label/-l)"
    ),
    label_opt: Optional[str] = typer.Option(None, "--label", "-l", help="Exact label to delete"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete an entry permanently."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)
    _unlock(v)

    target = label or label_opt
    if not target:
        rprint("[red]A label is required (provide it as a positional argument or with --label / -l).[/red]")
        raise typer.Exit(1)

    e = v.get(target)
    if e is None:
        rprint(f"[red]No entry with label '{target}'.[/red]")
        raise typer.Exit(1)

    if not yes:
        confirm = typer.confirm(f"Really delete entry '{target}'?", default=False)
        if not confirm:
            rprint("Aborted.")
            raise typer.Exit()

    if v.delete(target):
        rprint(f"[green]Deleted[/green] {target}")
    else:
        rprint("[red]Delete failed (entry disappeared?).[/red]")


@app.command()
def edit(
    ctx: typer.Context,
    label: Optional[str] = typer.Argument(
        None, help="Label of the entry to edit (positional or use --label/-l)"
    ),
    label_opt: Optional[str] = typer.Option(None, "--label", "-l", help="Label of the entry to edit"),
    new_label: Optional[str] = typer.Option(None, "--new-label", help="Rename the entry"),
    username: Optional[str] = typer.Option(None, "--username", "-u"),
    password: Optional[str] = typer.Option(None, "--password", "-p"),
    url: Optional[str] = typer.Option(None, "--url"),
    notes: Optional[str] = typer.Option(None, "--notes", "-n"),
    tag: list[str] = typer.Option([], "--tag", "-t", help="Replace tags (repeatable)"),
):
    """Edit an existing entry. Only supplied fields are changed."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)
    _unlock(v)

    target = label or label_opt
    if not target:
        rprint("[red]A label is required (provide it as a positional argument or with --label / -l).[/red]")
        raise typer.Exit(1)

    changes: dict = {}
    if new_label is not None:
        changes["new_label"] = new_label
    if username is not None:
        changes["username"] = username
    if password is not None:
        changes["password"] = password
    if url is not None:
        changes["url"] = url
    if notes is not None:
        changes["notes"] = notes
    if tag:
        changes["tags"] = tag

    if not changes:
        rprint("[yellow]No changes supplied. Use flags like --username, --password, --new-label, etc.[/yellow]")
        raise typer.Exit(1)

    try:
        updated = v.update(target, **changes)
    except ValueError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)

    rprint(f"[green]Updated[/green] [bold]{updated.label}[/bold]")
    if password is not None:
        rprint("[dim]Password was changed (hidden).[/dim]")


@app.command("change-master")
def change_master(ctx: typer.Context):
    """Change the master password (re-encrypts the entire vault)."""
    v = _get_vault_from_ctx(ctx)
    _require_vault_exists(v)

    # We need the old master to decrypt first
    old_master = _prompt_master("Current master password: ")
    _unlock(v, old_master)

    new_master = _prompt_new_master()

    with console.status("[bold yellow]Re-encrypting vault with new master (this may take a moment)..."):
        try:
            v.change_master(new_master)
        except Exception as exc:
            rprint(f"[red]Failed to change master: {exc}[/red]")
            raise typer.Exit(1)

    rprint("[green]Master password changed successfully.[/green]")
    rprint("[yellow]All entries have been re-encrypted under the new master.[/yellow]")


@app.command()
def info(ctx: typer.Context):
    """Show information about the vault (header only — no unlock required)."""
    v = _get_vault_from_ctx(ctx)
    info = v.inspect_header()

    if not info.get("exists"):
        attempted = info.get("path") or str(v.vault_path)
        rprint(f"No vault at the configured location: {attempted}")
        rprint(f"Default location (if no --vault-path): {get_default_vault_path()}")
        return

    rprint(f"Vault path: [bold]{info['path']}[/bold]")
    rprint(f"Format: {info.get('magic')} v{info.get('format_version')}")
    rprint(f"Argon2id params: t={info.get('time_cost')}, m={info.get('memory_cost')} KiB, p={info.get('parallelism')}")
    rprint(f"Salt (hex): {info.get('salt_hex')}")
    rprint(f"Nonce (hex): {info.get('nonce_hex')}")
    rprint(f"Ciphertext length: {info.get('ciphertext_len')} bytes")


if __name__ == "__main__":
    app()
