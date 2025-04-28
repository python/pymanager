
class ArgumentError(Exception):
    def __init__(self, message):
        super().__init__(message)


class HashMismatchError(Exception):
    def __init__(self, message=None):
        super().__init__(message or
            "The downloaded file could not be verified and has been deleted. Please try again.")


class NoInstallsError(Exception):
    def __init__(self):
        super().__init__("""No runtimes are installed. Try running "py install default" first.""")


class NoInstallFoundError(Exception):
    def __init__(self, tag=None, script=None):
        self.tag = tag
        self.script = script
        if script:
            msg = f"No runtime installed that can launch {script}"
        elif tag:
            msg = f"""No runtime installed that matches {tag}. Try running "py install {tag}"."""
        else:
            msg = """No suitable runtime installed. Try running "py install default"."""
        super().__init__(msg)


class InvalidFeedError(Exception):
    def __init__(self, message=None, *, feed_url=None):
        from .urlutils import sanitise_url
        if feed_url:
            feed_url = sanitise_url(feed_url)
        if not message:
            if feed_url:
                message = f"There is an issue with the feed at {feed_url}. Please check your settings and try again."
            else:
                message = "There is an issue with the feed. Please check your settings and try again."
        super().__init__(message)
        self.feed_url = feed_url


class InvalidInstallError(Exception):
    def __init__(self, message, prefix=None):
        super().__init__(message)
        self.prefix = prefix


class InvalidConfigurationError(ValueError):
    def __init__(self, file=None, argument=None, value=None):
        if value:
            msg = f"Invalid configuration value {value!r} for key {argument} in {file}"
        elif argument:
            msg = f"Invalid configuration key {argument} in {file}"
        elif file:
            msg = f"Invalid configuration file {file}"
        else:
            msg = "Invalid configuration"
        super().__init__(msg)
        self.file = file
        self.argument = argument
        self.value = value


class AutomaticInstallDisabledError(Exception):
    exitcode = 0xA0000006 # ERROR_AUTO_INSTALL_DISABLED

    def __init__(self):
        super().__init__("Automatic installation has been disabled. "
                         'Please run "py install" directly.')


class FilesInUseError(Exception):
    def __init__(self, files):
        self.files = files
