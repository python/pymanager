import pytest
import secrets
from manage import commands, logging
from manage.exceptions import ArgumentError, NoInstallsError


def test_pymanager_help_command(assert_log):
    cmd = commands.HelpCommand([commands.HelpCommand.CMD], None)
    cmd.execute()
    assert_log(
        assert_log.skip_until(r"Python installation manager \d+\.\d+.*"),
        assert_log.skip_until(".*pymanager-pytest exec -V.*"),
        assert_log.skip_until(".*pymanager-pytest exec -3.*"),
        assert_log.skip_until(".*pymanager-pytest install.*"),
        assert_log.skip_until(".*pymanager-pytest list.*"),
        assert_log.skip_until(".*pymanager-pytest uninstall.*"),
    )


def test_py_help_command(assert_log, monkeypatch):
    monkeypatch.setattr(commands, "EXE_NAME", "py")
    cmd = commands.HelpCommand([commands.HelpCommand.CMD], None)
    cmd.execute()
    assert_log(
        assert_log.skip_until(r"Python installation manager \d+\.\d+.*"),
        assert_log.skip_until(".*pymanager-pytest -V.*"),
        assert_log.skip_until(".*pymanager-pytest -3.*"),
        assert_log.skip_until(".*py install.*"),
        assert_log.skip_until(".*py list.*"),
        assert_log.skip_until(".*py uninstall.*"),
    )


def test_help_with_error_command(assert_log):
    expect = secrets.token_hex(16)
    cmd = commands.HelpWithErrorCommand(
        [commands.HelpWithErrorCommand.CMD, expect, "-v", "-q"],
        None
    )
    cmd.execute()
    assert_log(
        assert_log.skip_until(f".*Unknown command: pymanager-pytest {expect} -v -q.*"),
        r"Python installation manager \d+\.\d+.*",
        assert_log.skip_until(f"The command .*?pymanager-pytest {expect} -v -q.*"),
    )


def test_exec_with_literal_default():
    cmd = commands.load_default_config(None)
    try:
        assert cmd.get_install_to_run("default", None)
    except ValueError:
        # This is our failure case!
        raise
    except NoInstallsError:
        # This is also an okay result, if the default runtime isn't installed
        pass


def test_legacy_list_command(assert_log, patched_installs):
    cmd = commands.ListLegacyCommand(["--list"])
    cmd.show_welcome()
    cmd.execute()
    assert_log(
        # Ensure welcome message is suppressed
        assert_log.not_logged(r"Python installation manager.+"),
        # Should have a range of values shown, we don't care too much
        assert_log.skip_until(r" -V:2\.0\[-64\]\s+Python.*"),
        assert_log.skip_until(r" -V:3\.0a1-32\s+Python.*"),
    )


def test_legacy_list_command_args():
    with pytest.raises(ArgumentError):
        commands.ListLegacyCommand(["--list", "--help"])


def test_legacy_listpaths_command_help(assert_log, patched_installs):
    cmd = commands.ListPathsLegacyCommand(["--list-paths"])
    cmd.help()
    assert_log(
        assert_log.skip_until(r".*List command.+py list.+"),
    )
