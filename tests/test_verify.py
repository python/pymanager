import pytest
import shutil
from pathlib import Path

from manage.urlutils import IndexDownloader
from manage.exceptions import InvalidFeedError
from _native import verify_trust

TESTDATA = Path(__file__).absolute().parent / "data"
INDEX_NAMES = ["index-windows.json", "index-windows-recent.json", "index-windows-legacy.json"]
TEST_INDEX = str(TESTDATA / INDEX_NAMES[0])
TEST_INDEX_URI = (TESTDATA / INDEX_NAMES[0]).as_uri()
TEST_CAT = str(TESTDATA / "psf-signed.cat")
UNTRUSTED_CAT = str(TESTDATA / "self-signed.cat")

AZURE_SIGN_SUBJECT = "CN=Microsoft Identity Verification Root Certificate Authority 2020, O=Microsoft Corporation, C=US"
PSF_SIGN_SUBJECT = "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US"
PSF_SIGN_EKU = "1.3.6.1.4.1.311.97.608394634.79987812.305991749.578777327"


def test_verify_all_fields():
    verify_trust(TEST_INDEX, TEST_CAT, AZURE_SIGN_SUBJECT, PSF_SIGN_SUBJECT, PSF_SIGN_EKU)

def test_verify_leaf():
    verify_trust(TEST_INDEX, TEST_CAT, None, PSF_SIGN_SUBJECT, None)

def test_verify_partial_leaf():
    verify_trust(TEST_INDEX, TEST_CAT, None, "CN=Python Software Foundation", None)
    verify_trust(TEST_INDEX, TEST_CAT, None, "C=US", None)
    subj = ",".join(sorted(PSF_SIGN_SUBJECT.split(","), reverse=True))
    verify_trust(TEST_INDEX, TEST_CAT, None, subj, None)

def test_verify_eku():
    verify_trust(TEST_INDEX, TEST_CAT, None, None, PSF_SIGN_EKU)

def test_verify_root():
    verify_trust(TEST_INDEX, TEST_CAT, AZURE_SIGN_SUBJECT, None, None)

def test_verify_os_only():
    verify_trust(TEST_INDEX, TEST_CAT, None, None, None)


def test_verify_invalid_leaf():
    with pytest.raises(OSError):
        verify_trust(TEST_INDEX, TEST_CAT, None, "CN=King Arthur", None)

def test_verify_invalid_eku():
    with pytest.raises(OSError):
        verify_trust(TEST_INDEX, TEST_CAT, None, None, "1.2.3.4.5")

def test_verify_invalid_root():
    with pytest.raises(OSError):
        verify_trust(TEST_INDEX, TEST_CAT, "CN=King Arthur", None, None)

def test_verify_unknown_cert():
    with pytest.raises(OSError):
        verify_trust(TEST_INDEX, UNTRUSTED_CAT, None, None, None)

def test_verify_tampered_file(tmp_path):
    p = tmp_path / "test_file.json"
    p.write_text("This is not the expected contents")
    with pytest.raises(OSError):
        verify_trust(str(p), TEST_CAT, None, None, None)


class MockConfig:
    REQUIRE_FULL = dict(
        requires_signature=True,
        required_root_subject=AZURE_SIGN_SUBJECT,
        required_publisher_subject=PSF_SIGN_SUBJECT,
        required_publisher_eku=PSF_SIGN_EKU,
    )
    REQUIRE_ROOT = dict(
        requires_signature=True,
        required_root_subject=AZURE_SIGN_SUBJECT,
    )
    REQUIRE_LEAF = dict(
        requires_signature=True,
        required_publisher_subject=PSF_SIGN_SUBJECT,
        required_publisher_eku=PSF_SIGN_EKU,
    )
    REQUIRE_VALID = dict(
        requires_signature=True,
    )
    REQUIRE_FULL_WRONG = dict(
        requires_signature=True,
        required_root_subject="C=Camelot",
        required_publisher_subject="CN=King Arthur, O=Knights of the Round Table, C=Camelot",
        required_publisher_eku="1.2.3.4.5",
    )
    REQUIRE_ROOT_WRONG = dict(
        requires_signature=True,
        required_root_subject="CN=King Arthur, O=Knights of the Round Table, C=Camelot",
    )
    REQUIRE_LEAF_WRONG = dict(
        requires_signature=True,
        required_publisher_subject="CN=King Arthur, O=Knights of the Round Table, C=Camelot",
        required_publisher_eku="1.2.3.4.5",
    )
    NOT_REQUIRED = dict(
        requires_signature=False,
        required_root_subject=AZURE_SIGN_SUBJECT,
        required_publisher_subject=PSF_SIGN_SUBJECT,
        required_publisher_eku=PSF_SIGN_EKU,
    )

    def __init__(self):
        self.asked = []
        self.response = True
        self.source_settings = {}

    def ask_ny(self, question):
        self.asked.append(question)
        return self.response


class MockIndex:
    def __init__(self, url, data):
        self.url = url
        self.data = data


@pytest.mark.parametrize("verify_with", [
    pytest.param(MockConfig.REQUIRE_FULL, id="full"),
    pytest.param(MockConfig.REQUIRE_ROOT, id="root"),
    pytest.param(MockConfig.REQUIRE_LEAF, id="publisher"),
    pytest.param(MockConfig.REQUIRE_VALID, id="only-valid"),
    pytest.param(MockConfig.NOT_REQUIRED, id="unchecked"),
])
def test_verify_index_ok(verify_with, tmp_path, assert_log):
    # All settings result in successful match
    cmd = MockConfig()
    for src, dest in [(TESTDATA / n, tmp_path / n) for n in INDEX_NAMES]:
        shutil.copy2(src, dest)
        shutil.copy2(TEST_CAT, dest.with_suffix(".json.cat"))
        cmd.source_settings[dest.as_uri()] = verify_with

    idx = IndexDownloader(cmd, (tmp_path / INDEX_NAMES[0]).as_uri(), MockIndex)
    indexes = list(idx)
    assert [Path(i.url).name for i in indexes] == INDEX_NAMES


@pytest.mark.parametrize("verify_with", [
    pytest.param(MockConfig.REQUIRE_FULL_WRONG, id="full"),
    pytest.param(MockConfig.REQUIRE_ROOT_WRONG, id="root"),
    pytest.param(MockConfig.REQUIRE_LEAF_WRONG, id="publisher"),
])
def test_verify_index_wrong(verify_with, tmp_path, assert_log):
    # Certs exist and verify, but don't match required settings
    cmd = MockConfig()
    for src, dest in [(TESTDATA / n, tmp_path / n) for n in INDEX_NAMES]:
        shutil.copy2(src, dest)
        shutil.copy2(TEST_CAT, dest.with_suffix(".json.cat"))
        cmd.source_settings[dest.as_uri()] = verify_with

    idx = IndexDownloader(cmd, (tmp_path / INDEX_NAMES[0]).as_uri(), MockIndex)
    with pytest.raises(InvalidFeedError):
        indexes = list(idx)
    assert_log(
        "Fetching.+",
        "The signature for %s could not be verified.",
    )


@pytest.mark.parametrize("verify_with, expect_fail", [
    pytest.param(MockConfig.REQUIRE_FULL, True, id="full"),
    pytest.param(MockConfig.REQUIRE_ROOT, True, id="root"),
    pytest.param(MockConfig.REQUIRE_LEAF, True, id="publisher"),
    pytest.param(MockConfig.REQUIRE_VALID, True, id="only-valid"),
    pytest.param(MockConfig.NOT_REQUIRED, False, id="unchecked"),
])
def test_verify_index_unsigned(verify_with, expect_fail, tmp_path, assert_log):
    # No certs exist, so mostly fail due to being required
    cmd = MockConfig()
    for src, dest in [(TESTDATA / n, tmp_path / n) for n in INDEX_NAMES]:
        shutil.copy2(src, dest)
        cmd.source_settings[dest.as_uri()] = verify_with

    idx = IndexDownloader(cmd, (tmp_path / INDEX_NAMES[0]).as_uri(), MockIndex)
    if expect_fail:
        with pytest.raises(InvalidFeedError):
            indexes = list(idx)
        assert_log(
            "Fetching.+",
            "The signature for %s could not be loaded."
        )
    else:
        indexes = list(idx)
        assert [Path(i.url).name for i in indexes] == INDEX_NAMES


@pytest.mark.parametrize("verify_with", [
    pytest.param(MockConfig.REQUIRE_FULL, id="full"),
    pytest.param(MockConfig.REQUIRE_ROOT, id="root"),
    pytest.param(MockConfig.REQUIRE_LEAF, id="publisher"),
    pytest.param(MockConfig.REQUIRE_VALID, id="only-valid"),
])
def test_verify_index_selfsigned_bypass(verify_with, tmp_path, assert_log):
    # Invalid cert, but user "responds" to continue
    cmd = MockConfig()
    cmd.response = False
    for src, dest in [(TESTDATA / n, tmp_path / n) for n in INDEX_NAMES]:
        shutil.copy2(src, dest)
        shutil.copy2(UNTRUSTED_CAT, dest.with_suffix(".json.cat"))
        cmd.source_settings[dest.as_uri()] = verify_with

    idx = IndexDownloader(cmd, (tmp_path / INDEX_NAMES[0]).as_uri(), MockIndex)
    indexes = list(idx)
    assert [Path(i.url).name for i in indexes] == INDEX_NAMES
    assert_log(
        "Fetching.+",
        "The signature for %s could not be verified.",
        "TRACEBACK",
        "Signature verification failure ignored for %s",
    )


@pytest.mark.parametrize("verify_with, expect_fail", [
    pytest.param(MockConfig.REQUIRE_FULL, True, id="full"),
    # The 'wrong' settings actually match the selfsigned cert we're testing with
    pytest.param(MockConfig.REQUIRE_ROOT, True, id="wrong-root"),
    pytest.param(MockConfig.REQUIRE_ROOT_WRONG, True, id="root"),
    pytest.param(MockConfig.REQUIRE_LEAF, True, id="wrong-publisher"),
    pytest.param(MockConfig.REQUIRE_LEAF_WRONG, True, id="publisher"),
    pytest.param(MockConfig.REQUIRE_VALID, True, id="only-valid"),
    pytest.param(MockConfig.NOT_REQUIRED, False, id="unchecked"),
])
def test_verify_index_selfsigned(verify_with, expect_fail, tmp_path, assert_log):
    # Wrong cert returned, mostly fail due to being untrusted by OS
    cmd = MockConfig()
    for src, dest in [(TESTDATA / n, tmp_path / n) for n in INDEX_NAMES]:
        shutil.copy2(src, dest)
        shutil.copy2(UNTRUSTED_CAT, dest.with_suffix(".json.cat"))
        cmd.source_settings[dest.as_uri()] = verify_with

    idx = IndexDownloader(cmd, (tmp_path / INDEX_NAMES[0]).as_uri(), MockIndex)
    if expect_fail:
        with pytest.raises(InvalidFeedError):
            indexes = list(idx)
        assert_log(
            "Fetching.+",
            "The signature for %s could not be verified."
        )
    else:
        indexes = list(idx)
        assert [Path(i.url).name for i in indexes] == INDEX_NAMES


def test_verify_index_later(assert_log):
    # Signature not required until reading the index file
    cmd = MockConfig()
    idx = IndexDownloader(cmd, (TESTDATA / "index-require-sig.json").as_uri(), MockIndex)
    with pytest.raises(InvalidFeedError):
        indexes = list(idx)
    assert_log(
        "Fetching.+",
        "The signature for %s could not be loaded.",
    )


def test_verify_index_not_later(assert_log):
    # Signature not required until reading the index file
    cmd = MockConfig()
    idx = IndexDownloader(cmd, (TESTDATA / "index-require-no-sig.json").as_uri(), MockIndex)
    indexes = list(idx)
    assert_log(
        "Fetching.+",
        "No signature to verify for %s",
    )
