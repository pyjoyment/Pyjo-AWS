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

:mod:`Pyjo.AWS.Steps` runs the coroutine, without an event loop, so it
awaits nothing else, not a :mod:`Pyjo.Promise` and not a future of asyncio,
which is a :exc:`TypeError`. :meth:`~Pyjo_AWS_Credentials_Provider.fetch` may
be a generator too, which yields the transactions and the programs, and takes the
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

:mod:`Pyjo.AWS.Credentials`, :mod:`Pyjo.AWS.Credentials.Chain`, :mod:`Pyjo.AWS.Steps`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.JSON
import Pyjo.Promise
import Pyjo.Transaction.HTTP
import Pyjo.UserAgent

from .. import Credentials, Steps

import os

from collections.abc import Sequence
from typing import Any


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
        return self.steps().run(self.ua)

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
            pending = self.steps().run_p(self.ua)

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

    def run(self, args: Sequence[str], input: bytes = b'') -> Steps.Command:
        """::

            code, out, err = await provider.run(['aws', 'configure', 'export-credentials'])
            code, out, err = await provider.run(['/opt/bin/credentials'], input=b'admin')

        A program for :meth:`fetch` to await, which gives its exit code, its
        standard output and its standard error.
        """
        return Steps.Command.new(args, input)

    def start(self, tx: Pyjo.Transaction.HTTP.object) -> Steps.Request:
        """::

            tx = await provider.start(provider.ua.build_tx('GET', 'http://169.254.170.2/v2/credentials'))

        A transaction for :meth:`fetch` to await, which :attr:`ua` starts, and
        which it gives back with its response.
        """
        return Steps.Request.new(tx)

    def steps(self) -> Steps.object[Credentials.object | None]:
        """::

            credentials = await provider.steps()
            credentials = yield from provider.steps()

        The :attr:`cached` credentials, or the ones of :meth:`fetch`, which it
        keeps, for a provider that gets its credentials with the ones of
        another, as a role with the credentials of its source.
        """
        return Steps.Steps(self._steps())

    async def _steps(self) -> Credentials.object | None:
        if self.is_fresh():
            return self.cached
        credentials = await Steps.Steps(self.fetch())
        self.cached = credentials
        return credentials


def write_cache(path: str | os.PathLike[str], data: dict[str, Any]) -> None:
    """::

        Pyjo.AWS.Credentials.Provider.write_cache(path, token)

    Write the JSON of a token to a file of a cache of the AWS CLI, replaced
    at once and readable by its owner only, as the AWS CLI writes it, so that
    the AWS CLI and the other programs share the token.
    """
    tmp = f'{path}.{os.getpid()}.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(Pyjo.JSON.encode_json(data))
    os.replace(tmp, path)


new = Pyjo_AWS_Credentials_Provider.new
object = Pyjo_AWS_Credentials_Provider
Provider = Pyjo_AWS_Credentials_Provider
