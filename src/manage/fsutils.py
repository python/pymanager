import os
import time

from .exceptions import FilesInUseError
from .logging import LOGGER
from .pathutils import Path


def ensure_tree(path, overwrite_files=True):
    if isinstance(path, (str, bytes)):
        path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        if not overwrite_files:
            raise
        for p in path.parents:
            if p.is_file():
                unlink(p)
                break
        path.parent.mkdir(parents=True, exist_ok=True)


def _rglob(root):
    q = [root]
    while q:
        r = q.pop(0)
        for f in os.scandir(r):
            p = r / f.name
            if f.is_dir():
                q.append(p)
                yield p, None
            else:
                yield None, p


def rglob(root, files=True, dirs=True):
    for d, f in _rglob(root):
        if d and dirs:
            yield d
        if f and files:
            yield f


def _unlink(f, on_missing=None, on_fail=None, on_isdir=None):
    try:
        f.unlink()
    except FileNotFoundError:
        if on_missing:
            on_missing(f)
        else:
            pass
    except PermissionError:
        if f.is_dir():
            if on_isdir:
                on_isdir(f)
            elif on_fail:
                on_fail(f)
            else:
                raise IsADirectoryError() from None
    except OSError:
        if on_fail:
            on_fail(f)
        else:
            raise


def _rmdir(d, on_missing=None, on_fail=None, on_isfile=None):
    try:
        d.rmdir()
    except FileNotFoundError:
        if on_missing:
            on_missing(d)
        else:
            pass
    except NotADirectoryError:
        if on_isfile:
            on_isfile(d)
        elif on_fail:
            on_fail(d)
        else:
            raise
    except OSError:
        if on_fail:
            on_fail(d)
        else:
            raise


def rmtree(path, after_5s_warning=None, remove_ext_first=()):
    start = time.monotonic()

    if isinstance(path, (str, bytes)):
        path = Path(path)
    if not path.is_dir():
        if path.is_file():
            unlink(path)
        return

    if remove_ext_first:
        exts = {e.strip(" .").casefold() for e in remove_ext_first}
        files = [f.path for f in os.scandir(path)
                 if f.is_file() and f.name.rpartition(".")[2].casefold() in exts]
        if files:
            LOGGER.debug("Atomically removing these files first: %s",
                         ", ".join(Path(f).name for f in files))
            try:
                atomic_unlink(files)
            except FilesInUseError as ex:
                LOGGER.debug("No files removed because these are in use: %s",
                             ", ".join(Path(f).name for f in ex.files))
                raise
            else:
                LOGGER.debug("Files successfully removed")

    for i in range(1000):
        if after_5s_warning and (time.monotonic() - start) > 5:
            LOGGER.warn(after_5s_warning)
            after_5s_warning = None
        new_path = path.with_name(f"{path.name}.{i}.deleteme")
        if new_path.exists():
            continue
        try:
            path = path.rename(new_path)
            break
        except OSError as ex:
            LOGGER.debug("Failed to rename to %s: %s", new_path, ex)
            time.sleep(0.01)
    else:
        raise FileExistsError(str(path))

    to_rmdir = [path]
    to_unlink = []
    for d, f in _rglob(path):
        if after_5s_warning and (time.monotonic() - start) > 5:
            LOGGER.warn(after_5s_warning)
            after_5s_warning = None

        if d:
            to_rmdir.append(d)
        else:
            _unlink(f, on_fail=to_unlink.append, on_isdir=to_rmdir.append)

    to_warn = []
    retries = 0
    while retries < 3 and (to_rmdir or to_unlink):
        retries += 1
        for f in to_unlink:
            _unlink(f, on_fail=to_warn.append, on_isdir=to_rmdir.append)
        to_unlink.clear()

        for d in sorted(to_rmdir, key=lambda p: len(p.parts), reverse=True):
            _rmdir(d, on_fail=to_warn.append, on_isfile=to_unlink)

    if to_warn:
        try:
            f = os.path.commonpath(to_warn)
        except ValueError:
            f = None
        if f:
            LOGGER.warn("Failed to remove %s", f)
        else:
            for f in to_warn:
                LOGGER.warn("Failed to remove %s", f)


def unlink(path, after_5s_warning=None):
    start = time.monotonic()

    if isinstance(path, (str, bytes)):
        path = Path(path)
    try:
        path.unlink()
        return
    except FileNotFoundError:
        return
    except PermissionError:
        if path.is_dir():
            raise IsADirectoryError() from None
    except OSError:
        pass

    orig_path = path
    for i in range(1000):
        if after_5s_warning and (time.monotonic() - start) > 5:
            LOGGER.warn(after_5s_warning)
            after_5s_warning = None

        try:
            path = path.rename(path.with_name(f"{path.name}.{i}.deleteme"))
            
            try:
                path.unlink()
            except OSError:
                pass
            break
        except OSError:
            time.sleep(0.01)
    else:
        LOGGER.warn("Failed to remove %s", orig_path)
        return


def atomic_unlink(paths):
    "Removes all of 'paths' or none, raising if an error occurs."
    from _native import file_lock_for_delete, file_unlock_for_delete, file_locked_delete
    
    handles = []
    files_in_use = []
    try:
        for p in map(str, paths):
            try:
                handles.append((p, file_lock_for_delete(p)))
            except FileNotFoundError:
                pass
            except PermissionError:
                files_in_use.append(p)

        if files_in_use:
            raise FilesInUseError(files_in_use)

        handles.reverse()
        while handles:
            p, h = handles.pop()
            try:
                file_locked_delete(h)
            except FileNotFoundError:
                pass
            except PermissionError:
                files_in_use.append(p)

        if files_in_use:
            raise FilesInUseError(files_in_use)
    finally:
        while handles:
            p, h = handles.pop()
            file_unlock_for_delete(h)
