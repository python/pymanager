import json
import sys

from collections import OrderedDict
from pathlib import Path
from urllib.request import Request, urlopen

REPO = Path(__file__).absolute().parent.parent
sys.path.append(str(REPO / "src"))
from manage.verutils import Version


# Like Invoke-RestMethod in PowerShell
def irm(url, method="GET", headers={}):
    headers = {
        "Accepts": "application/json",
        **headers,
    }
    req = Request(url, method=method, headers=headers)
    with urlopen(req) as r:
        return json.load(r)


NUGET_SOURCE = "https://api.nuget.org/v3/index.json"

SCHEMA = {
    "python": {
        "schema": 1,
        "id": "pythoncore-$XYVERSION$-64",
        "sort-version": "$FULLVERSION$",
        "company": "PythonCore",
        "tag": "$XYVERSION$-64",
        "install-for": [
            "$FULLVERSION$-64",
            "$XYVERSIONNOPRE$-64",
            "$XVERSIONNOPRE$-64",
            "$XYVERSIONDEV$-64",
        ],
        "run-for": [
            {"tag": "$FULLVERSION$-64", "target": "python.exe"},
            {"tag": "$XYVERSION$-64", "target": "python.exe"},
            {"tag": "$XVERSIONNOPRE$-64", "target": "python.exe"},
            {"tag": "$FULLVERSION$-64", "target": "pythonw.exe", "windowed": 1},
            {"tag": "$XYVERSION$-64", "target": "pythonw.exe", "windowed": 1},
            {"tag": "$XVERSIONNOPRE$-64", "target": "pythonw.exe", "windowed": 1},
        ],
        "alias": [
            {"name": "python$XYVERSION$.exe", "target": "python.exe"},
            {"name": "python$XVERSIONNOPRE$.exe", "target": "python.exe"},
            {"name": "pythonw$XYVERSION$.exe", "target": "pythonw.exe", "windowed": 1},
            {"name": "pythonw$XVERSIONNOPRE$.exe", "target": "pythonw.exe", "windowed": 1}
        ],
        "shortcuts": [
            {
                "kind": "pep514",
                "Key": r"PythonCore\$XYVERSION$",
                "DisplayName": "Python $FULLVERSION$",
                "SupportUrl": "https://www.python.org/",
                "SysArchitecture": "64bit",
                "SysVersion": "$XYVERSION$",
                "Version": "$FULLVERSION$",
                "InstallPath": {
                    "_": "%PREFIX%",
                    "ExecutablePath": "%PREFIX%python.exe",
                    "WindowedExecutablePath": "%PREFIX%pythonw.exe",
                },
                "Help": {
                    "Online Python Documentation": {
                        "_": "https://docs.python.org/$XYVERSION$/"
                    },
                },
            },
            {
                "kind": "start",
                "Name": "Python $XYVERSION$",
                "Items": [
                    {
                        "Name": "Python $XYVERSION$",
                        "Target": "%PREFIX%python.exe",
                        "Icon": "%PREFIX%python.exe",
                    },
                    {
                        "Name": "Python $XYVERSION$ Documentation",
                        "Icon": r"%SystemRoot%\System32\SHELL32.dll",
                        "IconIndex": 13,
                        "Target": "https://docs.python.org/$XYVERSION$/",
                    },
                ],
            },
            {
                "kind": "uninstall",
                "Publisher": "Python Software Foundation",
                "HelpLink": "https://docs.python.org/$XYVERSION$/",
            },
        ],
        "display-name": "Python $FULLVERSION$",
        "executable": "./python.exe",
        "url": "$PACKAGEURL$"
    },
    "pythonx86": {
        "schema": 1,
        "id": "pythoncore-$XYVERSION$-32",
        "sort-version": "$FULLVERSION$",
        "company": "PythonCore",
        "tag": "$XYVERSION$-32",
        "install-for": [
            "$FULLVERSION$-32",
            "$XYVERSIONNOPRE$-32",
            "$XVERSIONNOPRE$-32",
            "$XYVERSIONDEV$-32",
        ],
        "run-for": [
            {"tag": "$FULLVERSION$-32", "target": "python.exe"},
            {"tag": "$XYVERSION$-32", "target": "python.exe"},
            {"tag": "$XVERSIONNOPRE$-32", "target": "python.exe"},
            {"tag": "$FULLVERSION$-32", "target": "pythonw.exe", "windowed": 1},
            {"tag": "$XYVERSION$-32", "target": "pythonw.exe", "windowed": 1},
            {"tag": "$XVERSIONNOPRE$-32", "target": "pythonw.exe", "windowed": 1},
        ],
        "alias": [
            {"name": "python$XYVERSION$-32.exe", "target": "python.exe"},
            {"name": "python$XVERSIONNOPRE$-32.exe", "target": "python.exe"},
            {"name": "pythonw$XYVERSION$-32.exe", "target": "pythonw.exe", "windowed": 1},
            {"name": "pythonw$XVERSIONNOPRE$-32.exe", "target": "pythonw.exe", "windowed": 1}
        ],
        "shortcuts": [
            {
                "kind": "pep514",
                "Key": r"PythonCore\$XYVERSION$-32",
                "DisplayName": "Python $FULLVERSION$ (32-bit)",
                "SupportUrl": "https://www.python.org/",
                "SysArchitecture": "32bit",
                "SysVersion": "$XYVERSION$",
                "Version": "$FULLVERSION$",
                "InstallPath": {
                    "_": "%PREFIX%",
                    "ExecutablePath": "%PREFIX%python.exe",
                    "WindowedExecutablePath": "%PREFIX%pythonw.exe",
                },
                "Help": {
                    "Online Python Documentation": {
                        "_": "https://docs.python.org/$XYVERSION$/"
                    },
                },
            },
            {
                "kind": "start",
                "Name": "Python $XYVERSION$ (32-bit)",
                "Items": [
                    {
                        "Name": "Python $XYVERSION$ (32-bit)",
                        "Target": "%PREFIX%python.exe",
                        "Icon": "%PREFIX%python.exe",
                    },
                    {
                        "Name": "Python $XYVERSION$ Documentation",
                        "Icon": r"%SystemRoot%\System32\SHELL32.dll",
                        "IconIndex": 13,
                        "Target": "https://docs.python.org/$XYVERSION$/",
                    },
                ],
            },
            {
                "kind": "uninstall",
                "Publisher": "Python Software Foundation",
                "HelpLink": "https://docs.python.org/$XYVERSION$/",
            },
        ],
        "display-name": "Python $FULLVERSION$ (32-bit)",
        "executable": "./python.exe",
        "url": "$PACKAGEURL$"
    },
    "pythonarm64": {
        "schema": 1,
        "id": "pythoncore-$XYVERSION$-arm64",
        "sort-version": "$FULLVERSION$",
        "company": "PythonCore",
        "tag": "$XYVERSION$-arm64",
        "install-for": [
            "$FULLVERSION$-arm64",
            "$XYVERSIONNOPRE$-arm64",
            "$XVERSIONNOPRE$-arm64",
            "$XYVERSIONDEV$-arm64",
        ],
        "run-for": [
            {"tag": "$FULLVERSION$-arm64", "target": "python.exe"},
            {"tag": "$XYVERSION$-arm64", "target": "python.exe"},
            {"tag": "$XVERSIONNOPRE$-arm64", "target": "python.exe"},
            {"tag": "$FULLVERSION$-arm64", "target": "pythonw.exe", "windowed": 1},
            {"tag": "$XYVERSION$-arm64", "target": "pythonw.exe", "windowed": 1},
            {"tag": "$XVERSIONNOPRE$-arm64", "target": "pythonw.exe", "windowed": 1},
        ],
        "alias": [
            {"name": "python$XYVERSION$-arm64.exe", "target": "python.exe"},
            {"name": "python$XVERSIONNOPRE$-arm64.exe", "target": "python.exe"},
            {"name": "pythonw$XYVERSION$-arm64.exe", "target": "pythonw.exe", "windowed": 1},
            {"name": "pythonw$XVERSIONNOPRE$-arm64.exe", "target": "pythonw.exe", "windowed": 1}
        ],
        "shortcuts": [
            {
                "kind": "pep514",
                "Key": r"PythonCore\$XYVERSION$-arm64",
                "DisplayName": "Python $FULLVERSION$ (ARM64)",
                "SupportUrl": "https://www.python.org/",
                "SysArchitecture": "64bit",
                "SysVersion": "$XYVERSION$",
                "Version": "$FULLVERSION$",
                "InstallPath": {
                    "_": "%PREFIX%",
                    "ExecutablePath": "%PREFIX%python.exe",
                    "WindowedExecutablePath": "%PREFIX%pythonw.exe",
                },
                "Help": {
                    "Online Python Documentation": {
                        "_": "https://docs.python.org/$XYVERSION$/"
                    },
                },
            },
            {
                "kind": "start",
                "Name": "Python $XYVERSION$ (ARM64)",
                "Items": [
                    {
                        "Name": "Python $XYVERSION$ (ARM64)",
                        "Target": "%PREFIX%python.exe",
                        "Icon": "%PREFIX%python.exe",
                    },
                    {
                        "Name": "Python $XYVERSION$ Documentation",
                        "Icon": r"%SystemRoot%\System32\SHELL32.dll",
                        "IconIndex": 13,
                        "Target": "https://docs.python.org/$XYVERSION$/",
                    },
                ],
            },
            {
                "kind": "uninstall",
                "Publisher": "Python Software Foundation",
                "HelpLink": "https://docs.python.org/$XYVERSION$/",
            },
        ],
        "display-name": "Python $FULLVERSION$ (ARM64)",
        "executable": "./python.exe",
        "url": "$PACKAGEURL$"
    },
    "python-freethreaded": {
        "schema": 1,
        "id": "pythoncore-$XYVERSION$-t",
        "sort-version": "$FULLVERSION$",
        "company": "PythonCore",
        "tag": "$XYVERSION$t",
        "install-for": [
            "$FULLVERSION$t-64",
            "$XYVERSIONNOPRE$t-64",
            "$XVERSIONNOPRE$t-64",
            "$XYVERSIONDEV$t-64",
        ],
        "run-for": [
            {"tag": "$FULLVERSION$t-64", "target": "python$XYVERSION$t.exe"},
            {"tag": "$XYVERSION$t-64", "target": "python$XYVERSION$t.exe"},
            {"tag": "$XVERSIONNOPRE$t-64", "target": "python$XYVERSION$t.exe"},
            {"tag": "$FULLVERSION$t-64", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"tag": "$XYVERSION$t-64", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"tag": "$XVERSIONNOPRE$t-64", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
        ],
        "alias": [
            {"name": "python$XYVERSION$t.exe", "target": "python$XYVERSION$t.exe"},
            {"name": "python$XVERSIONNOPRE$t.exe", "target": "python$XYVERSION$t.exe"},
            {"name": "pythonw$XYVERSION$t.exe", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"name": "pythonw$XVERSIONNOPRE$t.exe", "target": "pythonw$XYVERSION$t.exe", "windowed": 1}
        ],
        "shortcuts": [
            {
                "kind": "pep514",
                "Key": r"PythonCoreFreeThreaded\$XYVERSION$",
                "DisplayName": "Python $FULLVERSION$ (free-threaded)",
                "SupportUrl": "https://www.python.org/",
                "SysArchitecture": "64bit",
                "SysVersion": "$XYVERSION$",
                "Version": "$FULLVERSION$",
                "InstallPath": {
                    "_": "%PREFIX%",
                    "ExecutablePath": "%PREFIX%python.exe",
                    "WindowedExecutablePath": "%PREFIX%pythonw.exe",
                },
                "Help": {
                    "Online Python Documentation": {
                        "_": "https://docs.python.org/$XYVERSION$/"
                    },
                },
            },
            {
                "kind": "start",
                "Name": "Python $XYVERSION$ (free-threaded)",
                "Items": [
                    {
                        "Name": "Python $XYVERSION$ (free-threaded)",
                        "Target": "%PREFIX%python.exe",
                        "Icon": "%PREFIX%python.exe",
                    },
                    {
                        "Name": "Python $XYVERSION$ Documentation",
                        "Icon": r"%SystemRoot%\System32\SHELL32.dll",
                        "IconIndex": 13,
                        "Target": "https://docs.python.org/$XYVERSION$/",
                    },
                ],
            },
            {
                "kind": "uninstall",
                "Publisher": "Python Software Foundation",
                "HelpLink": "https://docs.python.org/$XYVERSION$/",
            },
        ],
        "display-name": "Python $FULLVERSION$ (free-threaded)",
        "executable": "./python$XYVERSION$t.exe",
        "url": "$PACKAGEURL$"
    },
    "pythonx86-freethreaded": {
        "schema": 1,
        "id": "pythoncore-$XYVERSION$-32-t",
        "sort-version": "$FULLVERSION$",
        "company": "PythonCore",
        "tag": "$XYVERSION$t-32",
        "install-for": [
            "$FULLVERSION$t-32",
            "$XYVERSIONNOPRE$t-32",
            "$XVERSIONNOPRE$t-32",
            "$XYVERSIONDEV$t-32",
        ],
        "run-for": [
            {"tag": "$FULLVERSION$t-32", "target": "python$XYVERSION$t.exe"},
            {"tag": "$XYVERSION$t-32", "target": "python$XYVERSION$t.exe"},
            {"tag": "$XVERSIONNOPRE$t-32", "target": "python$XYVERSION$t.exe"},
            {"tag": "$FULLVERSION$t-32", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"tag": "$XYVERSION$t-32", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"tag": "$XVERSIONNOPRE$t-32", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
        ],
        "alias": [
            {"name": "python$XYVERSION$t-32.exe", "target": "python$XYVERSION$t.exe"},
            {"name": "python$XVERSIONNOPRE$t-32.exe", "target": "python$XYVERSION$t.exe"},
            {"name": "pythonw$XYVERSION$t-32.exe", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"name": "pythonw$XVERSIONNOPRE$t-32.exe", "target": "pythonw$XYVERSION$t.exe", "windowed": 1}
        ],
        "shortcuts": [
            {
                "kind": "pep514",
                "Key": r"PythonCoreFreeThreaded\$XYVERSION$-32",
                "DisplayName": "Python $FULLVERSION$ (32-bit, free-threaded)",
                "SupportUrl": "https://www.python.org/",
                "SysArchitecture": "32bit",
                "SysVersion": "$XYVERSION$",
                "Version": "$FULLVERSION$",
                "InstallPath": {
                    "_": "%PREFIX%",
                    "ExecutablePath": "%PREFIX%python.exe",
                    "WindowedExecutablePath": "%PREFIX%pythonw.exe",
                },
                "Help": {
                    "Online Python Documentation": {
                        "_": "https://docs.python.org/$XYVERSION$/"
                    },
                },
            },
            {
                "kind": "start",
                "Name": "Python $XYVERSION$ (32-bit, free-threaded)",
                "Items": [
                    {
                        "Name": "Python $XYVERSION$ (32-bit, free-threaded)",
                        "Target": "%PREFIX%python.exe",
                        "Icon": "%PREFIX%python.exe",
                    },
                    {
                        "Name": "Python $XYVERSION$ Documentation",
                        "Icon": r"%SystemRoot%\System32\SHELL32.dll",
                        "IconIndex": 13,
                        "Target": "https://docs.python.org/$XYVERSION$/",
                    },
                ],
            },
            {
                "kind": "uninstall",
                "Publisher": "Python Software Foundation",
                "HelpLink": "https://docs.python.org/$XYVERSION$/",
            },
        ],
        "display-name": "Python $FULLVERSION$ (32-bit, free-threaded)",
        "executable": "./python$XYVERSION$t.exe",
        "url": "$PACKAGEURL$"
    },
    "pythonarm64-freethreaded": {
        "schema": 1,
        "id": "pythoncore-$XYVERSION$-arm64-t",
        "sort-version": "$FULLVERSION$",
        "company": "PythonCore",
        "tag": "$XYVERSION$t-arm64",
        "install-for": [
            "$FULLVERSION$t-arm64",
            "$XYVERSIONNOPRE$t-arm64",
            "$XVERSIONNOPRE$t-arm64",
            "$XYVERSIONDEV$t-arm64",
        ],
        "run-for": [
            {"tag": "$FULLVERSION$t-arm64", "target": "python$XYVERSION$t.exe"},
            {"tag": "$XYVERSION$t-arm64", "target": "python$XYVERSION$t.exe"},
            {"tag": "$XVERSIONNOPRE$t-arm64", "target": "python$XYVERSION$t.exe"},
            {"tag": "$FULLVERSION$t-arm64", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"tag": "$XYVERSION$t-arm64", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"tag": "$XVERSIONNOPRE$t-arm64", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
        ],
        "alias": [
            {"name": "python$XYVERSION$t-arm64.exe", "target": "python$XYVERSION$t.exe"},
            {"name": "python$XVERSIONNOPRE$t-arm64.exe", "target": "python$XYVERSION$t.exe"},
            {"name": "pythonw$XYVERSION$t-arm64.exe", "target": "pythonw$XYVERSION$t.exe", "windowed": 1},
            {"name": "pythonw$XVERSIONNOPRE$t-arm64.exe", "target": "pythonw$XYVERSION$t.exe", "windowed": 1}
        ],
        "shortcuts": [
            {
                "kind": "pep514",
                "Key": r"PythonCoreFreeThreaded\$XYVERSION$-arm64",
                "DisplayName": "Python $FULLVERSION$ (ARM64, free-threaded)",
                "SupportUrl": "https://www.python.org/",
                "SysArchitecture": "64bit",
                "SysVersion": "$XYVERSION$",
                "Version": "$FULLVERSION$",
                "InstallPath": {
                    "_": "%PREFIX%",
                    "ExecutablePath": "%PREFIX%python.exe",
                    "WindowedExecutablePath": "%PREFIX%pythonw.exe",
                },
                "Help": {
                    "Online Python Documentation": {
                        "_": "https://docs.python.org/$XYVERSION$/"
                    },
                },
            },
            {
                "kind": "start",
                "Name": "Python $XYVERSION$ (ARM64, free-threaded)",
                "Items": [
                    {
                        "Name": "Python $XYVERSION$ (ARM64, free-threaded)",
                        "Target": "%PREFIX%python.exe",
                        "Icon": "%PREFIX%python.exe",
                    },
                    {
                        "Name": "Python $XYVERSION$ Documentation",
                        "Icon": r"%SystemRoot%\System32\SHELL32.dll",
                        "IconIndex": 13,
                        "Target": "https://docs.python.org/$XYVERSION$/",
                    },
                ],
            },
            {
                "kind": "uninstall",
                "Publisher": "Python Software Foundation",
                "HelpLink": "https://docs.python.org/$XYVERSION$/",
            },
        ],
        "display-name": "Python $FULLVERSION$ (ARM64, free-threaded)",
        "executable": "./python$XYVERSION$t.exe",
        "url": "$PACKAGEURL$"
    },
}


class NoSubstitution(Exception):
    pass

def dict_sub(d, subs):
    if isinstance(d, int):
        return d
    if isinstance(d, str):
        for k, v in subs.items():
            kk = f"${k}$"
            if kk in d:
                if v is None:
                    raise NoSubstitution
                d = d.replace(kk, v)
        return d
    if isinstance(d, list):
        r = []
        for v in d:
            try:
                r.append(dict_sub(v, subs))
            except NoSubstitution:
                # Omit list items with a missing substitution.
                pass
        return r
    if isinstance(d, dict):
        return {k: v for k, v in ((k, dict_sub(v, subs)) for k, v in d.items()) if v}
    raise TypeError("unsupported type: " + repr(type(d)))


RESOURCES = {r['@type']: r['@id'] for r in irm(NUGET_SOURCE)['resources']}
BASE_URL = RESOURCES["PackageBaseAddress/3.0.0"].rstrip("/")

INDEX_OLD = {"versions": []}
INDEX_CURRENT = {"versions": [], "next": ""}

# Earlier versions than this go into "legacy.json"
CURRENT_VERSION = Version("3.12")

for name, schema in SCHEMA.items():
    data = irm(f"{BASE_URL}/{name}/index.json")

    all_versions = sorted((Version(ver) for ver in data["versions"]), reverse=True)

    last_v = None
    for v in all_versions:
        if v.is_prerelease and last_v and v.to_python_style(3, False) == last_v:
            continue
        subs = {
            "FULLVERSION": v.to_python_style(3),
            "XYVERSION": v.to_python_style(2, False),
            "XYVERSIONNOPRE": None if v.is_prerelease else v.to_python_style(2, False),
            "XYVERSIONDEV": (v.to_python_style(2, False) + "-dev") if v.is_prerelease else None,
            "XVERSION": v.to_python_style(1, False),
            "XVERSIONNOPRE": None if v.is_prerelease else v.to_python_style(1, False),
            "PACKAGEURL": f"{BASE_URL}/{name}/{v}/{name}.{v}.nupkg",
        }
        index = INDEX_CURRENT if v >= CURRENT_VERSION else INDEX_OLD
        index["versions"].append(dict_sub(schema, subs))
        last_v = subs["FULLVERSION"]


for file in map(Path, sys.argv[1:]):
    legacy_name = f"{file.stem}-legacy.json"
    INDEX_CURRENT["next"] = legacy_name
    file.parent.mkdir(exist_ok=True, parents=True)
    with open(file, "w", encoding="utf-8") as f:
        json.dump(INDEX_CURRENT, f, indent=2)
    with open(file.with_name(legacy_name), "w", encoding="utf-8") as f:
        json.dump(INDEX_OLD, f, indent=2)


if not sys.argv[1:]:
    INDEX_CURRENT.pop("next", None)
    print(INDEX_CURRENT)
