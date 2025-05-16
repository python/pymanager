"""Simple script to allow running manage/firstrun.py without rebuilding.

You'll need to build the test module (_msbuild_test.py).
"""

import os
import pathlib
import sys


ROOT = pathlib.Path(__file__).absolute().parent.parent / "src"
sys.path.append(str(ROOT))


import _native
if not hasattr(_native, "coinitialize"):
    import _native_test
    for k in dir(_native_test):
        if k[:1] not in ("", "_"):
            setattr(_native, k, getattr(_native_test, k))


import manage.commands
cmd = manage.commands.FirstRun([], ROOT)
sys.exit(cmd.execute() or 0)
