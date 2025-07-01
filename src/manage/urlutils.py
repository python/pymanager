import os
import time

from .logging import LOGGER
from .fsutils import ensure_tree, rmtree, unlink
from .pathutils import Path, PurePath

try:
    from _native import file_url_to_path
except ImportError:
    from nturl2path import url2pathname as file_url_to_path

# Indexes into winhttp_urlsplit result for readability
U_SCHEME = 0
U_USERNAME = 1
U_PASSWORD = 2
U_NETLOC = 3
U_PORT = 4
U_PATH = 5
U_EXTRA = 6

try:
    from _native import winhttp_urlsplit, winhttp_urlunsplit
except ImportError:
    import urllib.parse
    def winhttp_urlsplit(u):
        p = urllib.parse.urlsplit(u)
        extra = f"?{p.query}" if p.query else ""
        extra = f"{extra}#{p.fragment}" if p.fragment else extra
        return (p.scheme, p.username, p.password, p.hostname, p.port, p.path, extra)

    def winhttp_urlunsplit(*a):
        netloc = a[U_NETLOC]
        if a[U_USERNAME]:
            if a[U_PASSWORD]:
                netloc = f"{a[U_USERNAME]}:{a[U_PASSWORD]}@{netloc}"
            else:
                netloc = f"{a[U_USERNAME]}@{netloc}"
        if a[U_PORT]:
            if a[U_PORT] == 80 and a[U_SCHEME].casefold() == "http":
                pass
            elif a[U_PORT] == 443 and a[U_SCHEME].casefold() == "https":
                pass
            else:
                netloc = f"{netloc}:{a[U_PORT]}"
        if a[U_EXTRA]:
            query, _, fragment = a[U_EXTRA].rpartition("#")
            if query[:1] == "?":
                query = query[1:]
        else:
            query = fragment = ""
        return urllib.parse.urlunsplit((a[0], netloc, a[U_PATH], query, fragment))


ENABLE_BITS = os.getenv("PYMANAGER_ENABLE_BITS_DOWNLOAD", "1").lower()[:1] in "1yt"
ENABLE_WINHTTP = os.getenv("PYMANAGER_ENABLE_WINHTTP_DOWNLOAD", "1").lower()[:1] in "1yt"
ENABLE_URLLIB = os.getenv("PYMANAGER_ENABLE_URLLIB_DOWNLOAD", "1").lower()[:1] in "1yt"
ENABLE_POWERSHELL = os.getenv("PYMANAGER_ENABLE_POWERSHELL_DOWNLOAD", "1").lower()[:1] in "1yt"

SUPPORTED_SCHEMES = "http".casefold(), "https".casefold(), "file".casefold()

class NoInternetError(Exception):
    pass


class _Request:
    def __init__(self, url, method="GET", headers={}, outfile=None):
        self.url = url
        self.method = method.upper()
        self.headers = dict(headers)
        self.chunksize = 64 * 1024
        self.username = None
        self.password = None
        self.outfile = Path(outfile) if outfile else None
        self._on_progress = None
        self._on_auth_request = None

    def __str__(self):
        return sanitise_url(self.url)

    def on_progress(self, progress):
        if self._on_progress:
            self._on_progress(progress)

    def on_auth_request(self, url=None):
        if url is None:
            url = self.url
        if self._on_auth_request:
            return self._on_auth_request(url)
        if self.username or self.password:
            return self.username, self.password
        return None


def _bits_urlretrieve(request):
    from _native import (coinitialize, bits_connect, bits_begin, bits_cancel,
        bits_get_progress, bits_retry_with_auth, bits_find_job, bits_serialize_job)

    assert request.outfile
    LOGGER.debug("_bits_urlretrieve: %s", request)
    coinitialize()
    bits = bits_connect()

    outfile = request.outfile

    job = None
    jobfile = outfile.with_suffix(".job")
    last_progress = None
    tried_auth = False
    try:
        job_id = jobfile.read_bytes()
    except OSError:
        job_id = None
    else:
        LOGGER.debug("Recovering job %s from %s", job_id, jobfile)

    try:
        if job_id:
            try:
                job = bits_find_job(bits, job_id)
            except OSError as ex:
                LOGGER.debug("Failed to recover job due to %s", ex)
                job = None
            else:
                last_progress = bits_get_progress(bits, job)
        if not job:
            LOGGER.debug("Starting new BITS job: %s -> %s", request, outfile)
            ensure_tree(outfile)
            job = bits_begin(bits, PurePath(outfile).name, request.url, outfile)
            LOGGER.debug("Writing %s", jobfile)
            jobfile.write_bytes(bits_serialize_job(bits, job))

        LOGGER.debug("Downloading %s", request)
        last_progress = -1
        while last_progress < 100:
            try:
                progress = bits_get_progress(bits, job)
            except OSError as ex:
                if (ex.winerror or 0) & 0xFFFFFFFF == 0x80190191:
                    # Returned HTTP status 401 (0x191)
                    if not tried_auth:
                        auth = request.on_auth_request()
                        if auth:
                            tried_auth = True
                            bits_retry_with_auth(bits, job, *auth)
                            continue
                if (ex.winerror or 0) & 0xFFFFFFFF == 0x80190194:
                    # Returned HTTP status 404 (0x194)
                    raise FileNotFoundError() from ex
                raise
            if progress > last_progress:
                request.on_progress(progress)
            last_progress = progress
            time.sleep(0.1)
    except OSError as ex:
        if job:
            bits_cancel(bits, job)
        if jobfile.is_file():
            unlink(jobfile)
        if (ex.winerror or 0) & 0xFFFFFFFF == 0x80200010:
            raise NoInternetError() from ex
        raise
    unlink(jobfile)


def _winhttp_urlopen(request):
    from _native import winhttp_urlopen, winhttp_isconnected
    headers = {k.lower(): v for k, v in request.headers.items()}
    accepts = headers.pop("accepts", "application/*;text/*")
    header_str = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
    method = request.method.upper()
    LOGGER.debug("winhttp_urlopen: %s", request)
    try:
        data = winhttp_urlopen(request.url, method, header_str, accepts,
            request.chunksize, request.on_progress, request.on_auth_request)
    except OSError as ex:
        if ex.winerror == 0x00002EE7:
            LOGGER.debug("winhttp_isconnected: %s", winhttp_isconnected())
            if not winhttp_isconnected():
                raise NoInternetError() from ex
        if (ex.winerror or 0) & 0xFFFFFFFF == 0x80190194:
            # Returned HTTP status 404 (0x194)
            raise FileNotFoundError() from ex
        raise
    if data[:3] == b"\xEF\xBB\xBF":
        data = data[3:]
    return data

def _winhttp_urlretrieve(request):
    assert request.outfile
    request.outfile.write_bytes(_winhttp_urlopen(request))


def _basic_auth_header(username, password):
    from base64 import b64encode
    pair = f"{username}:{password}".encode("utf-8")
    token = b64encode(pair)
    return "Basic " + token.decode("ascii")


def _urllib_urlopen(request):
    import urllib.error
    from urllib.request import Request, urlopen

    LOGGER.debug("urlopen: %s", request)
    req = Request(request.url, method=request.method, headers=request.headers)
    try:
        request.on_progress(0)
        try:
            r = urlopen(req)
        except urllib.error.HTTPError as ex:
            if ex.status == 401:
                auth = request.on_auth_request()
                if not auth:
                    raise
                req.headers["Authorization"] = _basic_auth_header(*auth)
                r = urlopen(req)
            elif ex.status == 404:
                raise FileNotFoundError from ex
            else:
                raise
        with r:
            data = r.read()
        request.on_progress(100)
        return data
    finally:
        LOGGER.debug("urlopen: complete")


def _urllib_urlretrieve(request):
    import urllib.error
    from urllib.request import Request, urlopen

    outfile = request.outfile
    LOGGER.debug("urlretrieve: %s -> %s", request, outfile)
    ensure_tree(outfile)
    unlink(outfile)
    req = Request(request.url, method=request.method, headers=request.headers)
    try:
        request.on_progress(0)
        try:
            r = urlopen(req)
        except urllib.error.HTTPError as ex:
            if ex.status == 401:
                req.auth = request.on_auth_request()
                if not req.auth:
                    raise
                r = urlopen(req)
            else:
                raise
        with r:
            progress = 0
            try:
                total = int(r.headers.get("Content-Length", 0))
            except ValueError:
                total = 1
            with open(outfile, "wb") as f:
                for chunk in iter(lambda: r.read(request.chunksize), b""):
                    f.write(chunk)
                    progress += len(chunk)
                    request.on_progress((progress * 100) // total)
        request.on_progress(100)
    finally:
        LOGGER.debug("urlretrieve: complete")


def _powershell_urlopen(request):
    import tempfile
    cwd = tempfile.mkdtemp()
    try:
        request.outfile = Path(cwd) / "response.dat"
        _powershell_urlretrieve(request)
        return request.outfile.read_bytes()
    finally:
        rmtree(cwd)


def _powershell_urlretrieve(request):
    from base64 import b64encode
    import subprocess

    headers = request.headers
    if "Authorization" not in headers:
        auth = extract_url_auth(request.url)
        if not auth:
            auth = request.on_auth_request(request.url)
        if auth:
            headers = {**headers, "Authorization": _basic_auth_header(*auth)}

    def _f(v):
        if isinstance(v, str):
            return "'" + v.replace("'", "''") + "'"
        return str(v)

    ps_headers = " ".join(f"{k!r}={_f(v)};" for k, v in headers.items())

    powershell = Path(os.getenv("SystemRoot")) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = fr"""$ProgressPreference = "SilentlyContinue"
$headers = @{{ {ps_headers} }}
$r = Invoke-WebRequest '{request.url}' -UseBasicParsing `
    -Headers $headers `
    -UseDefaultCredentials `
    -Method "{request.method}" `
    -OutFile "{request.outfile}"
"""
    LOGGER.debug("PowerShell script: %s", script)
    with subprocess.Popen(
        [powershell,
            "-ExecutionPolicy", "Bypass",
            "-OutputFormat", "Text",
            "-NonInteractive",
            "-EncodedCommand", b64encode(script.encode("utf-16-le"))
        ],
        cwd=request.outfile.parent,
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    ) as p:
        request.on_progress(0)
        start = time.time()
        while True:
            try:
                try:
                    out = p.communicate(b'', timeout=10.0)[0].decode("utf-8", "replace")
                    if '<S S="Error">Invoke-WebRequest' in out:
                        raise RuntimeError("Powershell download failed:" + out)
                    request.on_progress(100)
                    LOGGER.debug("PowerShell Output: %s", out)
                    return
                except subprocess.TimeoutExpired:
                    if not request.outfile.exists():
                        # Suppress the original exception to avoid leaking the command
                        raise subprocess.TimeoutExpired(powershell, int(time.time() - start)) from None
            except:
                p.terminate()
                out = p.communicate()[0]
                LOGGER.debug("PowerShell Output: %s", out.decode("utf-8", "replace"))
                raise


def urlopen(url, method="GET", headers={}, on_progress=None, on_auth_request=None):
    scheme, sep, path = url.partition("://")
    if not sep:
        scheme = "file"
        url = Path(url).absolute().as_uri()
    elif scheme.casefold() not in SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported scheme: {scheme}")

    if scheme.casefold() == "file".casefold():
        with open(file_url_to_path(url), "rb") as f:
            return f.read()

    request = _Request(url, method=method, headers=headers)
    request._on_progress = on_progress
    request._on_auth_request = on_auth_request

    first_error = None

    if ENABLE_WINHTTP:
        try:
            return _winhttp_urlopen(request)
        except ImportError:
            LOGGER.debug("WinHTTP module unavailable - using fallback")
        except NoInternetError as ex:
            # No point going any further if WinHTTP has detected no internet
            # connection.
            request.on_progress(None)
            LOGGER.error("Failed to download. Please connect to the internet and try again.")
            raise RuntimeError("Failed to download. Please connect to the internet and try again.") from ex
        except FileNotFoundError:
            # Indicates a successful 404, so let it bubble out
            raise
        except OSError as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using WinHTTP. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = ex

    if ENABLE_URLLIB:
        try:
            return _urllib_urlopen(request)
        except ImportError:
            LOGGER.debug("urllib download unavailable - using fallback")
        except (AttributeError, TypeError, ValueError):
            # Blame the caller for these errors and let them bubble out
            raise
        except FileNotFoundError:
            # Indicates a successful 404, so let it bubble out
            raise
        except Exception as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using urllib. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = first_error or ex

    if ENABLE_POWERSHELL:
        try:
            return _powershell_urlopen(request)
        except FileNotFoundError:
            LOGGER.debug("PowerShell download unavailable - using fallback")
        except Exception as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using PowerShell. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = first_error or ex

    if first_error:
        raise first_error

    raise RuntimeError("Unable to download from the internet")


def urlretrieve(url, outfile, method="GET", headers={}, chunksize=64 * 1024, on_progress=None, on_auth_request=None):
    scheme, sep, path = url.partition("://")
    if not sep:
        scheme = "file"
        url = Path(url).absolute().as_uri()
    elif scheme.casefold() not in SUPPORTED_SCHEMES:
        raise ValueError(f"Unsupported scheme: {scheme}")

    if scheme.casefold() == "file".casefold():
        if on_progress is None:
            def on_progress(_): pass

        with open(file_url_to_path(url), "rb") as r:
            if r.seekable:
                total = r.seek(0, os.SEEK_END)
                r.seek(0, os.SEEK_SET)
            else:
                total = None
            on_progress(0)
            with open(outfile, "wb") as f:
                for chunk in iter(lambda: r.read(chunksize), b""):
                    f.write(chunk)
                    if total:
                        on_progress((100 * f.tell()) // total)
            on_progress(100)
        return

    request = _Request(url, method=method, headers=headers)
    request.outfile = Path(outfile)
    request.chunksize = chunksize
    request._on_progress = on_progress
    request._on_auth_request = on_auth_request

    first_error = None

    if ENABLE_BITS and method.upper() == "GET":
        try:
            return _bits_urlretrieve(request)
        except ImportError:
            LOGGER.debug("BITS module unavailable - using fallback")
        except NoInternetError as ex:
            request.on_progress(None)
            try:
                from _native import winhttp_isconnected
            except ImportError:
                pass
            else:
                if not winhttp_isconnected():
                    LOGGER.error("Failed to download. Please connect to the internet and try again.")
                    raise RuntimeError("Failed to download. Please connect to the internet and try again.") from ex

            LOGGER.verbose("Failed to download using BITS, " +
                "possibly due to no internet. Retrying with fallback method.")
        except FileNotFoundError:
            # Indicates a successful 404, so let it bubble out
            raise
        except OSError as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using BITS. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = ex

    if ENABLE_WINHTTP:
        try:
            return _winhttp_urlretrieve(request)
        except ImportError:
            LOGGER.debug("WinHTTP module unavailable - using fallback")
        except NoInternetError as ex:
            # No point going any further if WinHTTP has detected no internet
            # connection.
            request.on_progress(None)
            LOGGER.error("Failed to download. Please connect to the internet and try again.")
            raise RuntimeError("Failed to download. Please connect to the internet and try again.") from ex
        except FileNotFoundError:
            # Indicates a successful 404, so let it bubble out
            raise
        except OSError as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using WinHTTP. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = first_error or ex

    if ENABLE_URLLIB:
        try:
            return _urllib_urlretrieve(request)
        except ImportError:
            LOGGER.debug("urllib module unavailable - using fallback")
        except (AttributeError, TypeError, ValueError):
            # Blame the caller for these errors and let them bubble out
            raise
        except FileNotFoundError:
            # Indicates a successful 404, so let it bubble out
            raise
        except Exception as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using urllib. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = first_error or ex

    if ENABLE_POWERSHELL:
        try:
            return _powershell_urlretrieve(request)
        except FileNotFoundError:
            LOGGER.debug("PowerShell download unavailable - using fallback")
        except Exception as ex:
            request.on_progress(None)
            LOGGER.verbose("Failed to download using PowerShell. Retrying with fallback method.")
            LOGGER.debug("ERROR:", exc_info=True)
            first_error = first_error or ex

    if first_error:
        raise first_error

    raise RuntimeError("Unable to download from the internet")


def extract_url_auth(url):
    if not url:
        return url
    p = winhttp_urlsplit(url)
    user, passw = p[U_USERNAME], p[U_PASSWORD]
    if user or passw:
        return user or "", passw or ""
    return None


def sanitise_url(url):
    if not url:
        return url
    try:
        p = list(winhttp_urlsplit(url))
    except OSError as ex:
        # Errors for an invalid URL
        if ex.winerror in (12005, 12006):
            return url
        raise
    p[U_USERNAME] = None
    pw = p[U_PASSWORD]
    if pw and not (pw.startswith("%") and pw.startswith("%")):
        p[U_PASSWORD] = None
    return winhttp_urlunsplit(*p)


def unsanitise_url(url, candidates):
    if not url:
        return url
    try:
        p = list(winhttp_urlsplit(url))
    except OSError as ex:
        # Errors for an invalid URL
        if ex.winerror in (12005, 12006):
            return url
        raise
    if p[U_USERNAME] or p[U_PASSWORD]:
        # URL contains user/pass info, so just return it
        return url
    best = None
    for url2 in candidates:
        p2 = winhttp_urlsplit(url2)
        if (
            p[U_SCHEME].casefold() == p2[U_SCHEME].casefold() and
            p[U_NETLOC].casefold() == p2[U_NETLOC].casefold() and
            p[U_PORT] == p2[U_PORT] and
            p[U_PATH].casefold().startswith(p2[U_PATH].casefold())
        ):
            if best is None or len(p2[U_PATH]) > len(best[U_PATH]):
                best = p2
    if best:
        p = list(p)
        p[U_USERNAME] = best[U_USERNAME]
        p[U_PASSWORD] = best[U_PASSWORD]
        return winhttp_urlunsplit(*p)


def urljoin(base_url, other_url, *, to_parent=False):
    if not other_url:
        return base_url
    scheme, sep, rest = other_url.partition("://")
    if sep:
        return other_url
    scheme, _, base = base_url.partition("://")
    path = base.lstrip("/")
    trimmed = "/" * (len(base) - len(path))
    root, _, path = path.partition("/")
    path = PurePath(path)
    if other_url.startswith("//"):
        root, sep, other_url = other_url[2:].partition("/")
        if sep:
            path = PurePath()
        else:
            to_parent = False
    other_url = PurePath(other_url)
    if to_parent:
        path = path.parent
    url_path = str(path / other_url).replace("\\", "/").lstrip("/")
    return f"{scheme}://{trimmed}{root.rstrip('/')}/{url_path}"


def is_valid_url(url):
    try:
        winhttp_urlsplit(url)
        return True
    except OSError:
        pass
    if not url.lower().startswith("file://"):
        return False
    try:
        file_url_to_path(url)
        return True
    except OSError:
        pass
    return False


class IndexDownloader:
    def __init__(self, source, index_cls, auth=None, cache=None, disk_cache=None):
        self.index_cls = index_cls
        self._url = source.rstrip("/")
        if not self._url.casefold().endswith(".json".casefold()):
            self._url += "/index.json"
        self._auth = auth if auth is not None else {}
        self._cache = cache if cache is not None else {}
        self._disk_cache = Path(disk_cache) if disk_cache is not None else None
        self._urlopen = urlopen
        self._used_auth = False

    def _use_disk_cache(self, url, data=None):
        if not self._disk_cache:
            return None
        try:
            if extract_url_auth(url):
                return None
        except OSError:
            return None
        from hashlib import sha256
        from time import time
        path = self._disk_cache / (sha256(url.encode("utf-8", "unicodeescape")).hexdigest() + ".cache")
        if data:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            return
        try:
            if time() - path.lstat().st_mtime < 60:
                return path.read_bytes()
            path.unlink()
            return None
        except OSError:
            return None

    def __iter__(self):
        return self

    def on_auth(self, url):
        # TODO: Try looking for parent paths from URL
        self._used_auth = True
        try:
            return self._auth[url]
        except LookupError:
            return None

    def __next__(self):
        if not self._url:
            raise StopIteration

        import json

        url = self._url
        LOGGER.debug("Fetching: %s", url)
        try:
            data = self._cache[url]
            LOGGER.debug("Fetched from cache")
        except LookupError:
            data = None

        data = self._use_disk_cache(url)
        if data:
            LOGGER.debug("Fetched from disk cache")

        if not data:
            try:
                self._used_auth = False
                data = self._cache[url] = self._urlopen(
                    url,
                    "GET",
                    {"Accepts": "application/json"},
                    on_auth_request=self.on_auth,
                )
                if not self._used_auth:
                    self._use_disk_cache(url, data)
            except FileNotFoundError: # includes 404
                LOGGER.error("Unable to find runtimes index at %s", sanitise_url(url))
                raise
            except OSError as ex:
                LOGGER.error(
                    "Unable to access runtimes index at %s: %s",
                    sanitise_url(url),
                    ex.args[1] if len(ex.args) >= 2 else ex
                )
                raise
            except RuntimeError as ex:
                LOGGER.error("An unexpected error occurred while downloading the index: %s", ex)
                raise

        j = json.loads(data)
        index = self.index_cls(self._url, j)

        if j.get("next"):
            self._url = urljoin(url, j["next"], to_parent=True)
        else:
            self._url = None
        return index
