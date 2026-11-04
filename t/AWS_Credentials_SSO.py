import Pyjo.AWS.Config
import Pyjo.AWS.Credentials
import Pyjo.AWS.Credentials.Chain
import Pyjo.AWS.Credentials.Profile
import Pyjo.AWS.Credentials.SSO
import Pyjo.AWS.Error
import Pyjo.File
import Pyjo.JSON
import Pyjo.UserAgent

from Pyjo.Test import *
from Pyjoyment.Lite import *

import contextlib
import datetime
import hashlib
import os
import re
import stat
import sys


# The credentials of IAM Identity Center, of the token of the cache of the AWS CLI, refreshed with SSO OIDC, against
# an application that serves SSO and SSO OIDC

tmp = Pyjo.File.tempdir()
cache = tmp.child('.aws', 'sso', 'cache').make_path()

NOW = datetime.datetime.now(datetime.UTC)
START_URL = 'https://company.awsapps.com/start'
LEGACY_URL = 'https://legacy.awsapps.com/start'


def iso(delta):
    return (NOW + delta).strftime('%Y-%m-%dT%H:%M:%SZ')


tmp.child('config').spew(f"""\
[profile sso]
sso_session = company
sso_account_id = 123456789012
sso_role_name = ReadOnly
region = us-west-2

[profile legacy]
sso_start_url = {LEGACY_URL}
sso_region = eu-central-1
sso_account_id = 210987654321
sso_role_name = Admin

[profile partial]
sso_session = company

[profile lost]
sso_session = nowhere
sso_account_id = 123456789012
sso_role_name = ReadOnly

[profile mismatch]
sso_session = company
sso_region = us-east-1
sso_account_id = 123456789012
sso_role_name = ReadOnly

[profile static]
aws_access_key_id = AKIDSTATIC
aws_secret_access_key = secret

[sso-session company]
sso_start_url = {START_URL}
sso_region = eu-central-1
sso_registration_scopes = sso:account:access
""")
tmp.child('credentials').spew('')


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
            AWS_ENDPOINT_URL_SSO='/sso',
            AWS_ENDPOINT_URL_SSO_OIDC='/oidc',
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


def token_file(key):
    return cache.child(hashlib.sha1(key.encode()).hexdigest() + '.json')


def write_token(key, token, expires, refresh=None, registered=datetime.timedelta(days=30)):
    data = {'startUrl': START_URL, 'region': 'eu-central-1', 'accessToken': token, 'expiresAt': iso(expires)}
    if refresh is not None:
        data.update(
            clientId='client',
            clientSecret='client-secret',
            registrationExpiresAt=iso(registered),
            refreshToken=refresh,
        )
    token_file(key).spew(Pyjo.JSON.encode_json(data))


def read_token(key):
    return Pyjo.JSON.decode_json(token_file(key).slurp())


app.log.level = 'fatal'
calls = {'sso': 0, 'oidc': 0}
seen = {}
TOKENS = {'valid', 'expiring', 'refreshed', 'legacy'}


@get('/sso/federation/credentials')
def credentials_action(c):
    calls['sso'] += 1
    seen.update(
        token=c.req.headers.header('X-Amz-Sso_bearer_token'),
        role_name=c.param('role_name'),
        account_id=c.param('account_id'),
        authorization=c.req.headers.authorization,
    )
    if seen['token'] not in TOKENS:
        c.res.headers.header('X-Amzn-ErrorType', 'UnauthorizedException')
        return c.render(json={'message': 'Session token not found or invalid'}, status=401)
    c.render(
        json={
            'roleCredentials': {
                'accessKeyId': f'AKIDSSO{seen["token"].upper()}',
                'secretAccessKey': 'secret',
                'sessionToken': 'session',
                'expiration': 1793707200000,
            }
        }
    )


@post('/oidc/token')
def token_action(c):
    calls['oidc'] += 1
    body = c.req.json()
    seen.update(oidc=body)
    if body.get('refreshToken') != 'refresh':
        c.res.headers.header('X-Amzn-ErrorType', 'InvalidGrantException')
        return c.render(json={'error': 'invalid_grant', 'error_description': 'Invalid refresh token'}, status=400)
    c.render(json={'accessToken': 'refreshed', 'expiresIn': 3600, 'refreshToken': 'refresh2', 'tokenType': 'Bearer'})


ua = Pyjo.UserAgent.new()
ua.server.app = app


def provider(profile, **kwargs):
    return Pyjo.AWS.Credentials.SSO.new(config=Pyjo.AWS.Config.new(profile=profile), ua=ua, **kwargs)


with subtest('Token of a session'):
    with environ():
        ok(provider('sso').cache_dir.endswith('/.aws/sso/cache'), 'cache of the AWS CLI')
        is_ok(provider('sso').cache_file('company'), str(token_file('company')), 'file of the SHA-1 of the session')

        write_token('company', 'valid', datetime.timedelta(hours=8))
        credentials = provider('sso').credentials()
        is_ok(credentials.access_key_id, 'AKIDSSOVALID', 'credentials of the role')
        is_ok(credentials.secret_access_key, 'secret', 'secret access key')
        is_ok(credentials.session_token, 'session', 'session token')
        is_ok(credentials.expiration, datetime.datetime(2026, 11, 3, 12, tzinfo=datetime.UTC), 'expiration of millis')
        is_ok(credentials.account_id, '123456789012', 'account')
        is_ok(credentials.provider, 'sso', 'provider')
        is_ok(seen['token'], 'valid', 'token of the cache')
        is_ok(seen['role_name'], 'ReadOnly', 'role name')
        is_ok(seen['account_id'], '123456789012', 'account ID')
        is_ok(seen['authorization'], None, 'not signed')
        is_ok(provider('static').credentials(), None, 'profile without SSO')

        result = wait(provider('sso').credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDSSOVALID', 'non-blocking')

with subtest('Refresh'):
    with environ():
        write_token('company', 'expiring', datetime.timedelta(minutes=2), 'refresh')
        oidc = calls['oidc']
        credentials = provider('sso').credentials()
        is_ok(calls['oidc'], oidc + 1, 'token refreshed before it expires')
        is_ok(
            seen['oidc'],
            {
                'grantType': 'refresh_token',
                'clientId': 'client',
                'clientSecret': 'client-secret',
                'refreshToken': 'refresh',
            },
            'CreateToken of the refresh token',
        )
        is_ok(credentials.access_key_id, 'AKIDSSOREFRESHED', 'credentials of the new token')
        token = read_token('company')
        is_ok(token['accessToken'], 'refreshed', 'new token in the cache')
        is_ok(token['refreshToken'], 'refresh2', 'new refresh token in the cache')
        is_ok(token['startUrl'], START_URL, 'the other fields kept')
        expires_in = (Pyjo.AWS.Credentials.parse_time(token['expiresAt']) - NOW).total_seconds()
        ok(3500 < expires_in < 3700, 'expiration of expiresIn')
        if sys.platform == 'win32':
            skip('no modes of files on Windows')
        else:
            is_ok(stat.S_IMODE(os.stat(token_file('company')).st_mode), 0o600, 'cache readable by its owner only')
        provider('sso').credentials()
        is_ok(calls['oidc'], oidc + 1, 'new token not refreshed again')

        write_token('company', 'expiring', datetime.timedelta(minutes=2), 'refresh')
        result = wait(provider('sso').credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDSSOREFRESHED', 'refreshed, non-blocking')

        write_token('company', 'expiring', datetime.timedelta(minutes=2), 'revoked')
        credentials = provider('sso').credentials()
        is_ok(credentials.access_key_id, 'AKIDSSOEXPIRING', 'token of a failed refresh while it is valid')
        is_ok(read_token('company')['accessToken'], 'expiring', 'cache not changed')

        write_token('company', 'expiring', datetime.timedelta(minutes=-1), 'revoked')
        throws_ok(
            lambda: provider('sso').credentials(),
            re.compile(
                r'^Cannot refresh the token of the SSO of company of AWS: InvalidGrantException: .*: '
                r'aws sso login --profile sso'
            ),
            'failed refresh of an expired token',
        )

        write_token('company', 'expiring', datetime.timedelta(minutes=-1), 'refresh', datetime.timedelta(days=-1))
        oidc = calls['oidc']
        throws_ok(
            lambda: provider('sso').credentials(),
            re.compile(r'^The token of the SSO of company of AWS expired at \S+: aws sso login --profile sso'),
            'expired registration',
        )
        is_ok(calls['oidc'], oidc, 'no refresh of an expired registration')

        write_token('company', 'expiring', datetime.timedelta(minutes=-1))
        throws_ok(
            lambda: provider('sso').credentials(),
            re.compile(r'^The token of the SSO of company of AWS expired at '),
            'expired token without a refresh token',
        )
        result = wait(provider('sso').credentials_p())
        like_ok(str(result['error']), re.compile(r'expired at'), 'expired token, non-blocking')

with subtest('Legacy profile'):
    with environ():
        write_token(LEGACY_URL, 'legacy', datetime.timedelta(minutes=2), 'refresh')
        oidc = calls['oidc']
        credentials = provider('legacy').credentials()
        is_ok(credentials.access_key_id, 'AKIDSSOLEGACY', 'token of the start URL')
        is_ok(credentials.account_id, '210987654321', 'account')
        is_ok(seen['role_name'], 'Admin', 'role name')
        is_ok(calls['oidc'], oidc, 'token of a legacy profile not refreshed')

        write_token(LEGACY_URL, 'legacy', datetime.timedelta(minutes=-1))
        throws_ok(
            lambda: provider('legacy').credentials(),
            re.compile(rf'^The token of the SSO of {re.escape(LEGACY_URL)} of AWS expired at '),
            'expired token',
        )

with subtest('Errors'):
    with environ():
        token_file('company').remove()
        throws_ok(
            lambda: provider('sso').credentials(),
            re.compile(r'^No token of the SSO of company of AWS in \S+\.json: aws sso login --profile sso'),
            'no token',
        )

        token_file('company').spew('{')
        throws_ok(
            lambda: provider('sso').credentials(),
            re.compile(r'^Invalid token of the SSO of company of AWS in '),
            'invalid cache',
        )
        token_file('company').spew('{"expiresAt": "2026-11-03T12:00:00Z"}')
        throws_ok(
            lambda: provider('sso').credentials(),
            re.compile(r'^Invalid token of the SSO of company of AWS in '),
            'cache without a token',
        )

        throws_ok(
            lambda: provider('partial').credentials(),
            re.compile(r'^The SSO of the profile partial of AWS has no sso_account_id, sso_role_name'),
            'profile without its account and role',
        )
        throws_ok(
            lambda: provider('lost').credentials(),
            re.compile(r'^The sso-session nowhere of AWS is not in \S+config'),
            'missing sso-session',
        )
        throws_ok(
            lambda: provider('mismatch').credentials(),
            re.compile(r'^The sso_region of the profile mismatch of AWS is not the one of its sso-session company'),
            'region of the profile and of the session',
        )

        write_token('company', 'unknown', datetime.timedelta(hours=8))
        try:
            provider('sso').credentials()
            fail_ok('no error of SSO')
        except Pyjo.AWS.Error.object as e:
            is_ok(e.code, 'UnauthorizedException', 'error of SSO')
            is_ok(e.status, 401, 'status of the error')

with subtest('Profile and chain'):
    with environ(AWS_PROFILE='sso'):
        write_token('company', 'valid', datetime.timedelta(hours=8))
        credentials = Pyjo.AWS.Credentials.Profile.new(ua=ua).credentials()
        is_ok(credentials.provider, 'sso', 'SSO of the profile')
        credentials = Pyjo.AWS.Credentials.Chain.new(ua=ua).credentials()
        is_ok(credentials.access_key_id, 'AKIDSSOVALID', 'SSO of the chain')
        result = wait(Pyjo.AWS.Credentials.Chain.new(ua=ua).credentials_p())
        is_ok(result['value'].provider, 'sso', 'SSO of the chain, non-blocking')

done_testing()
