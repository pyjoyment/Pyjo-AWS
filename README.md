[![Home](https://img.shields.io/badge/%F0%9F%8F%A0-Pyjoyment-02a7a0)](https://pyjoyment.dev/)
[![GitHub](https://img.shields.io/github/stars/pyjoyment/Pyjo-AWS?style=flat&label=GitHub%20%E2%AD%90&logo=github)](https://github.com/pyjoyment/Pyjo-AWS)
[![Documentation](https://img.shields.io/badge/docs-Read_the_Docs-blue?logo=readthedocs&logoColor=white)](https://pyjoyment.readthedocs.io/projects/pyjo-aws/en/stable/)
[![License](https://img.shields.io/github/license/pyjoyment/Pyjo-AWS.svg)](https://github.com/pyjoyment/Pyjo-AWS/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/Pyjo-AWS?logo=pypi&logoColor=white)](https://pypi.org/project/Pyjo-AWS/)
[![Tests](https://github.com/pyjoyment/Pyjo-AWS/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/pyjoyment/Pyjo-AWS/actions/workflows/tests.yaml)
[![Trunk Check](https://github.com/pyjoyment/Pyjo-AWS/actions/workflows/trunk-check.yaml/badge.svg?branch=main)](https://github.com/pyjoyment/Pyjo-AWS/actions/workflows/trunk-check.yaml)

# Pyjo-AWS

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/pyjoyment/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-white-4x.png">
    <img src="https://raw.githubusercontent.com/pyjoyment/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-black-4x.png" alt="Pyjoyment" width="322">
  </picture>
</p>

Amazon Web Services for [Pyjoyment](https://pyjoyment.dev/):
the requests of its user agent to the APIs of AWS, signed with Signature
Version 4, without an SDK. It is for a program that needs a few calls of AWS
and no dependency for them, not a replacement of the SDKs of AWS, which have
every API.

## Installation

From [PyPI](https://pypi.org/project/Pyjo-AWS/), with
[Pyjoyment](https://pypi.org/project/Pyjoyment/), which it depends on:

```sh
pip install Pyjo-AWS
```

or, in a project managed with [uv](https://docs.astral.sh/uv/):

```sh
uv add Pyjo-AWS
```

The credentials of `aws login` are refreshed with a signature of ECDSA,
which the package `cryptography` makes, of the extra `cryptography`, or
Python itself without it:

```sh
pip install 'Pyjo-AWS[cryptography]'
```

The development version is installed from the Git repository with uv, which
takes the version of Pyjoyment that it needs from Git too, before its
release:

```sh
uv pip install git+https://github.com/pyjoyment/Pyjo-AWS
```

## Usage

`Pyjo.AWS.Client` calls an operation of an API of AWS, with the credentials,
the region and the endpoint that the AWS CLI finds: of the environment, of a
profile with its keys, SSO of `aws sso login`, a session of `aws login`, a
role or `credential_process`, of a web identity, of the container of ECS or
EKS Pod Identity, or of the instance of EC2. The call is the operation in the
protocol of its API, with the names that its documentation has, and its result
is the XML of the response, as a `Pyjo.DOM` object, or its JSON:

```python
import Pyjo.AWS.Client
import Pyjo.AWS.Protocol.Query
import Pyjo.AWS.Protocol.RestJSON

sts = Pyjo.AWS.Client.new(service='sts')
print(sts.call(Pyjo.AWS.Protocol.Query.new('GetCallerIdentity', version='2011-06-15')).at('Arn').text)

lambda_ = Pyjo.AWS.Client.new(service='lambda', region='eu-central-1')
print(lambda_.call(Pyjo.AWS.Protocol.RestJSON.new('GET', '/2018-10-31/layers'))['Layers'])
```

The protocols are `Query`, of STS, IAM, SQS and SNS, `JSON`, of DynamoDB,
KMS and Secrets Manager, `RestJSON`, of Lambda and API Gateway, and
`RestXML`, of S3 and Route 53:

```python
import Pyjo.AWS.Config
import Pyjo.AWS.Protocol.JSON
import Pyjo.AWS.Protocol.RestXML

s3 = Pyjo.AWS.Client.new(service='s3', config=Pyjo.AWS.Config.new(profile='dev'))
dom = s3.call(Pyjo.AWS.Protocol.RestXML.new('GET', '/my-bucket', query={'list-type': 2, 'prefix': 'logs/'}))
print(dom.find('Contents > Key').map('text').join('\n'))

secrets = Pyjo.AWS.Client.new(service='secretsmanager')
call = Pyjo.AWS.Protocol.JSON.new('secretsmanager.GetSecretValue', {'SecretId': 'db'})
print(secrets.call(call)['SecretString'])
```

`call_p` is the same call, non-blocking, which returns a `Pyjo.Promise`
object, as an action of Pyjoyment awaits it:

```python
@get('/whoami')
async def whoami(c):
    dom = await sts.call_p(Pyjo.AWS.Protocol.Query.new('GetCallerIdentity', version='2011-06-15'))
    c.render(json={'arn': dom.at('Arn').text})
```

An error of AWS is a `Pyjo.AWS.Error`, with the code and the message of the
response:

```python
import Pyjo.AWS.Error

try:
    s3.call(Pyjo.AWS.Protocol.RestXML.new('GET', '/my-bucket/missing.txt'))
except Pyjo.AWS.Error.object as e:
    print(e.code, e.status, e.request_id)
```

`Pyjo.AWS.SigV4` signs a request of the user agent without the client, as
in the event `start` of the user agent, with the credentials of the
environment, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` and
`AWS_SESSION_TOKEN`, and the region of `AWS_REGION`:

```python
import Pyjo.AWS.SigV4
import Pyjo.UserAgent

signer = Pyjo.AWS.SigV4.new(service='lambda', region='eu-central-1')
ua = Pyjo.UserAgent.new()
ua.on('start', lambda ua, tx: signer.sign(tx.req))
print(ua.get('https://lambda.eu-central-1.amazonaws.com/2018-10-31/layers').result.json())
```

S3 signs its path as it is sent, and the hash of the body in a header of its
own, as the client signs it:

```python
signer = Pyjo.AWS.SigV4.new(service='s3', normalize_path=False, double_encode=False, content_sha256=True)
```

## Examples

[`examples/`](examples) has applications of Pyjoyment.Lite that call AWS, as
a bucket of S3 as a website:

```sh
uv run python examples/s3.py --profile myprofile --bucket mybucket daemon
```

## Documentation

The documentation of the API is on
[Read the Docs](https://pyjoyment.readthedocs.io/projects/pyjo-aws/en/stable/).

## License

Artistic License 2.0, as Pyjoyment. The cases of the
[AWS Signing Test Suite](https://github.com/awslabs/aws-c-auth) in
`t/aws-signing-test-suite` are under the Apache License 2.0 of their own.
