import Pyjo.AWS.Config
import Pyjo.AWS.Credentials
import Pyjo.AWS.Credentials.AssumeRole
import Pyjo.AWS.Credentials.Chain
import Pyjo.AWS.Credentials.Profile
import Pyjo.AWS.Credentials.Static
import Pyjo.AWS.Credentials.WebIdentity
import Pyjo.AWS.Error
import Pyjo.File
import Pyjo.UserAgent

from Pyjo.Test import *
from Pyjoyment.Lite import *

import contextlib
import datetime
import os
import re


# The credentials of the roles of STS, of AssumeRole with the credentials of a source and of
# AssumeRoleWithWebIdentity with a token, against an application that serves STS

tmp = Pyjo.File.tempdir()
token = tmp.child('token').spew('jwt')

tmp.child('config').spew(f"""\
[profile base]
aws_access_key_id = AKIDBASE
aws_secret_access_key = secret

[profile role]
role_arn = arn:aws:iam::123456789012:role/admin
source_profile = base
role_session_name = alice
external_id = 4c1d0e4f
duration_seconds = 900
region = eu-central-1

[profile chained]
role_arn = arn:aws:iam::210987654321:role/second
source_profile = role

[profile self]
role_arn = arn:aws:iam::123456789012:role/self
source_profile = self
aws_access_key_id = AKIDSELF
aws_secret_access_key = secret

[profile keyed]
role_arn = arn:aws:iam::123456789012:role/keyed
source_profile = both

[profile both]
role_arn = arn:aws:iam::123456789012:role/ignored
source_profile = base
aws_access_key_id = AKIDBOTH
aws_secret_access_key = secret

[profile cycle-a]
role_arn = arn:aws:iam::123456789012:role/a
source_profile = cycle-b

[profile cycle-b]
role_arn = arn:aws:iam::123456789012:role/b
source_profile = cycle-a

[profile environment]
role_arn = arn:aws:iam::123456789012:role/environment
credential_source = Environment

[profile imds]
role_arn = arn:aws:iam::123456789012:role/imds
credential_source = Ec2InstanceMetadata

[profile nowhere]
role_arn = arn:aws:iam::123456789012:role/nowhere
credential_source = Nowhere

[profile two-sources]
role_arn = arn:aws:iam::123456789012:role/two
source_profile = base
credential_source = Environment

[profile no-source]
role_arn = arn:aws:iam::123456789012:role/none

[profile mfa]
role_arn = arn:aws:iam::123456789012:role/mfa
source_profile = base
mfa_serial = arn:aws:iam::123456789012:mfa/alice

[profile lost]
role_arn = arn:aws:iam::123456789012:role/lost
source_profile = missing

[profile long]
role_arn = arn:aws:iam::123456789012:role/long
source_profile = base
duration_seconds = forever

[profile denied]
role_arn = arn:aws:iam::123456789012:role/denied
source_profile = base

[profile web]
role_arn = arn:aws:iam::123456789012:role/web
web_identity_token_file = {token}
role_session_name = web-session
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
            AWS_CONFIG_FILE=str(tmp.child('config')),
            AWS_SHARED_CREDENTIALS_FILE=str(tmp.child('credentials')),
            AWS_EC2_METADATA_DISABLED='true',
            AWS_ENDPOINT_URL_STS='/sts',
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


app.log.level = 'fatal'
calls = []


def response(c, action, account, role, session):
    c.res.headers.content_type = 'text/xml'
    c.render(
        data=(
            f'<{action}Response><{action}Result><Credentials>'
            f'<AccessKeyId>AKID{role.upper()}</AccessKeyId><SecretAccessKey>secret</SecretAccessKey>'
            f'<SessionToken>token-{role}</SessionToken><Expiration>2099-01-01T00:00:00Z</Expiration>'
            f'</Credentials><AssumedRoleUser><Arn>arn:aws:sts::{account}:assumed-role/{role}/{session}</Arn>'
            f'</AssumedRoleUser></{action}Result></{action}Response>'
        ).encode()
    )


def error(c, code, message, status=403):
    c.res.headers.content_type = 'text/xml'
    c.render(
        data=(
            f'<ErrorResponse><Error><Type>Sender</Type><Code>{code}</Code><Message>{message}</Message></Error>'
            '<RequestId>request</RequestId></ErrorResponse>'
        ).encode(),
        status=status,
    )


@post('/sts/')
def sts_action(c):
    authorization = c.req.headers.authorization
    signer = m[1] if authorization and (m := re.search(r'Credential=(\w+)/\d+/([\w-]+)/sts/', authorization)) else None
    region = m[2] if signer else None
    params = c.req.params.to_dict()
    calls.append({'signer': signer, 'region': region, **params})
    arn = params.get('RoleArn', '')
    account, role = arn.split(':')[4], arn.rsplit('/', 1)[-1]
    if params['Action'] == 'AssumeRole':
        if signer is None:
            return error(c, 'MissingAuthenticationToken', 'Request is missing Authentication Token')
        if role == 'denied':
            return error(c, 'AccessDenied', f'User {signer} is not authorized to perform: sts:AssumeRole')
        return response(c, 'AssumeRole', account, role, params['RoleSessionName'])
    if params['WebIdentityToken'] != 'jwt':
        return error(c, 'InvalidIdentityToken', 'Incorrect token audience', 400)
    response(c, 'AssumeRoleWithWebIdentity', account, role, params['RoleSessionName'])


ua = Pyjo.UserAgent.new()
ua.server.app = app


def profile(name, **kwargs):
    return Pyjo.AWS.Credentials.Profile.new(config=Pyjo.AWS.Config.new(profile=name), ua=ua, **kwargs)


with subtest('AssumeRole'):
    with environ():
        source = Pyjo.AWS.Credentials.Static.new(
            Pyjo.AWS.Credentials.new(access_key_id='AKIDSOURCE', secret_access_key='secret')
        )
        provider = Pyjo.AWS.Credentials.AssumeRole.new(
            source=source, role_arn='arn:aws:iam::123456789012:role/deploy', ua=ua
        )
        credentials = provider.credentials()
        is_ok(credentials.access_key_id, 'AKIDDEPLOY', 'credentials of the role')
        is_ok(credentials.session_token, 'token-deploy', 'session token')
        is_ok(credentials.expiration, datetime.datetime(2099, 1, 1, tzinfo=datetime.UTC), 'expiration')
        is_ok(credentials.account_id, '123456789012', 'account of the ARN of the user')
        is_ok(credentials.provider, 'assume-role', 'provider')
        is_ok(calls[-1]['signer'], 'AKIDSOURCE', 'signed with the source')
        is_ok(calls[-1]['region'], 'us-east-1', 'region of STS by default')
        like_ok(calls[-1]['RoleSessionName'], re.compile(r'^pyjo-aws-\d+$'), 'name of the session by default')
        ok('ExternalId' not in calls[-1] and 'DurationSeconds' not in calls[-1], 'no options')

        result = wait(provider.credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDDEPLOY', 'non-blocking')

        empty = Pyjo.AWS.Credentials.Profile.new(
            config=Pyjo.AWS.Config.new(config_file=str(tmp.child('none')), credentials_file=str(tmp.child('none')))
        )
        throws_ok(
            lambda: Pyjo.AWS.Credentials.AssumeRole.new(source=empty, role_arn='arn', ua=ua).credentials(),
            re.compile(r'^No credentials of AWS of the source of the role arn'),
            'source without credentials',
        )

with subtest('Roles of profiles'):
    with environ():
        count = len(calls)
        credentials = profile('role').credentials()
        is_ok(credentials.access_key_id, 'AKIDADMIN', 'role of source_profile')
        is_ok(calls[-1]['signer'], 'AKIDBASE', 'signed with the keys of the source profile')
        is_ok(calls[-1]['region'], 'eu-central-1', 'region of the profile')
        is_ok(calls[-1]['RoleSessionName'], 'alice', 'role_session_name')
        is_ok(calls[-1]['ExternalId'], '4c1d0e4f', 'external_id')
        is_ok(calls[-1]['DurationSeconds'], '900', 'duration_seconds')

        credentials = profile('chained').credentials()
        is_ok(credentials.access_key_id, 'AKIDSECOND', 'role of a role')
        is_ok(credentials.account_id, '210987654321', 'account of the second role')
        is_ok([call['signer'] for call in calls[-2:]], ['AKIDBASE', 'AKIDADMIN'], 'chain of the roles')

        is_ok(profile('self').credentials().access_key_id, 'AKIDSELF', 'source profile of its own role')
        is_ok(calls[-1]['signer'], 'AKIDSELF', 'signed with the keys of the profile')
        is_ok(profile('keyed').credentials().access_key_id, 'AKIDKEYED', 'source profile with keys')
        is_ok(calls[-1]['signer'], 'AKIDBOTH', 'keys of the source profile, not its role')

        provider = profile('role')
        provider.credentials()
        count = len(calls)
        provider.credentials()
        is_ok(len(calls), count, 'role cached')

        result = wait(profile('chained').credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDSECOND', 'role of a role, non-blocking')

    with environ(AWS_ACCESS_KEY_ID='AKIDENV', AWS_SECRET_ACCESS_KEY='secret'):
        is_ok(profile('environment').credentials().access_key_id, 'AKIDENVIRONMENT', 'credential_source Environment')
        is_ok(calls[-1]['signer'], 'AKIDENV', 'signed with the environment')

    with environ(AWS_PROFILE='role'):
        is_ok(Pyjo.AWS.Credentials.Chain.new(ua=ua).credentials().provider, 'assume-role', 'role of the chain')

with subtest('Errors of roles'):
    with environ():
        throws_ok(
            lambda: profile('cycle-a').credentials(),
            re.compile(r'^A cycle of the source_profile of AWS: cycle-a -> cycle-b -> cycle-a'),
            'cycle',
        )
        throws_ok(
            lambda: profile('imds').credentials(),
            re.compile(r'^No credentials of AWS of the source of the role arn:aws:iam::123456789012:role/imds'),
            'credential_source of IMDS without IMDS',
        )
        throws_ok(
            lambda: profile('nowhere').credentials(),
            re.compile(r'^Invalid credential_source Nowhere of the profile nowhere of AWS'),
            'invalid credential_source',
        )
        throws_ok(
            lambda: profile('two-sources').credentials(),
            re.compile(r'^The role of the profile two-sources of AWS has both source_profile and credential_source'),
            'two sources',
        )
        throws_ok(
            lambda: profile('no-source').credentials(),
            re.compile(r'^The role of the profile no-source of AWS has no source_profile, credential_source'),
            'no source',
        )
        throws_ok(
            lambda: profile('mfa').credentials(),
            re.compile(r'^The role of the profile mfa of AWS has mfa_serial, which is not supported'),
            'MFA',
        )
        throws_ok(
            lambda: profile('lost').credentials(),
            re.compile(r'^The source_profile missing of the profile lost of AWS is not in \S+config'),
            'missing source profile',
        )
        throws_ok(
            lambda: profile('long').credentials(),
            re.compile(r'^Invalid duration_seconds forever of the profile long of AWS'),
            'invalid duration',
        )
        throws_ok(
            lambda: profile('denied').credentials(),
            re.compile(r'^AccessDenied: User AKIDBASE is not authorized'),
            'error of STS',
        )
        ok(isinstance(wait(profile('denied').credentials_p())['error'], Pyjo.AWS.Error.object), 'error, non-blocking')

    with environ(AWS_PROFILE='environment'):
        throws_ok(
            lambda: profile('environment').credentials(),
            re.compile(r'^No credentials of AWS of the source of the role'),
            'credential_source Environment without credentials',
        )

with subtest('Web identity'):
    with environ():
        is_ok(Pyjo.AWS.Credentials.WebIdentity.new(ua=ua).credentials(), None, 'not configured')

    role = 'arn:aws:iam::123456789012:role/ci'
    with environ(AWS_WEB_IDENTITY_TOKEN_FILE=str(token), AWS_ROLE_ARN=role, AWS_ROLE_SESSION_NAME='ci-session'):
        credentials = Pyjo.AWS.Credentials.WebIdentity.new(ua=ua).credentials()
        is_ok(credentials.access_key_id, 'AKIDCI', 'credentials of the environment')
        is_ok(credentials.provider, 'web-identity', 'provider')
        is_ok(credentials.account_id, '123456789012', 'account')
        is_ok(calls[-1]['signer'], None, 'not signed')
        is_ok(calls[-1]['Action'], 'AssumeRoleWithWebIdentity', 'action')
        is_ok(calls[-1]['WebIdentityToken'], 'jwt', 'token of the file')
        is_ok(calls[-1]['RoleSessionName'], 'ci-session', 'name of the session of the environment')

        token.spew('rotated')
        throws_ok(
            lambda: Pyjo.AWS.Credentials.WebIdentity.new(ua=ua).credentials(),
            re.compile(r'^InvalidIdentityToken: Incorrect token audience'),
            'token read again',
        )
        token.spew('jwt\n')
        result = wait(Pyjo.AWS.Credentials.WebIdentity.new(ua=ua).credentials_p())
        is_ok(result['value'].access_key_id, 'AKIDCI', 'non-blocking, token without its new line')

        is_ok(Pyjo.AWS.Credentials.Chain.new(ua=ua).credentials().provider, 'web-identity', 'web identity of the chain')

    with environ(AWS_WEB_IDENTITY_TOKEN_FILE=str(token), AWS_ACCESS_KEY_ID='AKIDENV', AWS_SECRET_ACCESS_KEY='secret'):
        throws_ok(
            lambda: Pyjo.AWS.Credentials.WebIdentity.new(ua=ua).credentials(),
            re.compile(r'^Partial web identity of AWS in the environment: no AWS_ROLE_ARN'),
            'token file without a role',
        )
        is_ok(Pyjo.AWS.Credentials.Chain.new(ua=ua).credentials().provider, 'environment', 'environment first')

    with environ(AWS_WEB_IDENTITY_TOKEN_FILE=str(tmp.child('missing')), AWS_ROLE_ARN=role):
        throws_ok(
            lambda: Pyjo.AWS.Credentials.WebIdentity.new(ua=ua).credentials(),
            re.compile(r'^Cannot read the web identity token of AWS of \S+missing'),
            'missing token file',
        )

    with environ(AWS_ROLE_ARN=role, AWS_ROLE_SESSION_NAME='ignored'):
        credentials = profile('web').credentials()
        is_ok(credentials.access_key_id, 'AKIDWEB', 'web identity of a profile')
        is_ok(calls[-1]['RoleSessionName'], 'web-session', 'name of the session of the profile')
        is_ok(calls[-1]['signer'], None, 'not signed')

done_testing()
