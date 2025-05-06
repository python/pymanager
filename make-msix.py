import os
import sys
import zipfile

from pathlib import Path
from subprocess import check_call as run

from _make_helper import (
    copyfile,
    copytree,
    get_dirs,
    get_msix_version,
    get_output_name,
    get_sdk_bins,
    rmtree,
    unlink,
)

SDK_BINS = get_sdk_bins()

MAKEAPPX = SDK_BINS / "makeappx.exe"
MAKEPRI = SDK_BINS / "makepri.exe"

for tool in [MAKEAPPX, MAKEPRI]:
    if not tool.is_file():
        print("Unable to locate Windows Kit tool", tool.name, file=sys.stderr)
        sys.exit(3)

DIRS = get_dirs()
BUILD = DIRS["build"]
TEMP = DIRS["temp"]
LAYOUT = DIRS["out"]
LAYOUT2 = TEMP / "store-layout"
SRC = DIRS["src"]
DIST = DIRS["dist"]

# Calculate output names (must be after building)
NAME = get_output_name(DIRS)
VERSION = get_msix_version(DIRS)
DIST_MSIX = DIST / f"{NAME}.msix"
DIST_STORE_MSIX = DIST / f"{NAME}-store.msix"
DIST_APPXSYM = DIST / f"{NAME}-store.appxsym"
DIST_MSIXUPLOAD = DIST / f"{NAME}-store.msixupload"

unlink(DIST_MSIX, DIST_STORE_MSIX, DIST_APPXSYM, DIST_MSIXUPLOAD)

# Generate resources info in LAYOUT
if not (LAYOUT / "_resources.pri").is_file():
    run([MAKEPRI, "new", "/o",
                  "/pr", LAYOUT,
                  "/cf", SRC / "pymanager/resources.xml",
                  "/of", LAYOUT / "_resources.pri",
                  "/mf", "appx"])

# Clean up non-shipping files from LAYOUT
preserved = [
    *LAYOUT.glob("pyshellext*.dll"),
]

for f in preserved:
    print("Preserving", f, "as", TEMP / f.name)
    copyfile(f, TEMP / f.name)

unlink(
    *LAYOUT.rglob("*.pdb"),
    *LAYOUT.rglob("*.pyc"),
    *LAYOUT.rglob("__pycache__"),
    *preserved,
)

# Package into DIST
run([MAKEAPPX, "pack", "/o", "/d", LAYOUT, "/p", DIST_MSIX])

print("Copying appinstaller file to", DIST)
copyfile(LAYOUT / "pymanager.appinstaller", DIST / "pymanager.appinstaller")


if os.getenv("PYMANAGER_APPX_STORE_PUBLISHER"):
    # Clone and update layout for Store build
    rmtree(LAYOUT2)
    copytree(LAYOUT, LAYOUT2)
    unlink(*LAYOUT2.glob("*.appinstaller"))

    def patch_appx(source):
        from xml.etree import ElementTree as ET
        NS = {}
        with open(source, "r", encoding="utf-8") as f:
            NS = dict(e for _, e in ET.iterparse(f, events=("start-ns",)))
        for k, v in NS.items():
            ET.register_namespace(k, v)
        NS["x"] = NS[""]

        with open(source, "r", encoding="utf-8") as f:
            xml = ET.parse(f)

        identity = xml.find("x:Identity", NS)
        identity.set("Publisher", os.getenv("PYMANAGER_APPX_STORE_PUBLISHER"))
        p = xml.find("x:Properties", NS)
        e = p.find("uap13:AutoUpdate", NS)
        p.remove(e)
        e = p.find(f"uap17:UpdateWhileInUse", NS)
        p.remove(e)

        with open(source, "wb") as f:
            xml.write(f, "utf-8")

        # We need to remove unused namespaces from IgnorableNamespaces.
        # The easiest way to get this right is to read the file back in, see
        # which namespaces were silently left out by etree, and remove those.
        with open(source, "r", encoding="utf-8") as f:
            NS = dict(e for _, e in ET.iterparse(f, events=("start-ns",)))
        with open(source, "r", encoding="utf-8") as f:
            xml = ET.parse(f)
        p = xml.getroot()
        p.set("IgnorableNamespaces", " ".join(s for s in p.get("IgnorableNamespaces").split() if s in NS))
        with open(source, "wb") as f:
            xml.write(f, "utf-8")

    patch_appx(LAYOUT2 / "appxmanifest.xml")

    run([MAKEAPPX, "pack", "/o", "/d", LAYOUT2, "/p", DIST_STORE_MSIX])

    # Pack symbols
    print("Packing symbols to", DIST_APPXSYM)
    with zipfile.ZipFile(DIST_APPXSYM, "w") as zf:
        for f in BUILD.rglob("*.pdb"):
            zf.write(f, arcname=f.name)

    # Pack upload MSIX for Store
    print("Packing Store upload to", DIST_MSIXUPLOAD)
    with zipfile.ZipFile(DIST_MSIXUPLOAD, "w") as zf:
        zf.write(DIST_STORE_MSIX, arcname=DIST_STORE_MSIX.name)
        zf.write(DIST_APPXSYM, arcname=DIST_APPXSYM.name)


for f in preserved:
    print("Restoring", f, "from", TEMP / f.name)
    copyfile(TEMP / f.name, f)
    unlink(TEMP / f.name)
