"""
Pyjo.AWS.Config - Shared configuration files of AWS
===================================================
::

    from Pyjo.AWS.Config import Config

    config = Config()
    print(config.profile, config.region(), config.get('role_arn'))

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Config

    config = Pyjo.AWS.Config.new(profile='dev')
    print(config.settings())
    print(config.endpoint_url('S3'))

:mod:`Pyjo.AWS.Config` reads the shared configuration files of AWS,
``~/.aws/config`` and ``~/.aws/credentials``, as the SDKs of AWS and the AWS
CLI read them: the settings of a profile, the sections ``sso-session`` and
``services``, the region and the endpoint of a service.

The files are those of the ``AWS_CONFIG_FILE`` and
``AWS_SHARED_CREDENTIALS_FILE`` environment variables, or of the home
directory, and the profile is the one of the ``AWS_PROFILE`` environment
variable, or ``default``. A profile is ``[profile name]`` or ``[default]`` in
the configuration file, and ``[name]`` in the file of the credentials, whose
settings come first. The names of the settings are in lower case, as the
SDKs of AWS read them, and a setting without a value on its line has the
settings of the indented lines below it, as ``s3``: ::

    [profile dev]
    region = eu-central-1
    s3 =
        addressing_style = path

The files are read when a method needs them, once, and a file that does not
exist has no sections.

See also
--------

:mod:`Pyjo.AWS`,
https://docs.aws.amazon.com/sdkref/latest/guide/file-format.html.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception
import Pyjo.File

from Pyjo.Util import getenv

import configparser
import re

from typing import Any, cast


class Pyjo_AWS_Config(Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.Config` inherits all attributes and methods from
    :mod:`Pyjo.Base` and implements the following new ones.
    """

    def __init__(
        self, *, profile: str | None = None, config_file: str | None = None, credentials_file: str | None = None
    ) -> None:
        """::

            config = Pyjo.AWS.Config.new()
            config = Pyjo.AWS.Config.new(profile='dev', config_file='/etc/aws/config')

        Construct a new :mod:`Pyjo.AWS.Config` object.
        """
        self.profile = profile or getenv('AWS_PROFILE') or getenv('AWS_DEFAULT_PROFILE') or 'default'
        """::

            name = config.profile
            config.profile = 'dev'

        The name of the profile, defaults to the value of the ``AWS_PROFILE``
        environment variable, or of ``AWS_DEFAULT_PROFILE``, which the AWS CLI
        reads too, or ``default``.
        """

        self.explicit_profile = bool(profile)
        """::

            boolean = config.explicit_profile

        Whether the profile is the one of the argument ``profile``, as of the
        option ``--profile`` of the AWS CLI, not of the environment, so that
        :mod:`Pyjo.AWS.Credentials.Chain` takes the credentials of the
        profile, and not the ones of the environment, as botocore does.
        """

        self.config_file = Pyjo.File.new(config_file or getenv('AWS_CONFIG_FILE') or '~/.aws/config').expanduser()
        """::

            path = config.config_file
            config.config_file = '/etc/aws/config'

        The :mod:`Pyjo.File` object of the configuration file, defaults to the value of the
        ``AWS_CONFIG_FILE`` environment variable or ``~/.aws/config``.
        """

        self.credentials_file = Pyjo.File.new(
            credentials_file or getenv('AWS_SHARED_CREDENTIALS_FILE') or '~/.aws/credentials'
        ).expanduser()
        """::

            path = config.credentials_file
            config.credentials_file = '/etc/aws/credentials'

        The :mod:`Pyjo.File` object of the file of the credentials, defaults to the value of the
        ``AWS_SHARED_CREDENTIALS_FILE`` environment variable or
        ``~/.aws/credentials``.
        """

        self._sections: dict[str, dict[str, dict[str, Any]]] | None = None

    def endpoint_url(self, service: str, profile: str | None = None) -> str | None:
        """::

            url = config.endpoint_url('S3')
            url = config.endpoint_url('SSO OIDC', 'dev')

        The endpoint of a service of its ID, as ``S3``, ``Lambda`` or
        ``SSO OIDC``, which the environment or a profile, :attr:`profile` by
        default, configures, or ``None``: the value of the
        ``AWS_ENDPOINT_URL_<SERVICE>`` environment variable, of the setting
        ``endpoint_url`` of the service in the section ``services`` of the
        profile, of ``AWS_ENDPOINT_URL``, or of the setting ``endpoint_url`` of
        the profile, unless ``AWS_IGNORE_CONFIGURED_ENDPOINT_URLS`` or the
        setting ``ignore_configured_endpoint_urls`` is ``true``.
        """
        settings = self.settings(profile)
        ignore = getenv('AWS_IGNORE_CONFIGURED_ENDPOINT_URLS') or settings.get('ignore_configured_endpoint_urls')
        if _is_true(ignore):
            return None
        key = re.sub(r'[\s-]+', '_', service.strip())
        if url := getenv(f'AWS_ENDPOINT_URL_{key.upper()}'):
            return url
        if (name := settings.get('services')) is not None:
            section = self.services(name).get(key.lower())
            if isinstance(section, dict) and (url := cast(dict[str, str], section).get('endpoint_url')):
                return url
        return getenv('AWS_ENDPOINT_URL') or settings.get('endpoint_url') or None

    def get(self, name: str, profile: str | None = None) -> Any:
        """::

            value = config.get('role_arn')
            s3 = config.get('s3', 'dev')

        The value of a setting of a profile, :attr:`profile` by default, a
        string, or a :class:`dict` of the settings of its indented lines, or
        ``None``.
        """
        return self.settings(profile).get(name.lower())

    def has_profile(self, profile: str | None = None) -> bool:
        """::

            boolean = config.has_profile('dev')

        Whether a profile, :attr:`profile` by default, is in one of the files.
        """
        return (profile or self.profile) in self._load()['profile']

    def profiles(self) -> list[str]:
        """::

            names = config.profiles()

        The names of the profiles of both files, sorted.
        """
        return sorted(self._load()['profile'])

    def region(self, profile: str | None = None) -> str | None:
        """::

            region = config.region()
            region = config.region('dev')

        The region, of the value of the ``AWS_REGION`` environment variable, of
        ``AWS_DEFAULT_REGION``, or of the setting ``region`` of a profile,
        :attr:`profile` by default, or ``None``.
        """
        return getenv('AWS_REGION') or getenv('AWS_DEFAULT_REGION') or self.get('region', profile) or None

    def services(self, name: str) -> dict[str, Any]:
        """::

            services = config.services('local')

        The settings of a section ``[services name]`` of the configuration
        file, of a service of its ID in lower case, with ``_`` in the place of
        the spaces, as ``sso_oidc``, or an empty :class:`dict`.
        """
        return dict(self._load()['services'].get(name, {}))

    def settings(self, profile: str | None = None) -> dict[str, Any]:
        """::

            settings = config.settings()
            settings = config.settings('dev')

        The settings of a profile, :attr:`profile` by default, of the
        configuration file, with those of the file of the credentials over them,
        or an empty :class:`dict`.
        """
        return dict(self._load()['profile'].get(profile or self.profile, {}))

    def sso_session(self, name: str) -> dict[str, Any]:
        """::

            session = config.sso_session('company')

        The settings of a section ``[sso-session name]`` of the configuration
        file, or an empty :class:`dict`.
        """
        return dict(self._load()['sso-session'].get(name, {}))

    def _load(self) -> dict[str, dict[str, dict[str, Any]]]:
        if self._sections is not None:
            return self._sections
        sections: dict[str, dict[str, dict[str, Any]]] = {'profile': {}, 'sso-session': {}, 'services': {}}
        # The default profile of [profile default] over the one of [default], as the AWS CLI takes it
        for section, settings in sorted(_parse(self.config_file).items(), key=lambda item: item[0] != 'default'):
            kind, _, name = section.partition(' ')
            if section == 'default':
                kind, name = 'profile', 'default'
            if kind in sections and (name := name.strip()):
                sections[kind].setdefault(name, {}).update(settings)
        for name, settings in _parse(self.credentials_file).items():
            sections['profile'].setdefault(name.strip(), {}).update(settings)
        self._sections = sections
        return sections


def _is_true(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() == 'true'


# The sections of a file of INI, with the settings of the indented lines below a setting without a value as a dict, as
# botocore parses them, or none of a file that does not exist
def _parse(path: Pyjo.File.object) -> dict[str, dict[str, Any]]:
    # A section that is not unique is merged, and a section named DEFAULT is a profile as any other
    parser = configparser.RawConfigParser(strict=False, default_section='\0')
    try:
        if not parser.read(path, encoding='utf-8'):
            return {}
    except configparser.Error as e:
        raise Pyjo.Exception.new(f'Cannot parse the configuration file of AWS {path}: {e.message}') from e
    result: dict[str, dict[str, Any]] = {}
    for section in parser.sections():
        settings: dict[str, Any] = {}
        for name, value in parser.items(section):
            settings[name] = _subsection(path, value) if value.startswith('\n') else value
        result[section] = settings
    return result


def _subsection(path: Pyjo.File.object, value: str) -> dict[str, str]:
    settings: dict[str, str] = {}
    for line in value.splitlines():
        if not line.strip():
            continue
        name, sep, item = line.partition('=')
        if not sep:
            raise Pyjo.Exception.new(f'Cannot parse the configuration file of AWS {path}: {line.strip()!r}')
        settings[name.strip()] = item.strip()
    return settings


new = Pyjo_AWS_Config.new
object = Pyjo_AWS_Config
Config = Pyjo_AWS_Config
