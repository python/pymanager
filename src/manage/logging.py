import os
import sys

# For convenient changing in the future. With a bit of luck, we will always
# depend on this constant dynamically, and so could update it at runtime, but
# don't assume that if you're adding that feature!
# Note that this only applies to deliberate formatting tasks. In general, we
# write entire lines of text unwrapped and let the console handle it, but some
# tasks (e.g. progress bars, tables) need to know the width.
CONSOLE_MAX_WIDTH = 80


DEBUG = 10
VERBOSE = 15
INFO = 20
WARN = 30
ERROR = 40


COLOURS = {
    "!W!": "\033[0m",
    "!R!": "\033[31m",
    "!G!": "\033[32m",
    "!B!": "\033[36m",
    "!Y!": "\033[33m",
}


CONSOLE_PREFIX = {
    DEBUG: "!B!# {}!W!",
    VERBOSE: "!G!{}!W!",
    WARN: "!Y![WARNING] {}!W!",
    ERROR: "!R![ERROR] {}!W!",
}


FILE_PREFIX = {
    VERBOSE: ">> {}",
    INFO: ">  {}",
    WARN: "!  {}",
    ERROR: "!! {}",
}


def strip_colour(msg):
    for k in COLOURS:
        msg = msg.replace(k, "")
    return msg


def _len_without_codes(s, codes_subbed=False):
    n = len(s)
    for k, v in COLOURS.items():
        if not codes_subbed:
            n -= len(k) * s.count(k)
        n -= len(v) * s.count(v)
    return n


def wrap_and_indent(s, indent=0, width=None, hang="", codes_subbed=False):
    if width is None:
        width = CONSOLE_MAX_WIDTH
    
    bits = [" " * indent]
    if hang:
        cchw = _len_without_codes(hang, codes_subbed=codes_subbed)
        if cchw <= indent - 1:
            bits = [hang + " " * (indent - cchw)]
        else:
            yield hang
    cch = indent
    for w in s.split(" "):
        cchw = _len_without_codes(w, codes_subbed=codes_subbed)
        if len(bits) > 1 and cch + cchw > width:
            yield "".join(bits).rstrip()
            bits = [" " * indent]
            cch = indent
        bits.append(w)
        bits.append(" ")
        cch += cchw + 1
    if bits:
        yield "".join(bits).rstrip()


def supports_colour(stream):
    if os.getenv("PYTHON_COLORS", "").lower() in ("0", "no", "false"):
        return False
    try:
        stream = stream.buffer
    except AttributeError:
        pass
    try:
        stream = stream.raw
    except AttributeError:
        pass
    if type(stream).__name__ != "_WindowsConsoleIO":
        return False
    try:
        # Lazy import to allow us to import logging on its own
        from _native import fd_supports_vt100
        return fd_supports_vt100(stream.fileno())
    except Exception:
        if os.getenv("PYMANAGER_DEBUG"):
            raise
    return False


class Logger:
    def __init__(self, level=None, console=sys.stderr, print_console=sys.stdout):
        if level is not None:
            self.level = level
        elif os.getenv("PYMANAGER_DEBUG"):
            self.level = DEBUG
        elif os.getenv("PYMANAGER_VERBOSE"):
            self.level = VERBOSE
        else:
            self.level = INFO
        self.console = console
        self.console_colour = supports_colour(self.console)
        self.print_console = print_console
        self.print_console_colour = supports_colour(self.print_console)
        self.file = None
        self._list = None

    def set_level(self, level):
        self.level = level

    def reduce_level(self, new_level):
        if new_level is not None and new_level < self.level:
            self.level = new_level
        return self.level

    def debug(self, msg, *args, **kwargs):
        self.log(DEBUG, msg, *args, **kwargs)

    def verbose(self, msg, *args, **kwargs):
        self.log(VERBOSE, msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.log(INFO, msg, *args, **kwargs)

    def warn(self, msg, *args, **kwargs):
        self.log(WARN, msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.log(ERROR, msg, *args, **kwargs)

    def would_log_to_console(self, level):
        return level >= self.level

    def would_log(self, level):
        return (level >= self.level) or self.file

    def log(self, level, msg, *args, exc_info=False):
        if self._list is not None:
            self._list.append((msg, args))
        if not ((level >= self.level) or self.file is not None):
            return
        
        msg = msg % args
        if level >= self.level:
            try:
                cm = CONSOLE_PREFIX[level].replace("{}", msg)
            except LookupError:
                cm = msg
            if self.console_colour:
                for k in COLOURS:
                    cm = cm.replace(k, COLOURS[k])
            else:
                for k in COLOURS:
                    cm = cm.replace(k, "")
            print(cm, file=self.console)
        if self.file is not None:
            try:
                fm = FILE_PREFIX[level].replace("{}", msg)
            except LookupError:
                fm = msg
            for k in COLOURS:
                fm = fm.replace(k, "")
            print(fm, file=self.file)
        if exc_info:
            import traceback
            exc = traceback.format_exc()
            if level >= self.level:
                if self.console_colour:
                    print(COLOURS["!B!"], exc, COLOURS["!W!"], sep="", file=self.console)
                else:
                    print(exc, file=self.console)
            if self.file is not None:
                print(exc, file=self.file)

    def would_print(self, *args, always=False, level=INFO, **kwargs):
        if always:
            return True
        if level < self.level:
            return False
        return True

    def print(self, msg=None, *args, always=False, level=INFO, colours=True, wrap=False, **kwargs):
        if self._list is not None:
            if args:
                self._list.append(((msg or "") % args, ()))
            else:
                self._list.append((msg or "", ()))
        if not always and level < self.level:
            return
        if msg:
            if not colours:
                # Don't unescape or replace anything
                pass
            elif self.print_console_colour:
                for k in COLOURS:
                    msg = msg.replace(k, COLOURS[k])
            else:
                for k in COLOURS:
                    msg = msg.replace(k, "")
            if args:
                msg = msg % args
        elif args:
            msg = str(args[0])
        else:
            msg = ""
        if wrap:
            for s in wrap_and_indent(msg, codes_subbed=True):
                print(s, **kwargs, file=self.print_console)
        else:
            print(msg, **kwargs, file=self.print_console)

    def print_raw(self, *msg, **kwargs):
        kwargs["always"] = True
        kwargs["colours"] = False
        sep = kwargs.pop("sep", " ")
        return self.print(sep.join(str(s) for s in msg), **kwargs)


LOGGER = Logger()


class ProgressPrinter:
    def __init__(self, operation, maxwidth=...):
        self.operation = operation or "Progress"
        if maxwidth is ...:
            maxwidth = CONSOLE_MAX_WIDTH
        self.width = maxwidth - 3 - len(self.operation)
        self._dots_shown = 0
        self._started = False
        self._complete = False
        self._need_newline = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        if self._need_newline:
            if self._complete:
                LOGGER.print()
            else:
                try:
                    LOGGER.print("❌")
                except UnicodeEncodeError:
                    LOGGER.print("x")

    def __call__(self, progress):
        if self._complete:
            return

        if progress is None:
            if self._need_newline:
                if not self._complete:
                    try:
                        LOGGER.print("⏸️")
                    except UnicodeEncodeError:
                        LOGGER.print("|")
                    self._dots_shown = 0
                    self._started = False
                    self._need_newline = False
            return

        if not self._started:
            LOGGER.print("%s: ", self.operation, end="", flush=True)
            self._started = True
            self._need_newline = True

        dot_count = min(self.width, progress * self.width // 100) - self._dots_shown
        if dot_count <= 0:
            return

        self._dots_shown += dot_count
        LOGGER.print(None, "." * dot_count, end="", flush=True)
        self._need_newline = True
        if progress >= 100:
            try:
                LOGGER.print("✅", flush=True)
            except UnicodeEncodeError:
                LOGGER.print(".", flush=True)
            self._complete = True
            self._need_newline = False
