import os
import subprocess
import sys
from pathlib import PurePath
from subprocess import check_call as run
from _make_helper import get_dirs, rmtree, unlink

# Clean DEBUG flag in case it affects build
os.environ["PYMANAGER_DEBUG"] = ""

DIRS = get_dirs()
BUILD = DIRS["build"]
TEMP = DIRS["temp"]
LAYOUT = DIRS["out"]
SRC = DIRS["src"]
DIST = DIRS["dist"]

if "-i" not in sys.argv:
    rmtree(BUILD)
    rmtree(TEMP)
    rmtree(LAYOUT)

ref = "none"
try:
    if os.getenv("BUILD_SOURCEBRANCH"):
        ref = os.getenv("BUILD_SOURCEBRANCH")
    else:
        with subprocess.Popen(
            ["git", "describe", "HEAD", "--tags"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        ) as p:
            out, err = p.communicate()
        if out:
            ref = "refs/tags/" + out.decode().strip()
    ref = os.getenv("OVERRIDE_REF", ref)
    print("Building for tag", ref)
except subprocess.CalledProcessError:
    pass

# Run main build - this fills in BUILD and LAYOUT
run([sys.executable, "-m", "pymsbuild", "msix"],
    cwd=DIRS["root"],
    env={**os.environ, "BUILD_SOURCEBRANCH": ref})

# Bundle current latest release
run([LAYOUT / "py-manager.exe", "install", "-v", "-f", "--download", LAYOUT / "bundled", "default"])
(LAYOUT / "bundled" / "index.json").rename(LAYOUT / "bundled" / "fallback-index.json")

# Update package state for when we pack
new_lines = []
state_txt = LAYOUT.parent / "__state.txt"
for line in state_txt.read_text("utf-8").splitlines():
    if not line or "=" in line or line.startswith("#"):
        new_lines.append(line)
        continue
    # Exclude the in-proc shell extension from the MSIX
    if PurePath(line).match("pyshellext*.dll"):
        continue
    new_lines.append(line)
# Include the bundled files in the MSIX
for f in LAYOUT.rglob(r"bundled\*"):
    new_lines.append(str(f.relative_to(state_txt.parent)))

state_txt.write_text("\n".join(new_lines), encoding="utf-8")
