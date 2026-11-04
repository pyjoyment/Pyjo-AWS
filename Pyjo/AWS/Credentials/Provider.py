"""
Pyjo.AWS.Credentials.Provider - Base class of the providers of credentials
==========================================================================
::

    from Pyjo.AWS.Credentials import Credentials
    from Pyjo.AWS.Credentials.Provider import Provider

    class Static(Provider):
        async def fetch(self):
            return Credentials(access_key_id='AKIDEXAMPLE', secret_access_key='secret')

    credentials = Static().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials
    import Pyjo.AWS.Credentials.Provider

    class Service(Pyjo.AWS.Credentials.Provider.object):
        async def fetch(self):
            tx = await self.start(self.ua.build_tx('GET', 'http://127.0.0.1:8080/credentials'))
            data = tx.res.json()
            return Pyjo.AWS.Credentials.new(
                access_key_id=data['AccessKeyId'], secret_access_key=data['SecretAccessKey']
            )

    Service.new().credentials_p().then(lambda credentials: print(credentials.access_key_id)).wait()

:mod:`Pyjo.AWS.Credentials.Provider` is the base class of the providers of
:mod:`Pyjo.AWS.Credentials`. A provider gets its credentials in
:meth:`~Pyjo_AWS_Credentials_Provider.fetch`, keeps them until they are about
to expire, and gets them again then.

:meth:`~Pyjo_AWS_Credentials_Provider.fetch` is a coroutine, which awaits
what it needs to wait for, so that the same code runs blocking, in
:meth:`~Pyjo_AWS_Credentials_Provider.credentials`, and non-blocking, in
:meth:`~Pyjo_AWS_Credentials_Provider.credentials_p`:

* a transaction of :meth:`~Pyjo_AWS_Credentials_Provider.start`, which
  :attr:`~Pyjo_AWS_Credentials_Provider.ua` starts, gives the transaction
  back with its response, or raises the :mod:`Pyjo.Exception` of an error of
  the connection;
* a program of :meth:`~Pyjo_AWS_Credentials_Provider.run` gives its exit
  code, its output and its error, or raises the :mod:`Pyjo.Exception` of a
  program that cannot be run;
* the :meth:`~Pyjo_AWS_Credentials_Provider.steps` of another provider give
  its credentials.

No event loop runs the coroutine, so it awaits nothing else, not a
:mod:`Pyjo.Promise` and not a future of asyncio, which is a
:exc:`TypeError`. :meth:`~Pyjo_AWS_Credentials_Provider.fetch` may be a
generator too, which yields the transactions and the programs, and takes the
credentials of another provider with ``yield from`` of its
:meth:`~Pyjo_AWS_Credentials_Provider.steps`: ::

    class Service(Provider):
        def fetch(self):
            tx = yield self.start(self.ua.build_tx('GET', 'http://127.0.0.1:8080/credentials'))
            ...

What the coroutine returns is the credentials, or ``None`` when the
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

from collections.abc import Coroutine, Generator, Sequence
from typing import Any, Self, cast


type Anything = builtins.object


class Command(Pyjo.Base.object):
    """
    A program that a provider runs, with its arguments and what it gets on
    its standard input, of :meth:`~Pyjo_AWS_Credentials_Provider.run`. ::

        code, out, err = await Command.new(['aws', 'configure', 'export-credentials'])
    """

    def __init__(self, args: Sequence[str], input: bytes = b'') -> None:
        self.args = list(args)
        self.input = input

    def __await__(self) -> Generator[Self, Any, tuple[int | None, bytes, bytes]]:
        """::

            code, out, err = await command

        Run the program and give its exit code, its standard output and its
        standard error.
        """
        return (yield self)


class Request(Pyjo.Base.object):
    """
    A transaction that a provider starts, of
    :meth:`~Pyjo_AWS_Credentials_Provider.start`. ::

        tx = await Request.new(ua.build_tx('GET', 'http://169.254.170.2/v2/credentials'))
    """

    def __init__(self, tx: Pyjo.Transaction.HTTP.object) -> None:
        self.tx = tx

    def __await__(self) -> Generator[Self, Any, Pyjo.Transaction.HTTP.object]:
        """::

            tx = await request

        Start the transaction and give it back with its response.
        """
        return (yield self)


type Operation = Request | Command


class Steps[T](Pyjo.Base.object):
    """
    The steps of a coroutine or a generator of a provider, which ``await``
    and ``yield from`` take alike, so that the providers of both kinds take
    the credentials of each other. ::

        credentials = await Steps(provider.fetch())
        credentials = yield from Steps(provider.fetch())
    """

    def __init__(self, steps: Coroutine[Any, Any, T] | Generator[Operation, Any, T]) -> None:
        self._steps = steps

    def __await__(self) -> Generator[Operation, Any, T]:
        """::

            value = await steps

        Wait for the steps and give what they return.
        """
        steps = self._steps
        if isinstance(steps, Coroutine):
            return cast(Generator[Operation, Any, T], steps.__await__())
        return steps

    def __iter__(self) -> Generator[Operation, Any, T]:
        """::

            value = yield from steps

        Same as :meth:`__await__`, for a generator.
        """
        return self.__await__()


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

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        Get new credentials, a coroutine that awaits what it waits for, as the
        description of the class says, and returns the credentials or ``None``.
        A subclass implements it; this one has no credentials.
        """
        return None

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

    def run(self, args: Sequence[str], input: bytes = b'') -> Command:
        """::

            code, out, err = await provider.run(['aws', 'configure', 'export-credentials'])
            code, out, err = await provider.run(['/opt/bin/credentials'], input=b'admin')

        A program for :meth:`fetch` to await, which gives its exit code, its
        standard output and its standard error.
        """
        return Command.new(args, input)

    def start(self, tx: Pyjo.Transaction.HTTP.object) -> Request:
        """::

            tx = await provider.start(provider.ua.build_tx('GET', 'http://169.254.170.2/v2/credentials'))

        A transaction for :meth:`fetch` to await, which :attr:`ua` starts, and
        which it gives back with its response.
        """
        return Request.new(tx)

    def steps(self) -> Steps[Credentials.object | None]:
        """::

            credentials = await provider.steps()
            credentials = yield from provider.steps()

        The :attr:`cached` credentials, or the ones of :meth:`fetch`, which it
        keeps, for a provider that gets its credentials with the ones of
        another, as a role with the credentials of its source.
        """
        return Steps(self._steps())

    async def _steps(self) -> Credentials.object | None:
        if self.is_fresh():
            return self.cached
        credentials = await Steps(self.fetch())
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
    return Pyjo.Exception.new(f'{op.tx.req.method} {op.tx.req.url.to_str()}: {reason}')


# What a coroutine awaits that is not an operation, as a Pyjo.Promise or a future of asyncio, which only an event loop
# knows: the coroutine is closed and the error raised, not thrown into it, where catching the errors of a connection
# would hide it
def _unexpected(steps: Generator[Operation, Any, Any], op: Anything) -> TypeError | None:
    if isinstance(op, (Request, Command)):
        return None
    steps.close()
    return TypeError(
        f'A provider of AWS credentials awaits {type(op).__name__}: only start, run and the steps of a provider'
    )


def _blocking(op: Operation, ua: Pyjo.UserAgent.object) -> Any:
    if isinstance(op, Command):
        try:
            done = subprocess.run(op.args, input=op.input, capture_output=True, check=False)
        except OSError as e:
            raise _error(op, e) from e
        return done.returncode, done.stdout, done.stderr
    tx: Pyjo.Transaction.HTTP.object = ua.start(op.tx)
    if (err := tx.error) and not err.get('code'):
        raise _error(op, err['message'])
    return tx


def _nonblocking_p(op: Operation, ua: Pyjo.UserAgent.object) -> Pyjo.Promise.object:
    if isinstance(op, Command):
        promise: Pyjo.Promise.object = Pyjo.IOLoop.ChildProcess.new().run_p(op.args, input=op.input)

        def result(code: int | None, out: bytes, err: bytes) -> tuple[int | None, bytes, bytes]:
            return code, bytes(out), bytes(err)

        return promise.then(result)
    return ua.start_p(op.tx)


# The steps, blocking, as the result of each operation is sent into them, or its exception thrown in
def _run[T](steps: Steps[T], ua: Pyjo.UserAgent.object) -> T:
    gen = steps.__await__()
    value: Any = None
    error: Exception | None = None
    while True:
        try:
            op = gen.send(value) if error is None else gen.throw(error)
        except StopIteration as e:
            return cast(T, e.value)
        if unexpected := _unexpected(gen, op):
            raise unexpected
        value, error = None, None
        try:
            value = _blocking(op, ua)
        except Exception as e:
            error = e


# Same as _run, but non-blocking, with a promise of what the steps return
def _run_p[T](steps: Steps[T], ua: Pyjo.UserAgent.object) -> Pyjo.Promise.object:
    gen = steps.__await__()
    promise = Pyjo.Promise.new()

    def step(value: Any = None, error: Exception | None = None) -> None:
        try:
            op = gen.send(value) if error is None else gen.throw(error)
            if unexpected := _unexpected(gen, op):
                raise unexpected
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
