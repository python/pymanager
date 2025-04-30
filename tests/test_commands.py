import pytest
import secrets
from manage import commands


def test_help_with_error_command(assert_log, monkeypatch):
    expect = secrets.token_hex(16)
    cmd = commands.HelpWithErrorCommand(
        [commands.HelpWithErrorCommand.CMD, expect, "-v", "-q"],
        None
    )
    monkeypatch.setattr(commands, "WELCOME", "")
    cmd.execute()
    assert_log(
        assert_log.skip_until(rf".*Unknown command: pymanager-pytest {expect} -v -q.*"),
        r"Python installation manager \d+\.\d+.*",
        assert_log.skip_until(rf"The command .*?pymanager-pytest {expect} -v -q.*"),
    )
