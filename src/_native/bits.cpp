#include <Python.h>
#include <windows.h>
#include <bits.h>
#include <typeinfo>

#include "helpers.h"

#ifdef BITS_INJECT_ERROR
static HRESULT _inject_hr[]
#else
const HRESULT _inject_hr[]
#endif
    = { S_OK, S_OK, S_OK, S_OK };


static PyObject *
error_from_bits_hr(IBackgroundCopyManager *bcm, HRESULT hr, const char *operation)
{
    LPWSTR err;
    HRESULT hr2;
    if (FAILED(hr2 = _inject_hr[2])
        || FAILED(hr2 = bcm->GetErrorDescription(hr, LANGIDFROMLCID(GetThreadLocale()), &err))) {
        err_SetFromWindowsErrWithMessage(hr, operation);
        err_SetFromWindowsErrWithMessage(hr2, "Retrieving error message");
        return NULL;
    }

    size_t n = wcslen(err);
    while (n > 0 && isspace(err[--n])) {
        err[n] = L'\0';
    }
    err_SetFromWindowsErrWithMessage(hr, operation, err);
    CoTaskMemFree(err);
    return NULL;
}


static PyObject *
error_from_bits_job(IBackgroundCopyJob *job)
{
    IBackgroundCopyError *error = NULL;
    BG_ERROR_CONTEXT context;
    HRESULT hr, hr_error = S_FALSE;
    LPWSTR str_error;
    PyObject *exc, *val, *tb;

    if (FAILED(hr = _inject_hr[1])
        || FAILED(hr = job->GetError(&error))
        || FAILED(hr = error->GetError(&context, &hr_error))
    ) {
        if (error) {
            error->Release();
        }
        PyErr_SetString(PyExc_OSError, "Unidentified download error");
        err_SetFromWindowsErrWithMessage(hr, "Retrieving download error");
        return NULL;
    }

    if (FAILED(hr = _inject_hr[2])
        || FAILED(hr = error->GetErrorDescription(LANGIDFROMLCID(GetThreadLocale()), &str_error))
    ) {
        error->Release();
        //PyErr_SetFromWindowsErr(hr_error);
        //err_SetFromWindowsErrWithMessage(hr, "Retrieving error message");
        err_SetFromWindowsErrWithMessage(hr_error, "Could not retrieve message");
        return NULL;
    }

    size_t n = wcslen(str_error);
    while (n > 0 && isspace(str_error[--n])) {
        str_error[n] = L'\0';
    }

    err_SetFromWindowsErrWithMessage(hr_error, "Download error", str_error);
    CoTaskMemFree(str_error);
    error->Release();
    return NULL;
}


static HRESULT get_job_progress(IBackgroundCopyJob *job, int *progress, int *already_complete) {
    HRESULT hr;
    BG_JOB_STATE job_state;
    BG_JOB_PROGRESS job_progress;
    if (FAILED(hr = _inject_hr[0]) || FAILED(hr = job->GetState(&job_state))) {
        return hr;
    }

    *already_complete = 0;

    switch (job_state) {
    case BG_JOB_STATE_QUEUED:
    case BG_JOB_STATE_CONNECTING:
    case BG_JOB_STATE_CANCELLED:
        *progress = 0;
        break;
    case BG_JOB_STATE_TRANSFERRED:
        *progress = 100;
        break;
    case BG_JOB_STATE_ACKNOWLEDGED:
        *progress = 100;
        *already_complete = 1;
        break;
    case BG_JOB_STATE_TRANSFERRING:
    case BG_JOB_STATE_SUSPENDED:
        if (FAILED(hr = job->GetProgress(&job_progress))) {
            return hr;
        }
        // probably an unnecessary sanity check
        if (job_progress.FilesTransferred >= job_progress.FilesTotal
            || job_progress.BytesTransferred >= job_progress.BytesTotal) {
            *progress = 100;
        } else if (job_progress.BytesTotal == BG_SIZE_UNKNOWN) {
            *progress = (job_progress.FilesTransferred * 100) / job_progress.FilesTotal;
        } else {
            *progress = (job_progress.BytesTransferred * 100) / job_progress.BytesTotal;
        }
        break;
    case BG_JOB_STATE_TRANSIENT_ERROR:
    case BG_JOB_STATE_ERROR:
        return S_FALSE;
    }
    if (*progress < 0) {
        *progress = 0;
    } else if (*progress > 100) {
        *progress = 100;
    }
    return S_OK;
}


extern "C" {

// Returns a capsule containing the BackgroundCopyManager instance
PyObject *bits_connect(PyObject *, PyObject *args, PyObject *kwargs) {
    IBackgroundCopyManager *bcm = NULL;
    HRESULT hr = CoCreateInstance(
        __uuidof(BackgroundCopyManager),
        NULL,
        CLSCTX_LOCAL_SERVER,
        __uuidof(IBackgroundCopyManager),
        (void**)&bcm
    );
    if (FAILED(hr)) {
        PyErr_SetFromWindowsErr(hr);
        return NULL;
    }
    return make_capsule(bcm);
}


// (conn, job_id) -> job
PyObject *bits_find_job(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"conn", "job_id", NULL};
    IBackgroundCopyManager *bcm = NULL;
    Py_buffer job_id;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&y*:bits_find_job", keywords,
        from_capsule<IBackgroundCopyManager>, &bcm, &job_id
    )) {
        return NULL;
    }
    if (job_id.len < sizeof(GUID)) {
        PyBuffer_Release(&job_id);
        PyErr_SetString(PyExc_ValueError, "'job_id' must be a serialized job ID");
        return NULL;
    }

    PyObject *r = NULL;
    IBackgroundCopyJob *job = NULL;
    GUID job_guid = *(GUID *)job_id.buf;

    HRESULT hr;
    if (FAILED(hr = _inject_hr[0]) || FAILED(hr = bcm->GetJob(job_guid, &job))) {
        error_from_bits_hr(bcm, hr, "Getting background download");
    } else {
        r = make_capsule(job);
    }

    PyBuffer_Release(&job_id);
    return r;
}


// (conn, job) -> job_id
PyObject *bits_serialize_job(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"conn", "job", NULL};
    IBackgroundCopyManager *bcm = NULL;
    IBackgroundCopyJob* job = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&:bits_serialize_job", keywords,
        from_capsule<IBackgroundCopyManager>, &bcm, from_capsule<IBackgroundCopyJob>, &job)) {
        return NULL;
    }

    PyObject *r = NULL;
    GUID job_id;
    HRESULT hr;
    if (FAILED(hr = _inject_hr[0]) || FAILED(hr = job->GetId(&job_id))) {
        error_from_bits_hr(bcm, hr, "Getting download job ID");
    } else {
        r = PyBytes_FromStringAndSize((char *)&job_id, sizeof(job_id));
    }

    return r;
}


static HRESULT _job_setcredentials(IBackgroundCopyJob *job, wchar_t *username, wchar_t *password) {
    IBackgroundCopyJob2 *job2 = NULL;
    HRESULT hr;
    BG_AUTH_CREDENTIALS creds = {
        .Target = BG_AUTH_TARGET_SERVER,
        .Scheme = BG_AUTH_SCHEME_BASIC,
        .Credentials = {
            .Basic = {
                .UserName = username,
                .Password = username ? password : NULL
            }
        }
    };

    if (!username && !password) {
        return S_OK;
    }

    if (FAILED(hr = _inject_hr[3])
        || FAILED(hr = job->QueryInterface(__uuidof(IBackgroundCopyJob2), (void **)&job2))) {
        return hr;
    }
    hr = job2->SetCredentials(&creds);
    job2->Release();
    return hr;
}

// (conn, name, url, path, [username], [password]) -> job
PyObject *bits_begin(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"conn", "name", "url", "path", "username", "password", NULL};
    IBackgroundCopyManager *bcm = NULL;
    wchar_t *name = NULL;
    wchar_t *url = NULL;
    wchar_t *path = NULL;
    wchar_t *username = NULL;
    wchar_t *password = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&O&O&|O&O&:bits_begin", keywords,
        from_capsule<IBackgroundCopyManager>, &bcm, as_utf16, &name, as_utf16, &url, as_utf16, &path,
        as_utf16, &username, as_utf16, &password
    )) {
        return NULL;
    }

    PyObject *r = NULL;
    GUID jobId;
    IBackgroundCopyJob* job = NULL;
    HRESULT hr;
    if (FAILED(hr = _inject_hr[0])
        || FAILED(hr = bcm->CreateJob(name, BG_JOB_TYPE_DOWNLOAD, &jobId, &job))) {
        error_from_bits_hr(bcm, hr, "Creating download job");
        goto done;
    }
    if ((username || password) && FAILED(hr = _job_setcredentials(job, username, password))) {
        error_from_bits_hr(bcm, hr, "Adding basic credentials to download job");
        goto done;
    }
    if (FAILED(hr = job->AddFile(url, path))) {
        error_from_bits_hr(bcm, hr, "Adding file to download job");
        goto done;
    }
    if (FAILED(hr = job->SetPriority(BG_JOB_PRIORITY_FOREGROUND))) {
        error_from_bits_hr(bcm, hr, "Setting download job priority");
        goto done;
    }
    if (FAILED(hr = job->Resume())) {
        error_from_bits_hr(bcm, hr, "Starting download job");
        goto done;
    }

    job->AddRef();
    r = make_capsule(job);

done:
    if (job) {
        job->Release();
    }
    PyMem_Free(path);
    PyMem_Free(url);
    PyMem_Free(name);
    PyMem_Free(username);
    PyMem_Free(password);

    return r;
}


// (job)
PyObject *bits_cancel(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"conn", "job", NULL};
    IBackgroundCopyManager *bcm = NULL;
    IBackgroundCopyJob* job = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&:bits_cancel", keywords,
        from_capsule<IBackgroundCopyManager>, &bcm, from_capsule<IBackgroundCopyJob>, &job)) {
        return NULL;
    }
    HRESULT hr;
    if (FAILED(hr = _inject_hr[0]) || FAILED(hr = job->Cancel())) {
        return error_from_bits_hr(bcm, hr, "Cancelling download job");
    }
    Py_RETURN_NONE;
}


// (job) -> int[0..100] or exception
PyObject *bits_get_progress(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"conn", "job", NULL};
    IBackgroundCopyManager *bcm = NULL;
    IBackgroundCopyJob* job = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&:bits_get_progress", keywords,
        from_capsule<IBackgroundCopyManager>, &bcm, from_capsule<IBackgroundCopyJob>, &job)) {
        return NULL;
    }

    PyObject *r = NULL;
    int progress = 0, already_complete = 0;

    HRESULT hr = _inject_hr[0];
    if (!FAILED(hr) && hr != S_FALSE) {
        hr = get_job_progress(job, &progress, &already_complete);
    }

    if (hr == S_FALSE) {
        return error_from_bits_job(job);
    } else if (FAILED(hr)) {
        return error_from_bits_hr(bcm, hr, "Getting download progress");
    }

    if (progress == 100 && !already_complete) {
        hr = job->Complete();
        if (FAILED(hr)) {
            return error_from_bits_hr(bcm, hr, "Completing download job");
        }
    }
    return Py_BuildValue("i", progress);
}


// (conn, job, username, password) -> job
PyObject *bits_retry_with_auth(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"conn", "job", "username", "password", NULL};
    IBackgroundCopyManager *bcm = NULL;
    IBackgroundCopyJob* job = NULL;
    wchar_t *username = NULL;
    wchar_t *password = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&O&O&:bits_retry_with_auth", keywords,
        from_capsule<IBackgroundCopyManager>, &bcm, from_capsule<IBackgroundCopyJob>, &job,
        as_utf16, &username, as_utf16, &password
    )) {
        return NULL;
    }

    HRESULT hr;
    PyObject *r = NULL;

    if (FAILED(hr = _job_setcredentials(job, username, password))) {
        error_from_bits_hr(bcm, hr, "Adding basic credentials to download job");
        goto done;
    }
    if (FAILED(hr = job->Resume())) {
        error_from_bits_hr(bcm, hr, "Starting download job");
        goto done;
    }

    r = Py_GetConstant(Py_CONSTANT_NONE);

done:
    PyMem_Free(username);
    PyMem_Free(password);

    return r;
}


#ifdef BITS_INJECT_ERROR

PyObject *bits_inject_error(PyObject *, PyObject *args, PyObject *kwargs) {
    HRESULT hr;
    if (!PyArg_ParseTuple(
            args, "IIII:bits_inject_error",
            // replace HRESULT for primary operation
            &_inject_hr[0],
            // replace HRESULT for getting error code
            &_inject_hr[1],
            // replace HRESULT for getting error text
            &_inject_hr[2],
            // replace HRESULT for adding credentials to job
            &_inject_hr[3]
        )) {
        return NULL;
    }
    Py_RETURN_NONE;
}

#endif

}

