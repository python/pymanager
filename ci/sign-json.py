import json
import os
import sys

from pathlib import Path
from subprocess import run
from urllib.request import urlopen, Request
from zipfile import ZipFile

try:
    TOOLS = Path(os.environ["SIGN_TOOLS"])
    if not TOOLS.is_dir():
        raise KeyError
except KeyError:
    TOOLS = Path("_sign_tools").absolute()

def download_tool(url, name):
    dest = TOOLS / name
    dest.mkdir(parents=True, exist_ok=True)
    req = Request(url)
    print("Downloading from", req.full_url)
    with urlopen(req) as r:
        with open(dest / "_package.zip", "wb") as f:
            while b := r.read(1024 * 1024):
                f.write(b)
    with ZipFile(dest / "_package.zip", "r") as zf:
        for f in zf.namelist():
            if not f.replace("\\", "/").startswith("bin/"):
                continue
            if not (dest / f).relative_to(dest):
                print("Attempted to extract outside target directory")
                sys.exit(1)
            (dest / f).parent.mkdir(parents=True, exist_ok=True)
            with open(dest / f, "wb") as f2:
                f2.write(zf.read(f))

def find_tool(pattern, url):
    tools = list(TOOLS.glob(pattern))
    if tools:
        return tools[-1]
    if url:
        download_tool(url, pattern.replace("/", "\\").partition("\\")[0])
        tools = list(TOOLS.glob(pattern))
        if tools:
            return tools[-1]
    print("Failed to install tool for", pattern.replace("/", "\\").rpartition("\\")[-1])
    sys.exit(1)

SIGNTOOL = find_tool(
    "sign/bin/*/x64/signtool.exe",
    "https://www.nuget.org/api/v2/package/Microsoft.Windows.SDK.BuildTools/10.0.28000.1721",
)
MAKECAT = find_tool(
    "sign/bin/*/x64/makecat.exe",
    None,
)
DLIB = find_tool(
    "dlib/bin/x64/Azure.CodeSigning.Dlib.dll",
    "https://www.nuget.org/api/v2/package/Microsoft.ArtifactSigning.Client/1.0.128",
)


print("signtool:", SIGNTOOL)
print("makecat:", MAKECAT)
print("dlib:", DLIB)

AAS_DATA = {
    "Endpoint": os.environ["TRUSTED_SIGNING_URI"],
    "CodeSigningAccountName": os.environ["TRUSTED_SIGNING_ACCOUNT"],
    "CertificateProfileName": os.environ["TRUSTED_SIGNING_CERTIFICATE_NAME"],
    "ExcludeCredentials": [
        "ManagedIdentityCredential",
        "WorkloadIdentityCredential",
        "SharedTokenCacheCredential",
        "VisualStudioCredential",
        "VisualStudioCodeCredential",
        "AzureCliCredential",
        "AzurePowerShellCredential",
        "AzureDeveloperCliCredential",
        "InteractiveBrowserCredential"
    ]
}

with open(TOOLS / "metadata.json", "w", encoding="utf-8") as f:
    json.dump(AAS_DATA, f, indent=2)

CAT = Path.cwd() / (Path(sys.argv[1]).stem + ".cat")

with open(TOOLS / "files.cdf", "w", encoding="ansi") as f:
    print("[CatalogHeader]", file=f)
    print("Name=", CAT.name, sep="", file=f)
    print("ResultDir=", CAT.parent, sep="", file=f)
    print("PublicVersion=0x00000001", file=f)
    print("CatalogVersion=2", file=f)
    print("HashAlgorithms=SHA256", file=f)
    print("EncodingType=", file=f)
    print(file=f)
    print("[CatalogFiles]", file=f)
    for a in map(Path, sys.argv[1:]):
        print("<HASH>", a.name, "=", a.absolute(), sep="", file=f)

if CAT.is_file():
    CAT.unlink()

args = [MAKECAT, "-v", TOOLS / "files.cdf"]
print("##[command]", end="")
print(*args)
run(args)

if not CAT.is_file():
    print("Failed to create catalog.")
    sys.exit(2)

args = [
    SIGNTOOL, "sign",
    "/v",
    "/fd", "sha256",
    "/tr", "http://timestamp.acs.microsoft.com",
    "/td", "SHA256",
    "/dlib", DLIB,
    "/dmdf", TOOLS / "metadata.json",
    CAT
]

print("##[command]", end="")
print(*args)
run(args)
