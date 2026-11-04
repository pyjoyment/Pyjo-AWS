"""
Pyjo.AWS.Credentials.Profile - Credentials of a profile of the shared files
===========================================================================
::

    from Pyjo.AWS.Credentials.Profile import Profile

    credentials = Profile().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Config
    import Pyjo.AWS.Credentials.Profile

    provider = Pyjo.AWS.Credentials.Profile.new(config=Pyjo.AWS.Config.new(profile='dev'))
    print(provider.credentials().access_key_id)

:mod:`Pyjo.AWS.Credentials.Profile` is the provider of the credentials of a
profile of the shared files of :mod:`Pyjo.AWS.Config`, as the SDKs of AWS
take them: the keys ``aws_access_key_id``, ``aws_secret_access_key`` and
``aws_session_token`` of the profile, or the program of its
``credential_process``, of :mod:`Pyjo.AWS.Credentials.Process`, or the role
of IAM Identity Center of its ``sso_session`` or ``sso_start_url``, of
:mod:`Pyjo.AWS.Credentials.SSO`, which comes before them, or its
``role_arn``, which comes first: ::

    [profile admin]
    role_arn = arn:aws:iam::123456789012:role/admin
    source_profile = dev
    role_session_name = alice
    external_id = 4c1d0e4f
    duration_seconds = 900

The role of ``source_profile`` is assumed with the credentials of that
profile, of :mod:`Pyjo.AWS.Credentials.AssumeRole`, which may be a role
itself, whose cycle is an error; a source profile with its own keys gives
those, without its role, as botocore does, so that a profile may be the
source of its own role. The role of ``credential_source = Environment`` is
assumed with the credentials of the environment, and the role of
``web_identity_token_file`` with the token of the file, of
:mod:`Pyjo.AWS.Credentials.WebIdentity`. A role with ``mfa_serial`` is an
error, as there is no prompt for the code.

A profile that is not in the files is an error, but the profile ``default``,
which a machine without the files has not either.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Config`,
:mod:`Pyjo.AWS.Credentials.Process`, :mod:`Pyjo.AWS.Credentials.SSO`,
:mod:`Pyjo.AWS.Credentials.AssumeRole`, :mod:`Pyjo.AWS.Credentials.WebIdentity`.

Classes
-------
"""

import Pyjo.Exception

from .. import Config, Credentials
from . import SSO, AssumeRole, Environment, Process, Provider, WebIdentity

from collections.abc import Collection
from typing import Any


class Pyjo_AWS_Credentials_Profile(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Profile` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Credentials.Provider` and implements the following
    new ones.
    """

    def __init__(
        self,
        *,
        config: Config.object | None = None,
        profile: str | None = None,
        roles: bool = True,
        visited: Collection[str] = (),
        **kwargs: Any,
    ) -> None:
        """::

            provider = Pyjo.AWS.Credentials.Profile.new()
            provider = Pyjo.AWS.Credentials.Profile.new(config=Pyjo.AWS.Config.new(profile='dev'))
            provider = Pyjo.AWS.Credentials.Profile.new(profile='dev', roles=False)

        Construct a new :mod:`Pyjo.AWS.Credentials.Profile` object, with the
        options of :mod:`Pyjo.AWS.Credentials.Provider`.
        """
        super().__init__(**kwargs)

        self.config = config or Config.new()
        """::

            config = provider.config
            provider.config = Pyjo.AWS.Config.new(profile='dev')

        The shared files, a new :mod:`Pyjo.AWS.Config` object by default.
        """

        self.profile = profile or self.config.profile
        """::

            name = provider.profile

        The name of the profile, the
        :attr:`~Pyjo.AWS.Config.Pyjo_AWS_Config.profile` of :attr:`config`
        by default.
        """

        self.roles = roles
        """::

            boolean = provider.roles

        Assume the role of ``role_arn``, true by default, and false for a
        source profile with keys of its own.
        """

        self.visited = frozenset(visited)
        """::

            names = provider.visited

        The profiles whose roles have this one as their source, of which a
        source profile is a cycle.
        """

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of the profile, or ``None`` of a profile without them.
        """
        config, name = self.config, self.profile
        if not config.has_profile(name):
            if name == 'default' and not self.visited:
                return None
            raise Pyjo.Exception.new(f'The profile {name} of AWS is not in {config.config_file}')
        settings = config.settings(name)

        if self.roles and (role_arn := settings.get('role_arn')):
            return await self._role(name, settings, role_arn)

        if settings.get('sso_session') or settings.get('sso_start_url'):
            return await SSO.new(config=config, profile=name, ua=self.ua, refresh=self.refresh).fetch()

        access_key_id = settings.get('aws_access_key_id') or None
        secret_access_key = settings.get('aws_secret_access_key') or None
        if access_key_id is not None or secret_access_key is not None:
            if access_key_id is None or secret_access_key is None:
                missing = 'aws_access_key_id' if access_key_id is None else 'aws_secret_access_key'
                raise Pyjo.Exception.new(f'Partial credentials of the profile {name} of AWS: no {missing}')
            return Credentials.new(
                access_key_id=access_key_id,
                secret_access_key=secret_access_key,
                session_token=settings.get('aws_session_token') or None,
                account_id=settings.get('aws_account_id') or None,
                provider='profile',
            )

        if command := settings.get('credential_process'):
            return await Process.new(command=command, ua=self.ua).fetch()

        return None

    # The role of a profile, of its source_profile or credential_source, as AssumeRole of botocore resolves it, or of
    # its web_identity_token_file, which comes after them
    async def _role(self, name: str, settings: dict[str, Any], role_arn: str) -> Credentials.object | None:
        config = self.config
        source_profile = settings.get('source_profile') or None
        credential_source = settings.get('credential_source') or None
        token_file = settings.get('web_identity_token_file') or None
        role_session_name = settings.get('role_session_name') or None
        duration_seconds = _seconds(name, settings.get('duration_seconds'))
        region = config.region(name)

        if source_profile is None and credential_source is None:
            if token_file is None:
                raise Pyjo.Exception.new(
                    f'The role of the profile {name} of AWS has no source_profile, credential_source '
                    'or web_identity_token_file'
                )
            return await WebIdentity.new(
                role_arn=role_arn,
                token_file=token_file,
                role_session_name=role_session_name,
                duration_seconds=duration_seconds,
                region=region,
                config=config,
                ua=self.ua,
            ).fetch()

        if source_profile is not None and credential_source is not None:
            raise Pyjo.Exception.new(
                f'The role of the profile {name} of AWS has both source_profile and credential_source'
            )
        if settings.get('mfa_serial'):
            raise Pyjo.Exception.new(f'The role of the profile {name} of AWS has mfa_serial, which is not supported')

        source: Provider.object
        if source_profile is not None:
            if not config.has_profile(source_profile):
                raise Pyjo.Exception.new(
                    f'The source_profile {source_profile} of the profile {name} of AWS is not in {config.config_file}'
                )
            keys = bool(config.settings(source_profile).get('aws_access_key_id'))
            visited = self.visited | {name}
            if not keys and source_profile in visited:
                cycle = ' -> '.join([*sorted(visited), source_profile])
                raise Pyjo.Exception.new(f'A cycle of the source_profile of AWS: {cycle}')
            source = Profile.new(
                config=config, profile=source_profile, roles=not keys, visited=visited, ua=self.ua, refresh=self.refresh
            )
        elif credential_source == 'Environment':
            source = Environment.new(ua=self.ua)
        elif credential_source in ('Ec2InstanceMetadata', 'EcsContainer'):
            # TODO: the container and IMDS of the next step
            raise Pyjo.Exception.new(
                f'The credential_source {credential_source} of the profile {name} of AWS is not supported yet'
            )
        else:
            raise Pyjo.Exception.new(f'Invalid credential_source {credential_source} of the profile {name} of AWS')

        return await AssumeRole.new(
            source=source,
            role_arn=role_arn,
            role_session_name=role_session_name,
            external_id=settings.get('external_id') or None,
            duration_seconds=duration_seconds,
            region=region,
            config=config,
            ua=self.ua,
        ).fetch()


def _seconds(name: str, value: Any) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise Pyjo.Exception.new(f'Invalid duration_seconds {value} of the profile {name} of AWS') from None


new = Pyjo_AWS_Credentials_Profile.new
object = Pyjo_AWS_Credentials_Profile
Profile = Pyjo_AWS_Credentials_Profile
