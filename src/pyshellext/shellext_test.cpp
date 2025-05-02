#include <Python.h>

#include "shellext.h"
#include "..\_native\helpers.h"

extern "C" {

PyObject *shellext_RegReadStr(PyObject *, PyObject *args, PyObject *)
{
    HKEY hkey;
    PyObject *hkeyObj;
    wchar_t *valueName;
    if (!PyArg_ParseTuple(args, "OO&", &hkeyObj, as_utf16, &valueName)) {
        return NULL;
    }
    if (!PyLong_AsNativeBytes(hkeyObj, &hkey, sizeof(hkey), -1)) {
        PyMem_Free(valueName);
        return NULL;
    }

    PyObject *r = NULL;
    std::wstring result;
    int err = (int)RegReadStr(hkey, valueName, result);
    if (err) {
        PyErr_SetFromWindowsErr(err);
    } else {
        r = PyUnicode_FromWideChar(result.data(), result.size());
    }

    PyMem_Free(valueName);
    return r;
}


PyObject *shellext_ReadIdleInstalls(PyObject *, PyObject *args, PyObject *)
{
    HKEY hkey;
    wchar_t *company;
    REGSAM flags;
    PyObject *hkeyObj, *flagsObj;
    if (!PyArg_ParseTuple(args, "OO&O", &hkeyObj, as_utf16, &company, &flagsObj)) {
        return NULL;
    }
    if (!PyLong_AsNativeBytes(hkeyObj, &hkey, sizeof(hkey), -1) ||
        !PyLong_AsNativeBytes(flagsObj, &flags, sizeof(flags), -1)) {
        PyMem_Free(company);
        return NULL;
    }

    PyObject *r = NULL;
    std::vector<IdleData> result;
    HRESULT hr = ReadIdleInstalls(result, hkey, company, flags);

    if (FAILED(hr)) {
        PyErr_SetFromWindowsErr((int)hr);
    } else {
        r = PyList_New(0);
        for (auto &i : result) {
            PyObject *o = Py_BuildValue("uuu", i.title.c_str(), i.exe.c_str(), i.idle.c_str());
            if (!o) {
                Py_CLEAR(r);
                break;
            }
            if (PyList_Append(r, o) < 0) {
                Py_DECREF(o);
                Py_CLEAR(r);
                break;
            }
            Py_DECREF(o);
        }
    }

    PyMem_Free(company);
    return r;
}


PyObject *shellext_ReadAllIdleInstalls(PyObject *, PyObject *args, PyObject *)
{
    HKEY hkey;
    REGSAM flags;
    PyObject *hkeyObj, *flagsObj;
    if (!PyArg_ParseTuple(args, "OO", &hkeyObj, &flagsObj)) {
        return NULL;
    }
    if (!PyLong_AsNativeBytes(hkeyObj, &hkey, sizeof(hkey), -1) ||
        !PyLong_AsNativeBytes(flagsObj, &flags, sizeof(flags), -1)) {
        return NULL;
    }

    PyObject *r = NULL;
    std::vector<IdleData> result;
    HRESULT hr = ReadAllIdleInstalls(result, hkey, NULL, flags);

    if (FAILED(hr)) {
        PyErr_SetFromWindowsErr((int)hr);
    } else {
        r = PyList_New(0);
        for (auto &i : result) {
            PyObject *o = Py_BuildValue("uuu", i.title.c_str(), i.exe.c_str(), i.idle.c_str());
            if (!o) {
                Py_CLEAR(r);
                break;
            }
            if (PyList_Append(r, o) < 0) {
                Py_DECREF(o);
                Py_CLEAR(r);
                break;
            }
            Py_DECREF(o);
        }
    }

    return r;
}


PyObject *shellext_PassthroughTitle(PyObject *, PyObject *args, PyObject *)
{
    wchar_t *value;
    if (!PyArg_ParseTuple(args, "O&", as_utf16, &value)) {
        return NULL;
    }

    PyObject *r = NULL;
    IExplorerCommand *cmd = MakeLaunchCommand(value, L"", L"");
    wchar_t *title;
    HRESULT hr = cmd->GetTitle(NULL, &title);
    if (SUCCEEDED(hr)) {
        r = PyUnicode_FromWideChar(title, -1);
        CoTaskMemFree((void*)title);
    } else {
        PyErr_SetFromWindowsErr((int)hr);
    }
    cmd->Release();
    return r;
}


PyObject *shellext_IdleCommand(PyObject *, PyObject *args, PyObject *)
{
    HKEY hkey;
    REGSAM flags;
    PyObject *hkeyObj, *flagsObj;
    if (!PyArg_ParseTuple(args, "O", &hkeyObj)) {
        return NULL;
    }
    if (!PyLong_AsNativeBytes(hkeyObj, &hkey, sizeof(hkey), -1)) {
        return NULL;
    }

    IExplorerCommand *cmd = MakeIdleCommand(hkey, NULL);
    IEnumExplorerCommand *enm = NULL;
    PyObject *r = PyList_New(0);
    PyObject *o;
    wchar_t *s;
    HRESULT hr;
    ULONG fetched;
    
    hr = cmd->GetTitle(NULL, &s);
    if (SUCCEEDED(hr)) {
        o = PyUnicode_FromWideChar(s, -1);
        if (!o || PyList_Append(r, o) < 0) {
            goto abort;
        }
        Py_CLEAR(o);
        CoTaskMemFree((void *)s);
        s = NULL;
    } else {
        goto abort;
    }

    hr = cmd->GetIcon(NULL, &s);
    if (SUCCEEDED(hr)) {
        o = PyUnicode_FromWideChar(s, -1);
        if (!o || PyList_Append(r, o) < 0) {
            goto abort;
        }
        Py_CLEAR(o);
        CoTaskMemFree((void *)s);
        s = NULL;
    } else {
        goto abort;
    }

    hr = cmd->EnumSubCommands(&enm);
    cmd->Release();
    cmd = NULL;
    if (FAILED(hr)) {
        goto abort;
    }

    while ((hr = enm->Next(1, &cmd, &fetched)) == S_OK) {
        if (fetched != 1) {
            PyErr_SetString(PyExc_RuntimeError, "'fetched' was not 1");
            goto abort;
        }

        hr = cmd->GetTitle(NULL, &s);
        if (SUCCEEDED(hr)) {
            o = PyUnicode_FromWideChar(s, -1);
            if (!o || PyList_Append(r, o) < 0) {
                goto abort;
            }
            Py_CLEAR(o);
            CoTaskMemFree((void *)s);
            s = NULL;
        } else {
            goto abort;
        }

        cmd->Release();
        cmd = NULL;
    }
    if (FAILED(hr)) {
        goto abort;
    }

    enm->Release();
    enm = NULL;

    return r;

abort:
    Py_XDECREF(o);
    Py_XDECREF(r);
    CoTaskMemFree((void *)s);
    if (enm) {
        enm->Release();
    }
    if (cmd) {
        cmd->Release();
    }
    if (FAILED(hr)) {
        PyErr_SetFromWindowsErr((int)hr);
    }
    return NULL;
}


}
