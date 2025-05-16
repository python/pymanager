import os
import sys
import zipfile

from pathlib import Path
from subprocess import check_call as run

from _make_helper import (
    copyfile,
    copytree,
    get_dirs,
    get_output_name,
    rmtree,
    unlink,
)

DIRS = get_dirs()
BUILD = DIRS["build"]
TEMP = DIRS["temp"]
LAYOUT = DIRS["out"]
LAYOUT2 = TEMP / "store-layout"
SRC = DIRS["src"]
DIST = DIRS["dist"]

# Calculate output names (must be after building)
DIST_MSIX = DIST / get_output_name(LAYOUT)
DIST_STORE_MSIX = DIST_MSIX.with_name(f"{DIST_MSIX.stem}-store.msix")
DIST_APPXSYM = DIST_STORE_MSIX.with_suffix(".appxsym")
DIST_MSIXUPLOAD = DIST_STORE_MSIX.with_suffix(".msixupload")

unlink(DIST_MSIX, DIST_STORE_MSIX, DIST_APPXSYM, DIST_MSIXUPLOAD)

# Package into DIST
run([sys.executable, "-m", "pymsbuild", "pack", "-v"])

print("Copying appinstaller file to", DIST)
copyfile(LAYOUT / "python-manager/pymanager.appinstaller", DIST / "pymanager.appinstaller")


if os.getenv("PYMANAGER_APPX_STORE_PUBLISHER"):
    # Clone and update layout for Store build
    rmtree(LAYOUT2)
    copytree(LAYOUT, LAYOUT2)
    unlink(*LAYOUT2.glob("python-manager/*.appinstaller"))

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

    patch_appx(LAYOUT2 / "python-manager/appxmanifest.xml")

    run(
        [sys.executable, "-m", "pymsbuild", "pack", "-v"],
        env={
            **os.environ,
            "PYMSBUILD_LAYOUT_DIR": str(LAYOUT2),
            "PYMSBUILD_MSIX_NAME": DIST_STORE_MSIX.name,
        }
    )

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
