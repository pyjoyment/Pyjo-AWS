"""
Pyjo.AWS.Protocol - Base class of the calls of the protocols of AWS
===================================================================
::

    from Pyjo.AWS.Protocol import Protocol

    class Ping(Protocol):
        def build_tx(self, ua, url):
            url.path = '/ping'
            return ua.build_tx('GET', url)

        def parse(self, tx):
            return tx.res.text

:mod:`Pyjo.AWS.Protocol` is the base class of a call of an operation of an
API of AWS in one of its protocols, which :mod:`Pyjo.AWS.Client` makes: the
call builds the transaction of the request for the endpoint of the client,
which the client signs and starts, and reads the result of its response, or
the :mod:`Pyjo.AWS.Error` that AWS responds with.

The protocols of AWS are those of the models of its APIs, which the SDKs of
AWS are generated from:

* :mod:`Pyjo.AWS.Protocol.Query`, of the form of an action and the XML of
  its response, as STS, IAM, SQS and SNS have it;
* :mod:`Pyjo.AWS.Protocol.JSON`, of the JSON of an operation of
  ``X-Amz-Target``, as DynamoDB, KMS and Secrets Manager have it;
* :mod:`Pyjo.AWS.Protocol.RestJSON`, of the JSON of a method and a path, as
  Lambda, SSO and API Gateway have it;
* :mod:`Pyjo.AWS.Protocol.RestXML`, of the XML of a method and a path, as
  S3 and Route 53 have it.

Without the models of the APIs, a call takes the names and the structure of
the API as its documentation has them, and gives the result as the response
has it.

See also
--------

:mod:`Pyjo.AWS.Client`, :mod:`Pyjo.AWS.Error`,
https://smithy.io/2.0/aws/protocols/index.html.

Classes
-------
"""

import Pyjo.Base
import Pyjo.DOM
import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from .. import Error

from collections.abc import Mapping
from typing import Any, cast


class Pyjo_AWS_Protocol[T](Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.Protocol` inherits all attributes and methods from
    :mod:`Pyjo.Base` and implements the following new ones, with ``T``, the
    type of the result of a call.
    """

    def build_tx(self, ua: Pyjo.UserAgent.object, url: Pyjo.URL.object) -> Pyjo.Transaction.HTTP.object:
        """::

            tx = call.build_tx(ua, Pyjo.URL.new('https://sts.eu-central-1.amazonaws.com'))

        The transaction of the request of the call to an endpoint, of a new
        :mod:`Pyjo.URL` object, which it may change. A subclass implements
        it.
        """
        raise NotImplementedError('Method "build_tx" not implemented by subclass')

    def error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.error(tx)

        The error of a response with an error status, with the status as its
        code and its message, which a subclass reads of the body.
        """
        res = tx.res
        return self.new_error(tx, str(res.code), res.message or '')

    def new_error(self, tx: Pyjo.Transaction.HTTP.object, code: str | None, message: str | None) -> Error.object:
        """::

            e = call.new_error(tx, 'AccessDenied', 'Not authorized')

        A new :mod:`Pyjo.AWS.Error` object of a response, with its status and
        the ID of its request, of the status if the code is empty.
        """
        res = tx.res
        headers = res.headers
        request_id = headers.header('X-Amzn-RequestId') or headers.header('X-Amz-Request-Id') or None
        return Error.new(code or str(res.code), message or '', status=res.code, request_id=request_id, tx=tx)

    def json_error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.json_error(tx)

        The error of a response of JSON, of the protocols of JSON: the code of
        the header ``X-Amzn-ErrorType`` or of the field ``__type`` or
        ``code``, without the namespace before ``#``, and the message of the
        field ``message``, or ``error_description`` of OAuth, as SSO OIDC has
        it.
        """
        res = tx.res
        try:
            data: Any = res.json() if res.body else None
        except Exception:
            data = None
        fields = cast(dict[str, Any], data) if isinstance(data, dict) else {}
        code = (res.headers.header('X-Amzn-ErrorType') or '').split(':')[0]
        code = code or str(fields.get('__type') or fields.get('code') or fields.get('Code') or '')
        message = (
            fields.get('message')
            or fields.get('Message')
            or fields.get('errorMessage')
            or fields.get('error_description')
        )
        return self.new_error(tx, code.rsplit('#', 1)[-1], str(message) if message else None)

    def parse(self, tx: Pyjo.Transaction.HTTP.object) -> T:
        """::

            result = call.parse(tx)

        The result of a response with a successful status. A subclass
        implements it.
        """
        raise NotImplementedError('Method "parse" not implemented by subclass')

    def result(self, tx: Pyjo.Transaction.HTTP.object) -> T:
        """::

            result = call.result(tx)

        The result of the response of the call, of :meth:`parse`, or the
        :mod:`Pyjo.AWS.Error` of :meth:`error` raised for an error status.
        """
        if (code := tx.res.code) is None or code >= 300:
            raise self.error(tx)
        return self.parse(tx)

    def xml(self, tx: Pyjo.Transaction.HTTP.object) -> Pyjo.DOM.object:
        """::

            dom = call.xml(tx)

        The XML of a response, as a :mod:`Pyjo.DOM` object with the semantics
        of XML, whose tags have the case of AWS, as ``Arn``.
        """
        dom = Pyjo.DOM.new()
        dom.xml = True
        return dom.parse(tx.res.text)

    def xml_error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.xml_error(tx)

        The error of a response of XML, of the protocols of XML: the elements
        ``Code`` and ``Message`` of ``Error``, and ``RequestId``.
        """
        dom = self.xml(tx)
        e = self.new_error(tx, _text(dom, 'Error > Code'), _text(dom, 'Error > Message'))
        e.request_id = _text(dom, 'RequestId') or e.request_id
        return e


# The path of an endpoint and a call, with the parameters of a query, whose values are strings as AWS reads them
def url_for(url: Pyjo.URL.object, path: str, query: Mapping[str, Any] | None = None) -> Pyjo.URL.object:
    """::

        url = Pyjo.AWS.Protocol.url_for(url, '/2018-10-31/layers', {'MaxItems': 50})

    The URL of the path of a call, after the path of an endpoint, with a
    path that is percent-encoded already, as ``/a%2Fb``, and the parameters
    of a query, whose values of :func:`value` are added to those of the path.
    """
    target = Pyjo.URL.new(path)
    url.path = url.path.to_str().rstrip('/') + (target.path.to_str() or '/')
    url.query = target.query
    if query:
        url.query.append({name: value_of(v) for name, v in query.items() if v is not None})
    return url


def value_of(value: Any) -> str:
    """::

        string = Pyjo.AWS.Protocol.value_of(True)

    A value of a parameter as AWS reads it, ``true`` or ``false`` of a
    boolean, and the string of anything else.
    """
    if isinstance(value, bool):
        return 'true' if value else 'false'
    return str(value)


def _text(dom: Pyjo.DOM.object, selector: str) -> str | None:
    element = dom.at(selector)
    return element.text.strip() if element is not None else None


new = Pyjo_AWS_Protocol.new
object = Pyjo_AWS_Protocol
Protocol = Pyjo_AWS_Protocol
