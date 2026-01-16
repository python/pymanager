#include <Python.h>
#include <windows.h>
#include <winhttp.h>
#include <netlistmgr.h>

#include "helpers.h"

#pragma comment(lib, "winhttp.lib")

static void _winhttp_error(const char *location) {
    err_SetFromWindowsErrWithMessage(GetLastError(), location, NULL, GetModuleHandleW(L"winhttp"));
}

#ifdef ERROR_LOCATIONS
#define winhttp_error() _winhttp_error(__FILE__ ":" Py_STRINGIFY(__LINE__))
#else
#define winhttp_error() _winhttp_error(NULL)
#endif


template <typename T> struct WHQH_Flags { static const DWORD flags = 0; };
template <> struct WHQH_Flags<DWORD> { static const DWORD flags = WINHTTP_QUERY_FLAG_NUMBER; };
template <> struct WHQH_Flags<uint64_t> { static const DWORD flags = WINHTTP_QUERY_FLAG_NUMBER; };

template <typename T>
static bool read_header(HINTERNET hRequest, DWORD headerIndex, T *value) {
    DWORD value_len = sizeof(T);
    if (!WinHttpQueryHeaders(
        hRequest,
        headerIndex | WHQH_Flags<T>::flags,
        WINHTTP_HEADER_NAME_BY_INDEX,
        value,
        &value_len,
        WINHTTP_NO_HEADER_INDEX
    )) {
        winhttp_error();
        return false;
    }
    return true;
}

static void http_error(HINTERNET hRequest) {
    wchar_t *reason;
    DWORD reason_len;
    DWORD status;

    if (!read_header(hRequest, WINHTTP_QUERY_STATUS_CODE, &status)) {
        return;
    }
    err_SetFromWindowsErrWithMessage(0x80190000 | status);
}


static bool request_creds(HINTERNET hRequest, const wchar_t *url, PyObject *on_cred_request) {
    PyObject *result = PyObject_CallFunction(on_cred_request, "u", url);
    if (!result) {
        return false;
    }
    if (!PyObject_IsTrue(result)) {
        Py_DECREF(result);
        http_error(hRequest);
        return false;
    }
    // Read new auth from result
    wchar_t *user, *pass;
    if (!PyArg_ParseTuple(result, "O&O&", as_utf16, &user, as_utf16, &pass)) {
        Py_DECREF(result);
        return false;
    }
    Py_DECREF(result);

    BOOL r = WinHttpSetCredentials(
        hRequest,
        WINHTTP_AUTH_TARGET_SERVER,
        WINHTTP_AUTH_SCHEME_BASIC,
        user,
        pass,
        NULL
    );
    PyMem_Free(user);
    PyMem_Free(pass);
    return r;
}

static wchar_t **split_to_array(wchar_t *str, wchar_t sep) {
    int count = 1;
    wchar_t *i;
    for (i = str; *i; ++i) {
        if (*i == sep) {
            ++count;
        }
    }
    wchar_t **arr = (wchar_t **)PyMem_Malloc(sizeof(wchar_t *) * (count + 1));
    if (!arr) {
        PyErr_NoMemory();
        return NULL;
    }
    wchar_t **a = arr + count;
    *a-- = NULL;
    while (i >= &str[1]) {
        if (*--i == sep) {
            *i = L'\0';
            *a-- = i + 1;
        }
    }
    *arr = str;
    return arr;
}


static int crack_url(wchar_t *url, URL_COMPONENTS *parts, int add_nuls) {
    parts->lpszScheme = NULL;
    parts->lpszUserName = NULL;
    parts->lpszPassword = NULL;
    parts->lpszHostName = NULL;
    parts->lpszUrlPath = NULL;
    parts->lpszExtraInfo = NULL;
    parts->dwSchemeLength = -1;
    parts->dwUserNameLength = -1;
    parts->dwPasswordLength = -1;
    parts->dwHostNameLength = -1;
    parts->dwUrlPathLength = -1;
    parts->dwExtraInfoLength = -1;
    if (!WinHttpCrackUrl(url, 0, 0, parts)) {
        winhttp_error();
        return 0;
    }
    if (add_nuls) {
        if (parts->lpszScheme && parts->dwSchemeLength > 0) {
            parts->lpszScheme[parts->dwSchemeLength] = L'\0';
        }
        if (parts->lpszUserName && parts->dwUserNameLength > 0) {
            parts->lpszUserName[parts->dwUserNameLength] = L'\0';
        }
        if (parts->lpszPassword && parts->dwPasswordLength > 0) {
            parts->lpszPassword[parts->dwPasswordLength] = L'\0';
        }
        if (parts->lpszHostName && parts->dwHostNameLength > 0) {
            parts->lpszHostName[parts->dwHostNameLength] = L'\0';
        }
        if (parts->lpszUrlPath && parts->dwUrlPathLength > 0) {
            parts->lpszUrlPath[parts->dwUrlPathLength] = L'\0';
        }
        if (parts->lpszExtraInfo && parts->dwExtraInfoLength > 0) {
            parts->lpszExtraInfo[parts->dwExtraInfoLength] = L'\0';
        }
    }
    return 1;
}

extern "C" {

#define CHECK_WINHTTP(x) if (!x) { winhttp_error(); goto exit; }


static bool winhttp_apply_proxy(HINTERNET hSession, HINTERNET hRequest, const wchar_t *url) {
    bool result = false;
    WINHTTP_CURRENT_USER_IE_PROXY_CONFIG proxy_config = { 0 };
    WINHTTP_AUTOPROXY_OPTIONS proxy_opt = {
        .dwFlags = WINHTTP_AUTOPROXY_ALLOW_STATIC,
        .fAutoLogonIfChallenged = TRUE
    };
    WINHTTP_PROXY_INFO proxy_info = { 0 };

    // First load the global-ish config settings
    if (!WinHttpGetIEProxyConfigForCurrentUser(&proxy_config)) {
        if (GetLastError() != ERROR_FILE_NOT_FOUND) {
            goto exit;
        }
        // No global config, so assume auto-detect
        proxy_config.lpszProxy = proxy_config.lpszProxyBypass = proxy_config.lpszAutoConfigUrl = NULL;
        proxy_config.fAutoDetect = TRUE;
    }
    if (proxy_config.lpszProxy) {
        GlobalFree(proxy_config.lpszProxy);
    }
    if (proxy_config.lpszProxyBypass) {
        GlobalFree(proxy_config.lpszProxyBypass);
    }
    if (proxy_config.fAutoDetect) {
        proxy_opt.dwFlags |= WINHTTP_AUTOPROXY_AUTO_DETECT;
        proxy_opt.dwAutoDetectFlags = WINHTTP_AUTO_DETECT_TYPE_DHCP
            | WINHTTP_AUTO_DETECT_TYPE_DNS_A;
    }
    if (proxy_config.lpszAutoConfigUrl) {
        proxy_opt.dwFlags |= WINHTTP_AUTOPROXY_CONFIG_URL;
        proxy_opt.lpszAutoConfigUrl = proxy_config.lpszAutoConfigUrl;
    }

    // Now resolve the proxy required for the specified URL
    CHECK_WINHTTP(WinHttpGetProxyForUrl(hSession, url, &proxy_opt, &proxy_info));

    // Enable proxy servers to automatically login with implicit credentials
    // This is only used if the proxy sends a 407 response, otherwise, they are
    // ignored.
    CHECK_WINHTTP(WinHttpSetCredentials(
        hRequest,
        WINHTTP_AUTH_TARGET_PROXY,
        WINHTTP_AUTH_SCHEME_NEGOTIATE,
        NULL, NULL, NULL
    ));

    // Apply the proxy settings to the request
    CHECK_WINHTTP(WinHttpSetOption(
        hRequest,
        WINHTTP_OPTION_PROXY,
        &proxy_info,
        sizeof(proxy_info)
    ));

    result = true;
exit:
    if (proxy_info.lpszProxy) {
        GlobalFree((HGLOBAL)proxy_info.lpszProxy);
    }
    if (proxy_info.lpszProxyBypass) {
        GlobalFree((HGLOBAL)proxy_info.lpszProxyBypass);
    }
    if (proxy_opt.lpszAutoConfigUrl) {
        GlobalFree((HGLOBAL)proxy_opt.lpszAutoConfigUrl);
    }
    return result;
}


PyObject *winhttp_urlopen(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"url", "method", "headers", "accepts", "chunksize", "on_progress", "on_cred_request", NULL};
    wchar_t *url = NULL;
    wchar_t *url2 = NULL; // a copy of url for splitting
    wchar_t *method = NULL;
    wchar_t *headers = NULL;
    wchar_t *accepts = NULL;
    PyObject *on_progress = NULL;
    PyObject *on_cred_request = NULL;

    PyObject *result = NULL;
    URL_COMPONENTS url_parts = { sizeof(URL_COMPONENTS) };
    HINTERNET hSession = NULL;
    HINTERNET hConnection = NULL;
    HINTERNET hRequest = NULL;
    DWORD opt = 0;
    LPCWSTR *accepts_array;

    Py_ssize_t chunksize = 65536;
    DWORD status_code = 0;
    uint64_t content_length;
    PyObject *chunks = NULL;
    uint64_t content_read = 0;
    size_t n = 0;

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&O&O&|nOO:winhttp_urlopen", keywords,
        as_utf16, &url, as_utf16, &method, as_utf16, &headers, as_utf16, &accepts, &chunksize, &on_progress, &on_cred_request)) {
        return NULL;
    }

    if (on_progress && !PyObject_IsTrue(on_progress)) {
        on_progress = NULL;
    }
    if (on_cred_request && !PyObject_IsTrue(on_cred_request)) {
        on_cred_request = NULL;
    }

    accepts_array = (LPCWSTR*)split_to_array(accepts, L';');
    if (!accepts_array) {
        goto exit;
    }
    n = wcslen(url) + 1;
    url2 = (wchar_t *)PyMem_Malloc(n * sizeof(wchar_t));
    if (!url2) {
        PyErr_NoMemory();
        goto exit;
    }
    wcscpy_s(url2, n, url);
    if (!crack_url(url2, &url_parts, 1)) {
        goto exit;
    }

    hSession = WinHttpOpen(
        NULL,
        WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
        WINHTTP_NO_PROXY_NAME,
        WINHTTP_NO_PROXY_BYPASS,
        url_parts.nScheme == INTERNET_SCHEME_HTTPS
            ? WINHTTP_FLAG_SECURE_DEFAULTS & ~WINHTTP_FLAG_ASYNC
            : 0
    );
    if (!hSession && GetLastError() == ERROR_INVALID_PARAMETER) {
        // WINHTTP_FLAG_SECURE_DEFAULTS is not supported on older OS, so we'll
        // retry without it.
        hSession = WinHttpOpen(
            NULL,
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME,
            WINHTTP_NO_PROXY_BYPASS,
            0
        );
    }

    // Allow proxies to automatically log in (we'll set the default credentials
    // in winhttp_apply_proxy(), but this setting has to go on the session).
    opt = WINHTTP_AUTOLOGON_SECURITY_LEVEL_LOW;
    CHECK_WINHTTP(WinHttpSetOption(
        hSession,
        WINHTTP_OPTION_AUTOLOGON_POLICY,
        &opt,
        sizeof(opt)
    ));

    CHECK_WINHTTP(hSession);

    hConnection = WinHttpConnect(
        hSession,
        url_parts.lpszHostName,
        url_parts.nPort,
        0
    );
    CHECK_WINHTTP(hConnection);

    if (url_parts.dwUrlPathLength && !url_parts.lpszUrlPath[0]) {
        url_parts.lpszUrlPath[0] = L'/';
    }
    hRequest = WinHttpOpenRequest(
        hConnection,
        method,
        url_parts.lpszUrlPath,
        NULL,
        WINHTTP_NO_REFERER,
        accepts_array,
        url_parts.nScheme == INTERNET_SCHEME_HTTPS ? WINHTTP_FLAG_SECURE : 0
    );
    CHECK_WINHTTP(hRequest);

    CHECK_WINHTTP(winhttp_apply_proxy(hSession, hRequest, url));

    opt = WINHTTP_DECOMPRESSION_FLAG_ALL;
    CHECK_WINHTTP(WinHttpSetOption(
        hRequest,
        WINHTTP_OPTION_DECOMPRESSION,
        &opt,
        sizeof(opt)
    ));

    if (url_parts.dwUserNameLength || url_parts.dwPasswordLength) {
        CHECK_WINHTTP(WinHttpSetCredentials(
            hRequest,
            WINHTTP_AUTH_TARGET_SERVER,
            WINHTTP_AUTH_SCHEME_BASIC,
            url_parts.lpszUserName,
            url_parts.lpszPassword,
            NULL
        ));
    }

    while (!status_code) {
        CHECK_WINHTTP(WinHttpSendRequest(hRequest, headers, -1, NULL, 0, 0, NULL));
        CHECK_WINHTTP(WinHttpReceiveResponse(hRequest, NULL));
        if (!read_header(hRequest, WINHTTP_QUERY_STATUS_CODE, &status_code)) goto exit;

        if (status_code == HTTP_STATUS_DENIED) {
            // Status 401
            if (on_cred_request) {
                if (!request_creds(hRequest, url, on_cred_request)) {
                    goto exit;
                }
                // Make the request again
                status_code = 0;
                // Do not call on_cred_request again
                on_cred_request = NULL;
            } else {
                http_error(hRequest);
                goto exit;
            }
        } else if (status_code < 200 || status_code >= 300) {
            http_error(hRequest);
            goto exit;
        }
    }

    if (!read_header(hRequest, WINHTTP_QUERY_CONTENT_LENGTH, &content_length)) {
        PyErr_Clear();
        content_length = 0;
    }
    if (on_progress) {
        result = PyObject_CallFunction(on_progress, "i", 0);
        if (!result) {
            goto exit;
        }
        Py_CLEAR(result);
    }

    chunks = PyList_New(0);
    while (true) {
        DWORD data_len, data_read;
        // TODO: Check for KeyboardInterrupt and abort
        if (!WinHttpQueryDataAvailable(hRequest, &data_len)) {
            winhttp_error();
            goto exit;
        }
        if (!data_len) {
            break;
        }
        if (data_len > chunksize) {
            data_len = chunksize;
        }
        PyObject *buffer = PyBytes_FromStringAndSize(NULL, data_len);
        if (!buffer) {
            Py_CLEAR(chunks);
            break;
        }
        if (!WinHttpReadData(hRequest, PyBytes_AsString(buffer), data_len, &data_read)) {
            Py_DECREF(buffer);
            Py_CLEAR(chunks);
            break;
        }
        if (!data_read) {
            Py_DECREF(buffer);
            break;
        }
        _PyBytes_Resize(&buffer, data_read);
        if (!buffer) {
            Py_CLEAR(chunks);
            break;
        }
        if (PyList_Append(chunks, buffer) < 0) {
            Py_DECREF(buffer);
            Py_CLEAR(chunks);
            break;
        }
        Py_DECREF(buffer);
        content_read += data_read;
        if (on_progress && content_length) {
            result = PyObject_CallFunction(on_progress, "i", content_read * 100 / content_length);
            if (!result) {
                Py_CLEAR(chunks);
                break;
            }
            Py_CLEAR(result);
        }
    }

    if (chunks) {
        PyObject *sep = PyBytes_FromStringAndSize(NULL, 0);
        if (sep) {
            result = PyObject_CallMethod(sep, "join", "O", chunks);
            Py_DECREF(sep);
        }
        Py_DECREF(chunks);

        if (on_progress) {
            PyObject *result2 = PyObject_CallFunction(on_progress, "i", 100);
            if (!result2) {
                goto exit;
            }
            Py_DECREF(result2);
        }
    }
exit:
    if (hRequest) {
        WinHttpCloseHandle(hRequest);
    }
    if (hConnection) {
        WinHttpCloseHandle(hConnection);
    }
    if (hSession) {
        WinHttpCloseHandle(hSession);
    }
    PyMem_Free(accepts_array);
    PyMem_Free(accepts);
    PyMem_Free(headers);
    PyMem_Free(method);
    PyMem_Free(url2);
    PyMem_Free(url);
    return result;
}


PyObject *winhttp_isconnected(PyObject *, PyObject *, PyObject *) {
    INetworkListManager *nlm = NULL;
    VARIANT_BOOL connected;

    HRESULT hr = CoCreateInstance(
        CLSID_NetworkListManager,
        NULL,
        CLSCTX_ALL,
        IID_INetworkListManager,
        (LPVOID*)&nlm
    );
    if (FAILED(hr)) {
        err_SetFromWindowsErrWithMessage(hr, "Getting network list manager");
        return NULL;
    }
    if (FAILED(hr = nlm->get_IsConnectedToInternet(&connected))) {
        err_SetFromWindowsErrWithMessage(hr, "Checking internet access");
        nlm->Release();
        return NULL;
    }
    nlm->Release();
    if (!connected) {
        return Py_NewRef(Py_False);
    }
    return Py_NewRef(Py_True);
}


PyObject *winhttp_urlsplit(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"url", NULL};
    wchar_t *url = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&:winhttp_urlsplit", keywords,
        as_utf16, &url)) {
        return NULL;
    }
    URL_COMPONENTS url_parts = { sizeof(URL_COMPONENTS) };
    if (!crack_url(url, &url_parts, 0)) {
        PyMem_Free(url);
        return NULL;
    }
    PyObject *r = Py_BuildValue("(u#u#u#u#nu#u#)",
        url_parts.lpszScheme, (Py_ssize_t)url_parts.dwSchemeLength,
        url_parts.lpszUserName, (Py_ssize_t)url_parts.dwUserNameLength,
        url_parts.lpszPassword, (Py_ssize_t)url_parts.dwPasswordLength,
        url_parts.lpszHostName, (Py_ssize_t)url_parts.dwHostNameLength,
        (Py_ssize_t)url_parts.nPort,
        url_parts.lpszUrlPath, (Py_ssize_t)url_parts.dwUrlPathLength,
        url_parts.lpszExtraInfo, (Py_ssize_t)url_parts.dwExtraInfoLength
    );
    PyMem_Free(url);
    return r;
}


PyObject *winhttp_urlunsplit(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"scheme", "user", "password", "netloc", "port", "path", "extra", NULL};
    URL_COMPONENTS url = { sizeof(URL_COMPONENTS) };
    Py_ssize_t port = 0;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&O&O&nO&O&:winhttp_urlunsplit", keywords,
        as_utf16, &url.lpszScheme,
        as_utf16, &url.lpszUserName,
        as_utf16, &url.lpszPassword,
        as_utf16, &url.lpszHostName,
        &port,
        as_utf16, &url.lpszUrlPath,
        as_utf16, &url.lpszExtraInfo
    )) {
        return NULL;
    }
    DWORD cch = 0;
    PyObject *r = NULL;
    url.nPort = (INTERNET_PORT)port;
    if (WinHttpCreateUrl(&url, ICU_ESCAPE, NULL, &cch)) {
        // Success path, because it should've failed with ERROR_INSUFFICIENT_BUFFER
        PyErr_SetString(PyExc_ValueError, "unable to unsplit URL");
    } else if (GetLastError() != ERROR_INSUFFICIENT_BUFFER) {
        winhttp_error();
    } else {
        cch += 1;
        wchar_t *buf = (wchar_t*)PyMem_Malloc(cch * sizeof(wchar_t));
        if (!buf) {
            PyErr_NoMemory();
        } else if (!WinHttpCreateUrl(&url, ICU_ESCAPE, buf, &cch)) {
            winhttp_error();
            PyMem_Free(buf);
        } else {
            r = PyUnicode_FromWideChar(buf, cch);
            PyMem_Free(buf);
        }
    }
    PyMem_Free(url.lpszScheme);
    PyMem_Free(url.lpszUserName);
    PyMem_Free(url.lpszPassword);
    PyMem_Free(url.lpszHostName);
    PyMem_Free(url.lpszUrlPath);
    PyMem_Free(url.lpszExtraInfo);
    return r;
}


}