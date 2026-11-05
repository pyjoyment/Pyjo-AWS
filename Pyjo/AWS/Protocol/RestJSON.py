"""
Pyjo.AWS.Protocol.RestJSON - Call of the REST-JSON protocol of AWS
==================================================================
::

    from Pyjo.AWS.Client import Client
    from Pyjo.AWS.Protocol.RestJSON import RestJSON

    layers = Client(service='lambda').call(RestJSON('GET', '/2018-10-31/layers', query={'MaxItems': 50}))
    print([layer['LayerName'] for layer in layers['Layers']])

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Client
    import Pyjo.AWS.Protocol.RestJSON

    lambda_ = Pyjo.AWS.Client.new(service='lambda', region='eu-central-1')
    call = Pyjo.AWS.Protocol.RestJSON.new('POST', '/2015-03-31/functions/hello/invocations', {'name': 'World'})
    lambda_.call_p(call).then(lambda result: print(result)).wait()

:mod:`Pyjo.AWS.Protocol.RestJSON` is a call of the REST-JSON protocol of
AWS, of the APIs of Lambda, SSO, API Gateway, EKS, Glacier and others: a
method and a path, which is percent-encoded already, with the parameters of
its query, its headers and the JSON of its body. The result is the JSON of
the response, its body of another type, or ``None`` without a body.

The error of the response is the code of the header ``X-Amzn-ErrorType`` or
of the field ``code`` or ``__type``, and the message of the field
``message``.

See also
--------

:mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.AWS.Client`,
https://smithy.io/2.0/aws/protocols/aws-restjson1-protocol.html.

Classes
-------
"""

import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from .. import Error, Protocol

from collections.abc import Mapping
from typing import Any


class Pyjo_AWS_Protocol_RestJSON(Protocol.object[Any]):
    """
    :mod:`Pyjo.AWS.Protocol.RestJSON` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Protocol` and implements the following new ones.
    """

    def __init__(
        self,
        method: str,
        path: str,
        json: Any = None,
        *,
        query: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """::

            call = Pyjo.AWS.Protocol.RestJSON.new('GET', '/2018-10-31/layers')
            call = Pyjo.AWS.Protocol.RestJSON.new('GET', '/federation/credentials',
                                                  query={'role_name': 'admin', 'account_id': '123456789012'},
                                                  headers={'X-Amz-Sso_bearer_token': token})
            call = Pyjo.AWS.Protocol.RestJSON.new('POST', '/2018-10-31/layers/hello/versions', {'Content': content})

        Construct a new :mod:`Pyjo.AWS.Protocol.RestJSON` object.
        """
        self.method = method
        """::

            method = call.method

        The method of the request, as ``GET``.
        """

        self.path = path
        """::

            path = call.path

        The path of the request, which is percent-encoded already, as
        ``/2018-10-31/layers/hello%2Dworld/versions``, with the parameters of
        a query too.
        """

        self.json = json
        """::

            json = call.json

        The JSON of the body of the request, or ``None`` for none.
        """

        self.query = dict(query or {})
        """::

            query = call.query

        The parameters of the query, whose values are strings, ``true`` or
        ``false`` of booleans and the strings of the others, whose ``None``
        values the request leaves out.
        """

        self.headers = dict(headers or {})
        """::

            headers = call.headers

        The headers of the request.
        """

    def build_tx(self, ua: Pyjo.UserAgent.object, url: Pyjo.URL.object) -> Pyjo.Transaction.HTTP.object:
        """::

            tx = call.build_tx(ua, url)

        The transaction of the method and the path, after the path of the
        endpoint, with the JSON of the body.
        """
        url = Protocol.url_for(url, self.path, self.query)
        if self.json is None:
            return ua.build_tx(self.method, url, self.headers)
        return ua.build_tx(self.method, url, self.headers, json=self.json)

    def error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.error(tx)

        The error of the JSON of the response.
        """
        return self.json_error(tx)

    def parse(self, tx: Pyjo.Transaction.HTTP.object) -> Any:
        """::

            result = call.parse(tx)

        The JSON of the response, its body of a type that is not JSON, or
        ``None`` without a body.
        """
        res = tx.res
        if not res.body:
            return None
        if 'json' in (res.headers.content_type or 'json'):
            return res.json()
        return res.body


new = Pyjo_AWS_Protocol_RestJSON.new
object = Pyjo_AWS_Protocol_RestJSON
RestJSON = Pyjo_AWS_Protocol_RestJSON
