"""
Pyjo.AWS.Credentials - Credentials of AWS
=========================================
::

    from Pyjo.AWS.Credentials import Credentials

    credentials = Credentials(access_key_id='AKIDEXAMPLE', secret_access_key='secret')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.Chain

    # The credentials that the SDKs of AWS find, blocking
    credentials = Pyjo.AWS.Credentials.Chain.new().credentials()
    print(credentials.access_key_id, credentials.expiration, credentials.provider)

    # Non-blocking
    Pyjo.AWS.Credentials.Chain.new().credentials_p().then(lambda credentials: print(credentials.provider)).wait()

:mod:`Pyjo.AWS.Credentials` is the credentials of AWS that sign a request:
an access key, with the session token and the expiration of temporary
credentials. A provider of :mod:`Pyjo.AWS.Credentials.Provider` gets them,
as :mod:`Pyjo.AWS.Credentials.Chain` gets them from the places where the SDKs
of AWS find them.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Chain`,
:mod:`Pyjo.AWS.SigV4`, :mod:`Pyjo.AWS`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception

import datetime


class Pyjo_AWS_Credentials(Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.Credentials` inherits all attributes and methods from
    :mod:`Pyjo.Base` and implements the following new ones.
    """

    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        session_token: str | None = None,
        expiration: datetime.datetime | None = None,
        account_id: str | None = None,
        provider: str | None = None,
    ) -> None:
        """::

            credentials = Pyjo.AWS.Credentials.new(access_key_id='AKIDEXAMPLE', secret_access_key='secret')

        Construct a new :mod:`Pyjo.AWS.Credentials` object.
        """
        self.access_key_id = access_key_id
        """::

            access_key_id = credentials.access_key_id

        The access key ID.
        """

        self.secret_access_key = secret_access_key
        """::

            secret_access_key = credentials.secret_access_key

        The secret access key.
        """

        self.session_token = session_token
        """::

            session_token = credentials.session_token

        The session token of temporary credentials, or ``None``.
        """

        self.expiration = expiration
        """::

            expiration = credentials.expiration

        The time when temporary credentials expire, with its time zone, or
        ``None`` for credentials that do not expire.
        """

        self.account_id = account_id
        """::

            account_id = credentials.account_id

        The ID of the account of the credentials, where the provider knows it,
        or ``None``.
        """

        self.provider = provider
        """::

            name = credentials.provider

        The name of the provider of the credentials, as ``environment`` or
        ``profile``, or ``None``.
        """

    def __repr__(self) -> str:
        # Without the secrets, which a log or a traceback would show
        return f'<Credentials access_key_id={self.access_key_id!r} provider={self.provider!r}>'

    def expires_in(self, now: datetime.datetime | None = None) -> float | None:
        """::

            seconds = credentials.expires_in()

        The number of seconds until the credentials expire, negative once they
        have, or ``None`` for credentials that do not expire.
        """
        if self.expiration is None:
            return None
        return (self.expiration - (now or datetime.datetime.now(datetime.UTC))).total_seconds()


def parse_time(value: str) -> datetime.datetime:
    """::

        expiration = Pyjo.AWS.Credentials.parse_time('2026-11-03T12:00:00Z')

    A time of RFC 3339, as the expiration of credentials, with its time zone,
    UTC when it has none.
    """
    try:
        time = datetime.datetime.fromisoformat(value.strip())
    except ValueError as e:
        raise Pyjo.Exception.new(f'Invalid time of the expiration of credentials of AWS: {value!r}') from e
    return time if time.tzinfo is not None else time.replace(tzinfo=datetime.UTC)


new = Pyjo_AWS_Credentials.new
object = Pyjo_AWS_Credentials
Credentials = Pyjo_AWS_Credentials
