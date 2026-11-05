"""
Pyjo.AWS.Protocol.RestXML - Call of the REST-XML protocol of AWS
================================================================
::

    from Pyjo.AWS.Client import Client
    from Pyjo.AWS.Protocol.RestXML import RestXML

    dom = Client(service='s3').call(RestXML('GET', '/my-bucket', query={'list-type': 2, 'prefix': 'logs/'}))
    print(dom.find('Contents > Key').map('text').join('\\n'))

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Client
    import Pyjo.AWS.Protocol.RestXML

    s3 = Pyjo.AWS.Client.new(service='s3', region='eu-central-1')
    call = Pyjo.AWS.Protocol.RestXML.new('PUT', '/my-bucket/hello.txt', b'Hello!', headers={'Content-Type': 'text/plain'})
    s3.call_p(call).then(lambda dom: print('uploaded')).wait()

:mod:`Pyjo.AWS.Protocol.RestXML` is a call of the REST-XML protocol of AWS,
of the APIs of S3, Route 53 and CloudFront: a method and a path, which is
percent-encoded already, with the parameters of its query, its headers and
its body, as XML. The result is the XML of the response, as a
:mod:`Pyjo.DOM` object, the body of an object of S3 of another type, or
``None`` without a body, as the response of ``PUT`` of an object of S3,
whose result is in its headers, which a subclass of the call reads in its
:meth:`~Pyjo.AWS.Protocol.Pyjo_AWS_Protocol.result`, and :attr:`~Pyjo.AWS.Error.Pyjo_AWS_Error.tx` of an error has.

The error of the response is the code and the message of its element
``Error``, or its status, as ``404`` of ``HEAD``, without a body.

See also
--------

:mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.AWS.Client`,
https://smithy.io/2.0/aws/protocols/aws-restxml-protocol.html.

Classes
-------
"""

import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from .. import Error, Protocol

from collections.abc import Mapping
from typing import Any


class Pyjo_AWS_Protocol_RestXML(Protocol.object[Any]):
    """
    :mod:`Pyjo.AWS.Protocol.RestXML` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Protocol` and implements the following new ones.
    """

    def __init__(
        self,
        method: str,
        path: str,
        body: bytes | str | None = None,
        *,
        query: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """::

            call = Pyjo.AWS.Protocol.RestXML.new('GET', '/my-bucket', query={'list-type': 2})
            call = Pyjo.AWS.Protocol.RestXML.new('PUT', '/my-bucket/hello.txt', b'Hello!')
            call = Pyjo.AWS.Protocol.RestXML.new('POST', '/2013-04-01/hostedzone/Z123/rrset', xml)

        Construct a new :mod:`Pyjo.AWS.Protocol.RestXML` object.
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
        ``/my-bucket/a%20b.txt``, with the parameters of a query too.
        """

        self.body = body
        """::

            body = call.body

        The body of the request, its XML or an object of S3, or ``None`` for
        none.
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
        endpoint, with the body.
        """
        url = Protocol.url_for(url, self.path, self.query)
        body = self.body.encode() if isinstance(self.body, str) else self.body
        if body is None:
            return ua.build_tx(self.method, url, self.headers)
        return ua.build_tx(self.method, url, self.headers, body)

    def error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.error(tx)

        The error of the element ``Error`` of the response, or of its status
        without a body.
        """
        if not tx.res.body:
            return super().error(tx)
        return self.xml_error(tx)

    def parse(self, tx: Pyjo.Transaction.HTTP.object) -> Any:
        """::

            result = call.parse(tx)

        The XML of the response, as a :mod:`Pyjo.DOM` object, its body of
        another type, or ``None`` without a body.
        """
        res = tx.res
        if not res.body:
            return None
        if 'xml' in (res.headers.content_type or 'xml'):
            return self.xml(tx)
        return res.body


new = Pyjo_AWS_Protocol_RestXML.new
object = Pyjo_AWS_Protocol_RestXML
RestXML = Pyjo_AWS_Protocol_RestXML
