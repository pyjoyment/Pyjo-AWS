"""
Pyjo.AWS.Credentials.Environment - Credentials of the environment
=================================================================
::

    from Pyjo.AWS.Credentials.Environment import Environment

    credentials = Environment().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.Environment

    credentials = Pyjo.AWS.Credentials.Environment.new().credentials()

:mod:`Pyjo.AWS.Credentials.Environment` is the provider of the credentials
of the environment variables ``AWS_ACCESS_KEY_ID``, ``AWS_SECRET_ACCESS_KEY``
and ``AWS_SESSION_TOKEN``, with ``AWS_CREDENTIAL_EXPIRATION`` and
``AWS_ACCOUNT_ID``, as AWS Lambda, the OIDC of GitHub Actions and
``aws configure export-credentials`` set them. An empty variable is none, and
an access key without its secret is an error.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Chain`.

Classes
-------
"""

import Pyjo.Exception

from Pyjo.Util import getenv

from .. import Credentials
from . import Provider


class Pyjo_AWS_Credentials_Environment(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Environment` inherits all attributes and
    methods from :mod:`Pyjo.AWS.Credentials.Provider` and implements the
    following new ones.
    """

    def fetch(self) -> Provider.Steps:
        """::

            credentials = yield from provider.fetch()

        The credentials of the environment, or ``None`` without
        ``AWS_ACCESS_KEY_ID`` and ``AWS_SECRET_ACCESS_KEY``.
        """
        access_key_id = getenv('AWS_ACCESS_KEY_ID') or None
        secret_access_key = getenv('AWS_SECRET_ACCESS_KEY') or None
        if access_key_id is None and secret_access_key is None:
            return None
        if access_key_id is None or secret_access_key is None:
            raise Pyjo.Exception.new(
                'Partial credentials of AWS in the environment: '
                f'no {"AWS_ACCESS_KEY_ID" if access_key_id is None else "AWS_SECRET_ACCESS_KEY"}'
            )
        expiration = getenv('AWS_CREDENTIAL_EXPIRATION') or None
        return Credentials.new(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            session_token=getenv('AWS_SESSION_TOKEN') or None,
            expiration=Credentials.parse_time(expiration) if expiration else None,
            account_id=getenv('AWS_ACCOUNT_ID') or None,
            provider='environment',
        )
        yield

    def is_fresh(self) -> bool:
        """::

            boolean = provider.is_fresh()

        Always false, as the environment may change, and reading it costs
        nothing.
        """
        return False


new = Pyjo_AWS_Credentials_Environment.new
object = Pyjo_AWS_Credentials_Environment
Environment = Pyjo_AWS_Credentials_Environment
