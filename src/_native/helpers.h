template <typename T>
static int from_capsule(PyObject *obj, T **address) {
    T *p = (T *)PyCapsule_GetPointer(obj, typeid(T).name());
    if (!p) {
        return 0;
    }
    *address = p;
    return 1;
}

template <typename T>
static void Capsule_Release(PyObject *capsule) {
    T *p;
    if (from_capsule<T>(capsule, &p)) {
        p->Release();
    } else {
        PyErr_Clear();
    }
}

template <typename T>
static PyObject *make_capsule(T *p) {
    PyObject *r = PyCapsule_New(p, typeid(T).name(), Capsule_Release<T>);
    if (!r) {
        p->Release();
    }
    return r;
}


extern int as_utf16(PyObject *obj, wchar_t **address);

extern void err_SetFromWindowsErrWithMessage(
    int error,
    const char *message=NULL,
    const wchar_t *os_message=NULL,
    void *hModule=NULL
);
