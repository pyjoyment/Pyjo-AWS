import Pyjo.AWS.Client
import Pyjo.AWS.Config
import Pyjo.AWS.Credentials
import Pyjo.AWS.Credentials.Provider
import Pyjo.AWS.Error
import Pyjo.AWS.Protocol.JSON
import Pyjo.AWS.Protocol.Query
import Pyjo.AWS.Protocol.RestJSON
import Pyjo.AWS.Protocol.RestXML
import Pyjo.Date
import Pyjo.Exception
import Pyjo.File
import Pyjo.Promise
import Pyjo.UserAgent

from Pyjo.Test import *
from Pyjoyment.Lite import *

import contextlib
import os
import re
import time


# The client of an API of AWS, with its protocols, against an application that serves the endpoints of AWS

tmp = Pyjo.File.tempdir()

Query = Pyjo.AWS.Protocol.Query.new
JSON = Pyjo.AWS.Protocol.JSON.new
RestJSON = Pyjo.AWS.Protocol.RestJSON.new
RestXML = Pyjo.AWS.Protocol.RestXML.new

tmp.child('config').spew("""\
[profile dev]
region = eu-west-1
services = local

[services local]
sts =
    endpoint_url = http://sts.localhost:4566
sso_oidc =
    endpoint_url = http://oidc.localhost:4566
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


def error_of(code):
    try:
        code()
    except Pyjo.AWS.Error.object as e:
        return e
    raise AssertionError('no error of AWS')


class Static(Pyjo.AWS.Credentials.Provider.object):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fetched = 0

    async def fetch(self):
        self.fetched += 1
        return Pyjo.AWS.Credentials.new(
            access_key_id='AKIDEXAMPLE',
            secret_access_key='wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY',
            session_token='token',
            expiration=Pyjo.Date.new(time.time() + 3600),
            provider='static',
        )


class Nothing(Pyjo.AWS.Credentials.Provider.object):
    pass


app.log.level = 'fatal'
seen = {}


def remember(c):
    headers = c.req.headers
    seen.update(
        method=c.req.method,
        path=c.req.url.path.to_str(),
        query=c.req.url.query.to_str(),
        authorization=headers.authorization,
        token=headers.header('X-Amz-Security-Token'),
        sha256=headers.header('X-Amz-Content-Sha256'),
        target=headers.header('X-Amz-Target'),
        content_type=headers.content_type,
        bearer=headers.header('X-Amz-Sso_bearer_token'),
        body=c.req.body,
    )


def xml(c, text, status=200):
    c.res.headers.header('X-Amzn-RequestId', 'request-of-header')
    c.render(data=text.encode(), format='xml', status=status)


@post('/sts/')
def sts_action(c):
    remember(c)
    action = c.param('Action')
    if action == 'GetCallerIdentity':
        return xml(
            c,
            '<GetCallerIdentityResponse xmlns="https://sts.amazonaws.com/doc/2011-06-15/">'
            '<GetCallerIdentityResult><Arn>arn:aws:iam::123456789012:user/alice</Arn>'
            '<Account>123456789012</Account></GetCallerIdentityResult>'
            '<ResponseMetadata><RequestId>request-1</RequestId></ResponseMetadata>'
            '</GetCallerIdentityResponse>',
        )
    if action == 'AssumeRole':
        return xml(
            c,
            '<AssumeRoleResponse><AssumeRoleResult><Credentials>'
            f'<AccessKeyId>AKIDROLE{c.param("RoleSessionName")}</AccessKeyId><SecretAccessKey>secret</SecretAccessKey>'
            '<SessionToken>role</SessionToken><Expiration>2026-11-03T12:00:00Z</Expiration>'
            '</Credentials></AssumeRoleResult></AssumeRoleResponse>',
        )
    xml(
        c,
        '<ErrorResponse><Error><Type>Sender</Type><Code>InvalidAction</Code>'
        f'<Message>Could not find operation {action}</Message></Error>'
        '<RequestId>request-2</RequestId></ErrorResponse>',
        400,
    )


@post('/dynamodb/')
def dynamodb_action(c):
    remember(c)
    target = c.req.headers.header('X-Amz-Target')
    if target == 'DynamoDB_20120810.ListTables':
        return c.render(json={'TableNames': ['users'][: c.req.json('/Limit')]})
    if target == 'DynamoDB_20120810.DeleteTable':
        c.res.headers.header('X-Amzn-ErrorType', 'ResourceNotFoundException:http://internal.amazon.com/coral/')
        return c.render(json={'message': 'Requested resource not found'}, status=400)
    c.render(
        json={'__type': 'com.amazon.coral.service#UnknownOperationException', 'Message': 'Unknown'},
        status=400,
    )


@get('/lambda/2018-10-31/layers')
def layers_action(c):
    remember(c)
    c.res.headers.header('X-Amzn-RequestId', 'request-3')
    if c.param('Marker') == 'denied':
        c.res.headers.header('X-Amzn-ErrorType', 'AccessDeniedException')
        return c.render(json={'Message': 'User is not authorized'}, status=403)
    c.render(json={'Layers': [{'LayerName': 'pyjoyment'}], 'MaxItems': c.param('MaxItems')})


@post('/lambda/2018-10-31/layers/<name>/versions')
def publish_action(c):
    remember(c)
    c.render(json={'LayerName': c.param('name'), 'Version': 1, 'Description': c.req.json('/Description')})


@post('/lambda/2015-03-31/functions/<name>/invocations')
def invoke_action(c):
    remember(c)
    if c.param('name') == 'text':
        return c.render(data=b'Hello!', format='txt')
    c.rendered(204)


@get('/sso/federation/credentials')
def sso_action(c):
    remember(c)
    c.render(json={'roleCredentials': {'accessKeyId': 'AKIDSSO'}})


@any(['GET', 'PUT'], '/s3/<bucket>/*key')
def object_action(c):
    remember(c)
    key = c.param('key')
    if c.req.method == 'PUT':
        c.res.headers.etag = '"etag"'
        return c.rendered(200)
    if key == 'missing':
        return c.rendered(404)
    if key == 'text.txt':
        return c.render(data=b'Hello!', format='txt')
    xml(
        c,
        '<Error><Code>NoSuchKey</Code><Message>The specified key does not exist.</Message>'
        '<RequestId>request-4</RequestId></Error>',
        404,
    )


@get('/s3/<bucket>')
def bucket_action(c):
    remember(c)
    xml(
        c,
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        f'<Name>{c.param("bucket")}</Name><Contents><Key>a.txt</Key></Contents><Contents><Key>b.txt</Key></Contents>'
        '</ListBucketResult>',
    )


ua = Pyjo.UserAgent.new()
ua.server.app = app
# A relative endpoint, which the user agent resolves to its server of the blocking or the non-blocking requests
base = ''


def client(service, **kwargs):
    kwargs.setdefault('endpoint', f'{base}/{service}')
    kwargs.setdefault('region', 'eu-central-1')
    kwargs.setdefault('credentials', Static())
    kwargs.setdefault('ua', ua)
    return Pyjo.AWS.Client.new(service=service, **kwargs)


with subtest('Endpoint'):
    with environ():
        is_ok(
            Pyjo.AWS.Client.new(service='sts', region='eu-central-1').endpoint_url(),
            'https://sts.eu-central-1.amazonaws.com',
            'regional endpoint',
        )
        is_ok(
            Pyjo.AWS.Client.new(service='sts', region='cn-north-1').endpoint_url(),
            'https://sts.cn-north-1.amazonaws.com.cn',
            'endpoint of China',
        )
        is_ok(
            Pyjo.AWS.Client.new(
                service='awsssoportal', endpoint_prefix='portal.sso', region='eu-central-1'
            ).endpoint_url(),
            'https://portal.sso.eu-central-1.amazonaws.com',
            'prefix of the endpoint',
        )
        is_ok(
            Pyjo.AWS.Client.new(service='iam', endpoint='https://iam.amazonaws.com').endpoint_url(),
            'https://iam.amazonaws.com',
            'endpoint without a region',
        )
        is_ok(Pyjo.AWS.Client.new(service='sts').region, None, 'no region')
        throws_ok(
            lambda: Pyjo.AWS.Client.new(service='sts').endpoint_url(),
            re.compile(r'^No region of AWS for sts'),
            'no region, no endpoint',
        )

    with environ(AWS_REGION='us-west-2', AWS_ENDPOINT_URL_STS='http://127.0.0.1:4566'):
        is_ok(Pyjo.AWS.Client.new(service='sts').region, 'us-west-2', 'region of the environment')
        is_ok(Pyjo.AWS.Client.new(service='sts').endpoint_url(), 'http://127.0.0.1:4566', 'endpoint of the environment')
        is_ok(
            Pyjo.AWS.Client.new(service='sts', endpoint='http://127.0.0.1:1').endpoint_url(),
            'http://127.0.0.1:1',
            'endpoint of the argument first',
        )

    with environ(AWS_PROFILE='dev'):
        is_ok(Pyjo.AWS.Client.new(service='sts').region, 'eu-west-1', 'region of the profile')
        is_ok(Pyjo.AWS.Client.new(service='sts').endpoint_url(), 'http://sts.localhost:4566', 'endpoint of the profile')
        is_ok(
            Pyjo.AWS.Client.new(service='sso-oauth', endpoint_prefix='oidc', service_id='SSO OIDC').endpoint_url(),
            'http://oidc.localhost:4566',
            'endpoint of the ID of the service',
        )

with subtest('Query'):
    sts = client('sts')
    dom = sts.call(Query('GetCallerIdentity', version='2011-06-15'))
    is_ok(dom.at('GetCallerIdentityResult > Arn').text, 'arn:aws:iam::123456789012:user/alice', 'result')
    is_ok(dom.at('RequestId').text, 'request-1', 'metadata')
    is_ok(seen['method'], 'POST', 'posted')
    is_ok(seen['content_type'], 'application/x-www-form-urlencoded', 'form')
    is_ok(seen['body'], b'Action=GetCallerIdentity&Version=2011-06-15', 'action and version')
    like_ok(
        seen['authorization'],
        re.compile(r'^AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/\d{8}/eu-central-1/sts/aws4_request, SignedHeaders='),
        'signed',
    )
    is_ok(seen['token'], 'token', 'session token')
    ok(not ua.has_subscribers('start'), 'signer unsubscribed')

    dom = sts.call(
        Query(
            'AssumeRole',
            {'RoleArn': 'arn:aws:iam::123456789012:role/admin', 'RoleSessionName': 'a b', 'Tags.member.1.Key': None},
            version='2011-06-15',
        )
    )
    is_ok(dom.at('AccessKeyId').text, 'AKIDROLEa b', 'parameters')
    unlike_ok(seen['body'].decode(), re.compile(r'Tags'), 'no None')
    sts.call(Query('GetCallerIdentity', {'Flag': True, 'Count': 3}, version='2011-06-15'))
    like_ok(seen['body'].decode(), re.compile(r'Count=3&Flag=true'), 'values of booleans and numbers')

    e = error_of(lambda: sts.call(Query('Missing', version='2011-06-15')))
    is_ok(e.code, 'InvalidAction', 'code of the error')
    is_ok(e.message, 'InvalidAction: Could not find operation Missing', 'message of the error')
    is_ok(e.status, 400, 'status of the error')
    is_ok(e.request_id, 'request-2', 'request ID of the body')
    is_ok(e.tx.res.code, 400, 'transaction of the error')

    result = wait(sts.call_p(Query('GetCallerIdentity', version='2011-06-15')))
    is_ok(result['value'].at('Account').text, '123456789012', 'non-blocking')
    result = wait(sts.call_p(Query('Missing', version='2011-06-15')))
    is_ok(result['error'].code, 'InvalidAction', 'non-blocking error')

with subtest('JSON'):
    dynamodb = client('dynamodb')
    is_ok(
        dynamodb.call(JSON('DynamoDB_20120810.ListTables', {'Limit': 1}, version='1.0')),
        {'TableNames': ['users']},
        'result',
    )
    is_ok(seen['target'], 'DynamoDB_20120810.ListTables', 'target')
    is_ok(seen['content_type'], 'application/x-amz-json-1.0', 'version of the protocol')
    is_ok(seen['body'], b'{"Limit":1}', 'parameters')
    dynamodb.call(JSON('DynamoDB_20120810.ListTables'))
    is_ok(seen['content_type'], 'application/x-amz-json-1.1', 'default version')
    is_ok(seen['body'], b'{}', 'no parameters')

    throws_ok(
        lambda: dynamodb.call(JSON('DynamoDB_20120810.DeleteTable')),
        re.compile(r'^ResourceNotFoundException: Requested resource not found'),
        'error of the header',
    )
    e = error_of(lambda: dynamodb.call(JSON('DynamoDB_20120810.Missing')))
    is_ok(e.code, 'UnknownOperationException', 'error of the type without its namespace')
    is_ok(e.message, 'UnknownOperationException: Unknown', 'message of Message')

    result = wait(dynamodb.call_p(JSON('DynamoDB_20120810.ListTables', {'Limit': 0})))
    is_ok(result['value'], {'TableNames': []}, 'non-blocking')

with subtest('REST-JSON'):
    lambda_ = client('lambda')
    layers = lambda_.call(RestJSON('GET', '/2018-10-31/layers', query={'MaxItems': 50, 'Marker': None}))
    is_ok(layers['Layers'][0]['LayerName'], 'pyjoyment', 'result')
    is_ok(layers['MaxItems'], '50', 'query')
    is_ok(seen['path'], '/lambda/2018-10-31/layers', 'path after the path of the endpoint')
    is_ok(seen['query'], 'MaxItems=50', 'no None')
    lambda_.call(RestJSON('GET', '/2018-10-31/layers?MaxItems=10', query={'Marker': 'a'}))
    is_ok(seen['query'], 'MaxItems=10&Marker=a', 'query of the path and of the argument')

    version = lambda_.call(RestJSON('POST', '/2018-10-31/layers/hello%2Dworld/versions', {'Description': 'Hi'}))
    is_ok(version, {'LayerName': 'hello-world', 'Version': 1, 'Description': 'Hi'}, 'JSON of the body')
    is_ok(seen['path'], '/lambda/2018-10-31/layers/hello%2Dworld/versions', 'path percent-encoded already')
    is_ok(lambda_.call(RestJSON('POST', '/2015-03-31/functions/empty/invocations')), None, 'no body')
    is_ok(lambda_.call(RestJSON('POST', '/2015-03-31/functions/text/invocations')), b'Hello!', 'body not of JSON')

    e = error_of(lambda: lambda_.call(RestJSON('GET', '/2018-10-31/layers', query={'Marker': 'denied'})))
    is_ok(e.code, 'AccessDeniedException', 'code of the header')
    is_ok(e.message, 'AccessDeniedException: User is not authorized', 'message')
    is_ok(e.status, 403, 'status')
    is_ok(e.request_id, 'request-3', 'request ID of the header')

    sso = client('awsssoportal', endpoint=f'{base}/sso', unsigned=True, credentials=Nothing())
    call = RestJSON(
        'GET',
        '/federation/credentials',
        query={'role_name': 'admin', 'account_id': '123456789012'},
        headers={'X-Amz-Sso_bearer_token': 'bearer'},
    )
    is_ok(sso.call(call)['roleCredentials']['accessKeyId'], 'AKIDSSO', 'unsigned')
    is_ok(seen['authorization'], None, 'no signature')
    is_ok(seen['bearer'], 'bearer', 'headers')
    result = wait(sso.call_p(call))
    is_ok(result['value']['roleCredentials']['accessKeyId'], 'AKIDSSO', 'unsigned, non-blocking')

with subtest('REST-XML'):
    s3 = client('s3')
    dom = s3.call(RestXML('GET', '/my-bucket', query={'list-type': 2}))
    is_ok(dom.find('Contents > Key').map('text').to_list(), ['a.txt', 'b.txt'], 'result')
    like_ok(seen['authorization'], re.compile(r'/eu-central-1/s3/aws4_request'), 'signed for S3')
    like_ok(seen['sha256'], re.compile(r'^[0-9a-f]{64}$'), 'hash of the body')

    is_ok(s3.call(RestXML('PUT', '/my-bucket/a%20b.txt', b'Hello!')), None, 'no body')
    is_ok(seen['body'], b'Hello!', 'body')
    is_ok(seen['path'], '/s3/my-bucket/a%20b.txt', 'path')
    s3.call(RestXML('PUT', '/my-bucket/c.xml', '<a/>', headers={'Content-Type': 'application/xml'}))
    is_ok(seen['body'], b'<a/>', 'body of a string')
    is_ok(s3.call(RestXML('GET', '/my-bucket/text.txt')), b'Hello!', 'body not of XML')

    e = error_of(lambda: s3.call(RestXML('GET', '/my-bucket/none.txt')))
    is_ok(e.code, 'NoSuchKey', 'code of the element Error')
    is_ok(e.message, 'NoSuchKey: The specified key does not exist.', 'message')
    is_ok(e.request_id, 'request-4', 'request ID of the element Error')
    e = error_of(lambda: s3.call(RestXML('GET', '/my-bucket/missing')))
    is_ok(e.code, '404', 'code of the status without a body')
    is_ok(e.message, '404: Not Found', 'message of the status')

    result = wait(s3.call_p(RestXML('GET', '/my-bucket')))
    is_ok(result['value'].at('Name').text, 'my-bucket', 'non-blocking')

with subtest('Credentials'):
    provider = Static()
    sts = client('sts', credentials=provider)
    sts.call(Query('GetCallerIdentity', version='2011-06-15'))
    sts.call(Query('GetCallerIdentity', version='2011-06-15'))
    is_ok(provider.fetched, 1, 'credentials cached')

    provider = Static()
    sts = client('sts', credentials=provider)
    wait(
        Pyjo.Promise.all(
            sts.call_p(Query('GetCallerIdentity', version='2011-06-15')),
            sts.call_p(Query('GetCallerIdentity', version='2011-06-15')),
        )
    )
    is_ok(provider.fetched, 1, 'credentials got once for calls at once')

    sts = client('sts', credentials=Nothing())
    throws_ok(
        lambda: sts.call(Query('GetCallerIdentity', version='2011-06-15')),
        re.compile(r'^No credentials of AWS'),
        'no credentials',
    )
    result = wait(sts.call_p(Query('GetCallerIdentity', version='2011-06-15')))
    like_ok(str(result['error']), re.compile(r'^No credentials of AWS'), 'no credentials, non-blocking')

    with environ(AWS_ACCESS_KEY_ID='AKIDENV', AWS_SECRET_ACCESS_KEY='secret'):
        sts = Pyjo.AWS.Client.new(service='sts', endpoint=f'{base}/sts', region='eu-central-1', ua=ua)
        sts.call(Query('GetCallerIdentity', version='2011-06-15'))
        like_ok(seen['authorization'], re.compile(r'Credential=AKIDENV/'), 'credentials of the chain')
        is_ok(seen['token'], None, 'no session token')

    sts = client('sts', endpoint='http://127.0.0.1:1', ua=Pyjo.UserAgent.new(connect_timeout=2))
    throws_ok(
        lambda: sts.call(Query('GetCallerIdentity', version='2011-06-15')),
        re.compile(r'^POST http://127\.0\.0\.1:1/: '),
        'error of the connection',
    )

with subtest('Steps of a provider'):

    class Role(Pyjo.AWS.Credentials.Provider.object):
        def __init__(self, sts, source, name, **kwargs):
            super().__init__(**kwargs)
            self.sts, self.source, self.name = sts, source, name

        async def fetch(self):
            source = await self.source.steps()
            dom = await self.sts.steps(
                Query('AssumeRole', {'RoleArn': 'arn', 'RoleSessionName': self.name}, version='2011-06-15'), source
            )
            return Pyjo.AWS.Credentials.new(
                access_key_id=dom.at('AccessKeyId').text,
                secret_access_key=dom.at('SecretAccessKey').text,
                session_token=dom.at('SessionToken').text,
                expiration=Pyjo.AWS.Credentials.parse_time(dom.at('Expiration').text),
                provider='role',
            )

    source = Static()
    sts = client('sts', credentials=Nothing())
    other = Pyjo.UserAgent.new()
    credentials = Role(sts, source, 'blocking', ua=other).credentials()
    is_ok(credentials.access_key_id, 'AKIDROLEblocking', 'role of a provider of another user agent')
    like_ok(seen['authorization'], re.compile(r'Credential=AKIDEXAMPLE/'), 'signed with the source')
    is_ok(source.fetched, 1, 'source asked')

    result = wait(Role(sts, source, 'nonblocking', ua=other).credentials_p())
    is_ok(result['value'].access_key_id, 'AKIDROLEnonblocking', 'role, non-blocking')
    is_ok(source.fetched, 1, 'source cached')
    ok(not ua.has_subscribers('start'), 'signer unsubscribed')

done_testing()
