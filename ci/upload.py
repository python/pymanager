import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

UPLOAD_URL_PREFIX = os.getenv("UPLOAD_URL_PREFIX", "https://www.python.org/ftp/")
UPLOAD_PATH_PREFIX = os.getenv("UPLOAD_PATH_PREFIX", "/srv/www.python.org/ftp/")
UPLOAD_URL = os.getenv("UPLOAD_URL")
UPLOAD_DIR = os.getenv("UPLOAD_DIR")
# A version will be inserted before the extension later on
MANIFEST_FILE = os.getenv("MANIFEST_FILE")
UPLOAD_HOST = os.getenv("UPLOAD_HOST", "")
UPLOAD_HOST_KEY = os.getenv("UPLOAD_HOST_KEY", "")
UPLOAD_KEYFILE = os.getenv("UPLOAD_KEYFILE", "")
UPLOAD_USER = os.getenv("UPLOAD_USER", "")
NO_UPLOAD = os.getenv("NO_UPLOAD", "no")[:1].lower() in "yt1"


if not UPLOAD_URL:
    print("##[error]Cannot upload without UPLOAD_URL")
    sys.exit(1)


def find_cmd(env, exe):
    cmd = os.getenv(env)
    if cmd:
        return Path(cmd)
    for p in os.getenv("PATH", "").split(";"):
        if p:
            cmd = Path(p) / exe
            if cmd.is_file():
                return cmd
    if UPLOAD_HOST:
        raise RuntimeError(
            f"Could not find {exe} to perform upload. Try setting %{env}% or %PATH%"
        )
    print(f"Did not find {exe}, but not uploading anyway.")


PLINK = find_cmd("PLINK", "plink.exe")
PSCP = find_cmd("PSCP", "pscp.exe")


def _std_args(cmd):
    if not cmd:
        raise RuntimeError("Cannot upload because command is missing")
    all_args = [cmd, "-batch"]
    if UPLOAD_HOST_KEY:
        all_args.append("-hostkey")
        all_args.append(UPLOAD_HOST_KEY)
    if UPLOAD_KEYFILE:
        all_args.append("-noagent")
        all_args.append("-i")
        all_args.append(UPLOAD_KEYFILE)
    return all_args


class RunError(Exception):
    pass


def _run(*args):
    with subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="ascii",
        errors="replace",
    ) as p:
        out, _ = p.communicate(None)
        if out:
            print(out.encode("ascii", "replace").decode("ascii"))
        if p.returncode:
            raise RunError(p.returncode, out)


def call_ssh(*args, allow_fail=True):
    if not UPLOAD_HOST or NO_UPLOAD or LOCAL_INDEX:
        print("Skipping", args, "because UPLOAD_HOST is missing")
        return
    try:
        _run(*_std_args(PLINK), f"{UPLOAD_USER}@{UPLOAD_HOST}", *args)
    except RunError:
        if not allow_fail:
            raise


def upload_ssh(source, dest):
    if not UPLOAD_HOST or NO_UPLOAD or LOCAL_INDEX:
        print("Skipping upload of", source, "because UPLOAD_HOST is missing")
        return
    _run(*_std_args(PSCP), source, f"{UPLOAD_USER}@{UPLOAD_HOST}:{dest}")
    call_ssh(f"chgrp downloads {dest} && chmod g-x,o+r {dest}")


def download_ssh(source, dest):
    if not UPLOAD_HOST:
        print("Skipping download of", source, "because UPLOAD_HOST is missing")
        return
    Path(dest).parent.mkdir(exist_ok=True, parents=True)
    _run(*_std_args(PSCP), f"{UPLOAD_USER}@{UPLOAD_HOST}:{source}", dest)


def ls_ssh(dest):
    if not UPLOAD_HOST or LOCAL_INDEX:
        print("Skipping ls of", dest, "because UPLOAD_HOST is missing")
        return
    try:
        _run(*_std_args(PSCP), "-ls", f"{UPLOAD_USER}@{UPLOAD_HOST}:{dest}")
    except RunError as ex:
        if not ex.args[1].rstrip().endswith("No such file or directory"):
            raise
        print(dest, "was not found")


def url2path(url):
    if not UPLOAD_URL_PREFIX:
        raise ValueError("%UPLOAD_URL_PREFIX% was not set")
    if not url:
        raise ValueError("Unexpected empty URL")
    if not url.startswith(UPLOAD_URL_PREFIX):
        if LOCAL_INDEX:
            return url
        raise ValueError(f"Unexpected URL: {url}")
    return UPLOAD_PATH_PREFIX + url[len(UPLOAD_URL_PREFIX) :]


def validate_appinstaller(file, uploads):
    NS = {}
    with open(file, "r", encoding="utf-8") as f:
        NS = dict(e for _, e in ET.iterparse(f, events=("start-ns",)))
    for k, v in NS.items():
        ET.register_namespace(k, v)
    NS["x"] = NS[""]

    with open(file, "r", encoding="utf-8") as f:
        xml = ET.parse(f)

    self_uri = xml.find(".[@Uri]", NS).get("Uri")
    if not self_uri:
        print("##[error]Empty Uri attribute in appinstaller file")
        sys.exit(2)
    if not any(
        u.casefold() == self_uri.casefold() and f == file
        for f, u, _ in uploads
    ):
        print("##[error]Uri", self_uri, "in appinstaller file is not where "
              "the appinstaller file is being uploaded.")
        sys.exit(2)

    main = xml.find("x:MainPackage[@Uri]", NS)
    if main is None:
        print("##[error]No MainPackage element with Uri in appinstaller file")
        sys.exit(2)
    package_uri = main.get("Uri")
    if not package_uri:
        print("##[error]Empty Mainpackage.Uri attribute in appinstaller file")
        sys.exit(2)
    if package_uri.casefold() not in [u.casefold() for _, u, _ in uploads]:
        print("##[error]Uri", package_uri, "in appinstaller file is not being uploaded")
        sys.exit(2)

    print(file, "checked:")
    print("-", package_uri, "is part of this upload")
    print("-", self_uri, "is the destination of this file")
    print()


def purge(url):
    if not UPLOAD_HOST or NO_UPLOAD:
        print("Skipping purge of", url, "because UPLOAD_HOST is missing")
        return
    with urlopen(Request(url, method="PURGE", headers={"Fastly-Soft-Purge": 1})) as r:
        r.read()


UPLOAD_DIR = Path(UPLOAD_DIR).absolute()
UPLOAD_URL = UPLOAD_URL.rstrip("/") + "/"

UPLOADS = []

for pat in ("python-manager-*.msix", "python-manager-*.msi", "pymanager.appinstaller"):
    for f in UPLOAD_DIR.glob(pat):
        u = UPLOAD_URL + f.name
        UPLOADS.append((f, u, url2path(u)))

print("Planned uploads:")
for f, u, p in UPLOADS:
    print(f"{f} -> {p}")
    print(f"  Final URL: {u}")
print()

for f, *_ in UPLOADS:
    if f.match("*.appinstaller"):
        validate_appinstaller(f, UPLOADS)

for f, u, p in UPLOADS:
    print("Upload", f, "to", p)
    upload_ssh(f, p)
    print("Purge", u)
    purge(u)
