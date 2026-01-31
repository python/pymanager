"""Implementation of the 'default' command to manage default Python version."""

import json
from pathlib import Path as PathlibPath

from .exceptions import ArgumentError, NoInstallsError, NoInstallFoundError
from .installs import get_installs, get_matching_install_tags
from .logging import LOGGER
from .pathutils import Path
from .tagutils import tag_or_range


def _get_default_config_file(install_dir):
    """Get the path to the default install marker file."""
    return Path(install_dir) / ".default"


def _load_default_install_id(install_dir):
    """Load the saved default install ID from the marker file."""
    try:
        default_file = _get_default_config_file(install_dir)
        if default_file.exists():
            return default_file.read_text(encoding="utf-8").strip()
    except Exception as e:
        LOGGER.debug("Failed to load default install ID: %s", e)
    return None


def _save_default_install_id(install_dir, install_id):
    """Save the default install ID to the marker file."""
    try:
        default_file = _get_default_config_file(install_dir)
        default_file.parent.mkdir(parents=True, exist_ok=True)
        default_file.write_text(install_id, encoding="utf-8")
        LOGGER.info("Default Python version set to: !G!%s!W!", install_id)
    except Exception as e:
        LOGGER.error("Failed to save default install ID: %s", e)
        raise ArgumentError(f"Could not save default version: {e}") from e


def _show_current_default(cmd):
    """Show the currently configured default Python version."""
    try:
        installs = cmd.get_installs(set_default=False)
    except NoInstallsError:
        LOGGER.info("No Python installations found.")
        return

    # Check if there's an explicit default marked
    default_install = None
    for install in installs:
        if install.get("default"):
            default_install = install
            break

    if default_install:
        LOGGER.print("!G!Current default:!W! %s", default_install["display-name"])
        LOGGER.print("  ID: %s", default_install["id"])
        LOGGER.print("  Version: %s", default_install.get("sort-version", "unknown"))
    else:
        LOGGER.print("!Y!No explicit default set.!W!")
        LOGGER.print("Using tag-based default: !B!%s!W!", cmd.default_tag)


def _set_default_version(cmd, tag):
    """Set a specific Python version as the default."""
    try:
        installs = cmd.get_installs(set_default=False)
    except NoInstallsError:
        raise ArgumentError("No Python installations found. Install a version first with 'py install'.") from None

    if not installs:
        raise ArgumentError("No Python installations found. Install a version first with 'py install'.")

    # Find the install matching the provided tag
    try:
        tag_obj = tag_or_range(tag)
    except Exception as e:
        raise ArgumentError(f"Invalid tag format: {tag}") from e

    matching = get_matching_install_tags(
        installs,
        tag_obj,
        default_platform=cmd.default_platform,
        single_tag=False,
    )

    if not matching:
        raise NoInstallFoundError(tag=tag)

    selected_install, selected_run_for = matching[0]

    # Save the install ID as the default
    _save_default_install_id(cmd.install_dir, selected_install["id"])

    LOGGER.info("Default Python version set to: !G!%s!W! (%s)",
                selected_install["display-name"],
                selected_install["id"])


def execute(cmd):
    """Execute the default command."""
    cmd.show_welcome()

    if cmd.show_help:
        cmd.help()
        return

    if not cmd.args:
        # Show current default
        _show_current_default(cmd)
    else:
        # Set new default
        tag = " ".join(cmd.args[0:1])  # Take the first argument as the tag
        _set_default_version(cmd, tag)

