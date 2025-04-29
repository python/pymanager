import pytest

from manage import indexutils as iu
from manage.exceptions import InvalidFeedError


TEST_SCHEMA = {
    "int": int,
    "float": float,
    "str": str,
    "any": ...,
    "anyprops": {...: ...},
    "anystrprops": {...: str},
    "intlist": [int],
    "strlist": [str],
    "list": [
        {"key": ...},
        {"id": ...},
    ],
    "versionlist": [
        {"version": 1, ...: ...},
        {"version": 2, "x": str, "y": str},
    ],
}


EXAMPLE_V1_PACKAGE = {
    "versions": [
        {
            "schema": 1,
            "id": "pythoncore-3.13.0",
            "sort-version": "3.13.0",
            "company": "PythonCore",
            "tag": "3.13",
            "install-for": ["3.13.0", "3.13"],
            "run-for": [
                { "tag": "3.13", "target": "python.exe" },
                { "tag": "3", "target": "python.exe" }
            ],
            "alias": [
                { "name": "python3.13.exe", "target": "python.exe" },
                { "name": "python3.exe", "target": "python.exe" },
                { "name": "pythonw3.13.exe", "target": "pythonw.exe", "windowed": 1 },
                { "name": "pythonw3.exe", "target": "pythonw.exe", "windowed": 1 }
            ],
            "shortcuts": [
                {
                    "kind": "pep514",
                    "DisplayName": "Python 3.13",
                    "SupportUrl": "https://www.python.org/",
                    "SysArchitecture": "64bit",
                    "SysVersion": "3.13",
                    "Version": "3.13.0",
                    "InstallPath": {
                        "_": "%PREFIX%",
                        "ExecutablePath": "%PREFIX%\\python.exe",
                        "WindowedExecutablePath": "%PREFIX%\\pythonw.exe",
                    },
                    "Help": {
                        "Online Python Documentation": {
                            "_": "https://docs.python.org/3.13/"
                        },
                    },
                },
            ],
            "display-name": "Python 3.13.0",
            "executable": "./python.exe",
            "url": "https://api.nuget.org/v3-flatcontainer/python/3.13.0/python.3.13.0.nupkg"
        },
    ],
}


def fake_install_data(v, company="PythonCore", exe="python.exe", sort_version=None):
    assert len(v.split(".")) > 2, "Expect at least x.y.z"
    return {
        "schema": 1,
        "id": f"{company}-{v}",
        "sort-version": sort_version or v,
        "company": company,
        "tag": v,
        "install-for": [v, v.rpartition(".")[0], v.partition(".")[0]],
        "run-for": [
            {"tag": v, "target": exe},
            {"tag": v.rpartition(".")[0], "target": exe},
            {"tag": v.partition(".")[0], "target": exe},
        ],
        "display-name": f"{company} {v}",
        "executable": exe,
    }


class Unstringable:
    def __str__(self):
        raise TypeError("I am unstringable")


@pytest.mark.parametrize("value", [
    {"int": 1},
    {"float": 1.0},
    {"str": "abc"},
    {"any": 1}, {"any": 1.0}, {"any": "abc"},
    {"anyprops": {}}, {"anyprops": {"x": 1}}, {"anyprops": {"y": 2}},
    {"anystrprops": {}}, {"anystrprops": {"x": "abc"}},
    {"intlist": []}, {"intlist": [1, 2, 3]},
    {"strlist": []}, {"strlist": ["x", "y", "z"]},
    {"list": []}, {"list": [{"key": 1}, {"key": 2}, {"id": 3}]},
    {"versionlist": []}, {"versionlist": [{"version": 1, "y": 2}]},
])
def test_schema_parse_valid(value):
    assert iu._validate_one(value, TEST_SCHEMA) == value


@pytest.mark.parametrize("value, expect", [
    ({"int": "1"}, {"int": 1}),
    ({"float": "1"}, {"float": 1.0}),
    ({"str": 1}, {"str": "1"}),
    ({"intlist": 1}, {"intlist": [1]}),
    ({"strlist": "abc"}, {"strlist": ["abc"]}),
    ({"list": {"key": 1}}, {"list": [{"key": 1}]}),
    ({"list": {"id": 1}}, {"list": [{"id": 1}]}),
    ({"versionlist": {"version": 1, "x": 1}}, {"versionlist": [{"version": 1, "x": 1}]}),
    ({"versionlist": {"version": 2, "x": 1, "y": 2}}, {"versionlist": [{"version": 2, "x": "1", "y": "2"}]}),
])
def test_schema_parse_valid_2(value, expect):
    assert iu._validate_one(value, TEST_SCHEMA) == expect


@pytest.mark.parametrize("value, key", [
    ({"int": "xyz"}, "'int'"),
    ({"float": "xyz"}, "'float'"),
    ({"str": Unstringable()}, "'str'"),
    ({"list": {"neither": 1}}, "at list.[0]"),
    ({"list": [{"key": ...}, {"neither": 1}]}, "at list.[1]"),
    ({"versionlist": {"version": 3}}, "at versionlist.[0]"),
    ({"unknown": 1}, "key unknown"),
])
def test_schema_parse_invalid(value, key):
    with pytest.raises(InvalidFeedError) as ex:
        iu._validate_one(value, TEST_SCHEMA)
    assert key in str(ex.value)


def test_v1_package():
    # Ensure we don't change the schema for v1 packages
    iu._validate_one(EXAMPLE_V1_PACKAGE, iu.SCHEMA)


def test_install_lookup():
    index = iu.Index("https://localhost/", {
        "versions": [
            fake_install_data("3.13.1"),
            fake_install_data("3.12.2"),
            fake_install_data("3.11.3"),
            fake_install_data("3.10.4"),
        ],
    })
    assert index.find_to_install("3.13.1")["tag"] == "3.13.1"
    assert index.find_to_install("3.13")["tag"] == "3.13.1"
    assert index.find_to_install("3")["tag"] == "3.13.1"
    assert index.find_to_install("PythonCore/3")["tag"] == "3.13.1"
    assert index.find_to_install("Python/3")["tag"] == "3.13.1"
    assert index.find_to_install("cpy/3")["tag"] == "3.13.1"
    assert index.find_to_install("3.12")["tag"] == "3.12.2"

    assert index.find_to_install("!=3.13")["tag"] == "3.12.2"
    assert index.find_to_install("<=3.12")["tag"] == "3.12.2"
    assert index.find_to_install("<3.12")["tag"] == "3.11.3"
    assert index.find_to_install("<3.12,!=3.11")["tag"] == "3.10.4"
    assert index.find_to_install("<3.12,!=3.10")["tag"] == "3.11.3"


def test_select_package():
    from manage.install_command import select_package

    index = iu.Index("https://localhost/", {
        "versions": [
            fake_install_data("3.13.0-32", sort_version="3.13.0"),
            fake_install_data("3.13.0-64", sort_version="3.13.0"),
        ],
    })
    assert select_package([index], "3.13", "-64")["tag"] == "3.13.0-64"
    assert select_package([index], "3.13-32", "-64")["tag"] == "3.13.0-32"
    assert select_package([index], "3.13", "-32")["tag"] == "3.13.0-32"
    assert select_package([index], "3.13-64", "-32")["tag"] == "3.13.0-64"
