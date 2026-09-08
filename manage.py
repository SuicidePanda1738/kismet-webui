#!/usr/bin/env python3
"""
Administrative commands for Kismet WebUI, run from the terminal as root.

install.sh installs this as the `kismet-webui-admin` command, which loads
/etc/kismet-webui/env (SESSION_SECRET, DATABASE_URL) before running it.

    kismet-webui-admin reset-users               remove every account; the
                                                 web UI shows the setup page
    kismet-webui-admin reset-password <username> set a new password
"""

import argparse
import getpass
import sys

from app import app, db
from models import User


class AdminError(Exception):
    """A command could not be carried out; the message is shown to the operator."""


def _get_user(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        existing = ", ".join(u.username for u in User.query.order_by(User.username))
        raise AdminError(
            f"No account named '{username}'. Existing accounts: {existing or '(none)'}"
        )
    return user


def reset_password(username, password):
    """Set a new password for an existing account."""
    user = _get_user(username)
    user.set_password(password)
    db.session.commit()


def reset_users():
    """Delete every account so the web UI offers the setup page again."""
    removed = User.query.delete()
    db.session.commit()
    return removed


def _cmd_reset_password(username):
    _get_user(username)  # fail before asking for a password
    password = getpass.getpass("New password: ")
    if not password:
        raise AdminError("Password cannot be empty; nothing changed.")
    if getpass.getpass("Confirm password: ") != password:
        raise AdminError("Passwords do not match; nothing changed.")
    reset_password(username, password)
    print(f"Password updated for '{username}'.")
    return 0


def _cmd_reset_users():
    count = User.query.count()
    if count == 0:
        print("No accounts exist; the web UI already shows the setup page.")
        return 0
    answer = input(
        f"Remove {count} account(s)? The web UI will show the setup page again. [y/N] "
    )
    if answer.strip().lower() not in ("y", "yes"):
        print("Aborted; nothing changed.")
        return 1
    removed = reset_users()
    print(f"Removed {removed} account(s). Open the web UI to create a new one.")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="kismet-webui-admin",
        description="Administrative commands for Kismet WebUI.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "reset-users",
        help="remove every account so the web UI shows the setup page again",
    )
    reset_pw = commands.add_parser("reset-password", help="set a new password for an account")
    reset_pw.add_argument("username")
    args = parser.parse_args(argv)

    try:
        with app.app_context():
            if args.command == "reset-users":
                return _cmd_reset_users()
            return _cmd_reset_password(args.username)
    except AdminError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
