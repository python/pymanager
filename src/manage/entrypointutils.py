
def _scan(prefix, dirs):
    for dirname in dirs or ():
        # TODO: Handle invalid entries
        d = install["prefix"] / dirname

        # TODO: Scan d for dist-info directories with entry_points.txt
        # Filter down to [console_scripts] and [gui_scripts]

        # TODO: Yield the alias name and script contents
        # import sys; from <mod> import <func>; sys.exit(<func>())


def scan_and_create(cmd, install, shortcut):
    for name, code in _scan(install["prefix"], shortcut.get("dirs")):
        # TODO: Store name in cmd's metadata.
        # If it's already been stored, skip all further processing.

        # TOOD: Copy the launcher template and create a standard __target__ file
        # Also create an <alias>-script.py file containing code
        # pymanager/launcher.cpp wil need to be updated to use this script.
        # Regular alias creation will need to delete these scripts.


def cleanup(cmd, install_shortcut_pairs):
    seen_names = set()
    for install, shortcut in install_shortcut_pairs:
        for name, code in _scan(install["prefix"], shortcut.get("dirs")):
            seen_names.add(name)

    # TODO: Scan existing aliases, filter to those with -script.py files

    # TODO: Excluding any in seen_names, delete unused aliases
