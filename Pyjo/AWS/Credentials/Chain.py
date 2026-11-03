"""
Pyjo.AWS.Credentials.Chain - Chain of the providers of credentials
==================================================================
::

    from Pyjo.AWS.Credentials.Chain import Chain

    credentials = Chain().credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Config
    import Pyjo.AWS.Credentials.Chain
    import Pyjo.AWS.Credentials.Environment
    import Pyjo.AWS.Credentials.Profile

    chain = Pyjo.AWS.Credentials.Chain.new(config=Pyjo.AWS.Config.new(profile='dev'))
    chain.credentials_p().then(lambda credentials: print(credentials.provider)).wait()

    chain = Pyjo.AWS.Credentials.Chain.new(
        providers=[Pyjo.AWS.Credentials.Environment.new(), Pyjo.AWS.Credentials.Profile.new()]
    )

:mod:`Pyjo.AWS.Credentials.Chain` is the provider of the credentials of the
first of its providers that has them, in the order of the SDKs of AWS by
default:

#. the environment, of :mod:`Pyjo.AWS.Credentials.Environment`,
#. the profile of the shared files, of :mod:`Pyjo.AWS.Credentials.Profile`.

A provider that is not configured passes on to the next one, and the error
of one that is configured ends the chain, as the SDKs of AWS do, so that a
broken profile is not hidden by other credentials.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials`,
https://docs.aws.amazon.com/sdkref/latest/guide/standardized-credentials.html.

Classes
-------
"""

from .. import Config
from . import Environment, Profile, Provider

from collections.abc import Sequence
from typing import Any


class Pyjo_AWS_Credentials_Chain(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Chain` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Credentials.Provider` and implements the following
    new ones.
    """

    def __init__(
        self,
        *,
        providers: Sequence[Provider.object] | None = None,
        config: Config.object | None = None,
        **kwargs: Any,
    ) -> None:
        """::

            chain = Pyjo.AWS.Credentials.Chain.new()
            chain = Pyjo.AWS.Credentials.Chain.new(config=Pyjo.AWS.Config.new(profile='dev'))
            chain = Pyjo.AWS.Credentials.Chain.new(providers=[Pyjo.AWS.Credentials.Environment.new()])

        Construct a new :mod:`Pyjo.AWS.Credentials.Chain` object, with the
        options of :mod:`Pyjo.AWS.Credentials.Provider`, and the providers of
        the SDKs of AWS, with the shared files of ``config``, by default.
        """
        super().__init__(**kwargs)

        self.config = config or Config.new()
        """::

            config = chain.config

        The shared files of the default providers, a new :mod:`Pyjo.AWS.Config`
        object by default.
        """

        self.providers: list[Provider.object] = list(providers) if providers is not None else self.default_providers()
        """::

            providers = chain.providers
            chain.providers.append(Pyjo.AWS.Credentials.Process.new(command='/opt/bin/credentials'))

        The providers, in their order.
        """

    def default_providers(self) -> list[Provider.object]:
        """::

            providers = chain.default_providers()

        New providers of the SDKs of AWS, with :attr:`config` and the user
        agent of the chain, in their order.
        """
        # TODO: web identity of the environment, the container and IMDS
        return [
            Environment.new(ua=self.ua, refresh=self.refresh),
            Profile.new(config=self.config, ua=self.ua, refresh=self.refresh),
        ]

    def fetch(self) -> Provider.Steps:
        """::

            credentials = yield from chain.fetch()

        The credentials of the first provider that has them, or ``None``.
        """
        for provider in self.providers:
            if (credentials := (yield from provider.steps())) is not None:
                return credentials
        return None


new = Pyjo_AWS_Credentials_Chain.new
object = Pyjo_AWS_Credentials_Chain
Chain = Pyjo_AWS_Credentials_Chain
