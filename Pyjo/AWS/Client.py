"""
Pyjo.AWS.Client - Client of an API of AWS
=========================================
::

    from Pyjo.AWS.Client import Client
    from Pyjo.AWS.Protocol.Query import Query
    from Pyjo.AWS.Protocol.RestJSON import RestJSON

    sts = Client(service='sts')
    print(sts.call(Query('GetCallerIdentity', version='2011-06-15')).at('Arn').text)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Client
    import Pyjo.AWS.Config
    import Pyjo.AWS.Protocol.RestJSON

    lambda_ = Pyjo.AWS.Client.new(service='lambda', config=Pyjo.AWS.Config.new(profile='dev'))
    call = Pyjo.AWS.Protocol.RestJSON.new('GET', '/2018-10-31/layers')
    lambda_.call_p(call).then(lambda layers: print(layers['Layers'])).wait()

:mod:`Pyjo.AWS.Client` calls an API of AWS, of a service in a region, with
the calls of :mod:`Pyjo.AWS.Protocol`: it signs the request of a call with
the credentials of :mod:`Pyjo.AWS.Credentials`, which
:mod:`Pyjo.AWS.Credentials.Chain` finds by default, as the SDKs of AWS do,
starts it with :mod:`Pyjo.UserAgent`, blocking or non-blocking, and gives
the result of its response, or raises the :mod:`Pyjo.AWS.Error` that AWS
responds with.

The endpoint of the service is the one that the environment or the profile
of :mod:`Pyjo.AWS.Config` configures, as
:meth:`~Pyjo.AWS.Config.Pyjo_AWS_Config.endpoint_url` resolves it, or the
regional one of AWS, as ``https://sts.eu-central-1.amazonaws.com``, of
``amazonaws.com.cn`` in the regions of China. A service with a global
endpoint, as IAM, takes it as :attr:`~Pyjo_AWS_Client.endpoint`. ::

    iam = Pyjo.AWS.Client.new(service='iam', endpoint='https://iam.amazonaws.com', region='us-east-1')

A provider of credentials calls an API of AWS with
:meth:`~Pyjo_AWS_Client.steps`, which :mod:`Pyjo.Steps` runs with its
own steps, as a role of STS with the credentials of its source: ::

    async def fetch(self):
        source = await self.source.steps()
        dom = await sts.steps(Query('AssumeRole', {...}, version='2011-06-15'), source)

See also
--------

:mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.AWS.Error`, :mod:`Pyjo.AWS.SigV4`,
:mod:`Pyjo.AWS.Credentials`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-ss-endpoints.html.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception
import Pyjo.Promise
import Pyjo.Steps
import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from . import Config, Credentials, Protocol, SigV4
from .Credentials import Provider

from typing import Any


class Pyjo_AWS_Client(Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.Client` inherits all attributes and methods from
    :mod:`Pyjo.Base` and implements the following new ones.
    """

    def __init__(
        self,
        *,
        service: str,
        region: str | None = None,
        endpoint: str | None = None,
        endpoint_prefix: str | None = None,
        service_id: str | None = None,
        config: Config.object | None = None,
        credentials: Provider.object | None = None,
        unsigned: bool = False,
        ua: Pyjo.UserAgent.object | None = None,
    ) -> None:
        """::

            client = Pyjo.AWS.Client.new(service='sts')
            client = Pyjo.AWS.Client.new(service='lambda', region='eu-central-1',
                                         config=Pyjo.AWS.Config.new(profile='dev'))
            client = Pyjo.AWS.Client.new(service='awsssoportal', endpoint_prefix='portal.sso', service_id='SSO',
                                         unsigned=True)

        Construct a new :mod:`Pyjo.AWS.Client` object.
        """
        self.service = service
        """::

            service = client.service

        The name of the service in the signature, as ``sts`` or ``lambda``,
        which is the prefix of its endpoint and its ID by default.
        """

        self.config = config or Config.new()
        """::

            config = client.config

        The shared files of the region, the endpoint and the default
        credentials, a new :mod:`Pyjo.AWS.Config` object by default.
        """

        self.region = region or self.config.region()
        """::

            region = client.region
            client.region = 'eu-central-1'

        The region of the service, of :meth:`~Pyjo.AWS.Config.Pyjo_AWS_Config.region`
        of :attr:`config` by default, or ``None``, which a call raises an
        error of.
        """

        self.endpoint = endpoint
        """::

            url = client.endpoint
            client.endpoint = 'http://127.0.0.1:4566'

        The URL of the endpoint, which comes over the configured and the
        regional one, or ``None``.
        """

        self.endpoint_prefix = endpoint_prefix or service
        """::

            prefix = client.endpoint_prefix

        The prefix of the regional endpoint, as ``portal.sso`` of SSO,
        :attr:`service` by default.
        """

        self.service_id = service_id or service
        """::

            service_id = client.service_id

        The ID of the service, whose endpoint the environment and the profile
        configure, as ``SSO OIDC``, :attr:`service` by default.
        """

        self.ua = ua or Pyjo.UserAgent.new()
        """::

            ua = client.ua

        The user agent of the requests, a new :mod:`Pyjo.UserAgent` object by
        default, whose event ``start`` signs each request.
        """

        # Chain imports the providers of the profiles, of which SSO and the roles import this module
        from .Credentials import Chain

        self.credentials: Provider.object = credentials or Chain.new(config=self.config, ua=self.ua)
        """::

            provider = client.credentials

        The provider of the credentials, a new
        :mod:`Pyjo.AWS.Credentials.Chain` object of :attr:`config` by
        default.
        """

        self.unsigned = unsigned
        """::

            boolean = client.unsigned

        Send the requests without a signature, false by default, as those of
        SSO and SSO OIDC, which have a token of their own.
        """

    def call[T](self, call: Protocol.object[T]) -> T:
        """::

            result = client.call(Pyjo.AWS.Protocol.Query.new('GetCallerIdentity', version='2011-06-15'))

        Call an operation, blocking, and give its result, or raise its
        :mod:`Pyjo.AWS.Error`.
        """
        return self.steps(call).run(self.ua)

    def call_p(self, call: Protocol.object[Any]) -> Pyjo.Promise.object:
        """::

            promise = client.call_p(Pyjo.AWS.Protocol.Query.new('GetCallerIdentity', version='2011-06-15'))

        Same as :meth:`call`, but non-blocking, and returns a
        :mod:`Pyjo.Promise` object. The credentials come of
        :meth:`~Pyjo.AWS.Credentials.Provider.Pyjo_AWS_Credentials_Provider.credentials_p`,
        so that the calls while the provider gets them wait for them once.
        """
        if self.unsigned:
            return self.steps(call).run_p(self.ua)

        def signed(credentials: Credentials.object | None) -> Pyjo.Promise.object:
            return self.steps(call, _required(credentials)).run_p(self.ua)

        return self.credentials.credentials_p().then(signed)

    def endpoint_url(self) -> str:
        """::

            url = client.endpoint_url()

        The URL of the endpoint, :attr:`endpoint`, the configured one, or the
        regional one, which needs a :attr:`region`.
        """
        if url := self.endpoint or self.config.endpoint_url(self.service_id):
            return url
        region = _region(self.region, self.service)
        suffix = 'amazonaws.com.cn' if region.startswith('cn-') else 'amazonaws.com'
        return f'https://{self.endpoint_prefix}.{region}.{suffix}'

    def signer(self, credentials: Credentials.object) -> SigV4.object:
        """::

            signer = client.signer(credentials)

        A new :mod:`Pyjo.AWS.SigV4` object of the service and the region with
        credentials, which signs the path of S3 as it is, with the hash of its
        body.
        """
        region = _region(self.region, self.service)
        if self.service == 's3':
            return SigV4.new(
                service=self.service,
                region=region,
                credentials=credentials,
                normalize_path=False,
                double_encode=False,
                content_sha256=True,
            )
        return SigV4.new(service=self.service, region=region, credentials=credentials)

    def steps[T](self, call: Protocol.object[T], credentials: Credentials.object | None = None) -> Pyjo.Steps.object[T]:
        """::

            result = await client.steps(call)
            result = await client.steps(call, credentials)

        The :mod:`Pyjo.Steps` of a call, of a provider of credentials,
        with credentials, or those of :attr:`credentials` by default.
        """
        return Pyjo.Steps.Steps(self._steps(call, credentials))

    async def _steps[T](self, call: Protocol.object[T], credentials: Credentials.object | None) -> T:
        if not self.unsigned and credentials is None:
            credentials = _required(await self.credentials.steps())
        tx = call.build_tx(self.ua, Pyjo.URL.new(self.endpoint_url()))
        if credentials is not None and not self.unsigned:
            self._sign_on_start(tx, self.signer(credentials))
        return call.result(await Pyjo.Steps.Request.new(tx, self.ua))

    # The request is signed in the event start of the transaction, of the user agent that the request of the steps
    # names, as it is complete then; and of that transaction only, as the user agent may start others meanwhile
    def _sign_on_start(self, tx: Pyjo.Transaction.HTTP.object, signer: SigV4.object) -> None:
        ua = self.ua

        def sign(_: Pyjo.UserAgent.object, started: Pyjo.Transaction.HTTP.object) -> None:
            if started is tx:
                ua.unsubscribe('start', sign)
                signer.sign(started.req)

        ua.on('start', sign)


def _region(region: str | None, service: str) -> str:
    if not region:
        raise Pyjo.Exception.new(f'No region of AWS for {service}: AWS_REGION or region of the profile')
    return region


def _required(credentials: Credentials.object | None) -> Credentials.object:
    if credentials is None:
        raise Pyjo.Exception.new('No credentials of AWS')
    return credentials


new = Pyjo_AWS_Client.new
object = Pyjo_AWS_Client
Client = Pyjo_AWS_Client
