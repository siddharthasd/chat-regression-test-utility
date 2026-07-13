"""`harness users` — manage the user registry from the command line (015).

Pre-register users, list registrations, change roles, and remove users without
needing a browser session. Intended for initial bootstrap and admin scripting.
"""

from __future__ import annotations

import click

from harness.cli import harness_group
from harness.persistence import get_session
from harness.persistence.repositories.user_registration import UserRegistrationRepository


@click.group("users")
def users_group() -> None:
    """Manage user registrations (Azure AD RBAC)."""


@users_group.command("add")
@click.argument("email")
@click.option(
    "--role",
    default="user",
    type=click.Choice(["admin", "user"]),
    help="Role to assign (default: user).",
)
@click.option("--name", default=None, help="Display name (optional).")
def add_user(email: str, role: str, name: str | None) -> None:
    """Pre-register EMAIL in the user registry with the given role."""
    with get_session() as db:
        repo = UserRegistrationRepository(db)
        existing = repo.find_by_email(email)
        if existing:
            click.echo(f"Error: {email} is already registered (role={existing.role}).", err=True)
            raise SystemExit(1)
        reg = repo.create(email=email, role=role, display_name=name)
    click.echo(f"Registered {reg.email} as {reg.role} (id={reg.id}).")


@users_group.command("list")
def list_users() -> None:
    """List all registered users."""
    with get_session() as db:
        registrations = UserRegistrationRepository(db).list_all()
    if not registrations:
        click.echo("No users registered.")
        return
    click.echo(f"{'Email':<40} {'Role':<8} {'Linked':<8} {'Display Name'}")
    click.echo("-" * 75)
    for reg in registrations:
        linked = "yes" if reg.azure_oid else "no"
        click.echo(f"{reg.email:<40} {reg.role:<8} {linked:<8} {reg.display_name or ''}")


@users_group.command("change-role")
@click.argument("email")
@click.argument("role", type=click.Choice(["admin", "user"]))
def change_role(email: str, role: str) -> None:
    """Change the role of the user with EMAIL."""
    with get_session() as db:
        repo = UserRegistrationRepository(db)
        reg = repo.find_by_email(email)
        if reg is None:
            click.echo(f"Error: {email} not found.", err=True)
            raise SystemExit(1)
        repo.update_role(reg, role)
    click.echo(f"Updated {email} role to {role}.")


@users_group.command("remove")
@click.argument("email")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def remove_user(email: str, yes: bool) -> None:
    """Remove the user with EMAIL from the registry."""
    if not yes:
        click.confirm(f"Remove {email}?", abort=True)
    with get_session() as db:
        repo = UserRegistrationRepository(db)
        reg = repo.find_by_email(email)
        if reg is None:
            click.echo(f"Error: {email} not found.", err=True)
            raise SystemExit(1)
        repo.delete(reg)
    click.echo(f"Removed {email}.")


harness_group.add_command(users_group)
