import json
import os
import sys
import winreg

from .exceptions import InvalidConfigurationError
from .logging import LOGGER
from .pathutils import Path


DEFAULT_CONFIG_NAME = "pymanager.json"


def config_append(x, y):
    if x is None:
        return [y]
    if isinstance(x, list):
        return [*x, y]
    return [x, y]


def config_split(x):
    import re
    return re.split("[;:|,+]", x)


def config_split_append(x, y):
    return config_append(x, config_split(y))


def config_bool(v):
    if not v:
        return False
    if isinstance(v, str):
        return v.lower().startswith(("t", "y", "1"))
    return bool(v)


def _is_valid_url(u):
    from .urlutils import is_valid_url
    return is_valid_url(u)


def load_global_config(cfg, schema):
    try:
        from _native import package_get_root
    except ImportError:
        file = Path(sys.executable).parent / DEFAULT_CONFIG_NAME
    else:
        file = Path(package_get_root()) / DEFAULT_CONFIG_NAME
    try:
        load_one_config(cfg, file, schema=schema)
    except FileNotFoundError:
        pass


def load_config(root, override_file, schema):
    cfg = {}

    load_global_config(cfg, schema=schema)

    try:
        reg_cfg = load_registry_config(cfg["registry_override_key"], schema=schema)
        merge_config(cfg, reg_cfg, schema=schema, source="registry", overwrite=True)
    except LookupError:
        reg_cfg = {}

    for source, overwrite in [
        ("base_config", True),
        ("user_config", False),
        ("additional_config", False),
    ]:
        try:
            try:
                file = reg_cfg[source]
            except LookupError:
                file = cfg[source]
        except LookupError:
            pass
        else:
            if file:
                load_one_config(cfg, file, schema=schema, overwrite=overwrite)

    if reg_cfg:
        # Apply the registry overrides one more time
        merge_config(cfg, reg_cfg, schema=schema, source="registry", overwrite=True)

    if override_file:
        load_one_config(cfg, override_file, schema=schema, overwrite=True)

    return cfg


def load_one_config(cfg, file, schema, *, overwrite=False):
    LOGGER.verbose("Loading configuration from %s", file)
    try:
        with open(file, "r", encoding="utf-8-sig") as f:
            cfg2 = json.load(f)
    except FileNotFoundError:
        LOGGER.verbose("Skipping configuration at %s because it does not exist", file)
        return
    except OSError as ex:
        LOGGER.warn("Failed to read %s: %s", file, ex)
        LOGGER.debug("TRACEBACK:", exc_info=True)
        return
    except ValueError as ex:
        LOGGER.warn("Error reading configuration from %s: %s", file, ex)
        LOGGER.debug("TRACEBACK:", exc_info=True)
        return
    cfg2["_config_files"] = file
    resolve_config(cfg2, file, Path(file).absolute().parent, schema=schema)
    merge_config(cfg, cfg2, schema=schema, source=file, overwrite=overwrite)


def load_registry_config(key_path, schema):
    hive_name, _, key_name = key_path.replace("/", "\\").partition("\\")
    hive = getattr(winreg, hive_name)
    cfg = {}
    try:
        key = winreg.OpenKey(hive, key_name)
    except FileNotFoundError:
        return cfg
    with key:
        for i in range(10000):
            try:
                name, value, vt = winreg.EnumValue(key, i)
            except OSError:
                break
            bits = name.split(".")
            subcfg = cfg
            for b in bits[:-1]:
                subcfg = subcfg.setdefault(b, {})
            subcfg[bits[-1]] = value
        else:
            LOGGER.warn("Too many registry values were read from %s. " +
                        "This is very unexpected. Please check your configuration " +
                        "or report an issue at https://github.com/python/pymanager.",
                        key_path)

    try:
        from _native import package_get_root
        root = Path(package_get_root())
    except ImportError:
        root = Path(sys.executable).parent
    resolve_config(cfg, key_path, root, schema=schema, error_unknown=True)
    return cfg


def _expand_vars(v, env):
    import re
    def _sub(m):
        v2 = env.get(m.group(1))
        if v2:
            return v2 + (m.group(2) or "")
        return ""
    v2 = re.sub(r"%(.*?)%([\\/])?", _sub, v)
    return v2


def resolve_config(cfg, source, relative_to, key_so_far="", schema=None, error_unknown=False):
    for k, v in list(cfg.items()):
        try:
            subschema = schema[k]
        except LookupError:
            if error_unknown:
                raise InvalidConfigurationError(source, key_so_far + k)
            LOGGER.verbose("Ignoring unknown configuration %s%s in %s", key_so_far, k, source)
            continue

        if isinstance(subschema, dict):
            if not isinstance(v, dict):
                raise InvalidConfigurationError(source, key_so_far + k, v)
            resolve_config(v, source, relative_to, f"{key_so_far}{k}.", subschema)
            continue

        kind, merge, *opts = subschema
        from_env = False
        if "env" in opts and isinstance(v, str):
            try:
                orig_v = v
                v = _expand_vars(v, os.environ)
                from_env = orig_v != v
            except TypeError:
                pass
            if not v:
                del cfg[k]
                continue
        try:
            v = kind(v)
        except (TypeError, ValueError):
            raise InvalidConfigurationError(source, key_so_far + k, v)
        if v and "path" in opts and not _is_valid_url(v):
            # Paths from the config file are relative to the config file.
            # Paths from the environment are relative to the current working dir
            if not from_env:
                v = relative_to / v
            else:
                v = type(relative_to)(v).absolute()
        if v and "uri" in opts:
            if hasattr(v, "as_uri"):
                v = v.as_uri()
            else:
                v = str(v)
            if not _is_valid_url(v):
                raise InvalidConfigurationError(source, key_so_far + k, v)
        cfg[k] = v


def merge_config(into_cfg, from_cfg, schema, *, source="<unknown>", overwrite=False):
    for k, v in from_cfg.items():
        try:
            into = into_cfg[k]
        except LookupError:
            LOGGER.debug("Setting config %s to %r", k, v)
            into_cfg[k] = v
            continue

        try:
            subschema = schema[k]
        except LookupError:
            # No schema information, so let's just replace
            LOGGER.warn("Unknown configuration key %s in %s", k, source)
            into_cfg[k] = v
            continue

        if isinstance(subschema, dict):
            if isinstance(into, dict) and isinstance(v, dict):
                LOGGER.debug("Recursively updating config %s", k)
                merge_config(into, v, subschema, source=source, overwrite=overwrite)
            else:
                # Source isn't recursing, so let's ignore
                # Should have been validated earlier
                LOGGER.warn("Invalid configuration key %s in %s", k, source)
            continue

        _, merge, *_ = subschema
        if not merge or overwrite:
            LOGGER.debug("Updating config %s from %r to %r", k, into, v)
            into_cfg[k] = v
        else:
            v2 = merge(into, v)
            LOGGER.debug("Updating config %s from %r to %r", k, into, v2)
            into_cfg[k] = v2
