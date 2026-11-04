import Pyjo.AWS.Config
import Pyjo.AWS.Credentials
import Pyjo.AWS.Credentials.Chain
import Pyjo.AWS.Credentials.Environment
import Pyjo.AWS.Credentials.Process
import Pyjo.AWS.Credentials.Profile
import Pyjo.AWS.Credentials.Provider
import Pyjo.Exception
import Pyjo.File
import Pyjo.JSON
import Pyjo.Promise
import Pyjo.UserAgent

from Pyjo.Test import *
from Pyjoyment.Lite import *

import contextlib
import datetime
import os
import re
import shlex
import sys


# Credentials of AWS and their providers

tmp = Pyjo.File.tempdir()

NOW = datetime.datetime.now(datetime.UTC)

# A program of credential_process, which prints the credentials of its arguments, and counts its runs in a file
SCRIPT = tmp.child('credentials.py').spew("""\
import json, sys
count, expiration = sys.argv[1], sys.argv[2]
with open(count, 'a') as f:
    f.write('.')
if expiration == 'fail':
    print('No credentials here', file=sys.stderr)
    sys.exit(3)
if expiration == 'text':
    print('Not JSON')
    sys.exit(0)
data = {'Version': 1, 'AccessKeyId': 'AKIDPROCESS', 'SecretAccessKey': 'secret', 'SessionToken': 'token'}
if expiration == 'version':
    data['Version'] = 2
elif expiration != 'none':
    data['Expiration'] = expiration
    data['AccountId'] = '123456789012'
print(json.dumps(data))
""")


def command(expiration, count=None):
    count = count or tmp.child('count')
    return shlex.join([sys.executable, str(SCRIPT), str(count), expiration])


def runs(count=None):
    count = count or tmp.child('count')
    return len(count.slurp('UTF-8')) if os.path.exists(count) else 0


def iso(delta):
    return (NOW + delta).strftime('%Y-%m-%dT%H:%M:%SZ')


@contextlib.contextmanager
def environ(**values):
    saved = dict(os.environ)
    try:
        for name in list(os.environ):
            if name.startswith('AWS_'):
                del os.environ[name]
        os.environ.update(
            AWS_CONFIG_FILE=str(tmp.child('config')),
            AWS_SHARED_CREDENTIALS_FILE=str(tmp.child('credentials')),
            AWS_EC2_METADATA_DISABLED='true',
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


tmp.child('config').spew(f"""\
[profile static]
aws_access_key_id = AKIDCONFIG
aws_secret_access_key = secret
aws_session_token = token
aws_account_id = 123456789012

[profile partial]
aws_access_key_id = AKIDPARTIAL

[profile process]
credential_process = {command(iso(datetime.timedelta(hours=1)))}

[profile nothing]
region = eu-central-1
""")

tmp.child('credentials').spew("""\
[default]
aws_access_key_id = AKIDDEFAULT
aws_secret_access_key = secret
""")


with subtest('Credentials'):
    credentials = Pyjo.AWS.Credentials.new(access_key_id='AKIDEXAMPLE', secret_access_key='secret')
    is_ok(credentials.session_token, None, 'no session token')
    is_ok(credentials.expires_in(), None, 'no expiration')
    is_ok(repr(credentials), "<Credentials access_key_id='AKIDEXAMPLE' provider=None>", 'no secret in repr')
    credentials.expiration = NOW + datetime.timedelta(minutes=10)
    is_ok(credentials.expires_in(NOW), 600.0, 'expires in seconds')
    is_ok(
        Pyjo.AWS.Credentials.parse_time('2026-11-03T12:00:00Z'),
        datetime.datetime(2026, 11, 3, 12, tzinfo=datetime.UTC),
        'time in UTC',
    )
    is_ok(
        Pyjo.AWS.Credentials.parse_time('2026-11-03T13:00:00+01:00').astimezone(datetime.UTC),
        datetime.datetime(2026, 11, 3, 12, tzinfo=datetime.UTC),
        'time with an offset',
    )
    is_ok(Pyjo.AWS.Credentials.parse_time('2026-11-03T12:00:00').tzinfo, datetime.UTC, 'time without a zone in UTC')
    throws_ok(
        lambda: Pyjo.AWS.Credentials.parse_time('tomorrow'),
        re.compile(r"^Invalid time of the expiration of credentials of AWS: 'tomorrow'"),
        'invalid time',
    )

with subtest('Environment'):
    with environ():
        is_ok(Pyjo.AWS.Credentials.Environment.new().credentials(), None, 'no credentials')

    with environ(AWS_ACCESS_KEY_ID='', AWS_SECRET_ACCESS_KEY=''):
        is_ok(Pyjo.AWS.Credentials.Environment.new().credentials(), None, 'empty variables are none')

    with environ(
        AWS_ACCESS_KEY_ID='AKIDENV',
        AWS_SECRET_ACCESS_KEY='secret',
        AWS_SESSION_TOKEN='token',
        AWS_CREDENTIAL_EXPIRATION='2026-11-03T12:00:00Z',
        AWS_ACCOUNT_ID='123456789012',
    ):
        provider = Pyjo.AWS.Credentials.Environment.new()
        credentials = provider.credentials()
        is_ok(credentials.access_key_id, 'AKIDENV', 'access key ID')
        is_ok(credentials.secret_access_key, 'secret', 'secret access key')
        is_ok(credentials.session_token, 'token', 'session token')
        is_ok(credentials.expiration, datetime.datetime(2026, 11, 3, 12, tzinfo=datetime.UTC), 'expiration')
        is_ok(credentials.account_id, '123456789012', 'account ID')
        is_ok(credentials.provider, 'environment', 'provider')
        os.environ['AWS_ACCESS_KEY_ID'] = 'AKIDCHANGED'
        is_ok(provider.credentials().access_key_id, 'AKIDCHANGED', 'environment read again')

    with environ(AWS_ACCESS_KEY_ID='AKIDENV'):
        throws_ok(
            lambda: Pyjo.AWS.Credentials.Environment.new().credentials(),
            re.compile(r'^Partial credentials of AWS in the environment: no AWS_SECRET_ACCESS_KEY'),
            'partial credentials',
        )

    with environ(AWS_SECRET_ACCESS_KEY='secret'):
        result = wait(Pyjo.AWS.Credentials.Environment.new().credentials_p())
        like_ok(str(result['error']), re.compile(r'no AWS_ACCESS_KEY_ID'), 'partial credentials rejected')

with subtest('Process'):
    expiration = iso(datetime.timedelta(hours=1))
    credentials = Pyjo.AWS.Credentials.Process.new(command=command(expiration)).credentials()
    is_ok(credentials.access_key_id, 'AKIDPROCESS', 'access key ID')
    is_ok(credentials.session_token, 'token', 'session token')
    is_ok(credentials.expiration, Pyjo.AWS.Credentials.parse_time(expiration), 'expiration')
    is_ok(credentials.account_id, '123456789012', 'account ID')
    is_ok(credentials.provider, 'process', 'provider')
    is_ok(Pyjo.AWS.Credentials.Process.new(command=command('none')).credentials().expiration, None, 'no expiration')

    throws_ok(
        lambda: Pyjo.AWS.Credentials.Process.new(command=command('fail')).credentials(),
        re.compile(r'^credential_process \S+ failed with 3: No credentials here'),
        'program that fails',
    )
    throws_ok(
        lambda: Pyjo.AWS.Credentials.Process.new(command=command('text')).credentials(),
        re.compile(r'^credential_process \S+ printed no JSON'),
        'program that prints no JSON',
    )
    throws_ok(
        lambda: Pyjo.AWS.Credentials.Process.new(command=command('version')).credentials(),
        re.compile(r'^credential_process \S+ printed an unsupported Version: 2'),
        'unsupported version',
    )
    throws_ok(
        lambda: Pyjo.AWS.Credentials.Process.new(command=str(tmp.child('missing'))).credentials(),
        re.compile(r'^Cannot run \S+missing'),
        'program that does not exist',
    )
    throws_ok(
        lambda: Pyjo.AWS.Credentials.Process.new(command='  ').credentials(),
        re.compile(r'^Empty credential_process of AWS'),
        'empty command',
    )

    if sys.platform == 'win32':
        skip('the reactor watches no pipes on Windows', 3)
    else:
        result = wait(Pyjo.AWS.Credentials.Process.new(command=command(expiration)).credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDPROCESS', 'non-blocking')
        result = wait(Pyjo.AWS.Credentials.Process.new(command=command('fail')).credentials_p())
        like_ok(str(result['error']), re.compile(r'^credential_process \S+ failed with 3'), 'non-blocking failure')
        result = wait(Pyjo.AWS.Credentials.Process.new(command=str(tmp.child('missing'))).credentials_p())
        like_ok(str(result['error']), re.compile(r'^Cannot run \S+missing'), 'non-blocking missing program')

with subtest('Profile'):
    with environ():
        credentials = Pyjo.AWS.Credentials.Profile.new().credentials()
        is_ok(credentials.access_key_id, 'AKIDDEFAULT', 'default profile of the credentials file')
        is_ok(credentials.provider, 'profile', 'provider')

        config = Pyjo.AWS.Config.new(profile='static')
        credentials = Pyjo.AWS.Credentials.Profile.new(config=config).credentials()
        is_ok(credentials.access_key_id, 'AKIDCONFIG', 'keys of the config file')
        is_ok(credentials.session_token, 'token', 'session token')
        is_ok(credentials.account_id, '123456789012', 'account ID')

        config = Pyjo.AWS.Config.new(profile='process')
        credentials = Pyjo.AWS.Credentials.Profile.new(config=config).credentials()
        is_ok(credentials.access_key_id, 'AKIDPROCESS', 'credential_process')
        is_ok(credentials.provider, 'process', 'provider of credential_process')

        config = Pyjo.AWS.Config.new(profile='nothing')
        is_ok(Pyjo.AWS.Credentials.Profile.new(config=config).credentials(), None, 'profile without credentials')

        config = Pyjo.AWS.Config.new(profile='partial')
        throws_ok(
            lambda: Pyjo.AWS.Credentials.Profile.new(config=config).credentials(),
            re.compile(r'^Partial credentials of the profile partial of AWS: no aws_secret_access_key'),
            'partial credentials',
        )

        config = Pyjo.AWS.Config.new(profile='missing')
        throws_ok(
            lambda: Pyjo.AWS.Credentials.Profile.new(config=config).credentials(),
            re.compile(r'^The profile missing of AWS is not in \S+config'),
            'missing profile',
        )

        config = Pyjo.AWS.Config.new(config_file=str(tmp.child('none')), credentials_file=str(tmp.child('none')))
        is_ok(Pyjo.AWS.Credentials.Profile.new(config=config).credentials(), None, 'no default profile')

with subtest('Chain'):
    with environ(AWS_ACCESS_KEY_ID='AKIDENV', AWS_SECRET_ACCESS_KEY='secret'):
        is_ok(Pyjo.AWS.Credentials.Chain.new().credentials().provider, 'environment', 'environment first')
        result = wait(Pyjo.AWS.Credentials.Chain.new().credentials_p())
        is_ok(result['value'].provider, 'environment', 'environment first, non-blocking')

    with environ():
        is_ok(Pyjo.AWS.Credentials.Chain.new().credentials().access_key_id, 'AKIDDEFAULT', 'default profile')

    with environ(AWS_PROFILE='static'):
        is_ok(Pyjo.AWS.Credentials.Chain.new().credentials().access_key_id, 'AKIDCONFIG', 'profile of AWS_PROFILE')
        config = Pyjo.AWS.Config.new(profile='process')
        is_ok(Pyjo.AWS.Credentials.Chain.new(config=config).credentials().provider, 'process', 'profile of config')

    # A profile of the argument, as --profile of the AWS CLI, comes over the environment, which AWS_PROFILE does not
    with environ(AWS_ACCESS_KEY_ID='AKIDENV', AWS_SECRET_ACCESS_KEY='secret', AWS_PROFILE='static'):
        ok(not Pyjo.AWS.Config.new().explicit_profile, 'profile of AWS_PROFILE not explicit')
        is_ok(Pyjo.AWS.Credentials.Chain.new().credentials().provider, 'environment', 'environment over AWS_PROFILE')
        config = Pyjo.AWS.Config.new(profile='static')
        ok(config.explicit_profile, 'profile of the argument explicit')
        is_ok(
            Pyjo.AWS.Credentials.Chain.new(config=config).credentials().access_key_id, 'AKIDCONFIG', 'explicit profile'
        )
        config = Pyjo.AWS.Config.new(profile='nothing')
        is_ok(
            Pyjo.AWS.Credentials.Chain.new(config=config).credentials(), None, 'no environment for an explicit profile'
        )

    with environ(AWS_ROLE_ARN='arn:aws:iam::123456789012:role/ci'):
        throws_ok(
            lambda: Pyjo.AWS.Credentials.Chain.new().credentials(),
            re.compile(r'^Partial web identity of AWS in the environment'),
            'web identity of the environment',
        )
        config = Pyjo.AWS.Config.new(profile='static')
        is_ok(
            Pyjo.AWS.Credentials.Chain.new(config=config).credentials().access_key_id,
            'AKIDCONFIG',
            'no web identity of the environment for an explicit profile',
        )

    with environ(AWS_PROFILE='nothing'):
        is_ok(Pyjo.AWS.Credentials.Chain.new().credentials(), None, 'no credentials')

    with environ(AWS_PROFILE='partial', AWS_SECRET_ACCESS_KEY=''):
        throws_ok(
            lambda: Pyjo.AWS.Credentials.Chain.new().credentials(),
            re.compile(r'^Partial credentials of the profile partial'),
            'error of a configured provider ends the chain',
        )

    with environ():
        chain = Pyjo.AWS.Credentials.Chain.new(providers=[Pyjo.AWS.Credentials.Process.new(command=command('none'))])
        is_ok(chain.credentials().provider, 'process', 'providers of the argument')

with subtest('Cache and refresh'):
    count = tmp.child('cached')
    provider = Pyjo.AWS.Credentials.Process.new(command=command(iso(datetime.timedelta(hours=1)), count))
    ok(not provider.is_fresh(), 'nothing cached')
    provider.credentials()
    ok(provider.is_fresh(), 'fresh credentials')
    provider.credentials()
    is_ok(runs(count), 1, 'cached credentials')

    count = tmp.child('expiring')
    provider = Pyjo.AWS.Credentials.Process.new(command=command(iso(datetime.timedelta(minutes=4)), count))
    provider.credentials()
    ok(not provider.is_fresh(), 'credentials about to expire')
    provider.credentials()
    is_ok(runs(count), 2, 'credentials got again before their expiration')
    provider.refresh = 60
    provider.credentials()
    is_ok(runs(count), 2, 'shorter refresh')

    count = tmp.child('static')
    provider = Pyjo.AWS.Credentials.Process.new(command=command('none', count))
    provider.credentials()
    provider.credentials()
    is_ok(runs(count), 1, 'credentials without expiration cached')
    provider.cached = None
    provider.credentials()
    is_ok(runs(count), 2, 'cache cleared')

    if sys.platform == 'win32':
        skip('the reactor watches no pipes on Windows', 3)
    else:
        count = tmp.child('pending')
        provider = Pyjo.AWS.Credentials.Process.new(command=command('none', count))
        first, second = provider.credentials_p(), provider.credentials_p()
        ok(first is second, 'same promise while pending')
        wait(Pyjo.Promise.all(first, second))
        is_ok(runs(count), 1, 'credentials got once')
        ok(provider.credentials_p() is not first, 'cached credentials of a new promise')

with subtest('Requests'):
    app.log.level = 'fatal'

    @get('/credentials')
    def credentials_action(c):
        if c.req.headers.header('X-Token') != 'secret':
            return c.render(json={'message': 'Forbidden'}, status=403)
        c.render(json={'AccessKeyId': 'AKIDHTTP', 'SecretAccessKey': 'secret'})

    class HTTP(Pyjo.AWS.Credentials.Provider.object):
        def __init__(self, url, **kwargs):
            super().__init__(**kwargs)
            self.url = url

        async def fetch(self):
            try:
                tx = await self.start(self.ua.build_tx('GET', self.url, {'X-Token': 'secret'}))
            except Exception as e:
                raise Pyjo.Exception.new(f'Cannot get credentials: {e}') from e
            if tx.res.code != 200:
                raise Pyjo.Exception.new(f'Cannot get credentials: {tx.res.code}')
            data = tx.res.json()
            return Pyjo.AWS.Credentials.new(
                access_key_id=data['AccessKeyId'], secret_access_key=data['SecretAccessKey'], provider='http'
            )

    ua = Pyjo.UserAgent.new()
    ua.server.app = app
    is_ok(HTTP('/credentials', ua=ua).credentials().access_key_id, 'AKIDHTTP', 'request, blocking')
    result = wait(HTTP('/credentials', ua=ua).credentials_p())
    is_ok(result['value'].access_key_id, 'AKIDHTTP', 'request, non-blocking')

    closed = Pyjo.UserAgent.new(connect_timeout=2)
    refused = 'http://127.0.0.1:1/credentials'
    throws_ok(
        lambda: HTTP(refused, ua=closed).credentials(),
        re.compile(r'^Cannot get credentials: GET http://127\.0\.0\.1:1/credentials: '),
        'connection error thrown in, blocking',
    )
    result = wait(HTTP(refused, ua=closed).credentials_p())
    like_ok(
        str(result['error']),
        re.compile(r'^Cannot get credentials: GET http://127\.0\.0\.1:1/credentials: '),
        'connection error thrown in, non-blocking',
    )

with subtest('Generators and coroutines'):

    class Generated(Pyjo.AWS.Credentials.Provider.object):
        def __init__(self, url, **kwargs):
            super().__init__(**kwargs)
            self.url = url

        def fetch(self):
            tx = yield self.start(self.ua.build_tx('GET', self.url, {'X-Token': 'secret'}))
            if tx.res.code != 200:
                raise Pyjo.Exception.new(f'Cannot get credentials: {tx.res.code}')
            code, out, _ = yield self.run([sys.executable, '-c', 'print("process")'])
            return Pyjo.AWS.Credentials.new(
                access_key_id=tx.res.json('/AccessKeyId'),
                secret_access_key=out.decode().strip(),
                provider=f'generator {code}',
            )

    class Awaited(Pyjo.AWS.Credentials.Provider.object):
        def __init__(self, source, **kwargs):
            super().__init__(**kwargs)
            self.source = source

        async def fetch(self):
            source = await self.source.steps()
            return Pyjo.AWS.Credentials.new(
                access_key_id=f'{source.access_key_id}AWAITED',
                secret_access_key=source.secret_access_key,
                provider=f'awaited {source.provider}',
            )

    class Yielded(Awaited):
        def fetch(self):
            source = yield from self.source.steps()
            return Pyjo.AWS.Credentials.new(
                access_key_id=f'{source.access_key_id}YIELDED',
                secret_access_key=source.secret_access_key,
                provider=f'yielded {source.provider}',
            )

    credentials = Generated('/credentials', ua=ua).credentials()
    is_ok(credentials.access_key_id, 'AKIDHTTP', 'generator, request')
    is_ok(credentials.secret_access_key, 'process', 'generator, program')
    is_ok(credentials.provider, 'generator 0', 'generator, exit code')
    throws_ok(
        lambda: Generated('/forbidden', ua=ua).credentials(),
        re.compile(r'^Cannot get credentials: 404'),
        'generator, error',
    )

    source = Generated('/credentials', ua=ua)
    provider = Yielded(Awaited(source, ua=ua), ua=ua)
    is_ok(provider.credentials().access_key_id, 'AKIDHTTPAWAITEDYIELDED', 'generator over coroutine over generator')
    is_ok(provider.cached.provider, 'yielded awaited generator 0', 'providers in their order')
    ok(source.is_fresh(), 'source cached')

    if sys.platform == 'win32':
        skip('the reactor watches no pipes on Windows', 2)
    else:
        result = wait(Generated('/credentials', ua=ua).credentials_p())
        is_ok(result['value'].secret_access_key, 'process', 'generator, non-blocking')
        result = wait(Awaited(Yielded(Generated('/credentials', ua=ua), ua=ua), ua=ua).credentials_p())
        is_ok(
            result['value'].access_key_id,
            'AKIDHTTPYIELDEDAWAITED',
            'coroutine over generator over generator, non-blocking',
        )

    class Promised(Pyjo.AWS.Credentials.Provider.object):
        async def fetch(self):
            try:
                await Pyjo.Promise.new()
            except Exception:
                return None

    throws_ok(
        lambda: Promised().credentials(),
        re.compile(r'^Steps of AWS await \w+: only a Request, a Command and Steps'),
        'promise awaited, not thrown in',
    )
    result = wait(Promised().credentials_p())
    ok(isinstance(result['error'], TypeError), 'promise awaited, non-blocking')
    like_ok(str(result['error']), re.compile(r'^Steps of AWS await'), 'error of the promise')

done_testing()
