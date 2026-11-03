"""
Pyjo.AWS.Credentials.Provider - Base class of the providers of credentials
==========================================================================
::

    from Pyjo.AWS.Credentials import Credentials
    from Pyjo.AWS.Credentials.Provider import Provider

    class Static(Provider):
        def fetch(self):
            return Credentials(access_key_id='AKIDEXAMPLE', secret_access_key='secret')
            yield

    credentials = Static().credentials()

:mod:`Pyjo.AWS.Credentials.Provider` is the base class of the providers of
:mod:`Pyjo.AWS.Credentials`. A provider gets its credentials in
:meth:`~Pyjo_AWS_Credentials_Provider.fetch`, keeps them until they are about
to expire, and gets them again then.

:meth:`~Pyjo_AWS_Credentials_Provider.fetch` is a generator, which yields
what it needs to wait for, and gets its result back, so that the same code
runs blocking, in :meth:`~Pyjo_AWS_Credentials_Provider.credentials`, and
non-blocking, in :meth:`~Pyjo_AWS_Credentials_Provider.credentials_p`:

* a :mod:`Pyjo.Transaction.HTTP` object, which :attr:`ua` starts, gets the
  transaction back with its response, or the :mod:`Pyjo.Exception` of an
  error of the connection thrown in;
* a :class:`Command` gets the exit code, the output and the error of the
  program, or the :mod:`Pyjo.Exception` of a program that cannot be run
  thrown in.

What the generator returns is the credentials, or ``None`` when the
provider is not configured, as an environment without its variables, so that
:mod:`Pyjo.AWS.Credentials.Chain` asks the next one. An exception is an error
of a provider that is configured, which ends the chain.

See also
--------

:mod:`Pyjo.AWS.Credentials`, :mod:`Pyjo.AWS.Credentials.Chain`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception
import Pyjo.IOLoop.ChildProcess
import Pyjo.Promise
import Pyjo.Transaction.HTTP
import Pyjo.UserAgent

from .. import Credentials

import builtins
import subprocess

from collections.abc import Generator, Sequence
from typing import Any


type Anything = builtins.object


class Command(Pyjo.Base.object):
    """
    A program that :meth:`~Pyjo_AWS_Credentials_Provider.fetch` runs, with
    its arguments and what it gets on its standard input. ::

        code, out, err = yield Command.new(['aws', 'configure', 'export-credentials'])
    """

    def __init__(self, args: Sequence[str], input: bytes = b'') -> None:
        self.args = list(args)
        self.input = input


type Operation = Pyjo.Transaction.HTTP.object | Command
type Steps = Generator[Operation, Any, Credentials.object | None]


class Pyjo_AWS_Credentials_Provider(Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.Credentials.Provider` inherits all attributes and methods
    from :mod:`Pyjo.Base` and implements the following new ones.
    """

    def __init__(self, *, ua: Pyjo.UserAgent.object | None = None, refresh: float = 300) -> None:
        """::

            provider = Provider.new()
            provider = Provider.new(ua=Pyjo.UserAgent.new(request_timeout=5), refresh=600)

        Construct a new provider.
        """
        self.ua = ua or Pyjo.UserAgent.new()
        """::

            ua = provider.ua
            provider.ua = Pyjo.UserAgent.new()

        The user agent of the requests of the provider, a new
        :mod:`Pyjo.UserAgent` object by default.
        """

        self.refresh = refresh
        """::

            seconds = provider.refresh
            provider.refresh = 600

        The number of seconds before their expiration when the credentials are
        got again, 300 by default.
        """

        self.cached: Credentials.object | None = None
        """::

            credentials = provider.cached
            provider.cached = None

        The credentials that the provider got last, which it gives until they
        are about to expire, or ``None``, which makes it get them again.
        """

        self._pending: Pyjo.Promise.object | None = None

    def credentials(self) -> Credentials.object | None:
        """::

            credentials = provider.credentials()

        The credentials, :attr:`cached` ones or new ones, blocking, or
        ``None`` when the provider is not configured.
        """
        return _run(self.steps(), self.ua)

    def credentials_p(self) -> Pyjo.Promise.object:
        """::

            promise = provider.credentials_p()

        Same as :meth:`credentials`, but non-blocking, and returns a
        :mod:`Pyjo.Promise` object. The calls while the provider gets the
        credentials get the same promise, so that it gets them once.
        """
        if self.is_fresh():
            return Pyjo.Promise.resolve(self.cached)
        if self._pending is None:
            pending = _run_p(self.steps(), self.ua)

            def done(*_: Any) -> None:
                self._pending = None

            pending.then(done, done)
            self._pending = pending
        return self._pending

    def fetch(self) -> Steps:
        """::

            credentials = yield from provider.fetch()

        Get new credentials, a generator that yields what it waits for, as the
        description of the class says, and returns the credentials or ``None``.
        A subclass implements it; this one has no credentials.
        """
        return None
        yield

    def is_fresh(self) -> bool:
        """::

            boolean = provider.is_fresh()

        Whether the provider has :attr:`cached` credentials that are not about
        to expire.
        """
        if self.cached is None:
            return False
        expires_in = self.cached.expires_in()
        return expires_in is None or expires_in > self.refresh

    def steps(self) -> Steps:
        """::

            credentials = yield from provider.steps()

        The :attr:`cached` credentials, or the ones of :meth:`fetch`, which it
        keeps, for a provider that gets its credentials with the ones of
        another, as a role with the credentials of its source.
        """
        if self.is_fresh():
            return self.cached
        credentials = yield from self.fetch()
        self.cached = credentials
        return credentials


# The error of an operation, as a Pyjo.Exception with what failed, of the reason of a rejected promise too, which is a
# string of an error of a connection, or the OSError of a program that cannot be run
def _error(op: Operation, reason: Anything) -> Exception:
    if isinstance(op, Command):
        if isinstance(reason, OSError):
            reason = reason.strerror or reason
        elif isinstance(reason, Exception):
            return reason
        return Pyjo.Exception.new(f'Cannot run {op.args[0]}: {reason}')
    if isinstance(reason, Exception):
        return reason
    return Pyjo.Exception.new(f'{op.req.method} {op.req.url.to_str()}: {reason}')


def _blocking(op: Operation, ua: Pyjo.UserAgent.object) -> Any:
    if isinstance(op, Command):
        try:
            done = subprocess.run(op.args, input=op.input, capture_output=True, check=False)
        except OSError as e:
            raise _error(op, e) from e
        return done.returncode, done.stdout, done.stderr
    tx: Pyjo.Transaction.HTTP.object = ua.start(op)
    if (err := tx.error) and not err.get('code'):
        raise _error(op, err['message'])
    return tx


def _nonblocking_p(op: Operation, ua: Pyjo.UserAgent.object) -> Pyjo.Promise.object:
    if isinstance(op, Command):
        promise: Pyjo.Promise.object = Pyjo.IOLoop.ChildProcess.new().run_p(op.args, input=op.input)

        def result(code: int | None, out: bytes, err: bytes) -> tuple[int | None, bytes, bytes]:
            return code, bytes(out), bytes(err)

        return promise.then(result)
    return ua.start_p(op)


# The steps of a generator, blocking, as the result of each operation is sent into it, or its exception thrown in
def _run(steps: Steps, ua: Pyjo.UserAgent.object) -> Credentials.object | None:
    value: Any = None
    error: Exception | None = None
    while True:
        try:
            op = steps.send(value) if error is None else steps.throw(error)
        except StopIteration as e:
            return e.value
        value, error = None, None
        try:
            value = _blocking(op, ua)
        except Exception as e:
            error = e


# Same as _run, but non-blocking, with a promise of what the generator returns
def _run_p(steps: Steps, ua: Pyjo.UserAgent.object) -> Pyjo.Promise.object:
    promise = Pyjo.Promise.new()

    def step(value: Any = None, error: Exception | None = None) -> None:
        try:
            op = steps.send(value) if error is None else steps.throw(error)
            started = _nonblocking_p(op, ua)
        except StopIteration as e:
            promise.resolve(e.value)
            return
        except Exception as e:
            promise.reject(e)
            return

        def failed(reason: Anything) -> None:
            step(error=_error(op, reason))

        started.then(step, failed)

    step()
    return promise


new = Pyjo_AWS_Credentials_Provider.new
object = Pyjo_AWS_Credentials_Provider
Provider = Pyjo_AWS_Credentials_Provider
