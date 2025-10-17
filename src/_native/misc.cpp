#include <Python.h>
#include <windows.h>
#include <appmodel.h>

#include "helpers.h"


extern "C" {

PyObject *coinitialize(PyObject *, PyObject *args, PyObject *kwargs) {
    HRESULT hr = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    if (FAILED(hr)) {
        PyErr_SetFromWindowsErr(hr);
        return NULL;
    }
    Py_RETURN_NONE;
}

static void _invalid_parameter(
   const wchar_t * expression,
   const wchar_t * function,
   const wchar_t * file,
   unsigned int line,
   uintptr_t pReserved
) { }

PyObject *fd_supports_vt100(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"fd", NULL};
    int fd;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "i:fd_supports_vt100", keywords, &fd)) {
        return NULL;
    }
    PyObject *r = NULL;
    HANDLE h;
    DWORD mode;
    const DWORD expect_flags = ENABLE_PROCESSED_OUTPUT | ENABLE_VIRTUAL_TERMINAL_PROCESSING;

    auto handler = _set_thread_local_invalid_parameter_handler(_invalid_parameter);
    h = (HANDLE)_get_osfhandle(fd);
    _set_thread_local_invalid_parameter_handler(handler);

    if (GetConsoleMode(h, &mode)) {
        if ((mode & expect_flags) == expect_flags) {
            r = Py_GetConstant(Py_CONSTANT_TRUE);
        } else {
            r = Py_GetConstant(Py_CONSTANT_FALSE);
        }
    } else {
        PyErr_SetFromWindowsErr(0);
    }
    return r;
}

PyObject *date_as_str(PyObject *, PyObject *, PyObject *) {
    wchar_t buffer[256];
    DWORD cch = GetDateFormatEx(
        LOCALE_NAME_INVARIANT,
        0,
        NULL,
        L"yyyyMMdd",
        buffer,
        sizeof(buffer) / sizeof(buffer[0]),
        NULL
    );
    if (!cch) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    return PyUnicode_FromWideChar(buffer, cch - 1);
}

PyObject *datetime_as_str(PyObject *, PyObject *, PyObject *) {
    wchar_t buffer[256];
    DWORD cch = GetDateFormatEx(
        LOCALE_NAME_INVARIANT,
        0,
        NULL,
        L"yyyyMMdd",
        buffer,
        sizeof(buffer) / sizeof(buffer[0]),
        NULL
    );
    if (!cch) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    cch -= 1;
    cch += GetTimeFormatEx(
        LOCALE_NAME_INVARIANT,
        0,
        NULL,
        L"HHmmss",
        &buffer[cch],
        sizeof(buffer) / sizeof(buffer[0]) - cch
    );
    return PyUnicode_FromWideChar(buffer, cch - 1);
}

PyObject *reg_rename_key(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"handle", "name1", "name2", NULL};
    PyObject *handle_obj;
    wchar_t *name1 = NULL;
    wchar_t *name2 = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO&O&:reg_rename_key", keywords,
        &handle_obj, as_utf16, &name1, as_utf16, &name2)) {
        return NULL;
    }
    PyObject *r = NULL;
    HKEY h;
    if (PyLong_AsNativeBytes(handle_obj, &h, sizeof(h), -1) >= 0) {
        int err = (int)RegRenameKey(h, name1, name2);
        if (!err) {
            r = Py_GetConstant(Py_CONSTANT_NONE);
        } else {
            PyErr_SetFromWindowsErr(err);
        }
    }
    PyMem_Free(name1);
    PyMem_Free(name2);
    return r;
}


PyObject *get_current_package(PyObject *, PyObject *, PyObject *) {
    wchar_t package_name[256];
    UINT32 cch = sizeof(package_name) / sizeof(package_name[0]);
    int err = GetCurrentPackageFamilyName(&cch, package_name);
    switch (err) {
    case ERROR_SUCCESS:
        return PyUnicode_FromWideChar(package_name, cch ? cch - 1 : 0);
    case APPMODEL_ERROR_NO_PACKAGE:
        return Py_GetConstant(Py_CONSTANT_NONE);
    default:
        PyErr_SetFromWindowsErr(err);
        return NULL;
    }
}


PyObject *read_alias_package(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"path", NULL};
    wchar_t *path = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&:read_alias_package", keywords,
        as_utf16, &path)) {
        return NULL;
    }

    HANDLE h = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING,
                           FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS, NULL);
    PyMem_Free(path);
    if (h == INVALID_HANDLE_VALUE) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }

    struct {
        DWORD tag;
        DWORD _reserved1;
        DWORD _reserved2;
        wchar_t package_name[256];
        wchar_t nul;
    } buffer;
    DWORD nread;

    if (!DeviceIoControl(h, FSCTL_GET_REPARSE_POINT, NULL, 0,
        &buffer, sizeof(buffer), &nread, NULL)
        // we expect our buffer to be too small, but we only want the package
        && GetLastError() != ERROR_MORE_DATA) {
        PyErr_SetFromWindowsErr(0);
        CloseHandle(h);
        return NULL;
    }

    CloseHandle(h);

    if (buffer.tag != IO_REPARSE_TAG_APPEXECLINK) {
        return Py_GetConstant(Py_CONSTANT_NONE);
    }

    buffer.nul = 0;
    return PyUnicode_FromWideChar(buffer.package_name, -1);
}


typedef LRESULT (*PSendMessageTimeoutW)(
    HWND       hWnd,
    UINT       Msg,
    WPARAM     wParam,
    LPARAM     lParam,
    UINT       fuFlags,
    UINT       uTimeout,
    PDWORD_PTR lpdwResult
);

PyObject *broadcast_settings_change(PyObject *, PyObject *, PyObject *) {
    // Avoid depending on user32 because it's so slow
    HMODULE user32 = LoadLibraryExW(L"user32.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!user32) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    PSendMessageTimeoutW sm = (PSendMessageTimeoutW)GetProcAddress(user32, "SendMessageTimeoutW");
    if (!sm) {
        PyErr_SetFromWindowsErr(0);
        FreeLibrary(user32);
        return NULL;
    }

    // SendMessageTimeout needs special error handling
    SetLastError(0);
    LPARAM lParam = (LPARAM)L"Environment";

    if (!(*sm)(
        HWND_BROADCAST,
        WM_SETTINGCHANGE,
        NULL,
        lParam,
        SMTO_ABORTIFHUNG,
        50,
        NULL
    )) {
        int err = GetLastError();
        if (!err) {
            PyErr_SetString(PyExc_OSError, "Unspecified error");
        } else {
            PyErr_SetFromWindowsErr(err);
        }
        FreeLibrary(user32);
        return NULL;
    }

    FreeLibrary(user32);
    return Py_GetConstant(Py_CONSTANT_NONE);
}

typedef enum {
    CPU_X86     = 0,
    CPU_X86_64  = 9,
    CPU_ARM     = 5,
    CPU_ARM64   = 12,
    CPU_UNKNOWN = 0xffff
} CpuArchitecture;

PyObject *get_processor_architecture(PyObject *, PyObject *, PyObject *) {
    SYSTEM_INFO system_info;
    GetNativeSystemInfo(&system_info);
    
    switch (system_info.wProcessorArchitecture) {
        case CPU_X86: return PyUnicode_FromString("-32");
        case CPU_X86_64: return PyUnicode_FromString("-64");
        case CPU_ARM: return PyUnicode_FromString("-arm");
        case CPU_ARM64: return PyUnicode_FromString("-arm64");
        default: return PyUnicode_FromString("-64"); // x86-64
    }
}

}
