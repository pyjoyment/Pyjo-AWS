"""
Pyjo.AWS.Credentials.InstanceMetadata - Credentials of the instance metadata of EC2
===================================================================================
::

    from Pyjo.AWS.Credentials.InstanceMetadata import InstanceMetadata

    credentials = InstanceMetadata().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.InstanceMetadata

    provider = Pyjo.AWS.Credentials.InstanceMetadata.new(timeout=2, attempts=3)
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.InstanceMetadata` is the provider of the
credentials of the role of the instance profile of an instance of EC2, of
its instance metadata service, with a token of IMDSv2, or without one of
IMDSv1, where the service has no tokens, unless
``AWS_EC2_METADATA_V1_DISABLED`` or ``ec2_metadata_v1_disabled`` of the
profile is ``true``.

The service is the one of ``AWS_EC2_METADATA_SERVICE_ENDPOINT`` or
``ec2_metadata_service_endpoint``, or ``http://169.254.169.254``, or
``http://[fd00:ec2::254]`` of ``AWS_EC2_METADATA_SERVICE_ENDPOINT_MODE`` or
``ec2_metadata_service_endpoint_mode`` ``IPv6``, with the timeout of
``AWS_METADATA_SERVICE_TIMEOUT`` or ``metadata_service_timeout``, 1 second by
default, and the attempts of ``AWS_METADATA_SERVICE_NUM_ATTEMPTS`` or
``metadata_service_num_attempts``, 1 by default, as a machine that is not an
instance of EC2 has no service, which the provider waits for that long. The
``AWS_EC2_METADATA_DISABLED`` environment variable ``true`` turns it off.

A service that does not answer, or answers without a role, has no
credentials, as the SDKs of AWS have it, so that
:mod:`Pyjo.AWS.Credentials.Chain` ends without them; the credentials of a
role that the service does not give are an error.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Chain`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-imds-credentials.html.

Classes
-------
"""

import Pyjo.Exception
import Pyjo.Transaction.HTTP
import Pyjo.UserAgent

from Pyjo.Util import getenv

from .. import Config, Credentials
from . import Provider

from typing import Any, cast


ENDPOINT = 'http://169.254.169.254'
"""The service of IPv4."""

ENDPOINT_IPV6 = 'http://[fd00:ec2::254]'
"""The service of IPv6."""

TTL = 21600
"""The seconds of a token of IMDSv2, 6 hours, as the SDKs of AWS ask for."""

_PATH = '/latest/meta-data/iam/security-credentials/'


class Pyjo_AWS_Credentials_InstanceMetadata(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.InstanceMetadata` inherits all attributes and
    methods from :mod:`Pyjo.AWS.Credentials.Provider` and implements the
    following new ones.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        timeout: float | None = None,
        attempts: int | None = None,
        config: Config.object | None = None,
        ua: Pyjo.UserAgent.object | None = None,
        **kwargs: Any,
    ) -> None:
        """::

            provider = Pyjo.AWS.Credentials.InstanceMetadata.new()
            provider = Pyjo.AWS.Credentials.InstanceMetadata.new(endpoint='http://[fd00:ec2::254]', timeout=2)

        Construct a new :mod:`Pyjo.AWS.Credentials.InstanceMetadata` object,
        with the options of :mod:`Pyjo.AWS.Credentials.Provider`, and those of
        the environment and of the profile of ``config`` by default.
        """
        config = config or Config.new()

        self.timeout = timeout if timeout is not None else _number(config, 'metadata_service_timeout', 1.0)
        """::

            seconds = provider.timeout

        The timeout of the service, of the ``AWS_METADATA_SERVICE_TIMEOUT``
        environment variable or ``metadata_service_timeout`` of the profile,
        or 1 second, of a new :attr:`ua` of the provider.
        """

        super().__init__(
            ua=ua or Pyjo.UserAgent.new(connect_timeout=self.timeout, inactivity_timeout=self.timeout), **kwargs
        )

        self.config = config
        """::

            config = provider.config

        The shared files of the settings, a new :mod:`Pyjo.AWS.Config` object
        by default.
        """

        mode = getenv('AWS_EC2_METADATA_SERVICE_ENDPOINT_MODE') or config.get('ec2_metadata_service_endpoint_mode')
        self.endpoint = (
            endpoint
            or getenv('AWS_EC2_METADATA_SERVICE_ENDPOINT')
            or config.get('ec2_metadata_service_endpoint')
            or (ENDPOINT_IPV6 if str(mode).lower() == 'ipv6' else ENDPOINT)
        ).rstrip('/')
        """::

            url = provider.endpoint

        The URL of the service, of the ``AWS_EC2_METADATA_SERVICE_ENDPOINT``
        environment variable or ``ec2_metadata_service_endpoint`` of the
        profile, or of IPv4 or of IPv6 of the mode.
        """

        self.attempts = attempts if attempts is not None else int(_number(config, 'metadata_service_num_attempts', 1))
        """::

            attempts = provider.attempts

        The number of the attempts of a request that fails, of the
        ``AWS_METADATA_SERVICE_NUM_ATTEMPTS`` environment variable or
        ``metadata_service_num_attempts`` of the profile, or 1.
        """

        self.disabled = _is_true(getenv('AWS_EC2_METADATA_DISABLED'))
        """::

            boolean = provider.disabled

        Whether the provider is turned off, of the ``AWS_EC2_METADATA_DISABLED``
        environment variable ``true``.
        """

        self.v1_disabled = _is_true(getenv('AWS_EC2_METADATA_V1_DISABLED') or config.get('ec2_metadata_v1_disabled'))
        """::

            boolean = provider.v1_disabled

        Whether IMDSv1 without a token is turned off, of the
        ``AWS_EC2_METADATA_V1_DISABLED`` environment variable or
        ``ec2_metadata_v1_disabled`` of the profile ``true``.
        """

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of the role of the instance, or ``None`` without the
        service or a role.
        """
        if self.disabled:
            return None

        tx = await self._request('PUT', '/latest/api/token', {'X-aws-ec2-metadata-token-ttl-seconds': str(TTL)})
        if tx is None:
            return None
        headers: dict[str, str] = {}
        code = tx.res.code
        if code == 200:
            headers['X-aws-ec2-metadata-token'] = tx.res.text.strip()
        elif code not in (403, 404, 405) or self.v1_disabled:
            return None

        tx = await self._request('GET', _PATH, headers)
        if tx is None or tx.res.code != 200 or not (lines := tx.res.text.split()):
            return None
        role = lines[0]

        url = f'{self.endpoint}{_PATH}{role}'
        tx = await self._request('GET', _PATH + role, headers)
        if tx is None:
            raise Pyjo.Exception.new(f'Cannot get the credentials of the instance metadata of AWS of {url}')
        if tx.res.code != 200:
            raise Pyjo.Exception.new(
                f'Cannot get the credentials of the instance metadata of AWS of {url}: {tx.res.code}'
            )
        try:
            data: Any = tx.res.json()
        except Exception:
            data = None
        fields = cast(dict[str, Any], data) if isinstance(data, dict) else {}
        if fields.get('Code', 'Success') != 'Success' or not fields.get('AccessKeyId'):
            raise Pyjo.Exception.new(f'No credentials of the instance metadata of AWS of {url}: {fields.get("Code")}')
        expiration = fields.get('Expiration')
        return Credentials.new(
            access_key_id=fields['AccessKeyId'],
            secret_access_key=fields['SecretAccessKey'],
            session_token=fields.get('Token') or None,
            expiration=Credentials.parse_time(expiration) if isinstance(expiration, str) and expiration else None,
            provider='imds',
        )

    # A request of the service, tried again after an error of the connection or of the service, or None after the
    # last attempt, as a machine that is not an instance of EC2 has no service
    async def _request(self, method: str, path: str, headers: dict[str, str]) -> Pyjo.Transaction.HTTP.object | None:
        for _ in range(max(self.attempts, 1)):
            try:
                tx: Pyjo.Transaction.HTTP.object = await self.start(
                    self.ua.build_tx(method, self.endpoint + path, headers)
                )
            except Pyjo.Exception.object:
                continue
            if (tx.res.code or 0) < 500:
                return tx
        return None


def _is_true(value: Any) -> bool:
    return str(value or '').strip().lower() == 'true'


def _number(config: Config.object, name: str, default: float) -> float:
    value = getenv(f'AWS_{name.upper()}') or config.get(name)
    try:
        return float(value) if value else default
    except ValueError:
        raise Pyjo.Exception.new(f'Invalid {name} of AWS: {value}') from None


new = Pyjo_AWS_Credentials_InstanceMetadata.new
object = Pyjo_AWS_Credentials_InstanceMetadata
InstanceMetadata = Pyjo_AWS_Credentials_InstanceMetadata
