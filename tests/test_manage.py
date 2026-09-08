"""Tests for the kismet-webui-admin management commands (manage.py).

These import the Flask app, which only imports on Linux (service_manager
calls os.geteuid() at import time). Run from the repo root:

    python -m pytest tests/
"""

import os

import pytest

# app.py reads these at import time, so they must be set before importing.
os.environ.setdefault("SESSION_SECRET", "test-secret-not-for-production")
os.environ["DATABASE_URL"] = "sqlite://"

import manage  # noqa: E402
from app import app, db  # noqa: E402
from models import User  # noqa: E402


@pytest.fixture
def ctx():
    """Fresh, empty database inside an app context for each test."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield
        db.session.remove()


def add_user(username, password):
    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_reset_password_replaces_existing_password(ctx):
    add_user("alice", "old-password")

    manage.reset_password("alice", "new-password")

    user = User.query.filter_by(username="alice").one()
    assert user.check_password("new-password")
    assert not user.check_password("old-password")


def test_reset_password_unknown_user_lists_existing_usernames(ctx):
    add_user("alice", "pw")
    add_user("bob", "pw")

    with pytest.raises(manage.AdminError) as excinfo:
        manage.reset_password("carol", "new-password")

    message = str(excinfo.value)
    assert "carol" in message
    assert "alice" in message and "bob" in message


def test_reset_users_removes_every_account(ctx):
    add_user("alice", "pw")
    add_user("bob", "pw")

    removed = manage.reset_users()

    assert removed == 2
    assert User.query.count() == 0


# --- command-line entry point -------------------------------------------------


def fake_prompts(monkeypatch, *answers):
    """Make each getpass() call return the next of ``answers``."""
    replies = iter(answers)
    monkeypatch.setattr(manage.getpass, "getpass", lambda prompt="": next(replies))


def test_cli_reset_password_sets_password_when_entries_match(ctx, monkeypatch, capsys):
    add_user("alice", "old-password")
    fake_prompts(monkeypatch, "new-password", "new-password")

    assert manage.main(["reset-password", "alice"]) == 0

    assert User.query.filter_by(username="alice").one().check_password("new-password")
    assert "alice" in capsys.readouterr().out


def test_cli_reset_password_rejects_mismatched_entries(ctx, monkeypatch, capsys):
    add_user("alice", "old-password")
    fake_prompts(monkeypatch, "one", "two")

    assert manage.main(["reset-password", "alice"]) == 1

    assert User.query.filter_by(username="alice").one().check_password("old-password")
    assert "match" in capsys.readouterr().err


def test_cli_reset_password_rejects_empty_password(ctx, monkeypatch, capsys):
    add_user("alice", "old-password")
    fake_prompts(monkeypatch, "", "")

    assert manage.main(["reset-password", "alice"]) == 1

    assert User.query.filter_by(username="alice").one().check_password("old-password")
    assert "empty" in capsys.readouterr().err


def test_cli_reset_password_unknown_user_fails_before_prompting(ctx, monkeypatch, capsys):
    add_user("alice", "pw")
    monkeypatch.setattr(manage.getpass, "getpass", lambda prompt="": pytest.fail("should not prompt"))

    assert manage.main(["reset-password", "carol"]) == 1

    assert "alice" in capsys.readouterr().err


def test_cli_reset_users_removes_accounts_after_confirmation(ctx, monkeypatch, capsys):
    add_user("alice", "pw")
    add_user("bob", "pw")
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")

    assert manage.main(["reset-users"]) == 0

    assert User.query.count() == 0
    assert "2" in capsys.readouterr().out


def test_cli_reset_users_keeps_accounts_when_not_confirmed(ctx, monkeypatch, capsys):
    add_user("alice", "pw")
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")

    assert manage.main(["reset-users"]) == 1

    assert User.query.count() == 1
    assert "nothing changed" in capsys.readouterr().out.lower()


def test_cli_reset_users_with_no_accounts_does_not_prompt(ctx, monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("should not prompt"))

    assert manage.main(["reset-users"]) == 0

    assert "no accounts" in capsys.readouterr().out.lower()
