"""
Pyjo.AWS.Credentials.Login - Credentials of aws login
=====================================================
::

    from Pyjo.AWS.Credentials.Login import Login

    credentials = Login().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Config
    import Pyjo.AWS.Credentials.Login

    provider = Pyjo.AWS.Credentials.Login.new(config=Pyjo.AWS.Config.new(profile='console'))
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.Login` is the provider of the credentials of a
profile of ``aws login``, the credentials of a session of the AWS Management
Console, as the SDKs of AWS get them: the credentials of the cache of the AWS
CLI, in ``~/.aws/login/cache``, of the ``login_session`` of the profile, which
``aws login`` writes: ::

    [profile console]
    login_session = arn:aws:sts::123456789012:assumed-role/Admin/alice
    region = eu-central-1

The credentials, of 15 minutes, are refreshed before they expire with
``CreateOAuth2Token`` of the sign-in service of AWS in the region of the
profile, with the refresh token of the cache and the proof of possession of
its key, of DPoP, of RFC 9449, which :mod:`Pyjo.AWS.ECDSA` signs, and written
back to the cache, as the AWS CLI does, for the hours of the session of the
console.

A session that is not in the cache is an error, and so is one whose refresh
token has expired, which tells to run ``aws login``.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Profile`,
:mod:`Pyjo.AWS.ECDSA`,
https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html.

Classes
-------
"""

import Pyjo.Date
import Pyjo.Exception
import Pyjo.JSON

from Pyjo.Util import getenv, sha256_sum

from .. import ECDSA, Client, Config, Credentials, Error
from ..Protocol import RestJSON
from . import Provider

import os
import time
import uuid

from typing import Any, cast


_REQUIRED = ('accessToken', 'refreshToken', 'dpopKey', 'clientId')
_LOGIN_AGAIN = ('TOKEN_EXPIRED', 'USER_CREDENTIALS_CHANGED')


class Pyjo_AWS_Credentials_Login(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Login` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Credentials.Provider` and implements the following
    new ones.
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

            provider = Pyjo.AWS.Credentials.Login.new()
            provider = Pyjo.AWS.Credentials.Login.new(config=Pyjo.AWS.Config.new(profile='console'))
            provider = Pyjo.AWS.Credentials.Login.new(profile='console', cache_dir='/tmp/login')

        Construct a new :mod:`Pyjo.AWS.Credentials.Login` object, with the
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

        directory = cache_dir or getenv('AWS_LOGIN_CACHE_DIRECTORY') or '~/.aws/login/cache'
        self.cache_dir = os.path.expanduser(os.path.expandvars(directory))
        """::

            path = provider.cache_dir

        The directory of the cache of the sessions, of the
        ``AWS_LOGIN_CACHE_DIRECTORY`` environment variable, or
        ``~/.aws/login/cache`` of the AWS CLI by default.
        """

    def cache_file(self, session: str) -> str:
        """::

            path = provider.cache_file('arn:aws:sts::123456789012:assumed-role/Admin/alice')

        The file of a session in :attr:`cache_dir`, of the SHA-256 of its
        name, as the AWS CLI names it.
        """
        return os.path.join(self.cache_dir, sha256_sum(session.encode()) + '.json')

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of the session of the profile, refreshed before they
        expire, or ``None`` of a profile without ``login_session``.
        """
        session: str | None = self.config.settings(self.profile).get('login_session') or None
        if session is None:
            return None
        path = self.cache_file(session)
        login = f'aws login --profile {self.profile}'
        cached = _load(session, path, login)
        credentials = _credentials(cached)
        expires_in = cast(float, credentials.expires_in())
        if expires_in > self.refresh:
            return credentials

        try:
            created = await self._create_token(cached)
        except Exception as e:
            if expires_in > 0:
                return credentials
            reason = _reason(e)
            if reason in _LOGIN_AGAIN:
                raise Pyjo.Exception.new(f'The login session {session} of AWS has ended ({reason}): {login}') from e
            raise Pyjo.Exception.new(
                f'Cannot refresh the credentials of the login session {session} of AWS: {_message(e)}: {login}'
            ) from e

        fields = cast(dict[str, Any], created) if isinstance(created, dict) else {}
        token: Any = fields.get('accessToken')
        if not isinstance(token, dict) or not fields.get('expiresIn') or not fields.get('refreshToken'):
            raise Pyjo.Exception.new(f'Invalid response of the sign-in service of AWS for the login session {session}')
        access = cast(dict[str, Any], token)
        expiration = Pyjo.Date.new(int(time.time()) + int(fields['expiresIn']))
        cached.update(
            accessToken={
                'accessKeyId': access['accessKeyId'],
                'secretAccessKey': access['secretAccessKey'],
                'sessionToken': access['sessionToken'],
                'accountId': cached['accessToken'].get('accountId'),
                'expiresAt': expiration.to_rfc3339(),
            },
            refreshToken=fields['refreshToken'],
        )
        Provider.write_cache(path, cached)
        return _credentials(cached)

    def endpoint_url(self) -> str:
        """::

            url = provider.endpoint_url()

        The URL of the sign-in service, the one of the ID ``Signin`` that the
        environment or the profile configures, or the one of the region of
        the profile, as ``https://eu-central-1.signin.aws.amazon.com``.
        """
        if url := self.config.endpoint_url('Signin', self.profile):
            return url
        region = self.config.region(self.profile)
        if not region:
            raise Pyjo.Exception.new(
                f'No region of AWS for the sign-in service of the profile {self.profile}: AWS_REGION or region'
            )
        suffix = 'amazonaws.cn' if region.startswith('cn-') else 'aws.amazon.com'
        return f'https://{region}.signin.{suffix}'

    # CreateOAuth2Token of the refresh token, unsigned, with the proof of DPoP of the key of the session for the URL of
    # the request, as botocore sends it
    async def _create_token(self, cached: dict[str, Any]) -> Any:
        url = self.endpoint_url()
        try:
            key = ECDSA.from_pem(cached['dpopKey'])
        except Pyjo.Exception.object as e:
            raise Pyjo.Exception.new(f'Invalid dpopKey of the cache: {e.message}') from e
        client = Client.new(
            service='signin', service_id='Signin', endpoint=url, config=self.config, unsigned=True, ua=self.ua
        )
        call = RestJSON.new(
            'POST',
            '/v1/token',
            {'clientId': cached['clientId'], 'refreshToken': cached['refreshToken'], 'grantType': 'refresh_token'},
            headers={'DPoP': dpop(key, url.rstrip('/') + '/v1/token')},
        )
        return await client.steps(call)


def dpop(key: ECDSA.object, url: str, method: str = 'POST') -> str:
    """::

        proof = Pyjo.AWS.Credentials.Login.dpop(key, 'https://eu-central-1.signin.aws.amazon.com/v1/token')

    The proof of possession of a key of DPoP, of RFC 9449, for a request, a
    JSON Web Token of ES256 with the public key, as the sign-in service of
    AWS wants it.
    """
    header = {'typ': 'dpop+jwt', 'alg': 'ES256', 'jwk': key.jwk()}
    payload = {'htm': method, 'htu': url, 'iat': int(time.time()), 'jti': str(uuid.uuid4())}
    signing_input = f'{_segment(header)}.{_segment(payload)}'
    return f'{signing_input}.{ECDSA.base64url(key.sign(signing_input.encode()))}'


def _segment(value: dict[str, Any]) -> str:
    return ECDSA.base64url(Pyjo.JSON.encode_json(value))


# The token of the cache, with the fields that botocore requires, of which the key and the refresh token are needed only
# once the credentials expire
def _load(session: str, path: str, login: str) -> dict[str, Any]:
    try:
        with open(path, 'rb') as f:
            data: Any = Pyjo.JSON.decode_json(f.read())
    except FileNotFoundError:
        raise Pyjo.Exception.new(f'No login session {session} of AWS in {path}: {login}') from None
    except Exception as e:
        raise Pyjo.Exception.new(f'Invalid login session {session} of AWS in {path}: {_message(e)}') from e
    cached = cast(dict[str, Any], data) if isinstance(data, dict) else {}
    missing = [field for field in _REQUIRED if not cached.get(field)]
    access: Any = cached.get('accessToken')
    if not missing and not isinstance(access, dict):
        missing = ['accessToken']
    elif not missing:
        fields = cast(dict[str, Any], access)
        missing = [
            f'accessToken.{field}' for field in ('accessKeyId', 'secretAccessKey', 'expiresAt') if not fields.get(field)
        ]
    if missing:
        raise Pyjo.Exception.new(f'Invalid login session {session} of AWS in {path}: no {", ".join(missing)}: {login}')
    return cached


def _credentials(cached: dict[str, Any]) -> Credentials.object:
    access = cast(dict[str, Any], cached['accessToken'])
    return Credentials.new(
        access_key_id=access['accessKeyId'],
        secret_access_key=access['secretAccessKey'],
        session_token=access.get('sessionToken') or None,
        expiration=Credentials.parse_time(access['expiresAt']),
        account_id=access.get('accountId') or None,
        provider='login',
    )


# The OAuth error of an AccessDeniedException of the sign-in service, as TOKEN_EXPIRED, in its field error
def _reason(e: Exception) -> str | None:
    if not isinstance(e, Error.object) or e.tx is None:
        return None
    try:
        data: Any = e.tx.res.json()
    except Exception:
        return None
    reason = cast(dict[str, Any], data).get('error') if isinstance(data, dict) else None
    return reason if isinstance(reason, str) else None


# The message of an exception in another, without the new line that str of a Pyjo.Exception ends with
def _message(e: Exception) -> str:
    return e.message if isinstance(e, Pyjo.Exception.object) else str(e)


new = Pyjo_AWS_Credentials_Login.new
object = Pyjo_AWS_Credentials_Login
Login = Pyjo_AWS_Credentials_Login
