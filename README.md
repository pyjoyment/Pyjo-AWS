[![Home](https://img.shields.io/badge/%F0%9F%8F%A0-Pyjoyment-02a7a0)](https://github.com/pyjoyment/Pyjoyment)
[![GitHub](https://img.shields.io/github/stars/pyjoyment/Pyjo-AWS?style=flat&label=GitHub%20%E2%AD%90&logo=github)](https://github.com/pyjoyment/Pyjo-AWS)
[![Documentation](https://img.shields.io/badge/docs-Read_the_Docs-blue?logo=readthedocs&logoColor=white)](https://pyjoyment.readthedocs.io/projects/pyjo-aws/en/stable/)
[![License](https://img.shields.io/github/license/pyjoyment/Pyjo-AWS.svg)](https://github.com/pyjoyment/Pyjo-AWS/blob/main/LICENSE)
[![PyPI](https://img.shields.io/pypi/v/Pyjo-AWS?logo=pypi&logoColor=white)](https://pypi.org/project/Pyjo-AWS/)
[![Tests](https://github.com/pyjoyment/Pyjo-AWS/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/pyjoyment/Pyjo-AWS/actions/workflows/tests.yaml)

# Pyjo-AWS

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/pyjoyment/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-white-4x.png">
    <img src="https://raw.githubusercontent.com/pyjoyment/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-black-4x.png" alt="Pyjoyment" width="322">
  </picture>
</p>

Amazon Web Services for [Pyjoyment](https://github.com/pyjoyment/Pyjoyment):
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

The development version is installed from the Git repository:

```sh
pip install git+https://github.com/pyjoyment/Pyjo-AWS
```

## Usage

`Pyjo.AWS.SigV4` signs a request in the event `start` of the user agent, with
the credentials of the environment, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN`, and the region of
`AWS_REGION`:

```python
import Pyjo.AWS.SigV4
import Pyjo.UserAgent

signer = Pyjo.AWS.SigV4.new(service='lambda', region='eu-central-1')
ua = Pyjo.UserAgent.new()
ua.on('start', lambda ua, tx: signer.sign(tx.req))
print(ua.get('https://lambda.eu-central-1.amazonaws.com/2018-10-31/layers').result.json())
```

S3 signs its path as it is sent, and the hash of the body in a header of its
own:

```python
signer = Pyjo.AWS.SigV4.new(service='s3', normalize_path=False, double_encode=False, content_sha256=True)
```

## Documentation

The documentation of the API is on
[Read the Docs](https://pyjoyment.readthedocs.io/projects/pyjo-aws/en/stable/).

## License

Artistic License 2.0, as Pyjoyment. The cases of the
[AWS Signing Test Suite](https://github.com/awslabs/aws-c-auth) in
`t/aws-signing-test-suite` are under the Apache License 2.0 of their own.
