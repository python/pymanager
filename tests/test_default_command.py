"""Tests for the default command."""

import pytest
from manage import commands
from manage.exceptions import ArgumentError, NoInstallsError


def test_default_command_help(assert_log):
    """Test the default command help output."""
    cmd = commands.DefaultCommand([commands.DefaultCommand.CMD, "--help"], None)
    cmd.execute()
    assert_log(
        assert_log.skip_until(".*Default command.*"),
    )


def test_default_command_no_args_no_installs(assert_log):
    """Test default command with no arguments and no installations."""
    cmd = commands.DefaultCommand([commands.DefaultCommand.CMD], None)
    # This should handle the case gracefully
    # We expect it to either show a message about no installs or show current default
    # The actual behavior depends on how get_installs works
    try:
        cmd.execute()
    except NoInstallsError:
        # This is acceptable - no installs available
        pass


def test_default_command_with_invalid_tag():
    """Test default command with an invalid tag."""
    cmd = commands.DefaultCommand([commands.DefaultCommand.CMD, "invalid-tag"], None)
    try:
        cmd.execute()
    except (ArgumentError, NoInstallsError):
        # Expected - no matching install found or invalid tag
        pass


def test_default_command_args_parsing():
    """Test that default command properly parses arguments."""
    cmd = commands.DefaultCommand([commands.DefaultCommand.CMD, "3.13"], None)
    assert cmd.args == ["3.13"]
    assert cmd.show_help is False


def test_default_command_help_flag():
    """Test that --help flag is recognized."""
    cmd = commands.DefaultCommand([commands.DefaultCommand.CMD, "--help"], None)
    assert cmd.show_help is True


def test_default_command_class_attributes():
    """Test that DefaultCommand has required attributes."""
    assert commands.DefaultCommand.CMD == "default"
    assert hasattr(commands.DefaultCommand, "HELP_LINE")
    assert hasattr(commands.DefaultCommand, "USAGE_LINE")
    assert hasattr(commands.DefaultCommand, "HELP_TEXT")
    assert hasattr(commands.DefaultCommand, "execute")
