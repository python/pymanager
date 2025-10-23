# Python Install Manager

[![Codecov](https://codecov.io/gh/python/pymanager/graph/badge.svg)](https://codecov.io/gh/python/pymanager)

This is the source code for the Python Install Manager app.

For information about how to use the Python install manager,
including troubleshooting steps,
please refer to the documentation at
[docs.python.org/using/windows](https://docs.python.org/3.14/using/windows.html).

The original PEP leading to this tool was
[PEP 773](https://peps.python.org/pep-0773/).


# Build

To build and run locally requires [`pymsbuild`](https://pypi.org/project/pymsbuild)
and a Visual Studio installation that includes the C/C++ compilers.

```
> python -m pip install pymsbuild
> python -m pymsbuild
> python-manager\py.exe ...
```

Any modification to a source file requires rebuilding.
The `.py` files are packaged into an extension module.
However, see the following section on tests, as test runs do not require a full
build.

For additional output, set `%PYMANAGER_DEBUG%` to force debug-level output.
This is the equivalent of passing `-vv`, though it also works for contexts that
do not accept options (such as launching a runtime).

# Tests

To run the test suite locally:

```
> python -m pip install pymsbuild pytest
> python -m pymsbuild -c _msbuild_test.py
> python -m pytest
```

This builds the native components separately so that you can quickly iterate on
the Python code. Any updates to the C++ files will require running the
``pymsbuild`` step again.

# Package

To produce an (almost) installer app package:

```
> python -m pip install pymsbuild
> python make-all.py
```

This will rebuild the project and produce MSIX, APPXSYM and MSI packages.

You will need to sign the MSIX package before you can install it. This can be a
self-signed certificate, but it must be added to your Trusted Publishers.
Alternatively, rename the file to ``.zip`` and extract it to a directory, and
run ``Add-AppxPackage -Register <path to dir>\appxmanifest.xml`` to do a
development install. This should add the global aliases and allow you to test
as if it was properly installed.

# Contributions

Contributions are welcome under all the same conditions as for CPython, see
the [Python Developer's Guide](https://devguide.python.org/) for more information.

# Release Schedule

As this project is currently considered to be in prerelease stage,
the release schedule is "as needed".

The release manager for the Python Install Manager on Windows is whoever is the
build manager for Windows for CPython.

## Versioning

PyManager uses the two digit year as the first part of the version,
with the second part incrementing for each release.
This is to avoid any sense of features being tied to the version number,
and to avoid any direct association with Python releases.

The two digit year is used because MSI does not support major version fields
over 256. If/when we completely drop the MSI, we could switch to four digit
years, but as long as it exists we have to handle its compatibility constraints.


# Copyright and License Information

Copyright © 2025 Python Software Foundation.  All rights reserved.

See the [LICENSE](https://github.com/python/pymanager/blob/main/LICENSE) for
information on the terms & conditions for usage, and a DISCLAIMER OF ALL
WARRANTIES.

All trademarks referenced herein are property of their respective holders.
