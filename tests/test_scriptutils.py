import base64
import pytest
import subprocess
import sys
import textwrap

from pathlib import PurePath

from manage.scriptutils import (
    find_install_from_script,
    _find_shebang_command,
    _read_script,
    NewEncoding,
    _maybe_quote,
    quote_args,
    split_args
)

def _fake_install(v, **kwargs):
    try:
        kwargs["run-for"] = kwargs.pop("run_for")
    except LookupError:
        pass
    return {
        "company": kwargs.get("company", "Test"),
        "id": f"test-{v}",
        "tag": str(v),
        "version": str(v),
        "prefix": PurePath(f"./pkgs/test-{v}"),
        "executable": PurePath(f"./pkgs/test-{v}/test-binary-{v}.exe"),
        **kwargs
    }

INSTALLS = [
    _fake_install("1.0",
                  run_for=[dict(tag="1.0", target="./test-binary-1.0.exe"),
                           dict(tag="1.0", target="./test-binary-1.0-win.exe", windowed=1)],
                  alias=[dict(name="test1.0.exe", target="./test-binary-1.0.exe"),
                         dict(name="testw1.0.exe", target="./test-binary-w-1.0.exe", windowed=1)],
    ),
    _fake_install("1.1",
                  default=1,
                  run_for=[dict(tag="1.1", target="./test-binary-1.1.exe"),
                           dict(tag="1.1", target="./test-binary-1.1-win.exe", windowed=1)],
                  alias=[dict(name="test1.1.exe", target="./test-binary-1.1.exe"),
                         dict(name="testw1.1.exe", target="./test-binary-w-1.1.exe", windowed=1)],
    ),
    _fake_install("1.3.1", company="PythonCore"),
    _fake_install("1.3.2", company="PythonOther"),
    _fake_install("2.0", alias=[{"name": "test2.0.exe", "target": "./test-binary-2.0.exe"}]),
]

@pytest.mark.parametrize("script, expect", [
    ("", None),
    ("#! /usr/bin/test1.0\n#! /usr/bin/test2.0\n", "1.0"),
    ("#! /usr/bin/test2.0\n#! /usr/bin/test1.0\n", "2.0"),
    ("#! /usr/bin/test1.0.exe\n#! /usr/bin/test2.0\n", "1.0"),
    ("#!test1.0.exe\n", "1.0"),
    ("#!test1.1.exe\n", "1.1"),
    ("#!test1.2.exe\n", None),
    ("#!test-binary-1.1.exe\n", "1.1"),
    ("#!.\\pkgs\\test-1.1\\test-binary-1.1.exe\n", "1.1"),
    ("#!.\\pkgs\\test-1.0\\test-binary-1.1.exe\n", None),
    ("#! /usr/bin/env test1.0\n", "1.0"),
    ("#! /usr/bin/env test2.0\n", "2.0"),
    ("#! /usr/bin/env -S test2.0\n", "2.0"),
    # Legacy handling specifically for "python<TAG>"
    ("#! /usr/bin/python1.3.1", "1.3.1"),
    ("#! /usr/bin/env python1.3.1", "1.3.1"),
    ("#! /usr/bin/python1.3.2", None),
])
def test_read_shebang(fake_config, tmp_path, script, expect):
    fake_config.installs.extend(INSTALLS)
    if expect:
        expect = [i for i in INSTALLS if i["tag"] == expect][0]

    script_py = tmp_path / "test-script.py"
    if isinstance(script, str):
        script = script.encode()
    script_py.write_bytes(script)
    try:
        actual = find_install_from_script(fake_config, script_py, windowed=False)
        assert expect == actual
    except LookupError:
        assert not expect


@pytest.mark.parametrize("script, expect, windowed", [
    # Non-windowed alias from non-windowed launcher uses default 'executable'
    ("#! /usr/bin/test1.0\n", "test-binary-1.0.exe", False),
    # Non-windowed alias from windowed launcher uses first windowed 'run-for'
    ("#! /usr/bin/test1.0\n", "test-binary-1.0-win.exe", True),
    # Windowed alias from either launcher uses the discovered alias
    ("#! /usr/bin/testw1.0\n", "test-binary-w-1.0.exe", False),
    ("#! /usr/bin/testw1.0\n", "test-binary-w-1.0.exe", True),

    # No windowed option for 2.0, so picks the regular executable
    ("#! /usr/bin/test2.0\n", "test-binary-2.0.exe", False),
    ("#! /usr/bin/test2.0\n", "test-binary-2.0.exe", True),
    ("#! /usr/bin/testw2.0\n", None, False),
    ("#! /usr/bin/testw2.0\n", None, True),
    ("#!test1.0.exe\n", "test-binary-1.0.exe", False),
    ("#!test1.0.exe\n", "test-binary-1.0-win.exe", True),
    ("#!testw1.0.exe\n", "test-binary-w-1.0.exe", False),
    ("#!testw1.0.exe\n", "test-binary-w-1.0.exe", True),
    ("#!test1.1.exe\n", "test-binary-1.1.exe", False),
    ("#!test1.1.exe\n", "test-binary-1.1-win.exe", True),
    ("#!testw1.1.exe\n", "test-binary-w-1.1.exe", False),
    ("#!testw1.1.exe\n", "test-binary-w-1.1.exe", True),

    # Matching executable name won't be overridden by windowed setting
    ("#!test-binary-1.1.exe\n", "test-binary-1.1.exe", False),
    ("#!test-binary-1.1.exe\n", "test-binary-1.1.exe", True),
    ("#! /usr/bin/env test1.0\n", "test-binary-1.0.exe", False),
    ("#! /usr/bin/env test1.0\n", "test-binary-1.0-win.exe", True),
    ("#! /usr/bin/env testw1.0\n", "test-binary-w-1.0.exe", False),
    ("#! /usr/bin/env testw1.0\n", "test-binary-w-1.0.exe", True),

    # Default name will use default 'executable' or first windowed 'run-for'
    ("#! /usr/bin/python\n", "test-binary-1.1.exe", False),
    ("#! /usr/bin/python\n", "test-binary-1.1-win.exe", True),
    ("#! /usr/bin/pythonw\n", "test-binary-1.1-win.exe", False),
    ("#! /usr/bin/pythonw\n", "test-binary-1.1-win.exe", True),
])
def test_read_shebang_windowed(fake_config, tmp_path, script, expect, windowed):
    fake_config.installs.extend(INSTALLS)

    script_py = tmp_path / "test-script.py"
    if isinstance(script, str):
        script = script.encode()
    script_py.write_bytes(script)
    try:
        actual = find_install_from_script(fake_config, script_py, windowed=windowed)
        assert actual["executable"].match(expect)
    except LookupError:
        assert not expect


def test_default_py_shebang(fake_config, tmp_path):
    inst = _fake_install("1.0", company="PythonCore", prefix=PurePath("C:\\TestRoot"), default=True)
    inst["run-for"] = [
        dict(name="python.exe", target=".\\python.exe"),
        dict(name="pythonw.exe", target=".\\pythonw.exe", windowed=1),
    ]
    fake_config.installs[:] = [inst]

    def t(n):
        return _find_shebang_command(fake_config, n, windowed=False)

    # Finds the install's default executable
    assert t("python")["executable"].match("test-binary-1.0.exe")
    assert t("py")["executable"].match("test-binary-1.0.exe")
    assert t("python1.0")["executable"].match("test-binary-1.0.exe")
    # Finds the install's run-for executable with windowed=1
    assert t("pythonw")["executable"].match("pythonw.exe")
    assert t("pyw")["executable"].match("pythonw.exe")
    assert t("pythonw1.0")["executable"].match("pythonw.exe")



@pytest.mark.parametrize("script, expect", [
    ("# not a coding comment", None),
    ("# coding: utf-8-sig", None),
    ("# coding: utf-8", "utf-8"),
    ("# coding: ascii", "ascii"),
    ("# actually a coding: comment", "comment"),
    ("#~=~=~=coding:ascii=~=~=~=~", "ascii"),
    ("#! /usr/bin/env python\n# coding: ascii", None),
])
def test_read_coding_comment(fake_config, tmp_path, script, expect):
    script_py = tmp_path / "test-script.py"
    if isinstance(script, str):
        script = script.encode()
    script_py.write_bytes(script)
    try:
        _read_script(fake_config, script_py, "utf-8-sig", windowed=False)
    except NewEncoding as enc:
        assert enc.args[0] == expect
    except LookupError:
        assert not expect
    else:
        assert not expect


@pytest.mark.parametrize("arg, expect", [pytest.param(*a, id=a[0]) for a in [
    ('abc', 'abc'),
    ('a b c', '"a b c"'),
    ('abc ', '"abc "'),
    (' abc', '" abc"'),
    ('a1\\b\\c', 'a1\\b\\c'),
    ('a2\\ b', '"a2\\ b"'),
    ('a3\\b\\', 'a3\\b\\'),
    ('a4 b\\', '"a4 b\\\\"'),
    ('a5 b\\\\', '"a5 b\\\\\\\\"'),
    ('a1"b', 'a1\\"b'),
    ('a2\\"b', 'a2\\\\\\"b'),
    ('a3\\\\"b', 'a3\\\\\\\\\\"b'),
    ('a4\\\\\\"b', 'a4\\\\\\\\\\\\\\"b'),
    ('a5 "b', '"a5 \\"b"'),
    ('a6\\ "b', '"a6\\ \\"b"'),
    ('a7 \\"b', '"a7 \\\\\\"b"'),
]])
def test_quote_one_arg(arg, expect):
    # Test our expected result by passing it to Python and checking what it sees
    test_cmd = (
        'python -c "import base64, sys; '
        'expect = base64.b64decode(\'{}\').decode(); '
        'print(\'Expect:\', repr(expect), \' Actual:\', repr(sys.argv[1])); '
        'sys.exit(0 if expect == sys.argv[1] else 1)" {} END_OF_ARGS'
    ).format(base64.b64encode(arg.encode()).decode("ascii"), expect)
    subprocess.check_call(test_cmd, executable=sys.executable)
    # Test that our quote function produces the expected result
    assert expect == _maybe_quote(arg)


@pytest.mark.parametrize("arg, expect, expect_call", [pytest.param(*a, id=a[0]) for a in [
    ('"a1 b"', '"a1 b"', 'a1 b'),
    ('"a2" b"', '"a2\\" b"', 'a2" b'),
]])
def test_quote_one_quoted_arg(arg, expect, expect_call):
    # Test our expected result by passing it to Python and checking what it sees
    test_cmd = (
        'python -c "import base64, sys; '
        'expect = base64.b64decode(\'{}\').decode(); '
        'print(\'Expect:\', repr(expect), \' Actual:\', repr(sys.argv[1])); '
        'sys.exit(0 if expect == sys.argv[1] else 1)" {} END_OF_ARGS'
    ).format(base64.b64encode(expect_call.encode()).decode("ascii"), expect)
    subprocess.check_call(test_cmd, executable=sys.executable)
    # Test that our quote function produces the expected result
    assert expect == _maybe_quote(arg)


# We're not going to try too hard here - most of the tricky logic is covered
# by the previous couple of tests.
@pytest.mark.parametrize("args, expect", [pytest.param(*a, id=a[1]) for a in [
    (["a1", "b", "c"], 'a1 b c'),
    (["a2 b", "c d"], '"a2 b" "c d"'),
    (['a3"b', 'c"d', 'e f'], 'a3\\"b c\\"d "e f"'),
    (['a4"b c"d', 'e f'], '"a4\\"b c\\"d" "e f"'),
    (['a5\\b\\', 'c\\d'], 'a5\\b\\ c\\d'),
    (['a6\\b\\ c\\', 'd\\e'], '"a6\\b\\ c\\\\" d\\e'),
]])
def test_quote_args(args, expect):
    # Test our expected result by passing it to Python and checking what it sees
    test_cmd = (
        'python -c "import base64, sys; '
        'expect = base64.b64decode(\'{}\').decode().split(\'\\0\'); '
        'print(\'Expect:\', repr(expect), \' Actual:\', repr(sys.argv)); '
        'sys.exit(0 if expect == sys.argv[1:-1] else 1)" {} END_OF_ARGS'
    ).format(base64.b64encode('\0'.join(args).encode()).decode("ascii"), expect)
    subprocess.check_call(test_cmd, executable=sys.executable)
    # Test that our quote function produces the expected result
    assert expect == quote_args(args)
    # Test that our split function produces the same result
    assert args == split_args(expect), expect
