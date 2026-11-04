import Pyjo.AWS.Config
import Pyjo.File

from Pyjo.Test import *

import contextlib
import os
import re


# Shared configuration files of AWS

tmp = Pyjo.File.tempdir()

CONFIG = tmp.child('config').spew("""\
# A comment
[default]
region = us-west-2
output = json

[profile dev]
Region = eu-central-1
role_arn = arn:aws:iam::123456789012:role/dev
source_profile = default
s3 =
    addressing_style = path
    max_concurrent_requests = 10
services = local

[profile default]
output = text

[dev]
region = ignored

[sso-session company]
sso_start_url = https://company.awsapps.com/start
sso_region = eu-west-1

[services local]
s3 =
    endpoint_url = http://localhost:4566
sso_oidc =
    endpoint_url = http://localhost:4567

[profile local]
endpoint_url = http://localhost:9000
services = local

[profile ignore]
endpoint_url = http://localhost:9000
ignore_configured_endpoint_urls = true
""")

CREDENTIALS = tmp.child('credentials').spew("""\
[default]
AWS_ACCESS_KEY_ID = AKIDEXAMPLE
aws_secret_access_key = wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY

[keys]
aws_access_key_id = AKIDOTHER
aws_secret_access_key = other
region = ap-south-1
""")

NAMES = (
    'AWS_CONFIG_FILE',
    'AWS_SHARED_CREDENTIALS_FILE',
    'AWS_PROFILE',
    'AWS_DEFAULT_PROFILE',
    'AWS_REGION',
    'AWS_DEFAULT_REGION',
    'AWS_IGNORE_CONFIGURED_ENDPOINT_URLS',
)


# The variables of AWS of the environment of the test only, without those of the machine, as AWS_ENDPOINT_URL_*
@contextlib.contextmanager
def environ(**values):
    saved = dict(os.environ)
    try:
        for name in list(os.environ):
            if name in NAMES or name.startswith('AWS_ENDPOINT_URL'):
                del os.environ[name]
        os.environ.update(AWS_CONFIG_FILE=str(CONFIG), AWS_SHARED_CREDENTIALS_FILE=str(CREDENTIALS), **values)
        yield
    finally:
        os.environ.clear()
        os.environ.update(saved)


with subtest('Profiles'):
    with environ():
        config = Pyjo.AWS.Config.new()
        is_ok(config.profile, 'default', 'default profile')
        is_ok(config.config_file, str(CONFIG), 'config file of the environment')
        is_ok(config.credentials_file, str(CREDENTIALS), 'credentials file of the environment')
        is_ok(config.profiles(), ['default', 'dev', 'ignore', 'keys', 'local'], 'profiles of both files')
        is_ok(
            config.settings(),
            {
                'region': 'us-west-2',
                'output': 'text',
                'aws_access_key_id': 'AKIDEXAMPLE',
                'aws_secret_access_key': 'wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY',
            },
            'default profile of both files, with [profile default] over [default]',
        )
        is_ok(config.get('Region', 'dev'), 'eu-central-1', 'setting in lower case')
        is_ok(
            config.get('s3', 'dev'),
            {'addressing_style': 'path', 'max_concurrent_requests': '10'},
            'nested settings',
        )
        is_ok(config.get('nothing'), None, 'no setting')
        ok(config.has_profile('keys'), 'profile of the credentials file')
        ok(not config.has_profile('missing'), 'no profile')
        is_ok(config.settings('missing'), {}, 'no settings of a missing profile')
        is_ok(config.sso_session('company')['sso_region'], 'eu-west-1', 'sso-session')
        is_ok(config.sso_session('missing'), {}, 'no sso-session')
        config.settings()['region'] = 'changed'
        is_ok(config.get('region'), 'us-west-2', 'settings are a copy')

    with environ(AWS_PROFILE='dev'):
        is_ok(Pyjo.AWS.Config.new().profile, 'dev', 'profile of AWS_PROFILE')
        is_ok(Pyjo.AWS.Config.new(profile='keys').profile, 'keys', 'profile of an argument')

    with environ(AWS_DEFAULT_PROFILE='keys'):
        is_ok(Pyjo.AWS.Config.new().profile, 'keys', 'profile of AWS_DEFAULT_PROFILE')

with subtest('Region'):
    with environ():
        is_ok(Pyjo.AWS.Config.new().region(), 'us-west-2', 'region of the default profile')
        is_ok(Pyjo.AWS.Config.new().region('keys'), 'ap-south-1', 'region of the credentials file')
        is_ok(Pyjo.AWS.Config.new(profile='local').region(), None, 'no region')

    with environ(AWS_DEFAULT_REGION='eu-west-1'):
        is_ok(Pyjo.AWS.Config.new().region(), 'eu-west-1', 'region of AWS_DEFAULT_REGION')

    with environ(AWS_REGION='eu-north-1', AWS_DEFAULT_REGION='eu-west-1'):
        is_ok(Pyjo.AWS.Config.new().region(), 'eu-north-1', 'region of AWS_REGION')

with subtest('Endpoints'):
    with environ(AWS_PROFILE='local'):
        config = Pyjo.AWS.Config.new()
        is_ok(config.services('local')['s3'], {'endpoint_url': 'http://localhost:4566'}, 'section services')
        is_ok(config.endpoint_url('S3'), 'http://localhost:4566', 'endpoint of the section services')
        is_ok(config.endpoint_url('SSO OIDC'), 'http://localhost:4567', 'service ID with a space')
        is_ok(config.endpoint_url('Lambda'), 'http://localhost:9000', 'endpoint of the profile')
        is_ok(config.endpoint_url('Lambda', 'default'), None, 'no endpoint')

    with environ(AWS_PROFILE='local', AWS_ENDPOINT_URL='http://localhost:8000'):
        is_ok(
            Pyjo.AWS.Config.new().endpoint_url('S3'), 'http://localhost:4566', 'section services over AWS_ENDPOINT_URL'
        )
        is_ok(Pyjo.AWS.Config.new().endpoint_url('Lambda'), 'http://localhost:8000', 'AWS_ENDPOINT_URL over profile')

    with environ(AWS_PROFILE='local', AWS_ENDPOINT_URL_SSO_OIDC='http://localhost:7000'):
        is_ok(Pyjo.AWS.Config.new().endpoint_url('SSO OIDC'), 'http://localhost:7000', 'AWS_ENDPOINT_URL_<SERVICE>')
        is_ok(Pyjo.AWS.Config.new().endpoint_url('sso-oidc'), 'http://localhost:7000', 'service ID with a hyphen')

    with environ(AWS_PROFILE='ignore'):
        is_ok(Pyjo.AWS.Config.new().endpoint_url('S3'), None, 'ignore_configured_endpoint_urls')

    with environ(AWS_PROFILE='local', AWS_IGNORE_CONFIGURED_ENDPOINT_URLS='True'):
        is_ok(Pyjo.AWS.Config.new().endpoint_url('S3'), None, 'AWS_IGNORE_CONFIGURED_ENDPOINT_URLS')

with subtest('Files'):
    with environ():
        config = Pyjo.AWS.Config.new(config_file=str(tmp.child('missing')), credentials_file=str(tmp.child('none')))
        is_ok(config.profiles(), [], 'no files')
        is_ok(config.region(), None, 'no region without files')

        home = os.environ.get('HOME')
        os.environ['HOME'] = str(tmp)
        try:
            for name in ('AWS_CONFIG_FILE', 'AWS_SHARED_CREDENTIALS_FILE'):
                del os.environ[name]
            config = Pyjo.AWS.Config.new()
            is_ok(config.config_file, str(tmp.child('.aws', 'config')), 'config file of the home directory')
            is_ok(config.credentials_file, str(tmp.child('.aws', 'credentials')), 'credentials of the home directory')
            os.environ['AWS_CONFIG_FILE'] = '~/config'
            is_ok(Pyjo.AWS.Config.new().get('region'), 'us-west-2', 'path with a tilde')
        finally:
            if home is not None:
                os.environ['HOME'] = home

        broken = tmp.child('broken').spew('region = us-east-1\n')
        throws_ok(
            lambda: Pyjo.AWS.Config.new(config_file=str(broken)).settings(),
            re.compile(r'^Cannot parse the configuration file of AWS .*broken'),
            'no section',
        )
        broken.spew('[default]\ns3 =\n    addressing_style\n')
        throws_ok(
            lambda: Pyjo.AWS.Config.new(config_file=str(broken)).settings(),
            re.compile(r"^Cannot parse the configuration file of AWS .*broken: 'addressing_style'"),
            'nested setting without a value',
        )

done_testing()
