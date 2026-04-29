# mypy: ignore-errors
"""Pure-Python greenlet stub for environments where the greenlet C extension
is unavailable (e.g. blocked by Windows Smart App Control).

This module implements the minimal greenlet interface required by SQLAlchemy's
async engine using Python threads as the cooperative-switching mechanism.

IMPORTANT: This file must be imported (or sys.modules patched) BEFORE any
SQLAlchemy module that imports greenlet.  In practice, insert
``import app.persistence._greenlet_stub  # noqa: F401`` as the very first
import in your conftest.py.
"""

from __future__ import annotations

import sys
import threading
import types


class GreenletExit(BaseException):
    pass


class greenlet:  # noqa: N801
    """Thread-based cooperative-multitasking primitive that mirrors the
    greenlet.greenlet C class interface consumed by SQLAlchemy.

    Each instance wraps a synchronous callable (``fn``).  Cooperative
    hand-off between the caller and the greenlet is implemented with a pair
    of :class:`threading.Event` objects so that the greenlet body can pause
    mid-execution and pass a value back to the awaiting coroutine, then be
    resumed with the result.
    """

    _tls: threading.local = threading.local()

    # ------------------------------------------------------------------ #
    # class-level helpers                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def _getcurrent(cls) -> greenlet:
        cur = getattr(cls._tls, "current", None)
        if cur is None:
            cur = _MainGreenlet()
            cls._tls.current = cur
        return cur

    # ------------------------------------------------------------------ #
    # instance interface                                                   #
    # ------------------------------------------------------------------ #

    def __init__(self, fn: object = None, parent: greenlet | None = None) -> None:
        self.fn = fn
        self.parent = parent if parent is not None else greenlet._getcurrent()
        self._dead = False
        self.gr_context: object = None

        # Pair of events used for cooperative switching between the async
        # caller thread and the greenlet worker thread.
        self._to_greenlet: threading.Event = threading.Event()
        self._to_caller: threading.Event = threading.Event()
        self._value_in: object = None
        self._value_out: object = None
        self._exc_in: BaseException | None = None
        self._exc_out: BaseException | None = None
        self._started: bool = False
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------ #
    # greenlet protocol                                                    #
    # ------------------------------------------------------------------ #

    @property
    def dead(self) -> bool:
        return self._dead

    def switch(self, *args: object, **kwargs: object) -> object:
        """Start (or resume) the greenlet with *args*/*kwargs*, block until
        the greenlet either finishes or calls ``parent.switch(value)``.
        """
        value: object = (args, kwargs) if kwargs else args

        if not self._started:
            self._started = True
            self._value_in = value
            self._thread = threading.Thread(target=self._body, daemon=True)
            self._thread.start()
        else:
            self._exc_in = None
            # Unwrap single positional arg for convenience
            self._value_in = args[0] if (len(args) == 1 and not kwargs) else value
            self._to_greenlet.set()

        self._to_caller.wait()
        self._to_caller.clear()

        if self._exc_out is not None:
            exc = self._exc_out
            self._exc_out = None
            raise exc

        return self._value_out

    def throw(
        self,
        tp: type[BaseException] | BaseException | None = None,
        value: BaseException | None = None,
        tb: object = None,
    ) -> object:
        """Throw an exception into the greenlet."""
        if isinstance(tp, BaseException):
            exc: BaseException = tp
        elif isinstance(tp, type) and issubclass(tp, BaseException):
            exc = tp(value) if value is not None else tp()
            if tb is not None:
                exc = exc.with_traceback(tb)
        else:
            exc = GreenletExit()

        if not self._started or self._dead:
            self._dead = True
            raise exc

        self._exc_in = exc
        self._value_in = None
        self._to_greenlet.set()

        self._to_caller.wait()
        self._to_caller.clear()

        if self._exc_out is not None:
            exc2 = self._exc_out
            self._exc_out = None
            raise exc2

        return self._value_out

    # ------------------------------------------------------------------ #
    # internal                                                             #
    # ------------------------------------------------------------------ #

    def _body(self) -> None:
        """Run inside the worker thread."""
        prev: greenlet | None = getattr(greenlet._tls, "current", None)
        greenlet._tls.current = self  # type: ignore[assignment]
        try:
            val = self._value_in
            if isinstance(val, tuple) and len(val) == 2 and isinstance(val[1], dict):
                # Called with keyword arguments: packed as (args, kwargs)
                result = self.fn(*val[0], **val[1])  # type: ignore[misc]
            elif isinstance(val, tuple):
                result = self.fn(*val)  # type: ignore[misc]
            else:
                result = self.fn()  # type: ignore[misc]
            self._value_out = result
        except GreenletExit:
            self._value_out = None
        except BaseException as exc:
            self._exc_out = exc
            self._value_out = None
        finally:
            self._dead = True
            greenlet._tls.current = prev  # type: ignore[assignment]
            self._to_caller.set()

    def _yield_to_parent(self, value: object) -> object:
        """Called from *within* this greenlet's thread to pass a value back
        to the caller and suspend until resumed.
        """
        self._value_out = value
        self._exc_out = None
        self._to_caller.set()

        self._to_greenlet.wait()
        self._to_greenlet.clear()

        if self._exc_in is not None:
            exc = self._exc_in
            self._exc_in = None
            raise exc

        return self._value_in


class _MainGreenlet(greenlet):
    """Represents the 'main' greenlet of a thread (no callable, never starts)."""

    def __init__(self) -> None:
        self.fn = None
        self.parent = None
        self._dead = False
        self.gr_context = None
        self._to_greenlet = threading.Event()
        self._to_caller = threading.Event()
        self._value_in = None
        self._value_out = None
        self._exc_in = None
        self._exc_out = None
        self._started = True
        self._thread = None

    def switch(self, *args: object, **kwargs: object) -> object:  # type: ignore[override]
        """Forward a yield-value from a child greenlet back to the async caller.

        This is invoked when ``await_only()`` calls ``current.parent.switch(coro)``.
        The current *child* greenlet is still live and waiting, so we delegate
        to its ``_yield_to_parent`` to signal the outer ``switch()`` caller.
        """
        value = args[0] if (len(args) == 1 and not kwargs) else args
        current_child = greenlet._getcurrent()
        if current_child is not self:
            return current_child._yield_to_parent(value)
        return value


# --------------------------------------------------------------------------- #
# Patch sys.modules so that "import greenlet" resolves to this stub            #
# --------------------------------------------------------------------------- #


def _install() -> None:
    """Install the stub into ``sys.modules`` unless the real C extension loads."""
    # Try loading the real C extension first.
    _real_module_name = "_greenlet_real_backup"
    if "greenlet" in sys.modules and getattr(sys.modules["greenlet"], "_C_API", None) is not None:
        # Real greenlet already loaded successfully — nothing to do.
        return

    def getcurrent() -> greenlet:
        return greenlet._getcurrent()

    stub = types.ModuleType("greenlet")
    stub.greenlet = greenlet  # type: ignore[attr-defined]
    stub.GreenletExit = GreenletExit  # type: ignore[attr-defined]
    stub.getcurrent = getcurrent  # type: ignore[attr-defined]
    stub.error = Exception  # type: ignore[attr-defined]
    stub.gettrace = lambda: None  # type: ignore[attr-defined]
    stub.settrace = lambda _: None  # type: ignore[attr-defined]
    stub._C_API = None  # type: ignore[attr-defined]
    stub.GREENLET_USE_CONTEXT_VARS = True  # type: ignore[attr-defined]
    stub.GREENLET_USE_GC = True  # type: ignore[attr-defined]
    stub.GREENLET_USE_TRACING = True  # type: ignore[attr-defined]
    stub.CLOCKS_PER_SEC = 1000  # type: ignore[attr-defined]
    stub.enable_optional_cleanup = lambda *_a: None  # type: ignore[attr-defined]
    stub.get_clocks_used_doing_optional_cleanup = lambda: 0  # type: ignore[attr-defined]

    sys.modules["greenlet"] = stub
    # Some versions of SQLAlchemy also import greenlet._greenlet directly.
    sys.modules["greenlet._greenlet"] = stub


_install()
