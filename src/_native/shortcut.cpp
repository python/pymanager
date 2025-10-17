#include <Python.h>
#include <windows.h>
#include <shlobj.h>
#include <shlguid.h>
#include <iterator>
#include "helpers.h"

extern "C" {

PyObject *
shortcut_create(PyObject *, PyObject *args, PyObject *kwargs)
{
    static const char *keywords[] = {
        "path", "target", "arguments", "working_directory",
        "icon", "icon_index",
        NULL
    };
    wchar_t *path = NULL;
    wchar_t *target = NULL;
    wchar_t *arguments = NULL;
    wchar_t *workingDirectory = NULL;
    wchar_t *iconPath = NULL;
    int iconIndex = 0;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs,
            "O&O&|O&O&O&i:shortcut_create", keywords,
            as_utf16, &path, as_utf16, &target, as_utf16, &arguments, as_utf16, &workingDirectory,
            as_utf16, &iconPath, &iconIndex)) {
        return NULL;
    }

    PyObject *r = NULL;
    IShellLinkW *lnk = NULL;
    IPersistFile *persist = NULL;
    HRESULT hr;

    hr = CoCreateInstance(CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER,
        IID_IShellLinkW, (void **)&lnk);

    if (FAILED(hr)) {
        err_SetFromWindowsErrWithMessage(hr, "Creating system shortcut");
        goto done;
    }
    if (FAILED(hr = lnk->SetPath(target))) {
        err_SetFromWindowsErrWithMessage(hr, "Setting shortcut target");
        goto done;
    }
    if (arguments && *arguments && FAILED(hr = lnk->SetArguments(arguments))) {
        err_SetFromWindowsErrWithMessage(hr, "Setting shortcut arguments");
        goto done;
    }
    if (workingDirectory && *workingDirectory && FAILED(hr = lnk->SetWorkingDirectory(workingDirectory))) {
        err_SetFromWindowsErrWithMessage(hr, "Setting shortcut working directory");
        goto done;
    }
    if (iconPath && *iconPath && FAILED(hr = lnk->SetIconLocation(iconPath, iconIndex))) {
        err_SetFromWindowsErrWithMessage(hr, "Setting shortcut icon");
        goto done;
    }
    if (FAILED(hr = lnk->QueryInterface(&persist))) {
        err_SetFromWindowsErrWithMessage(hr, "Getting persist interface");
        goto done;
    }
    // gh-15: Apparently ERROR_USER_MAPPED_FILE can occur here, which suggests
    // contention on the file. We should be able to sleep and retry to handle it
    // in most cases.
    for (int retries = 5; retries; --retries) {
        if (SUCCEEDED(hr = persist->Save(path, 0))) {
            break;
        }
        if (retries == 1 || hr != HRESULT_FROM_WIN32(ERROR_USER_MAPPED_FILE)) {
            err_SetFromWindowsErrWithMessage(hr, "Writing shortcut");
            goto done;
        }
        Sleep(10);
    }

    r = Py_NewRef(Py_None);

done:
    if (persist) {
        persist->Release();
    }
    if (lnk) {
        lnk->Release();
    }
    if (path) PyMem_Free(path);
    if (target) PyMem_Free(target);
    if (arguments) PyMem_Free(arguments);
    if (workingDirectory) PyMem_Free(workingDirectory);
    if (iconPath) PyMem_Free(iconPath);
    return r;
}


PyObject *
shortcut_get_start_programs(PyObject *, PyObject *, PyObject *)
{
    wchar_t *path;
    HRESULT hr = SHGetKnownFolderPath(
        FOLDERID_Programs,
        KF_FLAG_NO_PACKAGE_REDIRECTION | KF_FLAG_CREATE,
        NULL,
        &path
    );
    if (FAILED(hr)) {
        err_SetFromWindowsErrWithMessage(hr, "Obtaining Start Menu location");
        return NULL;
    }
    PyObject *r = PyUnicode_FromWideChar(path, -1);
    CoTaskMemFree(path);
    return r;
}


PyObject *
shortcut_default_cwd(PyObject *, PyObject *, PyObject *)
{
    static const KNOWNFOLDERID fids[] = { FOLDERID_Documents, FOLDERID_Profile };
    for (auto i = std::begin(fids); i != std::end(fids); ++i) {
        wchar_t *path;
        if (SUCCEEDED(SHGetKnownFolderPath(
            *i,
            KF_FLAG_NO_PACKAGE_REDIRECTION,
            NULL,
            &path
        ))) {
            PyObject *r = PyUnicode_FromWideChar(path, -1);
            CoTaskMemFree(path);
            return r;
        }
    }
    return Py_GetConstant(Py_CONSTANT_NONE);
}


PyObject *
hide_file(PyObject *, PyObject *args, PyObject *kwargs)
{
    static const char *keywords[] = {"path", "hidden", NULL};
    wchar_t *path;
    int hidden = 1;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&|b:hide_file", keywords, as_utf16, &path, &hidden)) {
        return NULL;
    }
    PyObject *r = NULL;
    DWORD attr = GetFileAttributesW(path);
    if (attr == INVALID_FILE_ATTRIBUTES) {
        err_SetFromWindowsErrWithMessage(GetLastError(), "Reading file attributes");
        goto done;
    }
    if (hidden) {
        attr |= FILE_ATTRIBUTE_HIDDEN;
    } else {
        attr &= ~FILE_ATTRIBUTE_HIDDEN;
    }
    if (!SetFileAttributesW(path, attr)) {
        err_SetFromWindowsErrWithMessage(GetLastError(), "Setting file attributes");
        goto done;
    }

    r = Py_NewRef(Py_None);

done:
    PyMem_Free(path);
    return r;
}

}
