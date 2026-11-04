import Pyjo.AWS.Config
import Pyjo.AWS.Credentials
import Pyjo.AWS.Credentials.Chain
import Pyjo.AWS.Credentials.Login
import Pyjo.AWS.Credentials.Profile
import Pyjo.AWS.ECDSA
import Pyjo.Date
import Pyjo.File
import Pyjo.JSON
import Pyjo.UserAgent

from Pyjo.Test import *
from Pyjo.Util import b64url_decode, sha256_sum
from Pyjoyment.Lite import *

import contextlib
import os
import re
import stat
import sys
import time


# The credentials of aws login, of the cache of the AWS CLI, refreshed with CreateOAuth2Token of the sign-in service and
# the proof of DPoP of the key of the session, against an application that serves the sign-in service and checks the
# proof, with the cases of botocore

tmp = Pyjo.File.tempdir()
cache = tmp.child('.aws', 'login', 'cache').make_path()
CASES = Pyjo.JSON.decode_json(
    Pyjo.File.curfile().sibling('login-provider-test-cases', 'login-provider-test-cases.json').slurp()
)
SESSION = 'arn:aws:sts::012345678910:assumed-role/Admin/admin'
KEY = CASES[0]['cacheContents'][next(iter(CASES[0]['cacheContents']))]['dpopKey']


@contextlib.contextmanager
def environ(**values):
    saved = dict(os.environ)
    try:
        for name in list(os.environ):
            if name.startswith('AWS_'):
                del os.environ[name]
        os.environ.update(
            HOME=str(tmp),
            AWS_CONFIG_FILE=str(tmp.child('config')),
            AWS_SHARED_CREDENTIALS_FILE=str(tmp.child('credentials')),
            AWS_EC2_METADATA_DISABLED='true',
            AWS_LOGIN_CACHE_DIRECTORY=str(cache),
            AWS_ENDPOINT_URL_SIGNIN='/signin',
            **values,
        )
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


def wait(promise):
    result = {}
    promise.then(
        lambda *values: result.update(value=values[0] if len(values) == 1 else values),
        lambda reason: result.update(error=reason),
    ).wait()
    return result


def iso(seconds):
    return Pyjo.Date.new(int(time.time()) + seconds).to_rfc3339()


def setup(config, files):
    tmp.child('config').spew(config)
    tmp.child('credentials').spew('')
    for path in cache.list():
        path.remove()
    for name, content in files.items():
        cache.child(name).spew(Pyjo.JSON.encode_json(content))


def session_file(session=SESSION):
    return cache.child(sha256_sum(session.encode()) + '.json')


def token(access_key_id='AKIDLOGIN', expires=15 * 60, refresh='refresh', key=KEY):
    return {
        'accessToken': {
            'accessKeyId': access_key_id,
            'secretAccessKey': 'secret',
            'sessionToken': 'session',
            'accountId': '012345678901',
            'expiresAt': iso(expires),
        },
        'clientId': 'arn:aws:signin:::devtools/same-device',
        'refreshToken': refresh,
        'idToken': 'id',
        'dpopKey': key,
    }


def profile(name='signin', **kwargs):
    return Pyjo.AWS.Credentials.Profile.new(config=Pyjo.AWS.Config.new(profile=name), ua=ua, **kwargs)


# The sign-in service, whose responses of the refresh tokens of a test come in mocks, which checks the proof of DPoP
# of each request: its key in the header of the JWT, its signature of ES256, the method and the URL of the request,
# its time and its ID
app.log.level = 'fatal'
mocks = {}
calls = []


def proof(c):
    jwt = c.req.headers.header('DPoP') or ''
    parts = jwt.split('.')
    if len(parts) != 3:
        return 'no JWT'
    header, payload = Pyjo.JSON.decode_json(b64url_decode(parts[0])), Pyjo.JSON.decode_json(b64url_decode(parts[1]))
    jwk = header.get('jwk') or {}
    if header.get('typ') != 'dpop+jwt' or header.get('alg') != 'ES256' or jwk.get('crv') != 'P-256':
        return f'header {header}'
    point = (int.from_bytes(b64url_decode(jwk['x'])), int.from_bytes(b64url_decode(jwk['y'])))
    if not Pyjo.AWS.ECDSA.verify(point, f'{parts[0]}.{parts[1]}'.encode(), b64url_decode(parts[2])):
        return 'signature'
    if payload.get('htm') != 'POST' or payload.get('htu') != c.req.url.path.to_str():
        return f'payload {payload}'
    if abs(payload.get('iat', 0) - time.time()) > 60 or not re.match(r'^[0-9a-f-]{36}$', payload.get('jti', '')):
        return f'payload {payload}'
    return jwk


@post('/signin/v1/token')
def token_action(c):
    body = c.req.json()
    checked = proof(c)
    calls.append({'body': body, 'proof': checked, 'content_type': c.req.headers.content_type})
    if not isinstance(checked, dict):
        c.res.headers.header('X-Amzn-ErrorType', 'ValidationException')
        return c.render(json={'message': f'Invalid DPoP: {checked}'}, status=400)
    mock = mocks.get(body.get('refreshToken'))
    if mock is None:
        c.res.headers.header('X-Amzn-ErrorType', 'AccessDeniedException')
        return c.render(json={'error': 'TOKEN_EXPIRED', 'message': 'The refresh token has expired'}, status=401)
    if 'response' not in mock:
        return c.rendered(mock.get('responseCode', 500))
    c.render(json=mock['response']['tokenOutput'])


ua = Pyjo.UserAgent.new()
ua.server.app = app


def expires_in(value):
    return float(Pyjo.AWS.Credentials.parse_time(value)) - time.time()


with subtest('Cases of botocore'):
    for case in CASES:
        name = case['documentation']
        with environ():
            setup(case['configContents'], case.get('cacheContents', {}))
            mocks.clear()
            calls.clear()
            for mock in case.get('mockApiCalls', []):
                mocks[mock['request']['tokenInput']['refreshToken']] = mock
            try:
                credentials, error = profile().credentials(), None
            except Exception as e:
                credentials, error = None, e
            is_ok(
                [call['body'] for call in calls],
                [mock['request']['tokenInput'] for mock in case.get('mockApiCalls', [])],
                f'{name}: calls',
            )
            ok(all(isinstance(call['proof'], dict) for call in calls), f'{name}: proofs of DPoP')
            for outcome in case['outcomes']:
                if outcome['result'] == 'error':
                    ok(error is not None, f'{name}: error')
                elif outcome['result'] == 'credentials':
                    if error is not None:
                        fail_ok(f'{name}: credentials: {error}')
                        continue
                    is_ok(
                        [credentials.access_key_id, credentials.secret_access_key, credentials.session_token],
                        [outcome['accessKeyId'], outcome['secretAccessKey'], outcome['sessionToken']],
                        f'{name}: credentials',
                    )
                    is_ok(credentials.account_id, outcome['accountId'], f'{name}: account')
                    is_ok(credentials.provider, 'login', f'{name}: provider')
                    if case.get('mockApiCalls'):
                        ok(850 < credentials.expires_in() < 950, f'{name}: expiration of expiresIn')
                    else:
                        is_ok(
                            credentials.expiration,
                            Pyjo.AWS.Credentials.parse_time(outcome['expiresAt']),
                            f'{name}: expiration',
                        )
                elif outcome['result'] == 'cacheContents':
                    for file, expected in outcome.items():
                        if file == 'result':
                            continue
                        written = Pyjo.JSON.decode_json(cache.child(file).slurp())
                        ok(850 < expires_in(written['accessToken'].pop('expiresAt')) < 950, f'{name}: expiresAt')
                        expected['accessToken'].pop('expiresAt')
                        is_ok(written, expected, f'{name}: cache')
                        is_ok(stat.S_IMODE(cache.child(file).stat().st_mode), 0o600, f'{name}: owner only')

with subtest('Sessions'):
    config = (
        f'[profile signin]\nlogin_session = {SESSION}\nregion = eu-central-1\n\n[profile other]\nregion = us-east-1\n'
    )
    with environ():
        setup(config, {})
        provider = Pyjo.AWS.Credentials.Login.new(config=Pyjo.AWS.Config.new(profile='signin'), ua=ua)
        is_ok(provider.cache_dir, str(cache), 'cache of AWS_LOGIN_CACHE_DIRECTORY')
        is_ok(
            provider.cache_file(SESSION).basename(),
            next(iter(CASES[0]['cacheContents'])),
            'file of the SHA-256 of the session, as botocore names it',
        )
        is_ok(provider.endpoint_url(), '/signin', 'endpoint of AWS_ENDPOINT_URL_SIGNIN')
        is_ok(
            Pyjo.AWS.Credentials.Login.new(config=Pyjo.AWS.Config.new(profile='other')).credentials(),
            None,
            'no session',
        )
        throws_ok(
            lambda: provider.credentials(),
            re.compile(rf'^No login session {re.escape(SESSION)} of AWS in .*: aws login --profile signin'),
            'session not in the cache',
        )

    with environ():
        del os.environ['AWS_LOGIN_CACHE_DIRECTORY']
        del os.environ['AWS_ENDPOINT_URL_SIGNIN']
        setup(config, {})
        provider = Pyjo.AWS.Credentials.Login.new(config=Pyjo.AWS.Config.new(profile='signin'))
        is_ok(provider.cache_dir, str(tmp.child('.aws', 'login', 'cache')), 'cache of the AWS CLI')
        is_ok(provider.endpoint_url(), 'https://eu-central-1.signin.aws.amazon.com', 'endpoint of the region')
        os.environ['AWS_REGION'] = 'cn-north-1'
        is_ok(
            Pyjo.AWS.Credentials.Login.new(config=Pyjo.AWS.Config.new(profile='other')).endpoint_url(),
            'https://cn-north-1.signin.amazonaws.cn',
            'endpoint of China',
        )

    with environ():
        setup(config, {session_file().basename(): token()})
        mocks.clear()
        calls.clear()
        credentials = profile().credentials()
        is_ok(credentials.access_key_id, 'AKIDLOGIN', 'valid credentials of the cache')
        is_ok(calls, [], 'no refresh of valid credentials')
        result = wait(profile().credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDLOGIN', 'non-blocking')
        is_ok(
            Pyjo.AWS.Credentials.Chain.new(config=Pyjo.AWS.Config.new(profile='signin'), ua=ua).credentials().provider,
            'login',
            'credentials of the chain',
        )

        mocks['refresh'] = {
            'response': {
                'tokenOutput': {
                    'accessToken': {'accessKeyId': 'AKIDNEW', 'secretAccessKey': 'new', 'sessionToken': 'new-session'},
                    'refreshToken': 'refresh2',
                    'expiresIn': 900,
                    'tokenType': 'aws_sigv4',
                }
            }
        }
        setup(config, {session_file().basename(): token(expires=2 * 60)})
        credentials = profile().credentials()
        is_ok(credentials.access_key_id, 'AKIDNEW', 'refreshed before the expiration')
        is_ok(calls[-1]['content_type'], 'application/json', 'JSON of the request')
        written = Pyjo.JSON.decode_json(session_file().slurp())
        is_ok(written['refreshToken'], 'refresh2', 'new refresh token in the cache')
        is_ok(written['idToken'], 'id', 'other fields of the cache kept')

        setup(config, {session_file().basename(): token(expires=2 * 60, refresh='revoked')})
        is_ok(profile().credentials().access_key_id, 'AKIDLOGIN', 'valid credentials after a failed refresh')
        setup(config, {session_file().basename(): token(expires=-60, refresh='revoked')})
        throws_ok(
            lambda: profile().credentials(),
            re.compile(rf'^The login session {re.escape(SESSION)} of AWS has ended \(TOKEN_EXPIRED\): aws login'),
            'expired refresh token',
        )
        is_ok(
            Pyjo.JSON.decode_json(session_file().slurp())['refreshToken'],
            'revoked',
            'cache kept after a failed refresh',
        )

        setup(config, {session_file().basename(): token(expires=-60, key='broken')})
        throws_ok(
            lambda: profile().credentials(),
            re.compile(r'^Cannot refresh the credentials of the login session .*: Invalid dpopKey of the cache'),
            'invalid key',
        )

        cached = token()
        del cached['accessToken']['secretAccessKey']
        setup(config, {session_file().basename(): cached})
        throws_ok(
            lambda: profile().credentials(),
            re.compile(r'^Invalid login session .*: no accessToken\.secretAccessKey: aws login'),
            'credentials without their secret',
        )
        session_file().spew('{')
        throws_ok(lambda: profile().credentials(), re.compile(r'^Invalid login session '), 'invalid cache')

with subtest('Order of the profile'):
    with environ():
        setup(
            f'[profile both]\nlogin_session = {SESSION}\naws_access_key_id = AKIDKEYS\naws_secret_access_key = s\n\n'
            f'[profile process]\nlogin_session = {SESSION}\ncredential_process = {sys.executable} -c "exit(1)"\n',
            {session_file().basename(): token()},
        )
        is_ok(profile('both').credentials().access_key_id, 'AKIDKEYS', 'keys before the login session')
        is_ok(profile('process').credentials().access_key_id, 'AKIDLOGIN', 'login session before credential_process')

done_testing()
