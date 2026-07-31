import os
import time

import pytest

import _native
import manage.urlutils as UU


@pytest.fixture
def clean_proxy_env(monkeypatch):
    for name in ("NO_PROXY", "HTTP_PROXY", "HTTPS_PROXY"):
        monkeypatch.delenv(name, raising=False)


def test_proxy_settings_auto(clean_proxy_env):
    settings = UU._proxy_settings_from_env()
    assert settings.mode == UU.PROXY_MODE_AUTO
    assert settings.proxy_list is None
    assert settings.powershell_proxy is None
    assert settings.username is None
    assert settings.password is None


def test_proxy_settings_no_proxy(clean_proxy_env, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "example.com")
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:8080")

    settings = UU._proxy_settings_from_env()
    assert settings.mode == UU.PROXY_MODE_DIRECT
    assert settings.proxy_list is None
    assert settings.powershell_proxy is None


def test_proxy_settings_override(clean_proxy_env, monkeypatch):
    monkeypatch.setenv(
        "HTTP_PROXY",
        "http://http%40user:http%40password@http-proxy.example:8080/path",
    )
    monkeypatch.setenv(
        "HTTPS_PROXY",
        "https://https%40user:https%40password@https-proxy.example:8443/path",
    )

    settings = UU._proxy_settings_from_env()
    assert settings.mode == UU.PROXY_MODE_OVERRIDE
    assert settings.proxy_list == (
        "http=http://http-proxy.example:8080 "
        "https=https://https-proxy.example:8443"
    )
    assert settings.powershell_proxy == "https://https-proxy.example:8443"
    assert settings.username == "https@user"
    assert settings.password == "https@password"
    assert "http@password" not in settings.proxy_list
    assert "https@password" not in settings.proxy_list


def test_proxy_settings_http_credentials_fallback(clean_proxy_env, monkeypatch):
    monkeypatch.setenv(
        "HTTP_PROXY",
        "proxy%40user:proxy%40password@proxy.example:8080",
    )
    monkeypatch.setenv("HTTPS_PROXY", "https://secure-proxy.example:8443")

    settings = UU._proxy_settings_from_env()
    assert settings.proxy_list == (
        "http=http://proxy.example:8080 "
        "https=https://secure-proxy.example:8443"
    )
    assert settings.powershell_proxy == "https://secure-proxy.example:8443"
    assert settings.username == "proxy@user"
    assert settings.password == "proxy@password"


def test_winhttp_proxy_env(clean_proxy_env, monkeypatch, localserver):
    monkeypatch.setenv("HTTP_PROXY", localserver)
    request = UU._Request("http://proxy-target.invalid/through-proxy")

    assert UU._winhttp_urlopen(request) == b"Proxy OK"


def test_winhttp_proxy_env_auth(clean_proxy_env, monkeypatch, localserver):
    proxy = localserver.replace(
        "http://",
        "http://proxy-user:proxy-password@",
    )
    monkeypatch.setenv("HTTP_PROXY", proxy)
    request = UU._Request("http://proxy-target.invalid/through-auth-proxy")

    assert UU._winhttp_urlopen(request) == b"Proxy Basic proxy-user:proxy-password"


def test_powershell_proxy_env(clean_proxy_env, monkeypatch, localserver, tmp_path):
    monkeypatch.setenv("HTTPS_PROXY", localserver)
    request = UU._Request(
        "http://proxy-target.invalid/through-proxy",
        outfile=tmp_path / "proxy.txt",
    )

    UU._powershell_urlretrieve(request)

    assert request.outfile.read_bytes() == b"Proxy OK"


def test_powershell_proxy_env_auth(
    clean_proxy_env,
    monkeypatch,
    localserver,
    tmp_path,
):
    proxy = localserver.replace(
        "http://",
        "http://proxy-user:proxy-password@",
    )
    monkeypatch.setenv("HTTPS_PROXY", proxy)
    request = UU._Request(
        "http://proxy-target.invalid/through-auth-proxy",
        outfile=tmp_path / "proxy-auth.txt",
    )

    UU._powershell_urlretrieve(request)

    assert request.outfile.read_bytes() == b"Proxy Basic proxy-user:proxy-password"


def test_powershell_no_proxy_env(
    clean_proxy_env,
    monkeypatch,
    localserver,
    tmp_path,
):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "anything")
    request = UU._Request(
        localserver + "/1kb",
        outfile=tmp_path / "direct.txt",
    )

    UU._powershell_urlretrieve(request)

    assert len(request.outfile.read_bytes()) == 1024


def test_bits_proxy_env(clean_proxy_env, monkeypatch, localserver, tmp_path):
    monkeypatch.setenv("HTTP_PROXY", localserver)
    request = UU._Request(
        "http://proxy-target.invalid/through-proxy",
        outfile=tmp_path / "proxy.txt",
    )

    UU._bits_urlretrieve(request)

    assert request.outfile.read_bytes() == b"Proxy OK"


def test_bits_proxy_env_auth(clean_proxy_env, monkeypatch, localserver, tmp_path):
    proxy = localserver.replace(
        "http://",
        "http://proxy-user:proxy-password@",
    )
    monkeypatch.setenv("HTTP_PROXY", proxy)
    request = UU._Request(
        "http://proxy-target.invalid/through-auth-proxy",
        outfile=tmp_path / "proxy-auth.txt",
    )

    UU._bits_urlretrieve(request)

    assert request.outfile.read_bytes() == b"Proxy Basic proxy-user:proxy-password"


def test_winhttp_no_proxy_env(clean_proxy_env, monkeypatch, localserver):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "anything")
    request = UU._Request(localserver + "/1kb")

    assert UU._winhttp_urlopen(request)


def test_bits_no_proxy_env(
    clean_proxy_env,
    monkeypatch,
    localserver,
    tmp_path,
):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "anything")
    request = UU._Request(
        localserver + "/1kb",
        outfile=tmp_path / "direct.txt",
    )

    UU._bits_urlretrieve(request)

    assert request.outfile.is_file()


@pytest.mark.parametrize("url, expect", [pytest.param(*i, id=i[0]) for i in [
    ("https://example.com/", "https://example.com/"),
    ("https://user@example.com/", "https://example.com/"),
    ("https://user:placeholder@example.com/", "https://example.com/"),
    ("https://%placeholder%@example.com/", "https://%placeholder%@example.com/"),
    ("https://%user%:%placeholder%@example.com/", "https://%user%:%placeholder%@example.com/"),
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


def test_urlunsanitise_encoded():
    candidates = ["https://user%40example.com:place%40holder@example.com/"]
    url = "https://example.com/my_path"
    expect = "https://user%40example.com:place%40holder@example.com/my_path"
    assert expect == UU.unsanitise_url(url, candidates)


def test_extract_url_auth():
    assert "1", "2" == UU.extract_url_auth("https://1:2@example.com")
    assert "1", "" == UU.extract_url_auth("https://1@example.com")

    assert ("1", "2") == UU.extract_url_auth("https://%31:%32@example.com")
    assert ("1", "") == UU.extract_url_auth("https://%31@example.com")

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

        # We are intentionally blind to encoded chars.
        ("https://example.com/A/B/C", "%2fD", False, "https://example.com/A/B/C/%2fD"),
        ("https://example.com/A/B/C", "%2f%2fD", False, "https://example.com/A/B/C/%2f%2fD"),
        ("https://example.com/A/B%2fC", "D", True, "https://example.com/A/D"),

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


@pytest.mark.parametrize("cancel,cancel_error", [
    (False, False),
    (True, False),
    (True, True),
])
def test_bits_urlretrieve_keyboard_interrupt(
    monkeypatch, tmp_path, cancel, cancel_error
):
    bits = object()
    job = object()
    cancelled = []
    cancel_requested = []

    monkeypatch.setattr(_native, "coinitialize", lambda: None)
    monkeypatch.setattr(_native, "bits_connect", lambda: bits)
    monkeypatch.setattr(_native, "bits_begin", lambda *a, **k: job)
    monkeypatch.setattr(_native, "bits_serialize_job", lambda *a: b"job-id")

    def bits_get_progress(*args):
        raise KeyboardInterrupt()

    def bits_cancel(*args):
        cancelled.append(args)
        if cancel_error:
            raise OSError()

    monkeypatch.setattr(_native, "bits_get_progress", bits_get_progress)
    monkeypatch.setattr(_native, "bits_cancel", bits_cancel)

    request = UU._Request("https://example.com/download")
    request.outfile = tmp_path / "download.zip"
    progress = []
    request._on_progress = progress.append
    request._on_cancel = lambda: cancel_requested.append(True) or cancel
    jobfile = request.outfile.with_suffix(".job")

    with pytest.raises(KeyboardInterrupt):
        UU._bits_urlretrieve(request)

    assert cancel_requested == [True]
    assert progress == [None]
    assert bool(cancelled) == cancel
    assert jobfile.is_file() == (not cancel or cancel_error)


@pytest.fixture
def inject_error():
    try:
        yield _native.bits_inject_error
    finally:
        _native.bits_inject_error(0, 0, 0, 0)


def test_bits_errors(localserver, tmp_path, inject_error):
    import uuid

    ERROR_MR_MID_NOT_FOUND = 0x13D

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
    # Implicit credentials are always specified
    with pytest.raises(OSError) as ex:
        job = _native.bits_begin(conn, "PyManager Test", url, dest)
    # Original error is ours
    assert ex.value.__context__.winerror & 0xFFFFFFFF == 0xA0000001
    # The final error is the missing message
    assert ex.value.winerror & 0xFFFFFFFF == ERROR_MR_MID_NOT_FOUND

    # Add credentials also causes injected error
    with pytest.raises(OSError) as ex:
        job = _native.bits_begin(conn, "PyManager Test", url, dest, "x", "y")
    # Original error is ours
    assert ex.value.__context__.winerror & 0xFFFFFFFF == 0xA0000001
    # The final error is the missing message
    assert ex.value.winerror & 0xFFFFFFFF == ERROR_MR_MID_NOT_FOUND

