"""Library logging setup for cldc.

The library attaches a `NullHandler` to the root `cldc` logger so importing
cldc never prints anything by default. The CLI calls `configure_cli_logging`
to attach a stderr handler with a level derived from --verbose / --quiet.
"""

from __future__ import annotations

import logging

_ROOT_LOGGER_NAME = "cldc"
_CLI_HANDLER_NAME = "cldc.cli"

# Attach a NullHandler exactly once at import so the library is silent by default.
logging.getLogger(_ROOT_LOGGER_NAME).addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return a logger scoped under the `cldc` hierarchy.

    Usage at module top:
        from cldc._logging import get_logger
        logger = get_logger(__name__)
    """
    if not name.startswith(_ROOT_LOGGER_NAME):
        # __name__ is always like "cldc.foo.bar", so this is defense-in-depth.
        name = f"{_ROOT_LOGGER_NAME}.{name}"
    return logging.getLogger(name)


def configure_cli_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    """Attach a stderr handler to the cldc logger tree for CLI use.

    - `verbose=True`  -> DEBUG level, formatted with timestamp + level + name
    - `quiet=True`    -> ERROR level
    - neither         -> WARNING level (default)
    - both            -> raise ValueError (caller should have enforced via argparse mutex)
    """
    if verbose and quiet:
        raise ValueError("configure_cli_logging: verbose and quiet are mutually exclusive")

    root = logging.getLogger(_ROOT_LOGGER_NAME)
    # Remove any existing cli handlers we may have added on a prior call.
    for existing in list(root.handlers):
        if getattr(existing, "name", None) == _CLI_HANDLER_NAME:
            root.removeHandler(existing)

    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.ERROR
    else:
        level = logging.WARNING

    handler = logging.StreamHandler()  # defaults to sys.stderr
    handler.set_name(_CLI_HANDLER_NAME)
    if verbose:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    handler.setLevel(level)

    root.addHandler(handler)
    root.setLevel(level)
