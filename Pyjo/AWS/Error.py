"""
Pyjo.AWS.Error - Error of an API of AWS
=======================================
::

    from Pyjo.AWS.Client import Client
    from Pyjo.AWS.Error import Error
    from Pyjo.AWS.Protocol.Query import Query

    try:
        Client(service='iam', endpoint='https://iam.amazonaws.com', region='us-east-1').call(
            Query('GetRole', {'RoleName': 'missing'}, version='2010-05-08')
        )
    except Error as e:
        print(e.code, e.status, e.request_id)

:mod:`Pyjo.AWS.Error` is the error that an API of AWS responds with, which a
call of :mod:`Pyjo.AWS.Client` raises, or rejects its promise with, as
:mod:`Pyjo.AWS.Protocol` reads it of the response: the code of the error,
as ``AccessDenied`` or ``ResourceNotFoundException``, its message, the status
of the response and the ID of the request, which the support of AWS asks
for.

See also
--------

:mod:`Pyjo.AWS.Client`, :mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.Exception`.

Classes
-------
"""

import Pyjo.Exception
import Pyjo.Transaction.HTTP


class Pyjo_AWS_Error(Pyjo.Exception.object):
    """
    :mod:`Pyjo.AWS.Error` inherits all attributes and methods from
    :mod:`Pyjo.Exception` and implements the following new ones.
    """

    def __init__(
        self,
        code: str,
        message: str = '',
        *,
        status: int | None = None,
        request_id: str | None = None,
        tx: Pyjo.Transaction.HTTP.object | None = None,
    ) -> None:
        """::

            e = Pyjo.AWS.Error.new('AccessDenied', 'Not authorized', status=403, request_id='c6104cbe-...')

        Construct a new :mod:`Pyjo.AWS.Error` object, whose
        :attr:`~Pyjo.Exception.Pyjo_Exception.message` is the code and the
        message of AWS, as ``AccessDenied: Not authorized``.
        """
        super().__init__(f'{code}: {message}' if message else code)

        self.code = code
        """::

            code = e.code

        The code of the error, as ``AccessDenied``, or the status of a
        response without one, as ``404``.
        """

        self.status = status
        """::

            status = e.status

        The status of the response, as ``403``.
        """

        self.request_id = request_id
        """::

            request_id = e.request_id

        The ID of the request, of the response, or ``None``.
        """

        self.tx = tx
        """::

            tx = e.tx

        The transaction of the request and its response, or ``None``.
        """


new = Pyjo_AWS_Error.new
object = Pyjo_AWS_Error
Error = Pyjo_AWS_Error
