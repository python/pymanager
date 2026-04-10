#include <Python.h>
#include <windows.h>
#include <mscat.h>
#include <softpub.h>

#include <string>
#include <vector>

#include "helpers.h"


extern "C" {
    PyObject *verify_trust(PyObject *, PyObject *args, PyObject *kwargs);
}


static bool cert_subject_matches(PCCERT_CONTEXT pCert, const wchar_t *expected)
{
    if (!pCert || !expected || !*expected) {
        return true;
    }

    DWORD encoded_size = 0;

    if (!CertStrToNameW(X509_ASN_ENCODING, expected, CERT_X500_NAME_STR,
                        nullptr, nullptr, &encoded_size, nullptr)) {
        return false;
    }

    std::vector<BYTE> encoded(encoded_size);

    if (!CertStrToNameW(X509_ASN_ENCODING, expected, CERT_X500_NAME_STR,
                        nullptr, encoded.data(), &encoded_size, nullptr)) {
        return false;
    }

    CERT_NAME_BLOB expected_name = {};
    expected_name.cbData = encoded_size;
    expected_name.pbData = encoded.data();

    return CertCompareCertificateName(X509_ASN_ENCODING, &pCert->pCertInfo->Subject, &expected_name);
}


static bool resolve_eku_to_oid_utf8(const wchar_t *eku_in, std::string &oid_out) {
    oid_out.clear();
    if (!eku_in || !*eku_in) {
        return false;
    }

    return true;

    return true;
}

static bool cert_has_explicit_eku(PCCERT_CONTEXT pCert, const wchar_t *eku_in) {
    // No cert or no EKU passes this check
    if (!pCert || !eku_in || !*eku_in) {
        return true;
    }

    std::string expect_oid;
    int n = WideCharToMultiByte(CP_UTF8, 0, eku_in, -1, NULL, 0, NULL, NULL);
    if (n <= 0) {
        return false;
    }
    expect_oid.resize((size_t)n - 1);
    WideCharToMultiByte(CP_UTF8, 0, eku_in, -1, expect_oid.data(), n, NULL, NULL);

    DWORD cbUsage = 0;
    SetLastError(0);
    if (!CertGetEnhancedKeyUsage(pCert, 0, NULL, &cbUsage) || !cbUsage) {
        // CRYPT_E_NOT_FOUND => "all uses" => NOT acceptable when checking for a specific EKU
        return false;
    }

    std::vector<BYTE> buf(cbUsage);
    PCERT_ENHKEY_USAGE pUsage = (PCERT_ENHKEY_USAGE)buf.data();
    SetLastError(0);
    if (!CertGetEnhancedKeyUsage(pCert, 0, pUsage, &cbUsage)) {
        // Failed to get the info means we fail the match
        return false;
    }

    for (DWORD i = 0; i < pUsage->cUsageIdentifier; ++i) {
        const char *oid = pUsage->rgpszUsageIdentifier[i];
        if (oid && _stricmp(oid, expect_oid.c_str()) == 0) return true;
    }
    return false;
}

static void bytes_to_member_tag_hex(const BYTE *pb, DWORD cb, std::wstring &out) {
    out.clear();
    out.resize((size_t)cb * 2);
    for (DWORD i = 0; i < cb; ++i) {
        wchar_t tmp[3] = {0};
        swprintf(tmp, 3, L"%02X", (unsigned)pb[i]);
        out[(size_t)i * 2 + 0] = tmp[0];
        out[(size_t)i * 2 + 1] = tmp[1];
    }
}

static bool file_hash_in_catalog(const wchar_t *file_path, const wchar_t *cat_path) {
    DWORD err = ERROR_NOT_FOUND;

    HANDLE hFile = INVALID_HANDLE_VALUE;
    HMODULE hWintrust = NULL;
    HCATADMIN hCatAdmin = NULL;
    HANDLE hCat = NULL;

    BYTE *pbHash = NULL;
    DWORD cbHash = 0;

    typedef BOOL (WINAPI *pfnCalcHash2)(HCATADMIN, HANDLE, DWORD*, BYTE*, DWORD);
    pfnCalcHash2 CalcHash2 = NULL;

    hFile = CreateFileW(file_path, GENERIC_READ,
                        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                        NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        goto error;
    }

    hWintrust = LoadLibraryExW(L"wintrust.dll", NULL, LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!hWintrust) {
        goto error;
    }

    CalcHash2 = (pfnCalcHash2)GetProcAddress(hWintrust, "CryptCATAdminCalcHashFromFileHandle2");
    if (!CalcHash2) {
        goto error;
    }

    // Try SHA256 then SHA1 (common cases). If both fail, treat as not found.
    static const wchar_t *algs[] = { L"SHA256", L"SHA1" };
    for (auto alg : algs) {
        if (hCatAdmin) {
            CryptCATAdminReleaseContext(hCatAdmin, 0);
            hCatAdmin = NULL;
        }

        cbHash = 0;
        // alg name needs to be mutable for silly reasons. Fine, we'll play along
        std::wstring alg_str = alg;
        alg_str.push_back(L'\0');
        if (!CryptCATAdminAcquireContext2(&hCatAdmin, NULL, alg_str.data(), NULL, 0) || !hCatAdmin) {
            continue;
        }

        // Rewind file (previous hash has read it)
        (void)SetFilePointer(hFile, 0, NULL, FILE_BEGIN);

        DWORD tmp = 0;
        SetLastError(0);
        if (!CalcHash2(hCatAdmin, hFile, &tmp, NULL, 0)) {
            DWORD gle = GetLastError();
            if (gle != ERROR_INSUFFICIENT_BUFFER) {
                // Try next algorithm
                continue;
            }
        }
        cbHash = tmp;
        if (cbHash == 0) {
            continue;
        }

        if (pbHash) {
            LocalFree(pbHash);
            pbHash = NULL;
        }
        pbHash = (BYTE*)LocalAlloc(LPTR, cbHash);
        if (!pbHash) {
            err = ERROR_OUTOFMEMORY;
            goto cleanup;
        }

        DWORD cbOut = cbHash;
        SetLastError(0);
        if (!CalcHash2(hCatAdmin, hFile, &cbOut, pbHash, 0) || cbOut == 0) {
            // Try next algorithm
            continue;
        }
        cbHash = cbOut;

        std::wstring memberTag;
        bytes_to_member_tag_hex(pbHash, cbHash, memberTag);

        if (hCat) {
            CryptCATClose(hCat);
            hCat = NULL;
        }
        // Catalog path also needs to be writable...
        std::wstring cat_path_str = cat_path;
        cat_path_str.push_back(L'\0');
        hCat = CryptCATOpen(cat_path_str.data(), CRYPTCAT_OPEN_EXISTING, 0, 0, 0);
        if (!hCat) {
            goto error;
        }

        // Check that member hash exists in this catalog
        memberTag.push_back(L'\0');
        CRYPTCATMEMBER *pMember = CryptCATGetMemberInfo(hCat, memberTag.data());
        if (pMember) {
            // Success! Clear the error code and let's go home
            err = 0;
            break;
        }
    }

cleanup:
    if (pbHash) LocalFree(pbHash);
    if (hCat) CryptCATClose(hCat);
    if (hCatAdmin) CryptCATAdminReleaseContext(hCatAdmin, 0);
    if (hWintrust) FreeLibrary(hWintrust);
    if (hFile != INVALID_HANDLE_VALUE) CloseHandle(hFile);
    return err;
error:
    err = GetLastError();
    goto cleanup;
}


static DWORD extract_certs(
    const wchar_t *signed_path,
    PCCERT_CONTEXT &leaf_out,
    PCCERT_CONTEXT &root_out
) {
    leaf_out = NULL;
    root_out = NULL;

    HCERTSTORE hStore = NULL;
    HCRYPTMSG hMsg = NULL;
    PCCERT_CONTEXT pLeaf = NULL;
    PCCERT_CONTEXT pRoot = NULL;
    PCCERT_CONTEXT pRootCtx = NULL;
    PCERT_SIMPLE_CHAIN pSimple = NULL;
    PCCERT_CHAIN_CONTEXT pChain = NULL;

    PCMSG_SIGNER_INFO pSignerInfo = NULL;
    DWORD cbSignerInfo = 0;

    DWORD dwEncoding = 0, dwContentType = 0, dwFormatType = 0;
    DWORD err = 0;

    if (!CryptQueryObject(
            CERT_QUERY_OBJECT_FILE,
            signed_path,
            CERT_QUERY_CONTENT_FLAG_PKCS7_SIGNED_EMBED,
            CERT_QUERY_FORMAT_FLAG_BINARY,
            0,
            &dwEncoding, &dwContentType, &dwFormatType,
            &hStore, &hMsg, NULL
        )) {
        err = GetLastError();
        if (!err) {
            err = ERROR_INVALID_DATA;
        }
        goto cleanup;
    }

    if (!CryptMsgGetParam(hMsg, CMSG_SIGNER_INFO_PARAM, 0, NULL, &cbSignerInfo) || !cbSignerInfo) {
        err = GetLastError();
        if (!err) err = ERROR_INVALID_DATA;
        goto cleanup;
    }

    pSignerInfo = (PCMSG_SIGNER_INFO)LocalAlloc(LPTR, cbSignerInfo);
    if (!pSignerInfo) {
        err = ERROR_OUTOFMEMORY;
        goto cleanup;
    }

    if (!CryptMsgGetParam(hMsg, CMSG_SIGNER_INFO_PARAM, 0, pSignerInfo, &cbSignerInfo)) {
        err = GetLastError();
        LocalFree(pSignerInfo);
        if (!err) err = ERROR_INVALID_DATA;
        goto cleanup;
    }

    CERT_INFO ci;
    memset(&ci, 0, sizeof(ci));
    ci.Issuer = pSignerInfo->Issuer;
    ci.SerialNumber = pSignerInfo->SerialNumber;

    pLeaf = CertFindCertificateInStore(
        hStore,
        X509_ASN_ENCODING | PKCS_7_ASN_ENCODING,
        0,
        CERT_FIND_SUBJECT_CERT,
        &ci,
        NULL
    );

    LocalFree(pSignerInfo);

    if (!pLeaf) {
        err = GetLastError();
        if (!err) err = ERROR_INVALID_DATA;
        goto cleanup;
    }

    CERT_CHAIN_PARA chainPara;
    memset(&chainPara, 0, sizeof(chainPara));
    chainPara.cbSize = sizeof(chainPara);

    if (!CertGetCertificateChain(
            NULL,
            pLeaf,
            NULL,
            pLeaf->hCertStore,
            &chainPara,
            0,
            NULL,
            &pChain
        ) || !pChain || pChain->cChain == 0) {
        err = GetLastError();
        if (!err) err = ERROR_INVALID_DATA;
        goto cleanup;
    }

    pSimple = pChain->rgpChain[0];
    if (!pSimple || pSimple->cElement == 0) {
        err = ERROR_INVALID_DATA;
        goto cleanup;
    }

    pRootCtx = pSimple->rgpElement[pSimple->cElement - 1]->pCertContext;
    if (!pRootCtx) {
        err = ERROR_INVALID_DATA;
        goto cleanup;
    }

    pRoot = CertDuplicateCertificateContext(pRootCtx);
    if (!pRoot) {
        err = ERROR_OUTOFMEMORY;
        goto cleanup;
    }

    leaf_out = pLeaf;
    root_out = pRoot;
    pLeaf = NULL; // transferred
    pRoot = NULL; // transferred

cleanup:
    if (pChain) CertFreeCertificateChain(pChain);
    if (pRoot) CertFreeCertificateContext(pRoot);
    if (pLeaf) CertFreeCertificateContext(pLeaf);
    if (hMsg) CryptMsgClose(hMsg);
    if (hStore) CertCloseStore(hStore, 0);

    // Ensure outputs are NULL on failure
    if (err != 0) {
        if (leaf_out) { CertFreeCertificateContext(leaf_out); leaf_out = NULL; }
        if (root_out) { CertFreeCertificateContext(root_out); root_out = NULL; }
    }

    return err;
}

PyObject *verify_trust(PyObject *, PyObject *args, PyObject *kwargs) {
    static const char * keywords[] = {"path", "cat_path", "root_subject", "leaf_subject", "leaf_eku", NULL};
    wchar_t *path = NULL;
    wchar_t *cat_path = NULL;
    wchar_t *root_subject = NULL;
    wchar_t *leaf_subject = NULL;
    wchar_t *leaf_eku = NULL;
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O&O&O&O&O&:verify_trust", keywords,
        as_utf16, &path, as_utf16, &cat_path,
        as_utf16, &root_subject, as_utf16, &leaf_subject, as_utf16, &leaf_eku
    )) {
        return NULL;
    }

    PyObject *r = Py_NewRef(Py_None);
    PCCERT_CONTEXT pLeafCert = NULL;
    PCCERT_CONTEXT pRootCert = NULL;
    DWORD err = 0;

    // 1) Validate catalog file signature.
    {
        GUID policy = WINTRUST_ACTION_GENERIC_VERIFY_V2;

        WINTRUST_FILE_INFO fi;
        memset(&fi, 0, sizeof(fi));
        fi.cbStruct = sizeof(fi);
        fi.pcwszFilePath = cat_path;
        fi.hFile = NULL;

        WINTRUST_DATA wd;
        memset(&wd, 0, sizeof(wd));
        wd.cbStruct = sizeof(wd);
        wd.dwUnionChoice = WTD_CHOICE_FILE;
        wd.pFile = &fi;
        wd.dwUIChoice = WTD_UI_NONE;

        // Do a real validation pass (including revocation).
        wd.fdwRevocationChecks = WTD_REVOKE_WHOLECHAIN;
        wd.dwStateAction = WTD_STATEACTION_VERIFY;

        wd.dwUIChoice = WTD_UI_NONE;
        wd.dwProvFlags = WTD_USE_DEFAULT_OSVER_CHECK;

        LONG st = WinVerifyTrust(NULL, &policy, &wd);

        wd.dwStateAction = WTD_STATEACTION_CLOSE;
        (void)WinVerifyTrust(NULL, &policy, &wd);

        if (st != ERROR_SUCCESS) {
            PyErr_Format(PyExc_OSError, "WinVerifyTrust failed for catalog: 0x%08lX", (unsigned long)st);
            Py_CLEAR(r);
            goto done;
        }
    }

    // 2) Extract signer leaf and chain root certs from the signed catalog
    err = extract_certs(cat_path, pLeafCert, pRootCert);
    if (err) {
        PyErr_SetString(PyExc_OSError, "Failed to extract certificates from catalog signature");
        Py_CLEAR(r);
        goto done;
    }

    // 3) Optional subject checks
    if (!cert_subject_matches(pRootCert, root_subject)) {
        PyErr_SetString(PyExc_OSError, "Catalog root certificate subject mismatch");
        Py_CLEAR(r);
        goto done;
    }
    if (!cert_subject_matches(pLeafCert, leaf_subject)) {
        PyErr_SetString(PyExc_OSError, "Catalog leaf certificate subject mismatch");
        Py_CLEAR(r);
        goto done;
    }

    // 4) Optional EKU check (strict: if specified, must be explicitly present; otherwise skip entirely)
    if (!cert_has_explicit_eku(pLeafCert, leaf_eku)) {
        PyErr_SetString(PyExc_OSError, "Leaf certificate does not explicitly include required EKU");
        Py_CLEAR(r);
        goto done;
    }

    // 5) Ensure the target file’s catalog hash is present in the provided catalog file.
    err = file_hash_in_catalog(path, cat_path);
    if (err) {
        PyErr_SetString(PyExc_OSError, "File hash not present in the specified catalog");
        Py_CLEAR(r);
        goto done;
    }


done:
    if (pRootCert) CertFreeCertificateContext(pRootCert);
    if (pLeafCert) CertFreeCertificateContext(pLeafCert);
    PyMem_Free(path);
    PyMem_Free(cat_path);
    PyMem_Free(root_subject);
    PyMem_Free(leaf_subject);
    PyMem_Free(leaf_eku);

    return r;
}
