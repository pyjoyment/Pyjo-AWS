"""
Pyjo.AWS.SigV4 - Signature Version 4 of AWS
===========================================
::

    from Pyjo.AWS.SigV4 import SigV4

    signer = SigV4(service='lambda', region='eu-central-1')
    signer.sign(tx.req)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.SigV4
    import Pyjo.UserAgent

    signer = Pyjo.AWS.SigV4.new(service='lambda', region='eu-central-1')
    ua = Pyjo.UserAgent.new()
    ua.on('start', lambda ua, tx: signer.sign(tx.req))
    print(ua.get('https://lambda.eu-central-1.amazonaws.com/2018-10-31/layers').result.json())

:mod:`Pyjo.AWS.SigV4` signs a request of :mod:`Pyjo.Message.Request` with the
`Signature Version 4
<https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html>`_
of AWS, in its header ``Authorization``, with the credentials of the
environment by default, as the SDKs of AWS take them.

The event ``start`` of :mod:`Pyjo.UserAgent` is the place to sign a request,
as it is emitted for each transaction, a redirect too, once the request is
complete and before it is written. The request has no ``Host`` and no
``Content-Length`` then, which the request adds when it is written:
:meth:`~Pyjo_AWS_SigV4.sign` sets ``Host`` itself, and does not sign
``Content-Length``, which AWS does not require.

See also
--------

:mod:`Pyjo.AWS`, :mod:`Pyjo.UserAgent`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception
import Pyjo.Message.Request

from Pyjo.Util import getenv, hmac_sha256_bytes, hmac_sha256_sum, sha256_sum, url_escape

from . import Credentials

import datetime


_ALGORITHM = 'AWS4-HMAC-SHA256'

# The headers that a proxy or the user agent may change after the request is signed, as the SDKs of AWS leave them
_UNSIGNED = frozenset(('authorization', 'expect', 'transfer-encoding', 'user-agent', 'x-amzn-trace-id'))


class Pyjo_AWS_SigV4(Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.SigV4` inherits all attributes and methods from
    :mod:`Pyjo.Base` and implements the following new ones.
    """

    def __init__(
        self,
        *,
        service: str,
        region: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        session_token: str | None = None,
        credentials: Credentials.object | None = None,
        normalize_path: bool = True,
        double_encode: bool = True,
        content_sha256: bool = False,
    ) -> None:
        """::

            signer = Pyjo.AWS.SigV4.new(service='lambda')
            signer = Pyjo.AWS.SigV4.new(service='sts', credentials=Pyjo.AWS.Credentials.Chain.new().credentials())
            signer = Pyjo.AWS.SigV4.new(service='s3', region='us-east-1', normalize_path=False, double_encode=False,
                                        content_sha256=True)

        Construct a new :mod:`Pyjo.AWS.SigV4` object. The keys of
        :mod:`Pyjo.AWS.Credentials` of ``credentials`` come in the place of
        those of the environment, and of its session token too.
        """
        if credentials is not None:
            access_key_id = credentials.access_key_id if access_key_id is None else access_key_id
            secret_access_key = credentials.secret_access_key if secret_access_key is None else secret_access_key
            session_token = (credentials.session_token or '') if session_token is None else session_token

        self.service = service
        """::

            service = signer.service
            signer.service = 'lambda'

        The name of the service in the scope of the signature, as ``lambda``
        or ``s3``.
        """

        self.region = region or getenv('AWS_REGION') or getenv('AWS_DEFAULT_REGION') or 'us-east-1'
        """::

            region = signer.region
            signer.region = 'eu-central-1'

        The region in the scope of the signature, defaults to the value of
        the ``AWS_REGION`` or ``AWS_DEFAULT_REGION`` environment variable or
        ``us-east-1``.
        """

        self.access_key_id = access_key_id if access_key_id is not None else _environ('AWS_ACCESS_KEY_ID')
        """::

            access_key_id = signer.access_key_id
            signer.access_key_id = 'AKIDEXAMPLE'

        The access key ID, defaults to the value of the ``AWS_ACCESS_KEY_ID``
        environment variable, unless it is empty.
        """

        self.secret_access_key = (
            secret_access_key if secret_access_key is not None else _environ('AWS_SECRET_ACCESS_KEY')
        )
        """::

            secret_access_key = signer.secret_access_key
            signer.secret_access_key = 'wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY'

        The secret access key, defaults to the value of the
        ``AWS_SECRET_ACCESS_KEY`` environment variable, unless it is empty.
        """

        self.session_token = (session_token or None) if session_token is not None else _environ('AWS_SESSION_TOKEN')
        """::

            session_token = signer.session_token
            signer.session_token = 'AQoDYXdzEPT//////////wEXAMPLE...'

        The session token of temporary credentials, as those of a role,
        defaults to the value of the ``AWS_SESSION_TOKEN`` environment
        variable, unless it is empty, sent in the header ``X-Amz-Security-Token``.
        """

        self.normalize_path = normalize_path
        """::

            boolean = signer.normalize_path
            signer.normalize_path = False

        Remove the segments ``.`` and ``..`` and the empty ones from the path
        of the canonical request, true by default, which every service wants
        but S3.
        """

        self.double_encode = double_encode
        """::

            boolean = signer.double_encode
            signer.double_encode = False

        Encode the path of the canonical request once more, after the
        encoding of the URL, true by default, which every service wants but
        S3.
        """

        self.content_sha256 = content_sha256
        """::

            boolean = signer.content_sha256
            signer.content_sha256 = True

        Send the hash of the body in the header ``X-Amz-Content-Sha256``,
        false by default, which S3 requires. A request that has the header
        already is signed with its value, as ``UNSIGNED-PAYLOAD`` of S3.
        """

    def canonical_request(self, req: Pyjo.Message.Request.object) -> str:
        """::

            canonical = signer.canonical_request(req)

        The canonical request of a request with the headers that
        :meth:`sign` sets.
        """
        signed = self._signed_headers(req)
        return '\n'.join(
            (
                req.method,
                self._canonical_path(req),
                self._canonical_query(req),
                ''.join(f'{name}:{value}\n' for name, value in signed),
                ';'.join(name for name, _ in signed),
                self.payload_hash(req),
            )
        )

    def payload_hash(self, req: Pyjo.Message.Request.object) -> str:
        """::

            digest = signer.payload_hash(req)

        The SHA-256 of the body of a request in hexadecimal, or the value of
        its header ``X-Amz-Content-Sha256``.
        """
        if (value := req.headers.header('X-Amz-Content-Sha256')) is not None:
            return value
        return sha256_sum(req.body)

    def scope(self, req: Pyjo.Message.Request.object) -> str:
        """::

            scope = signer.scope(req)

        The scope of the signature of a request, as
        ``20150830/us-east-1/service/aws4_request``, of the date of its header
        ``X-Amz-Date``.
        """
        return f'{self._date(req)[:8]}/{self.region}/{self.service}/aws4_request'

    def sign(
        self, req: Pyjo.Message.Request.object, date: datetime.datetime | None = None
    ) -> Pyjo.Message.Request.object:
        """::

            req = signer.sign(req)
            req = signer.sign(req, datetime.datetime(2015, 8, 30, 12, 36, tzinfo=datetime.UTC))

        Sign a request at a date, now by default: set its headers ``Host``,
        ``X-Amz-Date``, ``X-Amz-Security-Token`` with a
        :attr:`session_token` and ``X-Amz-Content-Sha256`` with
        :attr:`content_sha256`, and its header ``Authorization``.
        """
        if self.access_key_id is None or self.secret_access_key is None:
            raise Pyjo.Exception.new('No credentials of AWS')

        headers = req.headers
        if headers.host is None:
            headers.host = req.url.host_port or ''
        date = (date or datetime.datetime.now(datetime.UTC)).astimezone(datetime.UTC)
        headers.header('X-Amz-Date', date.strftime('%Y%m%dT%H%M%SZ'))
        if self.session_token is not None:
            headers.header('X-Amz-Security-Token', self.session_token)
        if self.content_sha256 and headers.header('X-Amz-Content-Sha256') is None:
            headers.header('X-Amz-Content-Sha256', self.payload_hash(req))

        signed = ';'.join(name for name, _ in self._signed_headers(req))
        credential = f'{self.access_key_id}/{self.scope(req)}'
        headers.authorization = (
            f'{_ALGORITHM} Credential={credential}, SignedHeaders={signed}, Signature={self.signature(req)}'
        )
        return req

    def signature(self, req: Pyjo.Message.Request.object) -> str:
        """::

            signature = signer.signature(req)

        The signature of a request in hexadecimal, of its
        :meth:`string_to_sign`.
        """
        if self.secret_access_key is None:
            raise Pyjo.Exception.new('No credentials of AWS')
        key = ('AWS4' + self.secret_access_key).encode()
        for part in (self._date(req)[:8], self.region, self.service, 'aws4_request'):
            key = hmac_sha256_bytes(part.encode(), key)
        return hmac_sha256_sum(self.string_to_sign(req).encode(), key)

    def string_to_sign(self, req: Pyjo.Message.Request.object) -> str:
        """::

            string = signer.string_to_sign(req)

        The string to sign of a request with the headers that :meth:`sign`
        sets.
        """
        canonical = sha256_sum(self.canonical_request(req).encode())
        return '\n'.join((_ALGORITHM, self._date(req), self.scope(req), canonical))

    def _canonical_path(self, req: Pyjo.Message.Request.object) -> str:
        path = req.url.path.to_str() or '/'
        if self.normalize_path:
            segments: list[str] = []
            for segment in path.split('/'):
                if segment == '..':
                    if segments:
                        segments.pop()
                elif segment not in ('', '.'):
                    segments.append(segment)
            trailing = segments and path.rsplit('/', 1)[-1] in ('', '.', '..')
            path = '/' + '/'.join(segments) + ('/' if trailing else '')
        return url_escape(path, r'^A-Za-z0-9\-._~/') if self.double_encode else path

    def _canonical_query(self, req: Pyjo.Message.Request.object) -> str:
        pairs = sorted((_escape(name), _escape(value)) for name, value in req.url.query.pairs)
        return '&'.join(f'{name}={value}' for name, value in pairs)

    def _date(self, req: Pyjo.Message.Request.object) -> str:
        if (date := req.headers.header('X-Amz-Date')) is None:
            raise Pyjo.Exception.new('No header X-Amz-Date in the request')
        return date

    # The headers in lower case, sorted, with their values without the spaces at their ends and with one space between
    # their words, and the values of a repeated header joined with commas
    def _signed_headers(self, req: Pyjo.Message.Request.object) -> list[tuple[str, str]]:
        headers = req.headers
        return sorted(
            (name.lower(), ','.join(' '.join(value.split()) for value in headers.every_header(name)))
            for name in headers.names()
            if name.lower() not in _UNSIGNED
        )


def _escape(string: str) -> str:
    return url_escape(string.encode()).decode('ascii')


# A variable of the environment, where an empty one is none, as the SDKs of AWS take it
def _environ(name: str) -> str | None:
    return getenv(name) or None


new = Pyjo_AWS_SigV4.new
object = Pyjo_AWS_SigV4
SigV4 = Pyjo_AWS_SigV4
