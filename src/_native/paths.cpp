#include <Python.h>
#include <windows.h>
#include <shlwapi.h>
#include <string>

#include "helpers.h"

#pragma comment(lib, "Shlwapi.lib")

extern "C" {

PyObject *
package_get_root(PyObject *, PyObject *, PyObject *)
{
    // Assume current process is running in the package root
    wchar_t buffer[MAX_PATH];
    DWORD cch = GetModuleFileName(NULL, buffer, MAX_PATH);
    if (!cch) {
        PyErr_SetFromWindowsErr(GetLastError());
        return NULL;
    }
    while (cch > 0 && buffer[--cch] != L'\\') { }
    return PyUnicode_FromWideChar(buffer, cch);
}


PyObject *
file_url_to_path(PyObject *, PyObject *args, PyObject *kwargs)
{
    static const char * keywords[] = {"url", NULL};
    wchar_t *url = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&:file_url_to_path", keywords,
        as_utf16, &url)) {
        return NULL;
    }

    PyObject *r = NULL;
    wchar_t path[32768];
    DWORD path_len = 32767;
    HRESULT hr = PathCreateFromUrlW(url, path, &path_len, 0);
    if (SUCCEEDED(hr)) {
        r = PyUnicode_FromWideChar(path, -1);
    } else {
        PyErr_SetFromWindowsErr(hr);
    }
    PyMem_Free(url);
    return r;
}


PyObject *
file_lock_for_delete(PyObject *, PyObject *args, PyObject *kwargs)
{
    static const char * keywords[] = {"path", NULL};
    wchar_t *path = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&:file_lock_for_delete", keywords,
        as_utf16, &path)) {
        return NULL;
    }

    HANDLE h = CreateFileW(path, FILE_GENERIC_WRITE | DELETE, 0,
                           NULL, OPEN_EXISTING, 0, 0);
    if (h == INVALID_HANDLE_VALUE) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    return PyLong_FromNativeBytes(&h, sizeof(h), -1);
}


PyObject *
file_unlock_for_delete(PyObject *, PyObject *args, PyObject *kwargs)
{
    static const char * keywords[] = {"handle", NULL};
    PyObject *handle = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O:file_unlock_for_delete", keywords,
        &handle)) {
        return NULL;
    }
    HANDLE h;
    if (PyLong_AsNativeBytes(handle, &h, sizeof(h), -1) < 0) {
        return NULL;
    }
    CloseHandle(h);
    return Py_GetConstant(Py_CONSTANT_NONE);
}


PyObject *
file_locked_delete(PyObject *, PyObject *args, PyObject *kwargs)
{
    static const char * keywords[] = {"handle", NULL};
    PyObject *handle = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O:file_locked_delete", keywords,
        &handle)) {
        return NULL;
    }
    HANDLE h;
    if (PyLong_AsNativeBytes(handle, &h, sizeof(h), -1) < 0) {
        return NULL;
    }
    DWORD cch = 0;
    std::wstring buf;
    cch = GetFinalPathNameByHandleW(h, NULL, 0, FILE_NAME_OPENED);
    if (cch) {
        buf.resize(cch);
        cch = GetFinalPathNameByHandleW(h, buf.data(), cch, FILE_NAME_OPENED);
    }
    if (!cch) {
        PyErr_SetFromWindowsErr(0);
        CloseHandle(h);
        return NULL;
    }
    CloseHandle(h);
    if (!DeleteFileW(buf.c_str())) {
        PyErr_SetFromWindowsErr(0);
        return NULL;
    }
    return Py_GetConstant(Py_CONSTANT_NONE);
}


}