# This is an integration test, rather than a unit test.
# It should be run in a Python runtime that has been installed.
# The 'pymanager.exe' under test should be first on PATH

import json
import shutil
import subprocess
import sys

from pathlib import Path

EXIT_SETUP_FAILED = 1
EXIT_ALIAS_NOT_CREATED = 2
EXIT_ALIAS_INVALID = 3

CLEANUP = []

def run(*args, **kwargs):
    print("##[command]", *args)
    with subprocess.Popen(
        args,
        stdout=kwargs.pop("stdout", subprocess.PIPE),
        stderr=kwargs.pop("stderr", subprocess.STDOUT),
        encoding=kwargs.pop("encoding", "ascii"),
        errors=kwargs.pop("errors", "replace"),
        **kwargs,
    ) as p:
        out, err = p.communicate(None)
        if p.returncode:
            raise subprocess.CalledProcessError(p.returncode, args, out, err)
        return out, err

def main():
    out, _ = run("pymanager", "list", "-f=json", "-q")
    for install in json.loads(out)["versions"]:
        if not install.get("unmanaged"):
            break
    else:
        print("[ERROR] No suitable (managed) runtime found.")
        sys.exit(EXIT_SETUP_FAILED)

    print("Using", install["display-name"], "from", install["prefix"], "for test")

    prefix = install["prefix"]
    exe = install["executable"]

    site = Path(prefix) / "Lib/site-packages"
    if not site.is_dir():
        print("[ERROR] Selected runtime has no site-packages folder.")
        sys.exit(EXIT_SETUP_FAILED)

    eptest_src = Path(__file__).parent / "eptestpackage"
    if not eptest_src.is_dir():
        print("[ERROR] eptestpackage is missing from test script location.")
        sys.exit(EXIT_SETUP_FAILED)

    dist_info = site / "eptestpackage-1.0.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    CLEANUP.append(lambda: shutil.rmtree(dist_info))
    for f in (eptest_src / "eptestpackage.dist-info").glob("*"):
        (dist_info / f.name).write_bytes(f.read_bytes())
    (site / "eptestpackage.py").write_bytes((eptest_src / "eptestpackage.py").read_bytes())
    CLEANUP.append((site / "eptestpackage.py").unlink)

    print("Listing 'installed' packages (should include eptestpackage)")
    print(*site.glob("*"), sep="\n")
    print()

    out, _ = run(exe, "-c", "import eptestpackage; eptestpackage.main()")
    if out.strip() != "eptestpackage:main":
        print(out)
        print("[ERROR] Failed to import eptestpackage")
        sys.exit(EXIT_SETUP_FAILED)
    print("Confirmed eptestpackage is importable")

    out, _ = run("pymanager", "list", "-f=config", "-q")
    try:
        config = json.loads(out)
    except json.JSONDecodeError:
        print("py list -f=config output:")
        print(out)
        raise
    bin_dir = Path(config["global_dir"])
    print(bin_dir)

    refresh_log, _ = run("pymanager", "install", "--refresh", "-vv")
    CLEANUP.append(lambda: run("pymanager", "install", "--refresh"))

    print("Listing global aliases (should include eptest, eptestw, eptest-refresh)")
    print(*bin_dir.glob("eptest*"), sep="\n")

    for n in ["eptest.exe", "eptestw.exe", "eptest-refresh.exe"]:
        if not (bin_dir / n).is_file():
            print("--refresh log follows")
            print(refresh_log)
            print("[ERROR] Did not create", n)
            sys.exit(EXIT_ALIAS_NOT_CREATED)

    out, _ = run(bin_dir / "eptest.exe")
    if out.strip() != "eptestpackage:main":
        print(out)
        print("[ERROR] eptest.exe alias failed")
        sys.exit(EXIT_ALIAS_INVALID)

    out, _ = run(bin_dir / "eptestw.exe")
    if out.strip() != "eptestpackage:mainw":
        print(out)
        print("[ERROR] eptestw.exe alias failed")
        sys.exit(EXIT_ALIAS_INVALID)

    out, _ = run(bin_dir / "eptest-refresh.exe")
    if not out.strip().endswith("eptestpackage:do_refresh"):
        print(out)
        print("[ERROR] eptest-refresh.exe alias failed")
        sys.exit(EXIT_ALIAS_INVALID)


try:
    main()
finally:
    print("Beginning cleanup")
    while CLEANUP:
        try:
            CLEANUP.pop()()
        except subprocess.CalledProcessError as ex:
            print("Subprocess failed during cleanup:")
            print(ex.args, ex.returncode)
            print(ex.output)
