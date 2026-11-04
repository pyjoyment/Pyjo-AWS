"""
Pyjo.AWS.Credentials.AssumeRole - Credentials of a role of STS
==============================================================
::

    from Pyjo.AWS.Credentials.AssumeRole import AssumeRole
    from Pyjo.AWS.Credentials.Profile import Profile

    provider = AssumeRole(source=Profile(), role_arn='arn:aws:iam::123456789012:role/admin')
    credentials = provider.credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.AssumeRole
    import Pyjo.AWS.Credentials.Environment

    provider = Pyjo.AWS.Credentials.AssumeRole.new(
        source=Pyjo.AWS.Credentials.Environment.new(),
        role_arn='arn:aws:iam::123456789012:role/deploy',
        role_session_name='deploy',
        external_id='4c1d0e4f',
        duration_seconds=900,
        region='eu-central-1',
    )
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.AssumeRole` is the provider of the credentials of
a role of ``AssumeRole`` of STS, signed with the credentials of another
provider, its source, as a profile of ``role_arn`` with ``source_profile`` or
``credential_source`` has them, of :mod:`Pyjo.AWS.Credentials.Profile`. The
credentials of the source are kept by the source, so that they are got
again only when they expire.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Profile`,
:mod:`Pyjo.AWS.Credentials.WebIdentity`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-assume-role-credentials.html.

Classes
-------
"""

import Pyjo.DOM
import Pyjo.Exception
import Pyjo.UserAgent

from .. import Client, Config, Credentials
from ..Protocol import Query
from . import Provider

import time

from typing import Any


VERSION = '2011-06-15'
"""The version of the API of STS."""


class Pyjo_AWS_Credentials_AssumeRole(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.AssumeRole` inherits all attributes and
    methods from :mod:`Pyjo.AWS.Credentials.Provider` and implements the
    following new ones.
    """

    def __init__(
        self,
        *,
        source: Provider.object,
        role_arn: str,
        role_session_name: str | None = None,
        external_id: str | None = None,
        duration_seconds: int | None = None,
        region: str | None = None,
        config: Config.object | None = None,
        **kwargs: Any,
    ) -> None:
        """::

            provider = Pyjo.AWS.Credentials.AssumeRole.new(source=source, role_arn='arn:aws:iam::123456789012:role/admin')

        Construct a new :mod:`Pyjo.AWS.Credentials.AssumeRole` object, with
        the options of :mod:`Pyjo.AWS.Credentials.Provider`.
        """
        super().__init__(**kwargs)

        self.source = source
        """::

            source = provider.source

        The provider of the credentials that sign ``AssumeRole``.
        """

        self.role_arn = role_arn
        """::

            arn = provider.role_arn

        The ARN of the role.
        """

        self.role_session_name = role_session_name
        """::

            name = provider.role_session_name

        The name of the session of the role, which CloudTrail logs, or
        ``None`` for ``pyjo-aws-`` and the time, as botocore names it.
        """

        self.external_id = external_id
        """::

            external_id = provider.external_id

        The external ID that the trust policy of the role requires, or
        ``None``.
        """

        self.duration_seconds = duration_seconds
        """::

            seconds = provider.duration_seconds

        The duration of the credentials, or ``None`` for the default of STS,
        one hour.
        """

        self.config = config or Config.new()
        """::

            config = provider.config

        The shared files of the endpoint of STS, a new :mod:`Pyjo.AWS.Config`
        object by default.
        """

        self.region = region
        """::

            region = provider.region

        The region of STS, or ``None`` for the one of :attr:`config`, or
        ``us-east-1``.
        """

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of the role, of the credentials of :attr:`source`.
        """
        source = await self.source.steps()
        if source is None:
            raise Pyjo.Exception.new(f'No credentials of AWS of the source of the role {self.role_arn}')
        params: dict[str, Any] = {
            'RoleArn': self.role_arn,
            'RoleSessionName': self.role_session_name or f'pyjo-aws-{int(time.time())}',
            'ExternalId': self.external_id,
            'DurationSeconds': self.duration_seconds,
        }
        sts = sts_client(self.ua, self.config, self.region)
        dom = await sts.steps(Query.new('AssumeRole', params, version=VERSION), source)
        return credentials_of(dom, 'assume-role')


def credentials_of(dom: Pyjo.DOM.object, provider: str) -> Credentials.object:
    """::

        credentials = Pyjo.AWS.Credentials.AssumeRole.credentials_of(dom, 'assume-role')

    The credentials of the XML of a response of STS, of its elements
    ``Credentials``, and the account of the ARN of ``AssumedRoleUser``.
    """
    fields = {
        name: element.text.strip() if (element := dom.at(f'Credentials > {name}')) is not None else ''
        for name in ('AccessKeyId', 'SecretAccessKey', 'SessionToken', 'Expiration')
    }
    if not fields['AccessKeyId'] or not fields['SecretAccessKey']:
        raise Pyjo.Exception.new('No Credentials in the response of STS')
    arn = dom.at('AssumedRoleUser > Arn')
    parts = arn.text.strip().split(':') if arn is not None else []
    return Credentials.new(
        access_key_id=fields['AccessKeyId'],
        secret_access_key=fields['SecretAccessKey'],
        session_token=fields['SessionToken'] or None,
        expiration=Credentials.parse_time(fields['Expiration']) if fields['Expiration'] else None,
        account_id=parts[4] if len(parts) > 4 and parts[4] else None,
        provider=provider,
    )


def sts_client(
    ua: Pyjo.UserAgent.object, config: Config.object, region: str | None = None, unsigned: bool = False
) -> Client.object:
    """::

        sts = Pyjo.AWS.Credentials.AssumeRole.sts_client(ua, config)

    A new client of STS of a provider, with its user agent, in a region, the
    one of the shared files, or ``us-east-1``, whose regional endpoint is the
    global one.
    """
    return Client.new(
        service='sts', region=region or config.region() or 'us-east-1', config=config, unsigned=unsigned, ua=ua
    )


new = Pyjo_AWS_Credentials_AssumeRole.new
object = Pyjo_AWS_Credentials_AssumeRole
AssumeRole = Pyjo_AWS_Credentials_AssumeRole
