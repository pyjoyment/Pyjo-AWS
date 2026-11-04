"""
Pyjo.AWS.ECDSA - Signatures of ES256 of a key of P-256
======================================================
::

    from Pyjo.AWS.ECDSA import ECDSA

    key = ECDSA.from_pem(open('key.pem').read())
    signature = key.sign(b'header.payload')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.ECDSA

    key = Pyjo.AWS.ECDSA.from_pem(pem, backend='python')
    print(key.jwk(), key.verify(b'header.payload', signature))

:mod:`Pyjo.AWS.ECDSA` is a private key of ECDSA of the curve P-256, which
signs with SHA-256, as ES256 of JSON Web Signature, of RFC 7518, has it: the
signature is ``r`` and ``s`` of 32 bytes each, not the DER of X.509. The DPoP
of :mod:`Pyjo.AWS.Credentials.Login` signs with it.

The signature is the one of the package ``cryptography`` when it is
installed, as the extra ``cryptography`` of the distribution installs it: ::

    pip install 'Pyjo-AWS[cryptography]'

or of Python itself otherwise, with the nonce of RFC 6979, which a key and a
message determine, so that no random number of the machine makes it. That
one is not constant-time: it is for a key and a signature that are made on
the machine that has the key, not for a server that signs what anyone sends
it.

See also
--------

:mod:`Pyjo.AWS.Credentials.Login`, :rfc:`6979`, :rfc:`7518`,
https://cryptography.io/.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception

import base64
import functools
import hashlib
import hmac
import importlib

from typing import Any, Literal, cast


P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
"""The prime of the field of P-256."""

A = P - 3
"""The coefficient ``a`` of P-256."""

B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
"""The coefficient ``b`` of P-256."""

N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
"""The order of the base point of P-256."""

G = (
    0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
    0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5,
)
"""The base point of P-256."""

# The object identifiers of a public key of EC, of X9.62, and of the curve P-256, prime256v1, as DER has them
_EC_PUBLIC_KEY = bytes.fromhex('2a8648ce3d0201')
_PRIME256V1 = bytes.fromhex('2a8648ce3d030107')

type Point = tuple[int, int] | None
type Backend = Literal['cryptography', 'python']


class Pyjo_AWS_ECDSA(Pyjo.Base.object):
    """
    :mod:`Pyjo.AWS.ECDSA` inherits all attributes and methods from
    :mod:`Pyjo.Base` and implements the following new ones.
    """

    def __init__(self, private_value: int, *, backend: Backend | None = None) -> None:
        """::

            key = Pyjo.AWS.ECDSA.new(0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721)
            key = Pyjo.AWS.ECDSA.new(private_value, backend='python')

        Construct a new :mod:`Pyjo.AWS.ECDSA` object of the private value of
        a key, with the backend of ``cryptography`` when it is installed, or
        of Python.
        """
        if not 0 < private_value < N:
            raise Pyjo.Exception.new('Invalid private key of P-256')

        self.private_value = private_value
        """::

            d = key.private_value

        The private value of the key.
        """

        crypto = _cryptography() if backend != 'python' else None
        if backend == 'cryptography' and crypto is None:
            raise Pyjo.Exception.new(
                "The backend cryptography of ECDSA is not installed: pip install 'Pyjo-AWS[cryptography]'"
            )

        self.backend: Backend = 'cryptography' if crypto is not None else 'python'
        """::

            name = key.backend

        The backend of the signatures, ``cryptography`` or ``python``.
        """

        self._key: Any = None
        if crypto is not None:
            self._key = crypto.ec.derive_private_key(private_value, crypto.ec.SECP256R1())
            numbers = self._key.public_key().public_numbers()
            point = (numbers.x, numbers.y)
        else:
            point = cast(tuple[int, int], _multiply(private_value, G))

        self.public_point: tuple[int, int] = point
        """::

            x, y = key.public_point

        The point of the public key.
        """

    @classmethod
    def from_pem(cls, pem: str | bytes, *, backend: Backend | None = None) -> 'Pyjo_AWS_ECDSA':
        """::

            key = Pyjo.AWS.ECDSA.from_pem(pem)

        A new :mod:`Pyjo.AWS.ECDSA` object of a private key of P-256 in PEM,
        of PKCS #8, ``BEGIN PRIVATE KEY``, or of SEC 1, ``BEGIN EC PRIVATE
        KEY``, without a password.
        """
        text = pem.decode() if isinstance(pem, bytes) else pem
        lines = [line.strip() for line in text.strip().splitlines()]
        if len(lines) < 3 or not lines[0].startswith('-----BEGIN ') or not lines[-1].startswith('-----END '):
            raise Pyjo.Exception.new('Invalid private key of P-256: not PEM')
        label = lines[0].removeprefix('-----BEGIN ').removesuffix('-----')
        try:
            der = base64.b64decode(''.join(lines[1:-1]), validate=True)
            if label == 'PRIVATE KEY':
                private_value = _pkcs8(der)
            elif label == 'EC PRIVATE KEY':
                private_value = _sec1(der, None)
            else:
                raise ValueError(f'a PEM of {label}')
        except ValueError as e:
            raise Pyjo.Exception.new(f'Invalid private key of P-256: {e}') from None
        return cls(private_value, backend=backend)

    def jwk(self) -> dict[str, str]:
        """::

            jwk = key.jwk()

        The public key as a JSON Web Key, of RFC 7518, with ``kty``, ``crv``,
        ``x`` and ``y``.
        """
        x, y = self.public_point
        return {'kty': 'EC', 'crv': 'P-256', 'x': base64url(_bytes(x)), 'y': base64url(_bytes(y))}

    def sign(self, data: bytes) -> bytes:
        """::

            signature = key.sign(b'header.payload')

        The signature of ES256 of data, ``r`` and ``s`` of 32 bytes each.
        """
        if self._key is not None:
            crypto = cast(Any, _cryptography())
            der = self._key.sign(data, crypto.ec.ECDSA(crypto.hashes.SHA256()))
            r, s = crypto.utils.decode_dss_signature(der)
            return _bytes(r) + _bytes(s)
        return _sign(self.private_value, hashlib.sha256(data).digest())

    def verify(self, data: bytes, signature: bytes) -> bool:
        """::

            boolean = key.verify(b'header.payload', signature)

        Whether a signature of ES256 of data is the one of the public key.
        """
        return verify(self.public_point, data, signature)


def base64url(data: bytes) -> str:
    """::

        string = Pyjo.AWS.ECDSA.base64url(b'data')

    The base64url of data without its padding, as JSON Web Signature has it.
    """
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def verify(public_point: tuple[int, int], data: bytes, signature: bytes) -> bool:
    """::

        boolean = Pyjo.AWS.ECDSA.verify((x, y), b'header.payload', signature)

    Whether a signature of ES256 of data is the one of a public key, in
    Python.
    """
    if len(signature) != 64 or not _on_curve(public_point):
        return False
    r, s = int.from_bytes(signature[:32]), int.from_bytes(signature[32:])
    if not (0 < r < N and 0 < s < N):
        return False
    e = int.from_bytes(hashlib.sha256(data).digest())
    w = pow(s, -1, N)
    point = _add(_multiply(e * w % N, G), _multiply(r * w % N, public_point))
    return point is not None and point[0] % N == r


# The modules of the package cryptography, which the distribution does not depend on, so that pyright takes them as Any
class _Crypto:
    def __init__(self) -> None:
        self.ec: Any = importlib.import_module('cryptography.hazmat.primitives.asymmetric.ec')
        self.hashes: Any = importlib.import_module('cryptography.hazmat.primitives.hashes')
        self.utils: Any = importlib.import_module('cryptography.hazmat.primitives.asymmetric.utils')


@functools.cache
def _cryptography() -> _Crypto | None:
    try:
        return _Crypto()
    except ImportError:
        return None


def _bytes(value: int) -> bytes:
    return value.to_bytes(32)


# The signature of a digest of SHA-256, of the nonce of RFC 6979, section 3.2, as the order of P-256 and the digest have
# 256 bits each, so that a value of HMAC is a candidate of the nonce as it is
def _sign(d: int, digest: bytes) -> bytes:
    e = int.from_bytes(digest)
    x, h = _bytes(d), _bytes(e % N)
    v, k = b'\x01' * 32, b'\x00' * 32
    k = hmac.digest(k, v + b'\x00' + x + h, 'sha256')
    v = hmac.digest(k, v, 'sha256')
    k = hmac.digest(k, v + b'\x01' + x + h, 'sha256')
    v = hmac.digest(k, v, 'sha256')
    while True:
        v = hmac.digest(k, v, 'sha256')
        nonce = int.from_bytes(v)
        if 0 < nonce < N:
            point = cast(tuple[int, int], _multiply(nonce, G))
            r = point[0] % N
            s = pow(nonce, -1, N) * (e + r * d) % N
            if r and s:
                return _bytes(r) + _bytes(s)
        k = hmac.digest(k, v + b'\x00', 'sha256')
        v = hmac.digest(k, v, 'sha256')


def _on_curve(point: Point) -> bool:
    if point is None:
        return False
    x, y = point
    return 0 <= x < P and 0 <= y < P and (y * y - x * x * x - A * x - B) % P == 0


# The sum of two points in affine coordinates, None for the point at infinity
def _add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        slope = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        slope = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (slope * slope - x1 - x2) % P
    return x3, (slope * (x1 - x3) - y1) % P


def _multiply(k: int, point: Point) -> Point:
    result: Point = None
    for bit in bin(k)[2:]:
        result = _add(result, result)
        if bit == '1':
            result = _add(result, point)
    return result


# A value of DER at a position: its tag, its content and the position after it
def _tlv(der: bytes, pos: int) -> tuple[int, bytes, int]:
    if pos + 2 > len(der):
        raise ValueError('a truncated DER')
    tag, length = der[pos], der[pos + 1]
    pos += 2
    if length & 0x80:
        size = length & 0x7F
        if not 0 < size <= 2 or pos + size > len(der):
            raise ValueError('an invalid length of DER')
        length = int.from_bytes(der[pos : pos + size])
        pos += size
    if pos + length > len(der):
        raise ValueError('a truncated DER')
    return tag, der[pos : pos + length], pos + length


def _sequence(der: bytes) -> list[tuple[int, bytes]]:
    tag, content, end = _tlv(der, 0)
    if tag != 0x30 or end != len(der):
        raise ValueError('not a sequence of DER')
    return _elements(content)


def _elements(content: bytes) -> list[tuple[int, bytes]]:
    items: list[tuple[int, bytes]] = []
    pos = 0
    while pos < len(content):
        tag, value, pos = _tlv(content, pos)
        items.append((tag, value))
    return items


# PrivateKeyInfo of PKCS #8, RFC 5208, whose algorithm is a public key of EC of P-256, with ECPrivateKey of SEC 1
def _pkcs8(der: bytes) -> int:
    items = _sequence(der)
    if len(items) < 3 or items[0] != (0x02, b'\x00') or items[1][0] != 0x30 or items[2][0] != 0x04:
        raise ValueError('not a private key of PKCS #8')
    algorithm = _elements(items[1][1])
    if [value for _, value in algorithm[:2]] != [_EC_PUBLIC_KEY, _PRIME256V1]:
        raise ValueError('not a key of P-256')
    return _sec1(items[2][1], _PRIME256V1)


# ECPrivateKey of SEC 1, RFC 5915, whose curve is P-256, of its parameters or of the algorithm of PKCS #8
def _sec1(der: bytes, curve: bytes | None) -> int:
    items = _sequence(der)
    if len(items) < 2 or items[0] != (0x02, b'\x01') or items[1][0] != 0x04 or len(items[1][1]) != 32:
        raise ValueError('not a private key of EC')
    for tag, value in items[2:]:
        if tag == 0xA0:
            _, oid, _ = _tlv(value, 0)
            curve = oid
    if curve != _PRIME256V1:
        raise ValueError('not a key of P-256')
    return int.from_bytes(items[1][1])


def from_pem(pem: str | bytes, *, backend: Backend | None = None) -> Pyjo_AWS_ECDSA:
    """::

        key = Pyjo.AWS.ECDSA.from_pem(pem)

    Alias for :meth:`Pyjo_AWS_ECDSA.from_pem`.
    """
    return Pyjo_AWS_ECDSA.from_pem(pem, backend=backend)


new = Pyjo_AWS_ECDSA.new
object = Pyjo_AWS_ECDSA
ECDSA = Pyjo_AWS_ECDSA
