#include <Python.h>

#include "helpers.h"
#include "proxy.h"

int proxy_settings_parse(PyObject *obj, ProxySettings *settings) {
    settings->mode = PROXY_MODE_AUTO;
    settings->proxy_list = NULL;
    settings->username = NULL;
    settings->password = NULL;

    if (!obj || Py_Is(obj, Py_GetConstantBorrowed(Py_CONSTANT_NONE))) {
        return 1;
    }

    int mode;
    if (!PyArg_ParseTuple(
        obj,
        "iO&O&O&:proxy_settings",
        &mode,
        as_utf16, &settings->proxy_list,
        as_utf16, &settings->username,
        as_utf16, &settings->password
    )) {
        // PyArg_ParseTuple calls cleanup for successful O& converters when a
        // later conversion fails, so these pointers no longer own memory.
        settings->proxy_list = NULL;
        settings->username = NULL;
        settings->password = NULL;
        return 0;
    }

    if (mode < PROXY_MODE_AUTO || mode > PROXY_MODE_OVERRIDE) {
        PyErr_SetString(PyExc_ValueError, "invalid proxy mode");
        proxy_settings_clear(settings);
        return 0;
    }
    settings->mode = (ProxyMode)mode;

    if (settings->mode == PROXY_MODE_OVERRIDE && !settings->proxy_list) {
        PyErr_SetString(PyExc_ValueError, "proxy override requires a proxy list");
        proxy_settings_clear(settings);
        return 0;
    }
    return 1;
}

void proxy_settings_clear(ProxySettings *settings) {
    PyMem_Free(settings->proxy_list);
    PyMem_Free(settings->username);
    PyMem_Free(settings->password);
    settings->mode = PROXY_MODE_AUTO;
    settings->proxy_list = NULL;
    settings->username = NULL;
    settings->password = NULL;
}
