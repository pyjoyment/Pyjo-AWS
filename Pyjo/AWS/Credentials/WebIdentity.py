"""
Pyjo.AWS.Credentials.WebIdentity - Credentials of a role of a web identity
==========================================================================
::

    from Pyjo.AWS.Credentials.WebIdentity import WebIdentity

    credentials = WebIdentity().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.WebIdentity

    provider = Pyjo.AWS.Credentials.WebIdentity.new(
        role_arn='arn:aws:iam::123456789012:role/ci', token_file='/var/run/secrets/token', role_session_name='ci'
    )
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.WebIdentity` is the provider of the credentials
of a role of ``AssumeRoleWithWebIdentity`` of STS, with the token of OpenID
Connect of a file, as the service accounts of EKS and the OIDC of CI have it:
of the ``AWS_WEB_IDENTITY_TOKEN_FILE``, ``AWS_ROLE_ARN`` and
``AWS_ROLE_SESSION_NAME`` environment variables by default, or of
``web_identity_token_file`` and ``role_arn`` of a profile, of
:mod:`Pyjo.AWS.Credentials.Profile`. The request is not signed, as the token
is its proof, and the file is read each time, as the token is rotated.

A token file without a role, or a role without a token file, of the
environment, is an error.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.AssumeRole`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-assume-role-credentials.html.

Classes
-------
"""

import Pyjo.Exception

from Pyjo.Util import getenv

from .. import Config, Credentials
from ..Protocol import Query
from . import AssumeRole, Provider

import time

from typing import Any


class Pyjo_AWS_Credentials_WebIdentity(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.WebIdentity` inherits all attributes and
    methods from :mod:`Pyjo.AWS.Credentials.Provider` and implements the
    following new ones.
    """

    def __init__(
        self,
        *,
        role_arn: str | None = None,
        token_file: str | None = None,
        role_session_name: str | None = None,
        duration_seconds: int | None = None,
        region: str | None = None,
        config: Config.object | None = None,
        **kwargs: Any,
    ) -> None:
        """::

            provider = Pyjo.AWS.Credentials.WebIdentity.new()
            provider = Pyjo.AWS.Credentials.WebIdentity.new(role_arn=arn, token_file='/var/run/secrets/token')

        Construct a new :mod:`Pyjo.AWS.Credentials.WebIdentity` object, with
        the options of :mod:`Pyjo.AWS.Credentials.Provider`, and the role,
        the token file and the name of the session of the environment
        without ``role_arn`` and ``token_file``.
        """
        super().__init__(**kwargs)

        environment = role_arn is None and token_file is None

        self.role_arn = (getenv('AWS_ROLE_ARN') or None) if environment else role_arn
        """::

            arn = provider.role_arn

        The ARN of the role, of the ``AWS_ROLE_ARN`` environment variable by
        default.
        """

        self.token_file = (getenv('AWS_WEB_IDENTITY_TOKEN_FILE') or None) if environment else token_file
        """::

            path = provider.token_file

        The file of the token, of the ``AWS_WEB_IDENTITY_TOKEN_FILE``
        environment variable by default.
        """

        self.role_session_name = (getenv('AWS_ROLE_SESSION_NAME') or None) if environment else role_session_name
        """::

            name = provider.role_session_name

        The name of the session of the role, of the ``AWS_ROLE_SESSION_NAME``
        environment variable by default, or ``None`` for ``pyjo-aws-`` and
        the time.
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

        The shared files of the endpoint and the region of STS, a new
        :mod:`Pyjo.AWS.Config` object by default.
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

        The credentials of the role, of the token of the file, or ``None``
        without a role and a token file.
        """
        role_arn, token_file = self.role_arn, self.token_file
        if role_arn is None and token_file is None:
            return None
        if role_arn is None or token_file is None:
            missing = 'AWS_ROLE_ARN' if role_arn is None else 'AWS_WEB_IDENTITY_TOKEN_FILE'
            raise Pyjo.Exception.new(f'Partial web identity of AWS in the environment: no {missing}')
        try:
            with open(token_file, encoding='utf-8') as f:
                token = f.read().strip()
        except OSError as e:
            raise Pyjo.Exception.new(f'Cannot read the web identity token of AWS of {token_file}: {e.strerror}') from e
        params: dict[str, Any] = {
            'RoleArn': role_arn,
            'RoleSessionName': self.role_session_name or f'pyjo-aws-{int(time.time())}',
            'WebIdentityToken': token,
            'DurationSeconds': self.duration_seconds,
        }
        sts = AssumeRole.sts_client(self.ua, self.config, self.region, unsigned=True)
        dom = await sts.steps(Query.new('AssumeRoleWithWebIdentity', params, version=AssumeRole.VERSION))
        return AssumeRole.credentials_of(dom, 'web-identity')


new = Pyjo_AWS_Credentials_WebIdentity.new
object = Pyjo_AWS_Credentials_WebIdentity
WebIdentity = Pyjo_AWS_Credentials_WebIdentity
