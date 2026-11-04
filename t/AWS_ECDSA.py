import Pyjo.AWS.ECDSA
import Pyjo.File

from Pyjo.Test import *

import base64
import importlib.util
import re
import shutil
import subprocess


# The key of P-256 of RFC 6979, A.2.5, and the signatures of SHA-256 of its messages, whose nonce the key and the message
# determine
D = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
UX = 0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6
UY = 0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299
VECTORS = {
    b'sample': (
        'EFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716',
        'F7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8',
    ),
    b'test': (
        'F1ABB023518351CD71D881567B1EA663ED3EFCF6C5132B354F28D3B0B7D38367',
        '019F4113742A2B14BD25926B49C649155F267E60D3814B4C0CC84250E46F0083',
    ),
}

# The key of PKCS #8 of the cases of aws login of botocore
PKCS8 = (
    '-----BEGIN PRIVATE KEY-----\n'
    'MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg+PNauWi/ihtwHHbq\n'
    '1tgc8Vgpwx0qQlNSN38y+z0igWehRANCAAR2Ntw6BXJ1v8jb9XjzKZJ+gL5f/3Jq\n'
    'IqiH2PUGKWxoFwNlcNB83FivEXEzlTbuCQK5OezOYb3gbvHuzKkB0nDX\n'
    '-----END PRIVATE KEY-----'
)
P256 = '06082a8648ce3d030107'
P384 = '06052b81040022'


def pem(label, der):
    lines = re.findall('.{1,64}', base64.b64encode(der).decode())
    return '\n'.join([f'-----BEGIN {label}-----', *lines, f'-----END {label}-----']) + '\n'


# ECPrivateKey of SEC 1 of a private value, with the parameters of a curve
def sec1(d, curve=P256):
    params = bytes.fromhex(curve)
    body = bytes.fromhex('020101' + '0420') + d.to_bytes(32) + bytes([0xA0, len(params)]) + params
    return pem('EC PRIVATE KEY', bytes([0x30, len(body)]) + body)


# The public key of SubjectPublicKeyInfo and the signature of DER, which openssl verifies
def public_pem(point):
    x, y = point
    der = (
        bytes.fromhex('3059301306072a8648ce3d020106082a8648ce3d030107034200')
        + b'\x04'
        + x.to_bytes(32)
        + y.to_bytes(32)
    )
    return pem('PUBLIC KEY', der)


def der_signature(signature):
    def integer(value):
        data = value.lstrip(b'\x00') or b'\x00'
        data = b'\x00' + data if data[0] & 0x80 else data
        return bytes([0x02, len(data)]) + data

    body = integer(signature[:32]) + integer(signature[32:])
    return bytes([0x30, len(body)]) + body


BACKENDS = ['python'] + (['cryptography'] if importlib.util.find_spec('cryptography') else [])

with subtest('Vectors of RFC 6979'):
    key = Pyjo.AWS.ECDSA.new(D, backend='python')
    is_ok(key.backend, 'python', 'backend of Python')
    is_ok(key.public_point, (UX, UY), 'public key')
    for message, (r, s) in VECTORS.items():
        is_ok(key.sign(message).hex().upper(), r + s, f'deterministic signature of {message.decode()}')
        ok(key.verify(message, key.sign(message)), f'verified signature of {message.decode()}')
    ok(not key.verify(b'other', key.sign(b'sample')), 'signature of another message')
    signature = bytearray(key.sign(b'sample'))
    signature[10] ^= 1
    ok(not key.verify(b'sample', bytes(signature)), 'changed signature')
    ok(not key.verify(b'sample', key.sign(b'sample')[:63]), 'short signature')
    other = Pyjo.AWS.ECDSA.new(D + 1, backend='python')
    ok(not other.verify(b'sample', key.sign(b'sample')), 'signature of another key')

with subtest('Keys of PEM'):
    key = Pyjo.AWS.ECDSA.from_pem(PKCS8, backend='python')
    is_ok(
        key.jwk(),
        {
            'kty': 'EC',
            'crv': 'P-256',
            'x': 'djbcOgVydb_I2_V48ymSfoC-X_9yaiKoh9j1BilsaBc',
            'y': 'A2Vw0HzcWK8RcTOVNu4JArk57M5hveBu8e7MqQHScNc',
        },
        'JSON Web Key of PKCS #8',
    )
    is_ok(Pyjo.AWS.ECDSA.from_pem(sec1(D), backend='python').public_point, (UX, UY), 'key of SEC 1')
    is_ok(Pyjo.AWS.ECDSA.from_pem(sec1(D).encode(), backend='python').private_value, D, 'PEM of bytes')
    for name, value, error in (
        ('not PEM', 'secret', 'not PEM'),
        ('P-384', sec1(D, P384), 'not a key of P-256'),
        ('certificate', pem('CERTIFICATE', b'\x30\x00'), 'a PEM of CERTIFICATE'),
        ('truncated', PKCS8.replace('IqiH2PUGKWxoFwNlcNB83FivEXEzlTbuCQK5OezOYb3gbvHuzKkB0nDX\n', ''), 'truncated'),
    ):
        throws_ok(
            lambda value=value: Pyjo.AWS.ECDSA.from_pem(value, backend='python'),
            re.compile(rf'^Invalid private key of P-256: .*{error}'),
            f'invalid key: {name}',
        )
    throws_ok(lambda: Pyjo.AWS.ECDSA.new(0), re.compile(r'^Invalid private key of P-256'), 'zero')
    throws_ok(lambda: Pyjo.AWS.ECDSA.new(Pyjo.AWS.ECDSA.N), re.compile(r'^Invalid private key of P-256'), 'order')

with subtest('Backends'):
    key = Pyjo.AWS.ECDSA.from_pem(PKCS8, backend='python')
    for backend in BACKENDS:
        signer = Pyjo.AWS.ECDSA.from_pem(PKCS8, backend=backend)
        is_ok(signer.backend, backend, f'backend {backend}')
        is_ok(signer.public_point, key.public_point, f'public key of {backend}')
        ok(key.verify(b'header.payload', signer.sign(b'header.payload')), f'signature of {backend} verified')
    if 'cryptography' in BACKENDS:
        is_ok(Pyjo.AWS.ECDSA.new(D).backend, 'cryptography', 'cryptography by default')
    else:
        is_ok(Pyjo.AWS.ECDSA.new(D).backend, 'python', 'Python without cryptography')
        throws_ok(
            lambda: Pyjo.AWS.ECDSA.new(D, backend='cryptography'),
            re.compile(r'^The backend cryptography of ECDSA is not installed'),
            'cryptography that is not installed',
        )

with subtest('Signatures verified by openssl'):
    if not shutil.which('openssl'):
        plan(skip_all='no openssl')
    tmp = Pyjo.File.tempdir()
    for backend in BACKENDS:
        key = Pyjo.AWS.ECDSA.from_pem(PKCS8, backend=backend)
        tmp.child('public.pem').spew(public_pem(key.public_point))
        tmp.child('data').spew(b'header.payload')
        tmp.child('signature').spew(der_signature(key.sign(b'header.payload')))
        result = subprocess.run(
            [
                'openssl',
                *('dgst', '-sha256', '-verify', str(tmp.child('public.pem'))),
                *('-signature', str(tmp.child('signature')), str(tmp.child('data'))),
            ],
            capture_output=True,
            text=True,
        )
        is_ok(result.stdout.strip(), 'Verified OK', f'signature of {backend}')

done_testing()
