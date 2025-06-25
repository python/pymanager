#include <Python.h>
#include <windows.h>

#include "helpers.h"

int as_utf16(PyObject *obj, wchar_t **address) {
    if (obj == NULL) {
        // Automatic cleanup
        PyMem_Free(*address);
        return 1;
    }
    if (!PyObject_IsTrue(obj)) {
        if (Py_Is(obj, Py_GetConstantBorrowed(Py_CONSTANT_NONE))) {
            *address = NULL;
            return 1;
        }
    }
    PyObject *wobj = PyObject_Str(obj);
    if (!wobj) {
        return 0;
    }
    PyObject *b = PyObject_CallMethod(wobj, "encode", "ss", "utf-16-le", "strict");
    Py_DECREF(wobj);
    if (!b) {
        return 0;
    }
    char *src;
    Py_ssize_t len;
    if (PyBytes_AsStringAndSize(b, &src, &len) < 0) {
        Py_DECREF(b);
        return 0;
    }
    Py_ssize_t wlen = len / sizeof(wchar_t);
    wchar_t *result = (wchar_t *)PyMem_Malloc((wlen + 1) * sizeof(wchar_t));
    if (!result) {
        Py_DECREF(b);
        PyErr_NoMemory();
        return 0;
    }
    wcsncpy_s(result, wlen + 1, (wchar_t *)src, wlen);
    Py_DECREF(b);
    *address = result;
    return Py_CLEANUP_SUPPORTED;
}


void err_SetFromWindowsErrWithMessage(int error, const char *message, const wchar_t *os_message, void *hModule) {
    LPWSTR os_message_buffer = NULL;
    PyObject *cause = NULL;
    if (PyErr_Occurred()) {
        cause = PyErr_GetRaisedException();
    }

    if ((error & 0xFFFF0000) == 0x80070000) {
        // Error code is an HRESULT containing a regular Windows error
        error &= 0xFFFF;
    }
    if (!hModule && error >= 12000 && error <= 12184) {
        // Error codes are from WinHTTP, which means we need a module
        hModule = GetModuleHandleW(L"winhttp");
    }

    if (!os_message) {
        DWORD len = FormatMessageW(
            /* Error API error */
            FORMAT_MESSAGE_ALLOCATE_BUFFER
            | FORMAT_MESSAGE_FROM_SYSTEM
            | (hModule ? FORMAT_MESSAGE_FROM_HMODULE : 0)
            | FORMAT_MESSAGE_IGNORE_INSERTS,
            hModule,
            error,
            MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
            (LPWSTR)&os_message_buffer,
            0,
            NULL
        );
        if (len) {
            while (len > 0 && isspace(os_message_buffer[--len])) {
                os_message_buffer[len] = L'\0';
            }
            os_message = os_message_buffer;
        }
    }

    PyObject *msg;
    if (message && os_message) {
        msg = PyUnicode_FromFormat("%s: %ls", message, os_message);
    } else if (os_message) {
        msg = PyUnicode_FromWideChar(os_message, -1);
    } else if (message) {
        msg = PyUnicode_FromString(message);
    } else {
        msg = PyUnicode_FromString("Unknown error");
    }

    if (msg) {
        // Hacky way to get OSError without a direct data reference
        // This allows us to delay load the Python DLL
        PyObject *builtins = PyEval_GetFrameBuiltins();
        PyObject *oserr = builtins ? PyDict_GetItemString(builtins, "OSError") : NULL;
        if (oserr) {
            PyObject *exc_args = Py_BuildValue(
                "(iOOiO)",
                (int)0,
                msg,
                Py_GetConstantBorrowed(Py_CONSTANT_NONE),
                error,
                Py_GetConstantBorrowed(Py_CONSTANT_NONE)
            );
            if (exc_args) {
                PyErr_SetObject(oserr, exc_args);
                Py_DECREF(exc_args);
            }
        }
        Py_XDECREF(builtins);
        Py_DECREF(msg);
    }

    if (os_message_buffer) {
        LocalFree((void *)os_message_buffer);
    }

    if (cause) {
        // References are all stolen here, so no DECREF required
        PyObject *chained = PyErr_GetRaisedException();
        PyException_SetContext(chained, cause);
        PyErr_SetRaisedException(chained);
    }
}

