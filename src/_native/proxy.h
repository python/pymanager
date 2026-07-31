#pragma once

#include <Python.h>

enum ProxyMode {
    PROXY_MODE_AUTO = 0,
    PROXY_MODE_DIRECT = 1,
    PROXY_MODE_OVERRIDE = 2,
};

struct ProxySettings {
    ProxyMode mode;
    wchar_t *proxy_list;
    wchar_t *username;
    wchar_t *password;
};

int proxy_settings_parse(PyObject *obj, ProxySettings *settings);
void proxy_settings_clear(ProxySettings *settings);
