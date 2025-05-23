import pytest
import re

from itertools import zip_longest

from manage import list_command
from manage.indexutils import Index

FAKE_INSTALLS = [
    {"company": "Company2", "tag": "1.0", "sort-version": "1.0"},
    {"company": "Company1", "tag": "2.0", "sort-version": "2.0"},
    {"company": "Company1", "tag": "1.0", "sort-version": "1.0", "default": True},
]

FAKE_INDEX = {
    "versions": [
        {
            **{k: v for k, v in i.items() if k not in ("default",)},
            "schema": 1,
            "id": f"{i['company']}-{i['tag']}",
            "install-for": [i["tag"]],
        } for i in FAKE_INSTALLS
    ]
}

class ListCapture:
    def __init__(self):
        self.args = []
        # Out of order on purpose - list_command should not modify order
        self.installs = FAKE_INSTALLS
        self.captured = []
        self.source = None
        self.install_dir = "<none>"
        self.format = "test"
        self.one = False
        self.unmanaged = True
        list_command.FORMATTERS["test"] = lambda c, i: self.captured.extend(i)

    def __call__(self, *filters, **kwargs):
        self.args = filters
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise TypeError(f"command has no option {k!r}")
            setattr(self, k, v)
        self.captured.clear()
        list_command.execute(self)
        return [f"{i['company']}/{i['tag']}" for i in self.captured]

    def get_installs(self, include_unmanaged=False):
        assert include_unmanaged == self.unmanaged
        return self.installs


@pytest.fixture
def list_cmd():
    try:
        yield ListCapture()
    finally:
        list_command.FORMATTERS.pop("test", None)


def test_list(list_cmd):
    # list_command does not sort its entries - get_installs() does that
    assert list_cmd() == [
        "Company2/1.0",
        "Company1/2.0",
        "Company1/1.0",
    ]
    # unmanaged doesn't affect our result (because we shim the function that
    # does the check), but it'll at least ensure it gets passed through.
    assert list_cmd(unmanaged=True)


def test_list_filter(list_cmd):
    assert list_cmd("2.0") == ["Company1/2.0"]
    assert list_cmd("1.0") == ["Company2/1.0", "Company1/1.0"]
    assert list_cmd("Company1/") == ["Company1/2.0", "Company1/1.0"]
    assert list_cmd("Company1\\") == ["Company1/2.0", "Company1/1.0"]
    assert list_cmd("Company\\") == ["Company2/1.0", "Company1/2.0", "Company1/1.0"]

    assert list_cmd(">1") == ["Company1/2.0"]
    assert list_cmd(">=1") == ["Company2/1.0", "Company1/2.0", "Company1/1.0"]
    assert list_cmd("<=2") == ["Company2/1.0", "Company1/2.0", "Company1/1.0"]
    assert list_cmd("<2") == ["Company2/1.0", "Company1/1.0"]

    assert list_cmd("1", "2") == ["Company2/1.0", "Company1/2.0", "Company1/1.0"]
    assert list_cmd("Company1\\1", "Company2\\1") == ["Company2/1.0", "Company1/1.0"]


def test_list_one(list_cmd):
    assert list_cmd("2", one=True) == ["Company1/2.0"]
    # Gets Company1/1.0 because it's marked as default
    assert list_cmd("1", one=True) == ["Company1/1.0"]


def from_index(*filters):
    return [
        f"{i['company']}/{i['tag']}"
        for i in list_command._get_installs_from_index([Index("./index.json", FAKE_INDEX)], filters)
    ]


def test_list_online():
    assert from_index("Company1\\2.0") == ["Company1/2.0"]
    assert from_index("Company2\\", "Company1\\1") == ["Company2/1.0", "Company1/1.0"]
    assert from_index() == ["Company1/2.0", "Company2/1.0", "Company1/1.0"]


def test_format_table(assert_log):
    list_command.format_table(None, FAKE_INSTALLS)
    assert_log(
        (r"!B!Tag\s+Name\s+Managed By\s+Version\s+Alias\s*!W!", ()),
        (r"Company2\\1\.0\s+Company2\s+1\.0", ()),
        (r"Company1\\2\.0\s+Company1\s+2\.0", ()),
        (r"!G!Company1\\1\.0\s+\*\s+Company1\s+1\.0\s*!W!", ()),
    )


def test_format_table_aliases(assert_log):
    list_command.format_table(None, [
        {
            "company": "COMPANY",
            "tag": "TAG",
            "display-name": "DISPLAY",
            "sort-version": "VER",
            "alias": [
                {"name": "python.exe"},
                {"name": "pythonw.exe"},
                {"name": "python3.10.exe"},
                {"name": "pythonw3.10.exe"},
            ],
        }
    ])
    assert_log(
        (r"!B!Tag\s+Name\s+Managed By\s+Version\s+Alias\s*!W!", ()),
        (r"COMPANY\\TAG\s+DISPLAY\s+COMPANY\s+VER\s+" + re.escape("python[w].exe, python[w]3.10.exe"), ()),
    )


def test_format_table_truncated(assert_log):
    list_command.format_table(None, [
        {
            "company": "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4,
            "tag": "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4,
            "display-name": "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4,
            "sort-version": "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4,
            "alias": [
                {"name": "ABCDEFGHIJKLMNOPQRSTUVWXYZ" * 4},
            ],
        }
    ])
    assert_log(
        (r"!B!Tag\s+Name\s+Managed By\s+Version\s+Alias\s*!W!", ()),
        (r"\w{27}\.\.\.\s+\w{57}\.\.\.\s+\w{27}\.\.\.\s+\w{12}\.\.\.\s+\w{47}\.\.\.", ()),
        (r"", ()),
        (r".+columns were truncated.+", ()),
    )


def test_format_table_empty(assert_log):
    list_command.format_table(None, [])
    assert_log(
        (r"!B!Tag\s+Name\s+Managed By\s+Version\s+Alias\s*!W!", ()),
        (r".+No runtimes.+", ()),
    )


def test_format_csv(assert_log):
    list_command.format_csv(None, FAKE_INSTALLS)
    # CSV format only contains columns that are present, so this doesn't look
    # as complete as for normal installs, but it's fine for the test.
    assert_log(
        "company,tag,sort-version,default",
        "Company2,1.0,1.0,",
        "Company1,2.0,2.0,",
        "Company1,1.0,1.0,True",
    )


def test_format_csv_complex(assert_log):
    data = [
        {
            **d,
            "alias": [dict(name=f"n{i}.{j}", target=f"t{i}.{j}") for j in range(i + 1)]
        }
        for i, d in enumerate(FAKE_INSTALLS)
    ]
    list_command.format_csv(None, data)
    assert_log(
        "company,tag,sort-version,alias.name,alias.target.default",
        "Company2,1.0,1.0,n0.0,t0.0,",
        "Company1,2.0,2.0,n1.0,t1.0,",
        "Company1,2.0,2.0,n1.1,t1.1,",
        "Company1,1.0,1.0,n2.0,t2.0,True",
        "Company1,1.0,1.0,n2.1,t2.1,True",
        "Company1,1.0,1.0,n2.2,t2.2,True",
    )


def test_format_csv_empty(assert_log):
    list_command.format_csv(None, [])
    assert_log(assert_log.end_of_log())


def test_csv_exclude():
    result = list(list_command._csv_filter_and_expand([
        dict(a=1, b=2),
        dict(a=3, c=4),
        dict(a=5, b=6, c=7),
    ], exclude={"b"}))
    assert result == [dict(a=1), dict(a=3, c=4), dict(a=5, c=7)]


def test_csv_expand():
    result = list(list_command._csv_filter_and_expand([
        dict(a=[1, 2], b=[3, 4]),
        dict(a=[5], b=[6]),
        dict(a=7, b=8),
    ], expand={"a"}))
    assert result == [
        dict(a=1, b=[3, 4]),
        dict(a=2, b=[3, 4]),
        dict(a=5, b=[6]),
        dict(a=7, b=8),
    ]


def test_formats(assert_log):
    list_command.list_formats(None, ["fake", "installs", "that", "should", "crash", 123])
    assert_log(
        r".*Format\s+Description",
        r"table\s+Lists.+",
        # Assume the rest are okay
    )
