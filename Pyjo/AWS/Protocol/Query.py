"""
Pyjo.AWS.Protocol.Query - Call of the query protocol of AWS
===========================================================
::

    from Pyjo.AWS.Client import Client
    from Pyjo.AWS.Protocol.Query import Query

    dom = Client(service='sts').call(Query('GetCallerIdentity', version='2011-06-15'))
    print(dom.at('Arn').text)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Client
    import Pyjo.AWS.Protocol.Query

    sqs = Pyjo.AWS.Client.new(service='sqs', region='eu-central-1')
    call = Pyjo.AWS.Protocol.Query.new(
        'SendMessage', {'QueueUrl': url, 'MessageBody': 'Hello', 'MessageAttribute.1.Name': 'From'},
        version='2012-11-05',
    )
    sqs.call_p(call).then(lambda dom: print(dom.at('MessageId').text)).wait()

:mod:`Pyjo.AWS.Protocol.Query` is a call of the query protocol of AWS, of
the APIs of STS, IAM, SQS, SNS, CloudWatch, EC2 and others: a form of the
action, the version of the API and the parameters, posted to the endpoint,
whose response is XML, as a :mod:`Pyjo.DOM` object. The parameters are
flat, as the documentation of the API names them, as ``Tags.member.1.Key``,
whose values are strings, ``true`` or ``false`` of booleans, and the
strings of the others.

The error of the response is the code and the message of its element
``Error``.

See also
--------

:mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.AWS.Client`,
https://smithy.io/2.0/aws/protocols/aws-query-protocol.html.

Classes
-------
"""

import Pyjo.DOM
import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from .. import Error, Protocol

from collections.abc import Mapping
from typing import Any


class Pyjo_AWS_Protocol_Query(Protocol.object[Pyjo.DOM.object]):
    """
    :mod:`Pyjo.AWS.Protocol.Query` inherits all attributes and methods from
    :mod:`Pyjo.AWS.Protocol` and implements the following new ones.
    """

    def __init__(self, action: str, params: Mapping[str, Any] | None = None, *, version: str) -> None:
        """::

            call = Pyjo.AWS.Protocol.Query.new('GetCallerIdentity', version='2011-06-15')
            call = Pyjo.AWS.Protocol.Query.new('GetRole', {'RoleName': 'admin'}, version='2010-05-08')

        Construct a new :mod:`Pyjo.AWS.Protocol.Query` object.
        """
        self.action = action
        """::

            action = call.action

        The action, as ``AssumeRole``.
        """

        self.params = dict(params or {})
        """::

            params = call.params

        The parameters of the action, as the documentation of the API names
        them, whose ``None`` values the request leaves out.
        """

        self.version = version
        """::

            version = call.version

        The version of the API, as ``2011-06-15`` of STS.
        """

    def build_tx(self, ua: Pyjo.UserAgent.object, url: Pyjo.URL.object) -> Pyjo.Transaction.HTTP.object:
        """::

            tx = call.build_tx(ua, url)

        The transaction of a form posted to the endpoint.
        """
        form = {'Action': self.action, 'Version': self.version}
        form.update({name: Protocol.value_of(value) for name, value in self.params.items() if value is not None})
        return ua.build_tx('POST', Protocol.url_for(url, '/'), form=form)

    def error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.error(tx)

        The error of the element ``Error`` of the response.
        """
        return self.xml_error(tx)

    def parse(self, tx: Pyjo.Transaction.HTTP.object) -> Pyjo.DOM.object:
        """::

            dom = call.parse(tx)

        The XML of the response, as ``<AssumeRoleResponse>``, whose result is
        its element of the action, as ``AssumeRoleResult``.
        """
        return self.xml(tx)


new = Pyjo_AWS_Protocol_Query.new
object = Pyjo_AWS_Protocol_Query
Query = Pyjo_AWS_Protocol_Query
