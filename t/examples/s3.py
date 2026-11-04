import Pyjo.File
import Pyjo.IOLoop.Server
import Pyjo.UserAgent

from Pyjo.Test import *

import os
import socket
import subprocess
import sys
import time


# The example against S3 of its own, which checks the signature of each request with the key of the profile of the
# example, both in processes of their own, as the example is a server of its own and its client a user agent of its own,
# which a server of a user agent of the test would not answer

tmp = Pyjo.File.tempdir()
ROOT = Pyjo.File.curfile().dirname().dirname().dirname()
EXAMPLE = ROOT.child('examples', 's3.py').to_str()

S3 = tmp.child('s3.py').spew(r"""
import Pyjo.AWS.SigV4
import Pyjo.IOLoop

from Pyjo.Util import md5_sum, xml_escape
from Pyjoyment.Lite import *

import re

app.log.level = 'fatal'

# S3 does not compress its responses, so that the large object comes in chunks
app.renderer.compress = False

SECRETS = {'AKIDPROFILE': 'profile-secret'}
PAGE = 2
BIG = bytes(range(256)) * 65536
OBJECTS = {
    'big.bin': ('application/octet-stream', BIG),
    'docs/a b,ü.txt': ('text/plain', b'Special'),
    'docs/index.html': ('text/html', b'<h1>Docs</h1>'),
    'empty.txt': ('text/plain', b''),
    'files/': ('application/x-directory', b''),
    'files/1.txt': ('text/plain', b'1'),
    'files/2.txt': ('text/plain', b'2'),
    'files/3.txt': ('text/plain', b'3'),
    'files/sub/x.txt': ('text/plain', b'x'),
    'secret.txt': ('text/plain', b'denied'),
    'slow.txt': ('text/plain', b'Slow'),
}
AUTHORIZATION = re.compile(
    r'AWS4-HMAC-SHA256 Credential=(\w+)/\d{8}/([\w-]+)/s3/aws4_request, SignedHeaders=([\w;-]+), Signature=(\w+)$'
)


def error(c, status, code, message):
    c.res.headers.content_type = 'application/xml'
    c.render(
        data=f'<Error><Code>{code}</Code><Message>{message}</Message><RequestId>s3-1</RequestId></Error>'.encode(),
        status=status,
    )


# The signature of the request as it came, before the router reads its path, with the headers that it signs only
@hook('before_dispatch')
def verify(c):
    m = AUTHORIZATION.match(c.req.headers.authorization or '')
    if not m or m[1] not in SECRETS or m[2] != 'eu-central-1':
        return error(c, 403, 'InvalidAccessKeyId', 'Unknown key')
    headers = c.req.headers
    for name in headers.names():
        if name.lower() not in m[3].split(';'):
            headers.remove(name)
    signer = Pyjo.AWS.SigV4.new(
        service='s3',
        region=m[2],
        access_key_id=m[1],
        secret_access_key=SECRETS[m[1]],
        normalize_path=False,
        double_encode=False,
        content_sha256=True,
    )
    if signer.signature(c.req) != m[4]:
        error(c, 403, 'SignatureDoesNotMatch', 'Signature does not match')


@get('/bucket')
def list_objects(c):
    if c.param('list-type') != '2':
        return error(c, 400, 'InvalidArgument', 'list-type')
    prefix, delimiter = c.param('prefix') or '', c.param('delimiter')
    entries = []
    for key in sorted(OBJECTS):
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        if delimiter and delimiter in rest:
            common = ('CommonPrefixes', prefix + rest.split(delimiter)[0] + delimiter)
            if common not in entries:
                entries.append(common)
        else:
            entries.append(('Contents', key))
    start = int(c.param('continuation-token') or 0)
    page = entries[start:start + min(PAGE, int(c.param('max-keys') or 1000))]
    rest = start + len(page) < len(entries)
    xml = ''.join(
        f'<Contents><Key>{xml_escape(name)}</Key></Contents>' if kind == 'Contents'
        else f'<CommonPrefixes><Prefix>{xml_escape(name)}</Prefix></CommonPrefixes>'
        for kind, name in page
    )
    token = f'<NextContinuationToken>{start + len(page)}</NextContinuationToken>' if rest else ''
    c.res.headers.content_type = 'application/xml'
    c.render(
        data=(
            f'<ListBucketResult><Name>bucket</Name><Prefix>{xml_escape(prefix)}</Prefix><KeyCount>{len(page)}</KeyCount>'
            f'<IsTruncated>{"true" if rest else "false"}</IsTruncated>{token}{xml}</ListBucketResult>'
        ).encode()
    )


@get('/bucket/*key')
def get_object(c):
    key = c.param('key')
    if key == 'secret.txt':
        return error(c, 403, 'AccessDenied', 'Access Denied')
    if key not in OBJECTS:
        return error(c, 404, 'NoSuchKey', 'The specified key does not exist.')
    content_type, body = OBJECTS[key]
    headers = c.res.headers
    headers.content_type = content_type
    headers.etag = f'"{md5_sum(body)}"'
    headers.last_modified = 'Wed, 04 Nov 2026 12:00:00 GMT'
    headers.header('X-Amz-Request-Id', 's3-1')

    # The headers before the content, as S3 sends them in records of TLS of their own
    if key == 'slow.txt':
        headers.content_length = len(body)
        c.write()
        Pyjo.IOLoop.timer(0.1, lambda loop: c.write(body))
        return
    c.render(data=body)


app.start()
""")

tmp.child('config').spew('[profile test]\nregion = us-east-1\n')
tmp.child('credentials').spew('[test]\naws_access_key_id = AKIDPROFILE\naws_secret_access_key = profile-secret\n')


def listen():
    port = Pyjo.IOLoop.Server.object.generate_port()
    return port, f'http://127.0.0.1:{port}'


def wait_for(process, port):
    deadline = time.monotonic() + 30
    while True:
        try:
            socket.create_connection(('127.0.0.1', port), timeout=1).close()
            return
        except OSError:
            if time.monotonic() > deadline or process.poll() is not None:
                raise
            time.sleep(0.1)


# The environment of the example, of the files of the test only, whose profile has the key that S3 knows, and the
# region of the options over the one of the profile; the profile of the option comes over the key of the environment,
# which S3 does not know, as --profile of the AWS CLI does
env = {name: value for name, value in os.environ.items() if not name.startswith(('AWS_', 'S3_'))}
env.update(
    AWS_ACCESS_KEY_ID='AKIDENVIRONMENT',
    AWS_SECRET_ACCESS_KEY='environment-secret',
    AWS_CONFIG_FILE=str(tmp.child('config')),
    AWS_SHARED_CREDENTIALS_FILE=str(tmp.child('credentials')),
    AWS_EC2_METADATA_DISABLED='true',
    HOME=str(tmp),
    PYJO_LOG_LEVEL='fatal',
)

s3_port, s3_url = listen()
app_port, app_url = listen()
s3 = subprocess.Popen(
    [sys.executable, str(S3), 'daemon', '-l', s3_url], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
stderr = tmp.child('stderr')
with stderr.open('w') as log:
    example = subprocess.Popen(
        [
            sys.executable,
            EXAMPLE,
            *('--bucket', 'bucket', '--profile', 'test', '--region', 'eu-central-1', '--endpoint-url', s3_url),
            *('daemon', '-l', app_url),
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=log,
    )

ua = Pyjo.UserAgent.new(max_connections=0)

try:
    wait_for(s3, s3_port)
    wait_for(example, app_port)

    with subtest('Objects'):
        tx = ua.get(f'{app_url}/big.bin')
        is_ok(tx.res.code, 200, 'large object')
        is_ok(tx.res.body, bytes(range(256)) * 65536, 'content of the large object')
        is_ok(tx.res.headers.content_type, 'application/octet-stream', 'type of the object')
        is_ok(tx.res.headers.content_length, str(256 * 65536), 'length of the object')
        like_ok(tx.res.headers.etag, r'^"[0-9a-f]{32}"$', 'ETag of the object')
        is_ok(tx.res.headers.last_modified, 'Wed, 04 Nov 2026 12:00:00 GMT', 'date of the object')
        is_ok(tx.res.headers.header('X-Amz-Request-Id'), None, 'other headers of S3 left out')

        tx = ua.get(f'{app_url}/docs/a%20b%2C%C3%BC.txt')
        is_ok(tx.res.code, 200, 'key with a space, a comma and UTF-8, signed as it is sent')
        is_ok(tx.res.text, 'Special', 'content of the key')

        tx = ua.get(f'{app_url}/slow.txt')
        is_ok(tx.res.code, 200, 'object whose content comes after its headers')
        is_ok(tx.res.text, 'Slow', 'content after the headers')

        tx = ua.get(f'{app_url}/empty.txt')
        is_ok(tx.res.code, 200, 'empty object')
        is_ok(tx.res.body, b'', 'no content')

        tx = ua.get(f'{app_url}/docs/')
        is_ok(tx.res.code, 200, 'index.html of a folder')
        is_ok(tx.res.text, '<h1>Docs</h1>', 'content of index.html')

        # A client that goes away in the middle of a large object, after which the example serves the others
        with socket.create_connection(('127.0.0.1', app_port)) as client:
            client.sendall(b'GET /big.bin HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n')
            ok(client.recv(1024).startswith(b'HTTP/1.1 200 OK'), 'large object to a client that goes away')
        time.sleep(0.5)
        is_ok(ua.get(f'{app_url}/files/1.txt').res.text, '1', 'object after a client that went away')

    with subtest('Folders'):
        tx = ua.get(f'{app_url}/')
        is_ok(tx.res.code, 200, 'root without index.html')
        is_ok(
            [a.text for a in tx.res.dom().find('li a')],
            ['big.bin', 'docs/', 'empty.txt', 'files/', 'secret.txt', 'slow.txt'],
            'folders and objects of the pages of the list',
        )

        tx = ua.get(f'{app_url}/files/')
        is_ok(
            [a.text for a in tx.res.dom().find('li a')],
            ['../', '1.txt', '2.txt', '3.txt', 'sub/'],
            'folder without its own empty object',
        )
        is_ok(tx.res.dom().at('a[href$="sub/"]')['href'], '/files/sub/', 'link of a subfolder')

        tx = ua.get(f'{app_url}/docs')
        is_ok(tx.res.code, 302, 'folder without its slash')
        is_ok(tx.res.headers.location, '/docs/', 'redirect to the folder')

    with subtest('Errors'):
        is_ok(ua.get(f'{app_url}/missing').res.code, 404, 'missing object')
        is_ok(ua.get(f'{app_url}/missing/').res.code, 404, 'missing folder')
        is_ok(ua.get(f'{app_url}/secret.txt').res.code, 500, 'error of S3')
finally:
    for process in (example, s3):
        process.terminate()
        process.wait()

is_ok(example.returncode, 0, 'the example stopped and closed its connections')
is_ok(stderr.slurp().decode(), '', 'nothing on the standard error of the example')

done_testing()
