import Pyjo.AWS.Config
import Pyjo.AWS.Credentials
import Pyjo.AWS.Credentials.Chain
import Pyjo.AWS.Credentials.Container
import Pyjo.AWS.Credentials.InstanceMetadata
import Pyjo.AWS.Credentials.Profile
import Pyjo.File
import Pyjo.IOLoop.Server
import Pyjo.UserAgent

from Pyjo.Test import *

import contextlib
import os
import re
import socket
import subprocess
import sys
import time


# The credentials of the container of ECS and EKS and of the instance metadata of EC2, against a server of their own
# in a process of its own, as the providers have user agents of their own, which a server of a user agent of the test
# would not answer

tmp = Pyjo.File.tempdir()

SERVER = tmp.child('server.py').spew("""\
import re
from Pyjoyment.Lite import *

app.log.level = 'fatal'
state = {}
calls = []
DEFAULT = {'token': 'ok', 'role': 'web-server', 'credentials': 'ok', 'auth': None, 'fail': 0}
state.update(DEFAULT)


def record(c):
    headers = c.req.headers
    calls.append({
        'method': c.req.method,
        'path': c.req.url.path.to_str(),
        'token': headers.header('X-aws-ec2-metadata-token'),
        'ttl': headers.header('X-aws-ec2-metadata-token-ttl-seconds'),
        'authorization': headers.authorization,
    })


@post('/state')
def state_action(c):
    state.clear()
    state.update(DEFAULT)
    state.update(c.req.json())
    calls.clear()
    c.render(json=state)


@get('/calls')
def calls_action(c):
    c.render(json=calls)


@put('/latest/api/token')
def token_action(c):
    record(c)
    mode = state['token']
    if mode == 'ok':
        return c.render(text='imds-token')
    c.rendered(int(mode))


@get('/latest/meta-data/iam/security-credentials/')
def roles_action(c):
    record(c)
    if state['token'] == 'ok' and c.req.headers.header('X-aws-ec2-metadata-token') != 'imds-token':
        return c.rendered(401)
    if not state['role']:
        return c.rendered(404)
    c.render(text=state['role'] + '\\n')


@get('/latest/meta-data/iam/security-credentials/<role>')
def credentials_action(c):
    record(c)
    if state['credentials'] == 'broken':
        return c.render(json={'Code': 'Failure'})
    c.render(json={
        'Code': 'Success',
        'Type': 'AWS-HMAC',
        'AccessKeyId': 'AKIDIMDS',
        'SecretAccessKey': 'secret',
        'Token': 'imds-session',
        'Expiration': '2099-01-01T00:00:00Z',
    })


@get('/container/credentials')
def container_action(c):
    record(c)
    if state['fail'] > 0:
        state['fail'] -= 1
        return c.rendered(500)
    if state['auth'] is not None and c.req.headers.authorization != state['auth']:
        return c.render(json={'message': 'denied'}, status=403)
    c.render(json={
        'AccessKeyId': 'AKIDCONTAINER',
        'SecretAccessKey': 'secret',
        'Token': 'container-session',
        'Expiration': '2099-01-01T00:00:00Z',
        'AccountId': '123456789012',
    })


@post('/sts/')
def sts_action(c):
    record(c)
    m = re.search(r'Credential=(\\w+)/', c.req.headers.authorization or '')
    signer = m[1] if m else 'none'
    c.res.headers.content_type = 'text/xml'
    c.render(data=(
        '<AssumeRoleResponse><AssumeRoleResult><Credentials>'
        f'<AccessKeyId>AKIDROLEOF{signer}</AccessKeyId><SecretAccessKey>secret</SecretAccessKey>'
        '<SessionToken>role</SessionToken><Expiration>2099-01-01T00:00:00Z</Expiration>'
        '</Credentials></AssumeRoleResult></AssumeRoleResponse>'
    ).encode())


app.start()
""")

tmp.child('config').spew('')
tmp.child('credentials').spew('')

port = Pyjo.IOLoop.Server.object.generate_port()
base = f'http://127.0.0.1:{port}'
closed = f'http://127.0.0.1:{Pyjo.IOLoop.Server.object.generate_port()}'
server = subprocess.Popen(
    [sys.executable, str(SERVER), 'daemon', '-l', base], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
deadline = time.monotonic() + 30
while True:
    try:
        socket.create_connection(('127.0.0.1', port), timeout=1).close()
        break
    except OSError:
        if time.monotonic() > deadline or server.poll() is not None:
            server.kill()
            raise
        time.sleep(0.1)

control = Pyjo.UserAgent.new(max_connections=0)


def state(**values):
    control.post(f'{base}/state', json=values)


def calls():
    return control.get(f'{base}/calls').res.json()


@contextlib.contextmanager
def environ(**values):
    saved = dict(os.environ)
    try:
        for name in list(os.environ):
            if name.startswith('AWS_'):
                del os.environ[name]
        os.environ.update(
            AWS_CONFIG_FILE=str(tmp.child('config')), AWS_SHARED_CREDENTIALS_FILE=str(tmp.child('credentials'))
        )
        os.environ.update(values)
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


Container = Pyjo.AWS.Credentials.Container.new
InstanceMetadata = Pyjo.AWS.Credentials.InstanceMetadata.new
CONTAINER = f'{base}/container/credentials'

try:
    with subtest('Container'):
        with environ():
            is_ok(Container().credentials(), None, 'not configured')
            is_ok(Container(relative_uri='/v2/credentials/1').url(), 'http://169.254.170.2/v2/credentials/1', 'ECS')
            for url in (
                'http://169.254.170.23/v1/credentials',
                'http://[fd00:ec2::23]/v1/credentials',
                'http://localhost:8080/credentials',
                'http://127.0.0.2/credentials',
                'https://credentials.example.com/credentials',
            ):
                is_ok(Container(full_uri=url).url(), url, f'allowed {url}')
            throws_ok(
                lambda: Container(full_uri='http://credentials.example.com/credentials').credentials(),
                re.compile(r'^The AWS_CONTAINER_CREDENTIALS_FULL_URI \S+ is not HTTPS, an agent of ECS or EKS'),
                'HTTP of another host',
            )
            is_ok(Container().ua.connect_timeout, 2, 'user agent of its own with a short timeout')
            is_ok(Container().ua.max_connections, 0, 'no kept connections')

        with environ(AWS_CONTAINER_CREDENTIALS_FULL_URI=CONTAINER):
            state()
            credentials = Container().credentials()
            is_ok(credentials.access_key_id, 'AKIDCONTAINER', 'credentials of the full URI')
            is_ok(credentials.session_token, 'container-session', 'session token')
            is_ok(credentials.expiration.to_rfc3339(), '2099-01-01T00:00:00Z', 'expiration')
            is_ok(credentials.account_id, '123456789012', 'account')
            is_ok(credentials.provider, 'container', 'provider')
            is_ok(calls()[-1]['authorization'], None, 'no authorization')

            result = wait(Container().credentials_p())
            is_ok(result['value'].access_key_id, 'AKIDCONTAINER', 'non-blocking')

            state(fail=2)
            is_ok(Container().credentials().access_key_id, 'AKIDCONTAINER', 'errors of the agent tried again')
            is_ok(len(calls()), 3, 'three attempts')
            state(fail=3)
            throws_ok(
                lambda: Container().credentials(),
                re.compile(r'^Cannot get the credentials of the container of AWS of \S+: 500'),
                'error of the last attempt',
            )

        with environ(AWS_CONTAINER_CREDENTIALS_FULL_URI=CONTAINER, AWS_CONTAINER_AUTHORIZATION_TOKEN='secret'):
            state(auth='secret')
            is_ok(Container().credentials().access_key_id, 'AKIDCONTAINER', 'token of the environment')
            is_ok(calls()[-1]['authorization'], 'secret', 'header Authorization')

            tmp.child('token').spew('rotated\n')
            os.environ['AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE'] = str(tmp.child('token'))
            state(auth='rotated')
            is_ok(Container().credentials().access_key_id, 'AKIDCONTAINER', 'token of the file first')
            is_ok(calls()[-1]['authorization'], 'rotated', 'token of the file without its new line')

            state(auth='other')
            throws_ok(
                lambda: Container().credentials(),
                re.compile(r'^Cannot get the credentials of the container of AWS of \S+: 403 \{"message":"denied"\}'),
                'error of the agent',
            )
            is_ok(len(calls()), 1, 'no other attempt of an error of the client')

            tmp.child('token').spew('a\nb')
            throws_ok(
                lambda: Container().credentials(),
                re.compile(r'^Invalid authorization token of the container of AWS: a line break'),
                'token with a line break',
            )
            os.environ['AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE'] = str(tmp.child('missing'))
            throws_ok(
                lambda: Container().credentials(),
                re.compile(r'^Cannot read the authorization token of the container of AWS of \S+missing'),
                'missing token file',
            )

        with environ(AWS_CONTAINER_CREDENTIALS_FULL_URI=f'{closed}/credentials'):
            throws_ok(
                lambda: Container(timeout=1).credentials(),
                re.compile(r'^Cannot get the credentials of the container of AWS of \S+: GET \S+: '),
                'agent that does not answer',
            )

    with subtest('Instance metadata'):
        with environ(AWS_EC2_METADATA_SERVICE_ENDPOINT=base):
            state()
            credentials = InstanceMetadata().credentials()
            is_ok(credentials.access_key_id, 'AKIDIMDS', 'credentials of the role')
            is_ok(credentials.session_token, 'imds-session', 'session token')
            is_ok(credentials.expiration.to_rfc3339(), '2099-01-01T00:00:00Z', 'expiration')
            is_ok(credentials.provider, 'imds', 'provider')
            requests = calls()
            is_ok(
                [(call['method'], call['path']) for call in requests],
                [
                    ('PUT', '/latest/api/token'),
                    ('GET', '/latest/meta-data/iam/security-credentials/'),
                    ('GET', '/latest/meta-data/iam/security-credentials/web-server'),
                ],
                'token, role and credentials',
            )
            is_ok(requests[0]['ttl'], '21600', 'TTL of the token')
            is_ok([call['token'] for call in requests[1:]], ['imds-token', 'imds-token'], 'token of IMDSv2')

            result = wait(InstanceMetadata().credentials_p())
            is_ok(result['value'].access_key_id, 'AKIDIMDS', 'non-blocking')

            state(token='403')
            is_ok(InstanceMetadata().credentials().access_key_id, 'AKIDIMDS', 'IMDSv1 without tokens')
            is_ok([call['token'] for call in calls()[1:]], [None, None], 'no token')

            state(token='400')
            is_ok(InstanceMetadata().credentials(), None, 'error of the token')
            state(role='')
            is_ok(InstanceMetadata().credentials(), None, 'no role')
            state(credentials='broken')
            throws_ok(
                lambda: InstanceMetadata().credentials(),
                re.compile(r'^No credentials of the instance metadata of AWS of \S+web-server: Failure'),
                'credentials of the role that the service does not give',
            )

            state(token='500')
            is_ok(InstanceMetadata(attempts=2).credentials(), None, 'error of the service')
            is_ok(len(calls()), 2, 'attempts')

        with environ(AWS_EC2_METADATA_SERVICE_ENDPOINT=base, AWS_EC2_METADATA_V1_DISABLED='true'):
            state(token='403')
            is_ok(InstanceMetadata().credentials(), None, 'IMDSv1 turned off')
            is_ok(len(calls()), 1, 'no request without a token')

        with environ(AWS_EC2_METADATA_SERVICE_ENDPOINT=base, AWS_EC2_METADATA_DISABLED='true'):
            state()
            is_ok(InstanceMetadata().credentials(), None, 'turned off')
            is_ok(calls(), [], 'no request')

        with environ(AWS_EC2_METADATA_SERVICE_ENDPOINT=closed):
            is_ok(InstanceMetadata().credentials(), None, 'no service')
            is_ok(wait(InstanceMetadata().credentials_p())['value'], None, 'no service, non-blocking')

        with environ():
            provider = InstanceMetadata()
            is_ok(provider.endpoint, 'http://169.254.169.254', 'endpoint of IPv4')
            is_ok(provider.timeout, 1.0, 'timeout of 1 second')
            is_ok(provider.ua.connect_timeout, 1.0, 'user agent of its own with the timeout')
            is_ok(provider.ua.max_connections, 0, 'no kept connections')
            is_ok(provider.attempts, 1, 'one attempt')

        with environ(
            AWS_EC2_METADATA_SERVICE_ENDPOINT_MODE='IPv6',
            AWS_METADATA_SERVICE_TIMEOUT='3',
            AWS_METADATA_SERVICE_NUM_ATTEMPTS='2',
        ):
            provider = InstanceMetadata()
            is_ok(provider.endpoint, 'http://[fd00:ec2::254]', 'endpoint of IPv6')
            is_ok(provider.timeout, 3.0, 'timeout of the environment')
            is_ok(provider.attempts, 2, 'attempts of the environment')

        tmp.child('imds').spew(f"""\
[default]
ec2_metadata_service_endpoint = {base}/
metadata_service_timeout = 2
metadata_service_num_attempts = 3
ec2_metadata_v1_disabled = true
""")
        with environ(AWS_CONFIG_FILE=str(tmp.child('imds'))):
            provider = InstanceMetadata()
            is_ok(provider.endpoint, base, 'endpoint of the profile')
            is_ok(
                (provider.timeout, provider.attempts, provider.v1_disabled), (2.0, 3, True), 'settings of the profile'
            )
            state()
            is_ok(provider.credentials().access_key_id, 'AKIDIMDS', 'credentials of the endpoint of the profile')

    with subtest('Chain and profile'):
        with environ(AWS_EC2_METADATA_SERVICE_ENDPOINT=base):
            state()
            is_ok(Pyjo.AWS.Credentials.Chain.new().credentials().provider, 'imds', 'instance metadata last')
            result = wait(Pyjo.AWS.Credentials.Chain.new().credentials_p())
            is_ok(result['value'].provider, 'imds', 'instance metadata last, non-blocking')
            os.environ['AWS_CONTAINER_CREDENTIALS_FULL_URI'] = CONTAINER
            is_ok(Pyjo.AWS.Credentials.Chain.new().credentials().provider, 'container', 'container before')

        tmp.child('roles').spew("""\
[profile container]
role_arn = arn:aws:iam::123456789012:role/container
credential_source = EcsContainer

[profile instance]
role_arn = arn:aws:iam::123456789012:role/instance
credential_source = Ec2InstanceMetadata
""")
        with environ(
            AWS_CONFIG_FILE=str(tmp.child('roles')),
            AWS_ENDPOINT_URL_STS=f'{base}/sts',
            AWS_CONTAINER_CREDENTIALS_FULL_URI=CONTAINER,
            AWS_EC2_METADATA_SERVICE_ENDPOINT=base,
        ):
            state()
            # The user agent of STS keeps no connection to the server, which the exit of the interpreter would not
            # close, as ResourceWarning reports
            config = Pyjo.AWS.Config.new(profile='container')
            credentials = Pyjo.AWS.Credentials.Profile.new(config=config, ua=control).credentials()
            is_ok(credentials.access_key_id, 'AKIDROLEOFAKIDCONTAINER', 'role of credential_source EcsContainer')
            config = Pyjo.AWS.Config.new(profile='instance')
            credentials = Pyjo.AWS.Credentials.Profile.new(config=config, ua=control).credentials()
            is_ok(credentials.access_key_id, 'AKIDROLEOFAKIDIMDS', 'role of credential_source Ec2InstanceMetadata')
finally:
    server.terminate()
    server.wait()

done_testing()
