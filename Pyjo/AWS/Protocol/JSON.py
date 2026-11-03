"""
Pyjo.AWS.Protocol.JSON - Call of the JSON protocol of AWS
=========================================================
::

    from Pyjo.AWS.Client import Client
    from Pyjo.AWS.Protocol.JSON import JSON

    tables = Client(service='dynamodb').call(JSON('DynamoDB_20120810.ListTables', {'Limit': 10}, version='1.0'))
    print(tables['TableNames'])

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Client
    import Pyjo.AWS.Protocol.JSON

    secrets = Pyjo.AWS.Client.new(service='secretsmanager', region='eu-central-1')
    call = Pyjo.AWS.Protocol.JSON.new('secretsmanager.GetSecretValue', {'SecretId': 'database'})
    secrets.call_p(call).then(lambda secret: print(secret['SecretString'])).wait()

:mod:`Pyjo.AWS.Protocol.JSON` is a call of the JSON protocol of AWS, of the
APIs of DynamoDB, KMS, Secrets Manager, CloudWatch Logs, ECR and others: the
JSON of the parameters posted to the endpoint, with the target of the
operation in the header ``X-Amz-Target``, as ``DynamoDB_20120810.ListTables``,
and the version of the protocol in the type of the content,
``application/x-amz-json-1.1`` by default, or ``1.0``, as the model of the
API has it. The result is the JSON of the response.

The error of the response is the code of the header ``X-Amzn-ErrorType`` or
of the field ``__type``, and the message of the field ``message``.

See also
--------

:mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.AWS.Client`,
https://smithy.io/2.0/aws/protocols/aws-json-1_1-protocol.html.

Classes
-------
"""

import Pyjo.Transaction.HTTP
import Pyjo.URL
import Pyjo.UserAgent

from .. import Error, Protocol

from collections.abc import Mapping
from typing import Any


class Pyjo_AWS_Protocol_JSON(Protocol.object[Any]):
    """
    :mod:`Pyjo.AWS.Protocol.JSON` inherits all attributes and methods from
    :mod:`Pyjo.AWS.Protocol` and implements the following new ones.
    """

    def __init__(self, target: str, params: Mapping[str, Any] | None = None, *, version: str = '1.1') -> None:
        """::

            call = Pyjo.AWS.Protocol.JSON.new('secretsmanager.ListSecrets')
            call = Pyjo.AWS.Protocol.JSON.new('DynamoDB_20120810.GetItem', {'TableName': 'users', 'Key': key},
                                              version='1.0')

        Construct a new :mod:`Pyjo.AWS.Protocol.JSON` object.
        """
        self.target = target
        """::

            target = call.target

        The target of the operation, the prefix of the API and the name of
        the operation, as ``DynamoDB_20120810.ListTables``.
        """

        self.params = dict(params or {})
        """::

            params = call.params

        The parameters of the operation, as its JSON.
        """

        self.version = version
        """::

            version = call.version

        The version of the protocol, ``1.1`` by default, or ``1.0``.
        """

    def build_tx(self, ua: Pyjo.UserAgent.object, url: Pyjo.URL.object) -> Pyjo.Transaction.HTTP.object:
        """::

            tx = call.build_tx(ua, url)

        The transaction of the JSON posted to the endpoint.
        """
        headers = {'X-Amz-Target': self.target, 'Content-Type': f'application/x-amz-json-{self.version}'}
        return ua.build_tx('POST', Protocol.url_for(url, '/'), headers, json=self.params)

    def error(self, tx: Pyjo.Transaction.HTTP.object) -> Error.object:
        """::

            e = call.error(tx)

        The error of the JSON of the response.
        """
        return self.json_error(tx)

    def parse(self, tx: Pyjo.Transaction.HTTP.object) -> Any:
        """::

            result = call.parse(tx)

        The JSON of the response, or ``None`` without a body.
        """
        res = tx.res
        return res.json() if res.body else None


new = Pyjo_AWS_Protocol_JSON.new
object = Pyjo_AWS_Protocol_JSON
JSON = Pyjo_AWS_Protocol_JSON
