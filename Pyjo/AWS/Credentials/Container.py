"""
Pyjo.AWS.Credentials.Container - Credentials of a container of ECS or EKS
=========================================================================
::

    from Pyjo.AWS.Credentials.Container import Container

    credentials = Container().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.Container

    provider = Pyjo.AWS.Credentials.Container.new(full_uri='http://127.0.0.1:8080/credentials', token='secret')
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.Container` is the provider of the credentials of
the role of a task of ECS, of a pod of EKS Pod Identity, or of a server of
credentials on the loopback, as the agent of the container serves them: of
the ``AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`` environment variable, a path on
``http://169.254.170.2``, which ECS sets, or of
``AWS_CONTAINER_CREDENTIALS_FULL_URI``, a URL, which EKS Pod Identity sets,
with the token of ``AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE``, read each time,
as EKS rotates it, or of ``AWS_CONTAINER_AUTHORIZATION_TOKEN`` in the header
``Authorization``.

A URL of HTTP is one of the agents of ECS and EKS, ``169.254.170.2``,
``169.254.170.23`` or ``fd00:ec2::23``, or of the loopback, as the SDKs of AWS
allow it, and a URL of HTTPS is any. The user agent of the provider has a
timeout of 2 seconds, and a request is tried 3 times, as botocore does.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Chain`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-container-credentials.html.

Classes
-------
"""

import Pyjo.Exception
import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from Pyjo.Util import getenv

from .. import Credentials
from . import Provider

import ipaddress

from typing import Any, cast


HOST = 'http://169.254.170.2'
"""The agent of ECS, of a relative URI."""

_AGENTS = {'169.254.170.2', '169.254.170.23', 'fd00:ec2::23', 'localhost'}


class Pyjo_AWS_Credentials_Container(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Container` inherits all attributes and
    methods from :mod:`Pyjo.AWS.Credentials.Provider` and implements the
    following new ones.
    """

    def __init__(
        self,
        *,
        relative_uri: str | None = None,
        full_uri: str | None = None,
        token: str | None = None,
        token_file: str | None = None,
        timeout: float = 2,
        attempts: int = 3,
        ua: Pyjo.UserAgent.object | None = None,
        **kwargs: Any,
    ) -> None:
        """::

            provider = Pyjo.AWS.Credentials.Container.new()
            provider = Pyjo.AWS.Credentials.Container.new(relative_uri='/v2/credentials/1234')
            provider = Pyjo.AWS.Credentials.Container.new(full_uri='http://169.254.170.23/v1/credentials',
                                                          token_file='/var/run/secrets/token')

        Construct a new :mod:`Pyjo.AWS.Credentials.Container` object, with
        the options of :mod:`Pyjo.AWS.Credentials.Provider`, and the URI and
        the token of the environment without ``relative_uri`` and
        ``full_uri``.
        """
        super().__init__(ua=ua or Pyjo.UserAgent.new(connect_timeout=timeout, inactivity_timeout=timeout), **kwargs)

        environment = relative_uri is None and full_uri is None

        self.relative_uri = (getenv('AWS_CONTAINER_CREDENTIALS_RELATIVE_URI') or None) if environment else relative_uri
        """::

            path = provider.relative_uri

        The path of the credentials on :data:`HOST`, of the
        ``AWS_CONTAINER_CREDENTIALS_RELATIVE_URI`` environment variable by
        default, which comes over :attr:`full_uri`.
        """

        self.full_uri = (getenv('AWS_CONTAINER_CREDENTIALS_FULL_URI') or None) if environment else full_uri
        """::

            url = provider.full_uri

        The URL of the credentials, of the ``AWS_CONTAINER_CREDENTIALS_FULL_URI``
        environment variable by default.
        """

        self.token = (getenv('AWS_CONTAINER_AUTHORIZATION_TOKEN') or None) if token is None else token
        """::

            token = provider.token

        The token of the header ``Authorization``, of the
        ``AWS_CONTAINER_AUTHORIZATION_TOKEN`` environment variable by default.
        """

        self.token_file = (
            (getenv('AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE') or None) if token_file is None else token_file
        )
        """::

            path = provider.token_file

        The file of the token, which comes over :attr:`token`, of the
        ``AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE`` environment variable by
        default.
        """

        self.attempts = attempts
        """::

            attempts = provider.attempts

        The number of the attempts of a request that fails, 3 by default.
        """

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of the container, or ``None`` without a URI.
        """
        if (url := self.url()) is None:
            return None
        headers: dict[str, str] = {}
        if (token := self.authorization()) is not None:
            headers['Authorization'] = token

        error = ''
        for _ in range(max(self.attempts, 1)):
            try:
                tx: Pyjo.Transaction.HTTP.object = await self.start(self.ua.build_tx('GET', url, headers))
            except Pyjo.Exception.object as e:
                error = e.message
                continue
            code = tx.res.code or 0
            if code == 200:
                return _credentials(url, tx)
            error = f'{code} {tx.res.body.decode(errors="replace").strip()}'.strip()
            if code < 500:
                break
        raise Pyjo.Exception.new(f'Cannot get the credentials of the container of AWS of {url}: {error}')

    def authorization(self) -> str | None:
        """::

            token = provider.authorization()

        The value of the header ``Authorization``, of :attr:`token_file` or
        :attr:`token`, or ``None``, without the white space around it, which
        has no line breaks.
        """
        token = self.token
        if self.token_file is not None:
            try:
                with open(self.token_file, encoding='utf-8') as f:
                    token = f.read()
            except OSError as e:
                raise Pyjo.Exception.new(
                    f'Cannot read the authorization token of the container of AWS of {self.token_file}: {e.strerror}'
                ) from e
        if token is None:
            return None
        token = token.strip()
        if '\r' in token or '\n' in token:
            raise Pyjo.Exception.new('Invalid authorization token of the container of AWS: a line break')
        return token

    def url(self) -> str | None:
        """::

            url = provider.url()

        The URL of the credentials, of :attr:`relative_uri` on :data:`HOST`,
        or of :attr:`full_uri`, which is HTTPS or of an agent or the
        loopback, or ``None``.
        """
        if self.relative_uri is not None:
            return HOST + self.relative_uri
        if self.full_uri is None:
            return None
        url = Pyjo.URL.new(self.full_uri)
        host = (url.host or '').strip('[]').lower()
        if url.scheme == 'https' or (url.scheme == 'http' and (host in _AGENTS or _is_loopback(host))):
            return self.full_uri
        raise Pyjo.Exception.new(
            f'The AWS_CONTAINER_CREDENTIALS_FULL_URI {self.full_uri} is not HTTPS, an agent of ECS or EKS, '
            'or the loopback'
        )


def _credentials(url: str, tx: Pyjo.Transaction.HTTP.object) -> Credentials.object:
    try:
        data: Any = tx.res.json()
    except Exception:
        data = None
    fields = cast(dict[str, Any], data) if isinstance(data, dict) else {}
    if not fields.get('AccessKeyId') or not fields.get('SecretAccessKey'):
        raise Pyjo.Exception.new(f'No credentials of the container of AWS of {url}')
    expiration = fields.get('Expiration')
    return Credentials.new(
        access_key_id=fields['AccessKeyId'],
        secret_access_key=fields['SecretAccessKey'],
        session_token=fields.get('Token') or None,
        expiration=Credentials.parse_time(expiration) if isinstance(expiration, str) and expiration else None,
        account_id=fields.get('AccountId') or None,
        provider='container',
    )


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


new = Pyjo_AWS_Credentials_Container.new
object = Pyjo_AWS_Credentials_Container
Container = Pyjo_AWS_Credentials_Container
