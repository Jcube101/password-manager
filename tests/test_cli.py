"""
Basic CLI tests using typer.testing.CliRunner.

These cover non-interactive paths and help text (no master password prompts).
Full interactive flows (init, add that needs master, change-master) are covered
by manual end-to-end testing with the user.

Run with: pytest tests/test_cli.py -q
"""

from typer.testing import CliRunner

from pwm.cli import app
from pwm.vault import Vault

runner = CliRunner()


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "pwm 0.1.0" in result.stdout


def test_help_shows_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "add" in result.stdout
    assert "generate" in result.stdout
    assert "copy" in result.stdout


def test_generate_works():
    result = runner.invoke(app, ["generate", "--length", "12", "--no-symbols"])
    assert result.exit_code == 0
    assert len(result.stdout.strip()) == 12


def test_info_no_vault(tmp_path):
    # Use a non-existing path so it doesn't touch real user data
    dummy = tmp_path / "no-such-vault"
    result = runner.invoke(app, ["--vault-path", str(dummy), "info"])
    assert result.exit_code == 0
    assert "No vault" in result.stdout or "no vault" in result.stdout.lower()


def test_add_help_shows_label_option():
    result = runner.invoke(app, ["add", "--help"])
    assert result.exit_code == 0
    assert "--label" in result.stdout or "-l" in result.stdout
    assert "Human label for the entry" in result.stdout


def test_get_help_shows_dual_label():
    result = runner.invoke(app, ["get", "--help"])
    assert result.exit_code == 0
    # Shows both the argument help and the option
    assert "positional or use --label" in result.stdout or "--label" in result.stdout
    assert "LABEL" in result.stdout.upper() or "label" in result.stdout.lower()


def test_copy_and_delete_help_dual():
    for cmd in ["copy", "delete", "edit"]:
        result = runner.invoke(app, [cmd, "--help"])
        assert result.exit_code == 0
        assert "--label" in result.stdout or "-l" in result.stdout


def test_bare_pwm_no_vault_shows_landing(tmp_path):
    dummy = tmp_path / "no-such-vault"
    result = runner.invoke(app, ["--vault-path", str(dummy)])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert "no vault" in out
    assert "pwm init" in out
    # Path may wrap inside a Rich panel; the leaf name must still appear.
    assert dummy.name in result.stdout
    assert "master password" not in out


def test_bare_pwm_with_vault_shows_path_and_next_commands(tmp_path):
    vault_file = tmp_path / "vault"
    Vault(vault_file).create("test-master-for-landing-page")
    result = runner.invoke(app, ["--vault-path", str(vault_file)])
    assert result.exit_code == 0
    out = result.stdout.lower()
    assert vault_file.name in result.stdout
    assert "back up" in out
    assert "pwm copy" in out
    assert "pwm add" in out
    assert "pwm list" in out
    assert "pwm search" in out
    assert "master password" not in out
    # Header-only: no decrypted inventory
    assert "no entries" not in out


def test_bare_pwm_does_not_replace_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "init" in result.stdout
    assert "copy" in result.stdout
