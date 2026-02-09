import os
import shutil
import subprocess
import sys
import time
import winreg

from pathlib import Path

def get_msbuild():
    exe = os.getenv("MSBUILD", "")
    if exe:
        if Path(exe).is_file():
            return [exe]
        return _split_args(exe)
    
    for part in os.getenv("PATH", "").split(os.path.pathsep):
        p = Path(part)
        if p.is_dir():
            exe = p / "msbuild.exe"
            if exe.is_file():
                return [str(exe)]

    vswhere = Path(os.getenv("ProgramFiles(x86)"), "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if vswhere.is_file():
        out = Path(subprocess.check_output([
            str(vswhere),
            "-nologo",
            "-property", "installationPath",
            "-latest",
            "-prerelease",
            "-products", "*",
            "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
            "-utf8",
        ], encoding="utf-8", errors="strict").strip())
        if out.is_dir():
            exe = out / "MSBuild" / "Current" / "Bin" / "msbuild.exe"
            if exe.is_file():
                return [str(exe)]

    raise FileNotFoundError("msbuild.exe")


def get_sdk_bins():
    sdk = os.getenv("WindowsSdkDir")
    if not sdk:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows Kits\Installed Roots",
            access=winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
        ) as key:
            sdk, keytype = winreg.QueryValueEx(key, "KitsRoot10")

        if keytype != winreg.REG_SZ:
            print("Unexpected registry value for Windows Kits root.", file=sys.stderr)
            print("Try setting %WindowsSdkDir%", file=sys.stderr)
            sys.exit(1)

    sdk = Path(sdk)

    sdk_ver = os.getenv("WindowsSDKVersion", "10.*")

    bins = list((sdk / "bin").glob(sdk_ver))[-1] / "x64"
    if not bins.is_dir():
        print("Unable to locate Windows Kits binaries.", file=sys.stderr)
        sys.exit(2)

    return bins


def _envpath_or(var, default):
    p = os.getenv(var)
    if p:
        return Path(p)
    return default


def get_dirs():
    root = Path.cwd()
    src = root / "src"
    dist = _envpath_or("PYMSBUILD_DIST_DIR", root / "dist")
    _temp = _envpath_or("PYMSBUILD_TEMP_DIR", Path.cwd() / "build")
    build = _temp / "bin"
    temp = _temp / "temp"
    _layout = _envpath_or("PYMSBUILD_LAYOUT_DIR", None)
    if not _layout:
        _layout = _temp / "layout"
        os.environ["PYMSBUILD_LAYOUT_DIR"] = str(_layout)
    out = _layout / "python-manager"

    return dict(
        root=root,
        out=out,
        src=src,
        dist=dist,
        build=build,
        temp=temp,
    )


def get_msix_version(dirs):
    from io import StringIO
    from xml.etree import ElementTree as ET
    appx = (dirs["out"] / "appxmanifest.xml").read_text("utf-8")
    NS = dict(e for _, e in ET.iterparse(StringIO(appx), events=("start-ns",)))
    for k, v in NS.items():
        ET.register_namespace(k, v)
    xml = ET.parse(StringIO(appx))
    identity = xml.find(f"x:Identity", {"x": NS[""]})
    return identity.attrib['Version']


def get_output_name(dirs):
    with open(dirs["out"] / "version.txt", "r", encoding="utf-8") as f:
        version = f.read().strip()
    return f"python-manager-{version}"


copyfile = shutil.copyfile
copytree = shutil.copytree


def rmtree(path):
    print("Removing", path)
    if not path.is_dir():
        return
    try:
        shutil.rmtree(path)
    except OSError:
        time.sleep(1.0)
        shutil.rmtree(path)


def unlink(*paths):
    for p in paths:
        try:
            print("Removing", p)
            try:
                p.unlink()
            except IsADirectoryError:
                rmtree(p)
            except FileNotFoundError:
                pass
        except OSError as ex:
            print("Failed to remove", p, ex)


def download_zip_into(url, path):
    from urllib.request import urlretrieve
    import zipfile

    path.mkdir(exist_ok=True, parents=True)
    name = url.rpartition("/")[-1]
    if not name.casefold().endswith(".zip".casefold()):
        name += ".zip"
    zip_file = path.parent / name
    if not zip_file.exists():
        print("Downloading from", url)
        urlretrieve(url, zip_file)
    print("Extracting", zip_file)
    with zipfile.ZipFile(zip_file) as zf:
        prefix = os.path.commonpath(zf.namelist())
        for m in zf.infolist():
            fn = m.filename.removeprefix(prefix).lstrip("/\\")
            if not fn or fn.endswith(("/", "\\")):
                continue
            dest = path / fn
            assert dest.relative_to(path)
            dest.parent.mkdir(exist_ok=True, parents=True)
            with open(dest, "wb") as f:
                f.write(zf.read(m))
