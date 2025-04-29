# Build script for test module. This is needed to run tests in-tree.
#
#  python -m pymsbuild -c _msbuild_test.py
#  python -m pytest
#
from pymsbuild import *
from pymsbuild.dllpack import *

METADATA = {
    "Metadata-Version": "2.2",
    "Name": "manage",
    "Version": "1.0.0.0",
    "Author": "Steve Dower",
    "Author-email": "steve.dower@python.org",
    "Summary": "Test build",
}


PACKAGE = Package('src',
    DllPackage('_native_test',
        PyFile('__init__.py'),
        ItemDefinition("ClCompile",
            PreprocessorDefinitions=Prepend("ERROR_LOCATIONS=1;BITS_INJECT_ERROR=1;"),
            LanguageStandard="stdcpp20",
        ),
        IncludeFile('*.h'),
        CSourceFile('*.cpp'),
        CFunction('coinitialize'),
        CFunction('bits_connect'),
        CFunction('bits_begin'),
        CFunction('bits_cancel'),
        CFunction('bits_get_progress'),
        CFunction('bits_retry_with_auth'),
        CFunction('bits_find_job'),
        CFunction('bits_serialize_job'),
        CFunction('bits_inject_error'), # only in tests
        CFunction('winhttp_urlopen'),
        CFunction('winhttp_isconnected'),
        CFunction('winhttp_urlsplit'),
        CFunction('winhttp_urlunsplit'),
        CFunction('file_url_to_path'),
        CFunction('file_lock_for_delete'),
        CFunction('file_unlock_for_delete'),
        CFunction('file_locked_delete'),
        CFunction('package_get_root'),
        CFunction('shortcut_create'),
        CFunction('shortcut_get_start_programs'),
        CFunction('hide_file'),
        CFunction('fd_supports_vt100'),
        CFunction('date_as_str'),
        CFunction('datetime_as_str'),
        CFunction('reg_rename_key'),
        source='src/_native',
    ),
)
