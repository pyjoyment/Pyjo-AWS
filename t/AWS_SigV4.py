import Pyjo.AWS.SigV4
import Pyjo.File
import Pyjo.JSON
import Pyjo.Message.Request
import Pyjo.UserAgent

from Pyjo.Test import *
from Pyjoyment.Lite import *

import datetime
import os
import re


# Signature Version 4 of AWS

SUITE = Pyjo.File.curfile().sibling('aws-signing-test-suite', 'v4')

# The suite sends a path as it is, also with a space or UTF-8 that HTTP sends percent-encoded, which the double encoding
# encodes again; and a session token that is not signed is the one of AWS IoT
SKIP = {
    'get-space-normalized': 'a path with a space, which HTTP sends percent-encoded',
    'get-space-unnormalized': 'a path with a space, which HTTP sends percent-encoded',
    'get-utf8': 'a path with UTF-8, which HTTP sends percent-encoded',
    'post-sts-header-after': 'a session token that is not signed',
}

DATE = datetime.datetime(2015, 8, 30, 12, 36, tzinfo=datetime.UTC)


def parse(raw):
    # The requests of the suite end without the empty line after their headers when they have no body
    return Pyjo.Message.Request.new().parse(raw if b'\n\n' in raw else raw + b'\n\n')


def request(method, url):
    req = Pyjo.Message.Request.new().set(method=method)
    req.url.parse(url)
    return req


def signer(**kwargs):
    return Pyjo.AWS.SigV4.new(
        service='service',
        region='us-east-1',
        access_key_id='AKIDEXAMPLE',
        secret_access_key='wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY',
        **kwargs,
    )


for case in SUITE.list(dir=True):
    with subtest(name := case.basename()):
        if name in SKIP:
            skip(SKIP[name], 5)
            continue
        context = Pyjo.JSON.decode_json(case.child('context.json').slurp())
        credentials = context['credentials']
        req = parse(case.child('request.txt').slurp())
        ok(req.is_finished, 'request parsed')
        sigv4 = Pyjo.AWS.SigV4.new(
            service=context['service'],
            region=context['region'],
            access_key_id=credentials['access_key_id'],
            secret_access_key=credentials['secret_access_key'],
            session_token=credentials.get('token'),
            normalize_path=context['normalize'],
            content_sha256=context['sign_body'],
        )
        sigv4.sign(req, datetime.datetime.fromisoformat(context['timestamp']))
        is_ok(
            sigv4.canonical_request(req), case.child('header-canonical-request.txt').slurp('UTF-8'), 'canonical request'
        )
        is_ok(sigv4.string_to_sign(req), case.child('header-string-to-sign.txt').slurp('UTF-8'), 'string to sign')
        is_ok(sigv4.signature(req), case.child('header-signature.txt').slurp('UTF-8'), 'signature')
        signed = parse(case.child('header-signed-request.txt').slurp())
        is_ok(req.headers.authorization, signed.headers.authorization, 'header Authorization')

with subtest('Credentials of the environment'):
    environ = dict(os.environ)
    try:
        os.environ.update(
            AWS_ACCESS_KEY_ID='AKIDEXAMPLE',
            AWS_SECRET_ACCESS_KEY='secret',
            AWS_SESSION_TOKEN='token',
            AWS_REGION='eu-central-1',
        )
        sigv4 = Pyjo.AWS.SigV4.new(service='lambda')
        is_ok(sigv4.access_key_id, 'AKIDEXAMPLE', 'access key ID')
        is_ok(sigv4.secret_access_key, 'secret', 'secret access key')
        is_ok(sigv4.session_token, 'token', 'session token')
        is_ok(sigv4.region, 'eu-central-1', 'region')
        del os.environ['AWS_REGION']
        os.environ['AWS_DEFAULT_REGION'] = 'eu-west-1'
        is_ok(Pyjo.AWS.SigV4.new(service='lambda').region, 'eu-west-1', 'default region')
        del os.environ['AWS_DEFAULT_REGION']
        is_ok(Pyjo.AWS.SigV4.new(service='lambda').region, 'us-east-1', 'region of no environment')
        is_ok(Pyjo.AWS.SigV4.new(service='lambda', session_token='other').session_token, 'other', 'token of argument')
        os.environ['AWS_SESSION_TOKEN'] = ''
        is_ok(Pyjo.AWS.SigV4.new(service='lambda').session_token, None, 'empty token of the environment is none')
        req = request('GET', 'https://lambda.us-east-1.amazonaws.com/')
        Pyjo.AWS.SigV4.new(service='lambda').sign(req, DATE)
        is_ok(req.headers.header('X-Amz-Security-Token'), None, 'no header of an empty token')
        for name in ('AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY'):
            del os.environ[name]
        req = request('GET', 'https://lambda.us-east-1.amazonaws.com/')
        throws_ok(
            lambda: Pyjo.AWS.SigV4.new(service='lambda').sign(req),
            re.compile(r'^No credentials of AWS'),
            'no credentials',
        )
    finally:
        os.environ.clear()
        os.environ.update(environ)

with subtest('Headers'):
    req = request('POST', 'https://lambda.us-east-1.amazonaws.com:8443/a?b=c')
    req.headers.user_agent = 'Pyjoyment'
    req.headers.header('Expect', '100-continue')
    req.body = b'{}'
    signer(session_token='token').sign(req, DATE)
    is_ok(req.headers.host, 'lambda.us-east-1.amazonaws.com:8443', 'host with port')
    is_ok(req.headers.header('X-Amz-Date'), '20150830T123600Z', 'date')
    is_ok(req.headers.header('X-Amz-Security-Token'), 'token', 'session token')
    is_ok(req.headers.header('X-Amz-Content-Sha256'), None, 'no hash of the body')
    like_ok(
        req.headers.authorization,
        re.compile(
            r'^AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20150830/us-east-1/service/aws4_request, '
            r'SignedHeaders=host;x-amz-date;x-amz-security-token, Signature=[0-9a-f]{64}$'
        ),
        'header Authorization without User-Agent and Expect',
    )
    first = req.headers.authorization
    signer(session_token='token').sign(req, DATE)
    is_ok(req.headers.authorization, first, 'signed again without the header Authorization')

with subtest('Hash of the body'):
    req = request('PUT', 'https://bucket.s3.amazonaws.com/key')
    req.body = b'Param1=value1'
    sigv4 = signer(content_sha256=True)
    sigv4.sign(req, DATE)
    digest = '9095672bbd1f56dfc5b65f3e153adc8731a4a654192329106275f4c7b24d0b6e'
    is_ok(req.headers.header('X-Amz-Content-Sha256'), digest, 'header of the hash')
    is_ok(sigv4.canonical_request(req).split('\n')[-1], digest, 'hash in the canonical request')
    req.headers.header('X-Amz-Content-Sha256', 'UNSIGNED-PAYLOAD')
    sigv4.sign(req, DATE)
    is_ok(req.headers.header('X-Amz-Content-Sha256'), 'UNSIGNED-PAYLOAD', 'header of the request kept')
    is_ok(sigv4.canonical_request(req).split('\n')[-1], 'UNSIGNED-PAYLOAD', 'header in the canonical request')

with subtest('Path'):
    url = 'https://example.amazonaws.com/a%20b//c/./d/../e/'
    req = request('GET', url)
    sigv4 = signer()
    sigv4.sign(req, DATE)
    is_ok(sigv4.canonical_request(req).split('\n')[1], '/a%2520b/c/e/', 'normalized and encoded twice')
    sigv4 = signer(normalize_path=False, double_encode=False)
    sigv4.sign(req, DATE)
    is_ok(sigv4.canonical_request(req).split('\n')[1], '/a%20b//c/./d/../e/', 'as it is sent, as S3 has it')
    req = request('GET', 'https://example.amazonaws.com')
    sigv4.sign(req, DATE)
    is_ok(sigv4.canonical_request(req).split('\n')[1], '/', 'empty path')

with subtest('User agent'):
    received = {}
    app.log.level = 'fatal'

    @post('/2018-10-31/layers/<name>/versions')
    def publish(c):
        received['req'] = c.req
        c.render(json={'Version': 1})

    sigv4 = signer()
    ua = Pyjo.UserAgent.new()
    ua.server.app = app
    ua.on('start', lambda ua, tx: sigv4.sign(tx.req))
    tx = ua.post('/2018-10-31/layers/python3_14-arm64/versions', json={'Content': {'ZipFile': 'UEsFBg=='}})
    is_ok(tx.res.json(), {'Version': 1}, 'right response')
    req = received['req']
    authorization = req.headers.authorization
    signed = re.search(r'SignedHeaders=([^,]+)', authorization)[1].split(';')
    is_ok(signed, ['accept-encoding', 'content-type', 'host', 'x-amz-date'], 'signed headers')
    for name in req.headers.names():
        if name.lower() not in signed:
            req.headers.remove(name)
    is_ok(re.search(r'Signature=(\w+)', authorization)[1], sigv4.signature(req), 'signature verified by the server')

done_testing()
