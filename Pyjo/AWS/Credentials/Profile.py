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
``credential_process``, of :mod:`Pyjo.AWS.Credentials.Process`.

A profile that is not in the files is an error, but the profile ``default``,
which a machine without the files has not either.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Config`,
:mod:`Pyjo.AWS.Credentials.Process`.

Classes
-------
"""

import Pyjo.Exception

from .. import Config, Credentials
from . import Process, Provider

from typing import Any


class Pyjo_AWS_Credentials_Profile(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Profile` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Credentials.Provider` and implements the following
    new ones.
    """

    def __init__(self, *, config: Config.object | None = None, **kwargs: Any) -> None:
        """::

            provider = Pyjo.AWS.Credentials.Profile.new()
            provider = Pyjo.AWS.Credentials.Profile.new(config=Pyjo.AWS.Config.new(profile='dev'))

        Construct a new :mod:`Pyjo.AWS.Credentials.Profile` object, with the
        options of :mod:`Pyjo.AWS.Credentials.Provider`.
        """
        super().__init__(**kwargs)

        self.config = config or Config.new()
        """::

            config = provider.config
            provider.config = Pyjo.AWS.Config.new(profile='dev')

        The shared files, whose :attr:`~Pyjo.AWS.Config.Pyjo_AWS_Config.profile`
        is the one of the credentials, a new :mod:`Pyjo.AWS.Config` object by
        default.
        """

    def fetch(self) -> Provider.Steps:
        """::

            credentials = yield from provider.fetch()

        The credentials of the profile, or ``None`` of a profile without them.
        """
        config = self.config
        name = config.profile
        if not config.has_profile(name):
            if name == 'default':
                return None
            raise Pyjo.Exception.new(f'The profile {name} of AWS is not in {config.config_file}')
        settings = config.settings(name)

        # TODO: role_arn, web_identity_token_file, sso_session and sso_start_url, which come before the keys

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
            return (yield from Process.new(command=command, ua=self.ua).fetch())

        return None


new = Pyjo_AWS_Credentials_Profile.new
object = Pyjo_AWS_Credentials_Profile
Profile = Pyjo_AWS_Credentials_Profile
