"""
Pyjo.AWS.Credentials.Static - Credentials that do not change
============================================================
::

    from Pyjo.AWS.Credentials import Credentials
    from Pyjo.AWS.Credentials.Static import Static

    provider = Static(Credentials(access_key_id='AKIDEXAMPLE', secret_access_key='secret'))

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Client
    import Pyjo.AWS.Credentials
    import Pyjo.AWS.Credentials.Static

    credentials = Pyjo.AWS.Credentials.new(access_key_id='AKIDEXAMPLE', secret_access_key='secret')
    sts = Pyjo.AWS.Client.new(service='sts', credentials=Pyjo.AWS.Credentials.Static.new(credentials))

:mod:`Pyjo.AWS.Credentials.Static` is the provider of credentials that it
is given, as those of a program of its own, or the keys of a profile that
are the source of its role.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials`.

Classes
-------
"""

from .. import Credentials
from . import Provider

from typing import Any


class Pyjo_AWS_Credentials_Static(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Static` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Credentials.Provider` and implements the following
    new ones.
    """

    def __init__(self, value: Credentials.object, **kwargs: Any) -> None:
        """::

            provider = Pyjo.AWS.Credentials.Static.new(credentials)

        Construct a new :mod:`Pyjo.AWS.Credentials.Static` object, with the
        options of :mod:`Pyjo.AWS.Credentials.Provider`.
        """
        super().__init__(**kwargs)

        self.value = value
        """::

            credentials = provider.value
            provider.value = Pyjo.AWS.Credentials.new(access_key_id='AKIDEXAMPLE', secret_access_key='secret')

        The credentials of the provider.
        """

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials of :attr:`value`.
        """
        return self.value

    def is_fresh(self) -> bool:
        """::

            boolean = provider.is_fresh()

        Always false, so that a change of :attr:`value` comes at
        once, as getting them costs nothing.
        """
        return False


new = Pyjo_AWS_Credentials_Static.new
object = Pyjo_AWS_Credentials_Static
Static = Pyjo_AWS_Credentials_Static
