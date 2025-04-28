from subprocess import check_call as run

from _make_helper import (
    get_dirs,
    get_msbuild,
    get_msix_version,
    get_output_name,
)

MSBUILD_CMD = get_msbuild()

DIRS = get_dirs()
BUILD = DIRS["build"]
TEMP = DIRS["temp"]
LAYOUT = DIRS["out"]
SRC = DIRS["src"]
DIST = DIRS["dist"]

# Calculate output names (must be after building)
NAME = get_output_name(DIRS)
VERSION = get_msix_version(DIRS)

# Package into MSI
pydllname = [p.stem for p in (LAYOUT / "runtime").glob("python*.dll")][0]
pydsuffix = [p.name.partition(".")[-1] for p in (LAYOUT / "runtime").glob("manage*.pyd")][0]

run([
    *MSBUILD_CMD,
    "-Restore",
    SRC / "pymanager/msi.wixproj",
    "/p:Platform=x64",
    "/p:Configuration=Release",
    f"/p:OutputPath={DIST}",
    f"/p:IntermediateOutputPath={TEMP}\\",
    f"/p:TargetName={NAME}",
    f"/p:Version={VERSION}",
    f"/p:PythonDLLName={pydllname}",
    f"/p:PydSuffix={pydsuffix}",
    f"/p:LayoutDir={LAYOUT}",
])
