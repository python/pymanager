from .exceptions import ArgumentError, FilesInUseError
from .fsutils import rmtree, unlink
from .installs import get_matching_install_tags
from .install_command import update_all_shortcuts
from .logging import LOGGER
from .pathutils import PurePath
from .tagutils import tag_or_range


def _iterdir(p, only_files=False):
    try:
        return list(p.iterdir())
    except FileNotFoundError:
        LOGGER.debug("Skipping %s because it does not exist", p)
        return []


def execute(cmd):
    LOGGER.debug("BEGIN uninstall_command.execute: %r", cmd.args)

    warn_msg = ("Attempting to remove {} is taking longer than expected. " +
        "Ensure no Python interpreters are running, and continue to wait " +
        "or press Ctrl+C to abort.")

    # Clear any active venv so we don't try to delete it
    cmd.virtual_env = None
    installed = list(cmd.get_installs())

    self.tags = []

    if cmd.purge:
        if cmd.ask_yn("Uninstall all runtimes?"):
            for i in installed:
                LOGGER.info("Purging %s from %s", i["display-name"], i["prefix"])
                try:
                    rmtree(
                        i["prefix"],
                        after_5s_warning=warn_msg.format(i["display-name"]),
                        remove_ext_first=("exe", "dll", "json")
                    )
                except FilesInUseError:
                    LOGGER.warn("Unable to purge %s because it is still in use.",
                                i["display-name"])
                    continue
            LOGGER.info("Purging saved downloads")
            for f in _iterdir(cmd.install_dir):
                LOGGER.debug("Purging %s", f)
                try:
                    rmtree(f, after_5s_warning=warn_msg.format("cached downloads"),
                           remove_ext_first=("exe", "dll", "json"))
                except FilesInUseError:
                    pass
            LOGGER.info("Purging global commands")
            for f in _iterdir(cmd.global_dir):
                LOGGER.debug("Purging %s", f)
                rmtree(f, after_5s_warning=warn_msg.format("global commands"))
        LOGGER.debug("END uninstall_command.execute")
        return

    if not cmd.args:
        raise ArgumentError("Please specify one or more runtimes to uninstall.")

    to_uninstall = []
    if not cmd.by_id:
        for tag in cmd.args:
            try:
                if tag.casefold() == "default".casefold():
                    self.tags.append(tag_or_range(cmd.default_tag))
                else:
                    self.tags.append(tag_or_range(tag))
            except ValueError as ex:
                LOGGER.warn("%s", ex)

        for tag in self.tags:
            candidates = get_matching_install_tags(
                installed,
                tag,
                default_platform=cmd.default_platform,
            )
            if not candidates:
                LOGGER.warn("No install found matching '%s'", tag)
                continue
            i, _ = candidates[0]
            LOGGER.debug("Selected %s (%s) to uninstall", i["display-name"], i["id"])
            to_uninstall.append(i)
            installed.remove(i)
    else:
        ids = {tag.casefold() for tag in cmd.args}
        for i in installed:
            if i["id"].casefold() in ids:
                LOGGER.debug("Selected %s (%s) to uninstall", i["display-name"], i["id"])
                to_uninstall.append(i)
        for i in to_uninstall:
            installed.remove(i)

    if not to_uninstall:
        LOGGER.info("No runtimes selected to uninstall.")
        return
    elif cmd.confirm:
        if len(to_uninstall) == 1:
            if not cmd.ask_yn("Uninstall %s?", to_uninstall[0]["display-name"]):
                return
        else:
            msg = ", ".join(i["display-name"] for i in to_uninstall)
            if not cmd.ask_yn("Uninstall these runtimes: %s?", msg):
                return

    for i in to_uninstall:
        LOGGER.debug("Uninstalling %s from %s", i["display-name"], i["prefix"])
        try:
            rmtree(
                i["prefix"],
                after_5s_warning=warn_msg.format(i["display-name"]),
                remove_ext_first=("exe", "dll", "json"),
            )
        except FilesInUseError as ex:
            LOGGER.error("Could not uninstall %s because it is still in use.",
                         i["display-name"])
            raise SystemExit(1) from ex
        LOGGER.info("Removed %s", i["display-name"])
        try:
            for target in cmd.global_dir.glob("*.__target__"):
                alias = target.with_suffix("")
                entry = target.read_text(encoding="utf-8-sig", errors="strict")
                if PurePath(entry).match(i["executable"]):
                    LOGGER.debug("Unlink %s", alias)
                    unlink(alias, after_5s_warning=warn_msg.format(alias))
                    unlink(target, after_5s_warning=warn_msg.format(target))
        except OSError as ex:
            LOGGER.warn("Failed to remove alias: %s", ex)
            LOGGER.debug("TRACEBACK:", exc_info=True)

    if to_uninstall:
        update_all_shortcuts(cmd)

    LOGGER.debug("END uninstall_command.execute")
