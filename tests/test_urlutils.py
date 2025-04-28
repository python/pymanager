import os
import time

import pytest

import _native
import manage.urlutils as UU


@pytest.mark.parametrize("url, expect", [pytest.param(*i, id=i[0]) for i in [
    ("https://example.com/", "https://example.com/"),
    ("https://user@example.com/", "https://example.com/"),
    ("https://user:placeholder@example.com/", "https://example.com/"),
]])
def test_urlsanitise(url, expect):
    assert expect == UU.sanitise_url(url)


def test_urlunsanitise():
    candidates = ["https://placeholder:placeholder@example.com/"]
    url = "https://example.com/my_path"
    expect = "https://placeholder:placeholder@example.com/my_path"
    assert expect == UU.unsanitise_url(url, candidates)

    url = "https://test:test@example.com/my_path"
    assert url == UU.unsanitise_url(url, candidates)
    assert url == UU.unsanitise_url(url, [])

    url = "http://example.com/"
    assert None == UU.unsanitise_url(url, candidates)


def test_extract_url_auth():
    assert "1", "2" == UU.extract_url_auth("https://1:2@example.com")
    assert "1", "" == UU.extract_url_auth("https://1@example.com")

    os.environ["PYMANAGER_TEST_VALUE"] = v = str(time.time())
    assert "1", v == UU.extract_url_auth("https://1:%PYMANAGER_TEST_VALUE%@example.com")


@pytest.mark.parametrize("url1, url2, to_parent, expect",
    [pytest.param(*i, id=f'{i[1]}-{i[2]}') for i in [
        ("https://example.com/A/B/C", "D", False, "https://example.com/A/B/C/D"),
        ("https://example.com/A/B/C", "D", True, "https://example.com/A/B/D"),
        ("https://example.com/A/B/C", "/D", None, "https://example.com/D"),
        ("https://example.com/A/B/C", "//D", None, "https://D/A/B/C"),
        ("https://example.com/A/B/C", "//EXAMPLE.COM", None, "https://EXAMPLE.COM/A/B/C"),
        ("https://example.com/A/B/C", "//EXAMPLE.COM/A", True, "https://EXAMPLE.COM/A"),
        ("https://example.com/A/B/C", "//EXAMPLE.COM/", None, "https://EXAMPLE.COM/"),

        ("file:///C:/local/path", "file.json", False, "file:///C:/local/path/file.json"),
        ("file:///C:/local/path", "file.json", True, "file:///C:/local/file.json"),
        ("file:///C:/local/path", ".\\dir\\file.json", False, "file:///C:/local/path/dir/file.json"),
        ("file:///C:/local/path", ".\\dir\\file.json", True, "file:///C:/local/dir/file.json"),

        # Non-binding cases. These are likely going to be errors
        ("https://example.com/A/B/C", "http:", True, "https://example.com/A/B/http:"),
        ("https://example.com/A/B/C", "http:", False, "https://example.com/A/B/C/http:"),
        ("https://example.com/A/B/C", "http://", None, "http://"),
    ]
])
def test_urljoin(url1, url2, to_parent, expect):
    if to_parent != True:
        assert expect == UU.urljoin(url1, url2, to_parent=False)
    if to_parent != False:
        assert expect == UU.urljoin(url1, url2, to_parent=True)


@pytest.fixture
def local_128kb(localserver):
    req = UU._Request(localserver + "/128kb")
    req.chunksize = 1024
    req.progress = []
    req._on_progress = req.progress.append
    yield req


@pytest.fixture
def local_1kb(localserver):
    req = UU._Request(localserver + "/1kb")
    req.chunksize = 1024
    req.progress = []
    req._on_progress = req.progress.append
    yield req


@pytest.fixture
def local_withauth(localserver):
    req = UU._Request(localserver + "/withauth")
    yield req


def test_urllib_urlretrieve(local_128kb, tmp_path):
    local_128kb.outfile = dest = tmp_path / "read.txt"
    progress = local_128kb.progress
    UU._urllib_urlretrieve(local_128kb)
    assert dest.is_file()
    assert progress[:1] + progress[-1:] == [0, 100]
    assert sorted(progress) == progress


def test_urllib_urlopen(local_1kb):
    progress = local_1kb.progress
    data = UU._urllib_urlopen(local_1kb)
    assert data
    assert progress[:1] + progress[-1:] == [0, 100]
    assert sorted(progress) == progress


def test_powershell_urlretrieve(local_128kb, tmp_path):
    local_128kb.outfile = dest = tmp_path / "read.txt"
    progress = local_128kb.progress
    UU._powershell_urlretrieve(local_128kb)
    assert dest.is_file()
    assert progress[:1] + progress[-1:] == [0, 100]
    assert sorted(progress) == progress


def test_powershell_urlopen(local_1kb):
    progress = local_1kb.progress
    data = UU._powershell_urlopen(local_1kb)
    assert data
    assert progress[:1] + progress[-1:] == [0, 100]
    assert sorted(progress) == progress


def test_powershell_urlretrieve_auth(local_withauth, tmp_path):
    local_withauth.outfile = dest = tmp_path / "read.txt"
    creds = {
        local_withauth.url: ("placeholder", "placeholder"),
    }
    local_withauth._on_auth_request = creds.__getitem__
    UU._powershell_urlretrieve(local_withauth)
    assert dest.is_file()
    assert dest.read_bytes() == b"Basic placeholder:placeholder"


def test_urllib_auth(local_withauth):
    import base64
    with pytest.raises(Exception) as ex:
        data = UU._urllib_urlopen(local_withauth)
    assert "401" in str(ex)

    local_withauth.headers = {"Authorization": "Basic " + base64.b64encode("in header".encode()).decode()}
    data = UU._urllib_urlopen(local_withauth)
    assert data == b"Basic in header"
    local_withauth.headers = {}

    local_withauth._on_auth_request =  lambda u: ("on", "demand")
    data = UU._urllib_urlopen(local_withauth)
    assert data == b"Basic on:demand"


def test_winhttp_urlretrieve(local_128kb, tmp_path):
    local_128kb.outfile = dest = tmp_path / "read.txt"
    progress = local_128kb.progress
    UU._winhttp_urlretrieve(local_128kb)
    assert dest.is_file()
    # progress is _probably_ [0, 100, 100]
    assert progress[:1] + progress[-1:] == [0, 100]
    assert progress != [0, 100]
    assert sorted(progress) == progress


def test_winhttp_urlopen(local_1kb):
    progress = local_1kb.progress
    data = UU._winhttp_urlopen(local_1kb)
    assert data
    # progress is _probably_ [0, 100, 100]
    assert progress[:1] + progress[-1:] == [0, 100]
    assert progress != [0, 100]
    assert sorted(progress) == progress


def test_winhttp_https():
    data = UU._winhttp_urlopen(UU._Request("https://example.com"))
    assert data


def test_winhttp_auth(local_withauth):
    import base64
    with pytest.raises(Exception) as ex:
        data = UU._winhttp_urlopen(local_withauth)
    assert "401" in str(ex)

    local_withauth.headers = {"Authorization": "Basic " + base64.b64encode("in header".encode()).decode()}
    data = UU._winhttp_urlopen(local_withauth)
    assert data == b"Basic in header"
    local_withauth.headers = {}

    creds = {local_withauth.url: ("placeholder", "placeholder")}
    local_withauth._on_auth_request = creds.__getitem__
    data = UU._winhttp_urlopen(local_withauth)
    assert data == b"Basic placeholder:placeholder"



def test_bits_urlretrieve(local_128kb, tmp_path):
    local_128kb.outfile = dest = tmp_path / "read.txt"
    progress = local_128kb.progress
    UU._winhttp_urlretrieve(local_128kb)
    assert dest.is_file()
    assert progress[:1] + progress[-1:] == [0, 100]
    assert progress != [0, 100]
    assert sorted(progress) == progress


def test_bits_urlretrieve_auth(local_withauth, tmp_path):
    local_withauth.outfile = dest = tmp_path / "read.txt"
    creds = {
        local_withauth.url: ("placeholder", "placeholder"),
    }
    local_withauth._on_auth_request = creds.__getitem__
    UU._bits_urlretrieve(local_withauth)
    assert dest.is_file()
    assert dest.read_bytes() == b"Basic placeholder:placeholder"


@pytest.fixture
def inject_error():
    try:
        yield _native.bits_inject_error
    finally:
        _native.bits_inject_error(0, 0, 0, 0)


def test_bits_errors(localserver, tmp_path, inject_error):
    import uuid

    ERROR_MR_MID_NOT_FOUND = 0x8007013D

    dest = tmp_path / "read.txt"
    url = localserver + "/128kb"
    conn = _native.bits_connect()

    # Should get our error code, chained to "message not found" error
    inject_error(0xA0000001, 0, 0, 0)
    with pytest.raises(OSError) as ex:
        _native.bits_find_job(conn, uuid.UUID(int=0).bytes_le)
    assert "Retrieving error message" in str(ex.value)
    assert ex.value.winerror & 0xFFFFFFFF == ERROR_MR_MID_NOT_FOUND
    assert isinstance(ex.value.__context__, OSError)
    assert ex.value.__context__.winerror & 0xFFFFFFFF == 0xA0000001

    # Should get our error code, chained to our second error code
    inject_error(0xA0000001, 0, 0xA0000002, 0)
    with pytest.raises(OSError) as ex:
        _native.bits_find_job(conn, uuid.UUID(int=0).bytes_le)
    assert ex.value.winerror & 0xFFFFFFFF == 0xA0000002
    assert "Retrieving error message" in str(ex.value)
    assert isinstance(ex.value.__context__, OSError)
    assert ex.value.__context__.winerror & 0xFFFFFFFF == 0xA0000001

    # Inject errors into get_progress.
    # (No errors while we get started)
    inject_error(0, 0, 0, 0)
    job = _native.bits_begin(conn, "PyManager Test", url, dest)
    try:
        progress = _native.bits_get_progress(conn, job)

        # This will be treated as the reason we couldn't read the error code
        inject_error(1, 0xA0000001, 0, 0)
        with pytest.raises(OSError) as ex:
            _native.bits_get_progress(conn, job)
        # Original error is unspecified OSError
        assert ex.value.__context__.winerror == None
        # The cause is our error
        assert ex.value.winerror & 0xFFFFFFFF == 0xA0000001
    finally:
        _native.bits_cancel(conn, job)

    # Inject errors into get_progress.
    # (No errors while we get started)
    inject_error(0, 0, 0, 0)
    job = _native.bits_begin(conn, "PyManager Test", localserver + "/always404", dest)
    try:
        # This will be treated as the reason we couldn't get text for the error
        # code.
        inject_error(0, 0, 0xA0000002, 0)
        with pytest.raises(OSError) as ex:
            for _ in range(100):
                _native.bits_get_progress(conn, job)
                time.sleep(0.1)
        # HACK: We are overriding errors right now. Commented code is "ideal"
        ## Original error is the 404
        #assert "404" in str(ex.value.__context__)
        #assert ex.value.__context__.winerror & 0xFFFFFFFF == 0x80190194
        ## The cause is our error
        #assert ex.value.winerror & 0xFFFFFFFF == 0xA0000002
        assert "404" in str(ex.value)
        assert ex.value.winerror & 0xFFFFFFFF == 0x80190194
    finally:
        _native.bits_cancel(conn, job)


    # Inject an error when adding credentials
    inject_error(0, 0, 0, 0xA0000001)
    # No credentials specified, so does not raise
    try:
        job = _native.bits_begin(conn, "PyManager Test", url, dest)
    finally:
        _native.bits_cancel(conn, job)
    # Add credentials to cause injected error
    with pytest.raises(OSError) as ex:
        job = _native.bits_begin(conn, "PyManager Test", url, dest, "x", "y")
    # Original error is ours
    assert ex.value.__context__.winerror & 0xFFFFFFFF == 0xA0000001
    # The final error is the missing message
    assert ex.value.winerror & 0xFFFFFFFF == ERROR_MR_MID_NOT_FOUND

