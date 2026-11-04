"""
Pyjo.AWS.Credentials.SSO - Credentials of IAM Identity Center
=============================================================
::

    from Pyjo.AWS.Credentials.SSO import SSO

    credentials = SSO().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Config
    import Pyjo.AWS.Credentials.SSO

    provider = Pyjo.AWS.Credentials.SSO.new(config=Pyjo.AWS.Config.new(profile='dev'))
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.SSO` is the provider of the credentials of a role
of IAM Identity Center, the former AWS SSO, of a profile of the shared files
of :mod:`Pyjo.AWS.Config`, after ``aws sso login``, as the SDKs of AWS get
them: the token of the login, of the cache of the AWS CLI in
``~/.aws/sso/cache``, gets the credentials of the role of ``sso_role_name``
in the account of ``sso_account_id`` with ``GetRoleCredentials`` of SSO.

A profile of a section ``sso-session``, which ``aws configure sso`` writes,
has a token that is refreshed with ``CreateToken`` of SSO OIDC before it
expires, and written back to the cache, as the AWS CLI does: ::

    [profile dev]
    sso_session = company
    sso_account_id = 123456789012
    sso_role_name = ReadOnly

    [sso-session company]
    sso_start_url = https://company.awsapps.com/start
    sso_region = eu-central-1
    sso_registration_scopes = sso:account:access

A legacy profile, with ``sso_start_url`` and ``sso_region`` of its own, has a
token that is not refreshed, and expires after the hours of the session of
IAM Identity Center.

A token that is not in the cache, or has expired, is an error, which tells
to run ``aws sso login``.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Profile`,
:mod:`Pyjo.AWS.Client`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-sso-credentials.html.

Classes
-------
"""

import Pyjo.Date
import Pyjo.Exception
import Pyjo.File
import Pyjo.JSON

from Pyjo.Util import sha1_sum

from .. import Client, Config, Credentials
from ..Protocol import RestJSON
from . import Provider

import time

from typing import Any, cast


class Pyjo_AWS_Credentials_SSO(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.SSO` inherits all attributes and methods from
    :mod:`Pyjo.AWS.Credentials.Provider` and implements the following new
    ones.
    """

    def __init__(
        self,
        *,
        config: Config.object | None = None,
        profile: str | None = None,
        cache_dir: str | None = None,
        **kwargs: Any,
    ) -> None:
        """::

            provider = Pyjo.AWS.Credentials.SSO.new()
            provider = Pyjo.AWS.Credentials.SSO.new(config=Pyjo.AWS.Config.new(profile='dev'))
            provider = Pyjo.AWS.Credentials.SSO.new(profile='dev', cache_dir='/tmp/sso')

        Construct a new :mod:`Pyjo.AWS.Credentials.SSO` object, with the
        options of :mod:`Pyjo.AWS.Credentials.Provider`.
        """
        super().__init__(**kwargs)

        self.config = config or Config.new()
        """::

            config = provider.config

        The shared files, a new :mod:`Pyjo.AWS.Config` object by default.
        """

        self.profile = profile or self.config.profile
        """::

            name = provider.profile

        The name of the profile, the
        :attr:`~Pyjo.AWS.Config.Pyjo_AWS_Config.profile` of :attr:`config`
        by default.
        """

        self.cache_dir = Pyjo.File.new(cache_dir or '~/.aws/sso/cache').expanduser()
        """::

            path = provider.cache_dir

        The :mod:`Pyjo.File` object of the directory of the cache of the
        tokens, ``~/.aws/sso/cache`` of the
        AWS CLI by default.
        """

    def cache_file(self, key: str) -> Pyjo.File.object:
        """::

            path = provider.cache_file('company')
            path = provider.cache_file('https://company.awsapps.com/start')

        The file of the token of the name of a section ``sso-session``, or of
        the start URL of a legacy profile, in :attr:`cache_dir`, of the SHA-1
        of the key, as the AWS CLI names it.
        """
        return self.cache_dir.child(sha1_sum(key.encode()) + '.json')

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of the role of the profile, or ``None`` of a profile
        without SSO.
        """
        config, profile = self.config, self.profile
        settings = config.settings(profile)
        session_name: str | None = settings.get('sso_session') or None
        if session_name is not None:
            session = config.sso_session(session_name)
            if not session:
                raise Pyjo.Exception.new(f'The sso-session {session_name} of AWS is not in {config.config_file}')
            for field in ('sso_start_url', 'sso_region'):
                if (value := settings.get(field)) and value != session.get(field):
                    raise Pyjo.Exception.new(
                        f'The {field} of the profile {profile} of AWS is not the one of its sso-session {session_name}'
                    )
            source, key = session, session_name
        elif settings.get('sso_start_url'):
            source, key = settings, cast(str, settings['sso_start_url'])
        else:
            return None

        start_url, region = source.get('sso_start_url'), source.get('sso_region')
        account_id, role_name = settings.get('sso_account_id'), settings.get('sso_role_name')
        missing = [
            name
            for name, value in (
                ('sso_start_url', start_url),
                ('sso_region', region),
                ('sso_account_id', account_id),
                ('sso_role_name', role_name),
            )
            if not value
        ]
        if missing:
            raise Pyjo.Exception.new(f'The SSO of the profile {profile} of AWS has no {", ".join(missing)}')

        token = await self._token(key, cast(str, region), session_name is not None)
        call = RestJSON.new(
            'GET',
            '/federation/credentials',
            query={'role_name': role_name, 'account_id': account_id},
            headers={'X-Amz-Sso_bearer_token': token},
        )
        portal = self._client('awsssoportal', 'portal.sso', 'SSO', cast(str, region))
        data = await portal.steps(call)
        role: Any = cast(dict[str, Any], data).get('roleCredentials') if isinstance(data, dict) else None
        if not isinstance(role, dict):
            raise Pyjo.Exception.new(f'No roleCredentials of SSO for the profile {profile} of AWS')
        fields = cast(dict[str, Any], role)
        expiration = fields.get('expiration')
        return Credentials.new(
            access_key_id=fields['accessKeyId'],
            secret_access_key=fields['secretAccessKey'],
            session_token=fields.get('sessionToken') or None,
            expiration=Pyjo.Date.new(expiration / 1000) if isinstance(expiration, (int, float)) else None,
            account_id=cast(str, account_id),
            provider='sso',
        )

    def _client(self, service: str, prefix: str, service_id: str, region: str) -> Client.object:
        return Client.new(
            service=service,
            endpoint_prefix=prefix,
            service_id=service_id,
            region=region,
            config=self.config,
            unsigned=True,
            ua=self.ua,
        )

    # The access token of the cache, refreshed with SSO OIDC before it expires, of a section sso-session only, as the
    # AWS CLI writes the client and the refresh token of the registration for those only; the old token, while it is
    # valid, when the refresh fails, as the SDKs of AWS do, so that a failure of SSO OIDC does not end a session
    async def _token(self, key: str, region: str, refreshable: bool) -> str:
        path = self.cache_file(key)
        login = f'aws sso login --profile {self.profile}'
        try:
            data: Any = Pyjo.JSON.decode_json(path.slurp())
        except FileNotFoundError:
            raise Pyjo.Exception.new(f'No token of the SSO of {key} of AWS in {path}: {login}') from None
        except Exception as e:
            raise Pyjo.Exception.new(f'Invalid token of the SSO of {key} of AWS in {path}: {_message(e)}') from e
        cached = cast(dict[str, Any], data) if isinstance(data, dict) else {}
        if not cached.get('accessToken') or not cached.get('expiresAt'):
            raise Pyjo.Exception.new(f'Invalid token of the SSO of {key} of AWS in {path}: {login}')

        now = time.time()
        expires_in = float(Credentials.parse_time(cached['expiresAt'])) - now
        if expires_in > self.refresh:
            return cached['accessToken']

        registered = cached.get('registrationExpiresAt')
        if (
            refreshable
            and cached.get('refreshToken')
            and cached.get('clientId')
            and cached.get('clientSecret')
            and isinstance(registered, str)
            and float(Credentials.parse_time(registered)) > now
        ):
            call = RestJSON.new(
                'POST',
                '/token',
                {
                    'grantType': 'refresh_token',
                    'clientId': cached['clientId'],
                    'clientSecret': cached['clientSecret'],
                    'refreshToken': cached['refreshToken'],
                },
            )
            try:
                created = await self._client('sso-oauth', 'oidc', 'SSO OIDC', region).steps(call)
            except Exception as e:
                if expires_in > 0:
                    return cached['accessToken']
                raise Pyjo.Exception.new(
                    f'Cannot refresh the token of the SSO of {key} of AWS: {_message(e)}: {login}'
                ) from e
            fields = cast(dict[str, Any], created)
            expiration = Pyjo.Date.new(int(time.time()) + int(fields['expiresIn']))
            cached.update(
                accessToken=fields['accessToken'],
                expiresAt=expiration.to_rfc3339(),
                refreshToken=fields.get('refreshToken') or cached['refreshToken'],
            )
            Provider.write_cache(path, cached)
            return cached['accessToken']

        if expires_in > 0:
            return cached['accessToken']
        raise Pyjo.Exception.new(f'The token of the SSO of {key} of AWS expired at {cached["expiresAt"]}: {login}')


# The message of an exception in another, without the new line that str of a Pyjo.Exception ends with
def _message(e: Exception) -> str:
    return e.message if isinstance(e, Pyjo.Exception.object) else str(e)


new = Pyjo_AWS_Credentials_SSO.new
object = Pyjo_AWS_Credentials_SSO
SSO = Pyjo_AWS_Credentials_SSO
