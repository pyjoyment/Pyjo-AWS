# Agent Guide: Pyjo-AWS

## Overview

`Pyjo.AWS` calls the APIs of Amazon Web Services with `Pyjo.UserAgent` of
Pyjoyment, without an SDK, in a distribution of its own, as Pyjoyment has no
business with one cloud. It is for a program that needs a few calls of AWS
and no dependency for them, as the publication of Pyjoyment-Lambda-Layers,
not a replacement of the SDKs of AWS: what it has is what such a program
needs, the signature, the credentials that the SDKs of AWS find, and the
protocols of the APIs, not the generated clients of every API. The
conventions are those of Pyjoyment: read its `AGENTS.md` in the checkout next
to this one, `../Pyjoyment/AGENTS.md`. The plan is in the issues of this
repository.

The reference is the behaviour of the SDKs of AWS, as the
[Reference Guide of the SDKs and Tools](https://docs.aws.amazon.com/sdkref/latest/guide/overview.html)
describes it, so that a program finds the credentials, the region and the
endpoints that the AWS CLI finds.

## Signature Version 4

`Pyjo.AWS.SigV4` signs the requests of `Pyjo.UserAgent` to the APIs of AWS.
It comes from Pyjoyment-Lambda-Layers, where it was a module of the namespace
`Pyjo` of Pyjoyment without a distribution, so that it could move here
without a change of its imports.

The event `start` of the user agent signs a request, as it comes for each
transaction, a redirect too, once the request is complete. The request has no
`Host` and no `Content-Length` then, which `fix_headers` of the request adds
when it is written, so `sign` sets `Host` itself, and `Content-Length` is not
signed, which AWS does not require. The headers that a proxy or the user agent
may change after the signature, as `User-Agent` and `Expect`, are not signed,
as the SDKs of AWS leave them.

The path of the canonical request is the one that HTTP sends, already
percent-encoded, which `double_encode` encodes again, as every service but S3
wants. `t/aws-signing-test-suite` has the cases of the test suite of
aws-c-auth, kept as they are, under the Apache License 2.0 of their own, which
`biome.jsonc` leaves out. The suite sends a path with a space or UTF-8 as it
is, which HTTP cannot, so the test skips those cases, and the one of a
session token that is not signed, of AWS IoT, which `Pyjo.AWS.SigV4` does
not have.

## The Shared Files

`Pyjo.AWS.Config` reads `~/.aws/config` and `~/.aws/credentials` as botocore
does, which the AWS CLI is made of, as the reference of the format: the
`RawConfigParser` of `configparser`, whose names of the settings are in lower
case, so that `AWS_ACCESS_KEY_ID =` of a hand-written file of the credentials
works, and whose value of a setting without one on its line is the indented
lines below it, which `_subsection` turns into a `dict`, as `s3 =`. A section
that is not unique is merged, as `strict=False`, and `default_section` is a
name that no file has, so that a section `[DEFAULT]` is not the defaults of
the others. In the configuration file, a profile is `[profile name]` or
`[default]`, and `[profile default]` comes over `[default]`; a section of
another name is not a profile, as `[dev]`, which the file of the credentials
names so. The settings of the file of the credentials come over those of the
configuration file.

The endpoint of a service is the one that the SDKs of AWS resolve from the
environment and the profile, in their order: `AWS_ENDPOINT_URL_<SERVICE>`,
the section `services` of the profile, `AWS_ENDPOINT_URL`, and
`endpoint_url` of the profile. The key of a service is its ID, as
`SSO OIDC`, with `_` in the place of the spaces and the hyphens, in upper
case in the environment and in lower case in the section `services`.

## The Steps

`Pyjo.AWS.Steps` runs a coroutine that awaits a `Request`, a `Command` or
other `Steps`, whose `__await__` yields the operation itself, and gets the
result back, or the exception of its error thrown in. No event loop runs the
coroutine: `run` drives it with `send` and `throw`, blocking, with `start`
of the user agent and `subprocess.run`, and `run_p` non-blocking, with
`start_p` and `run_p` of `Pyjo.IOLoop.ChildProcess`, so that the code of a
provider of credentials and of a call of the client is written once for
both modes. A coroutine that an event loop runs would not do: a blocking
call cannot run the event loop that is running already, where a blocking
request of the user agent runs on an event loop of its own.

So the coroutine awaits nothing else, not a `Pyjo.Promise` and not a future
of asyncio, whose `__await__` yields what only an event loop knows, the
promise itself on the reactor of Pyjo and a future on the one of asyncio.
The driver closes the coroutine and raises a `TypeError`, which it does not
throw into the coroutine, where the `except` of the errors of a connection
would hide it.

A generator that yields the operations runs too, as Python drives both
alike: `Steps` has `__await__` and `__iter__` of the same generator, so that
`await` and `yield from` take the steps of either kind. The code of the
package is coroutines, as pyright knows the types of what `await` gives
back, which `yield` leaves as `Any`. `Steps` is generic in what the steps
return, and `Steps.new` of `Pyjo.Base` loses its parameter, so the package
calls the class itself, `Steps.Steps(...)`.

A `Request` names the user agent that starts it, or the one of `run` is
taken: the client signs its request in the event `start` of its own user
agent, which a provider of credentials with a user agent of its own would
not emit otherwise, and the request would go out unsigned, without an error.

## The Credentials

A provider of `Pyjo.AWS.Credentials.Provider` gets its credentials in
`fetch`, a coroutine of `Pyjo.AWS.Steps`, which awaits `start` and `run` of
the provider, and returns the credentials, so that the provider is written
once for `credentials` and `credentials_p`, and a provider that needs the
credentials of another, as a role those of its source, awaits its `steps`,
cached as its own. `fetch` may be a generator too.

The error of a connection, which `start_p` rejects with a string and `start`
leaves in `error` of the transaction without a `code`, is thrown into the
coroutine as one `Pyjo.Exception`, with the method and the URL, and so is a
program that cannot be run, so that a provider handles both modes alike. A
response with an error status is a transaction as any other: the provider
reads its status.

A provider returns `None` when it is not configured, as an environment
without its variables, and raises when it is configured and fails, as a
profile with an access key without its secret, which ends
`Pyjo.AWS.Credentials.Chain`, as the SDKs of AWS do, so that a broken profile
is not hidden by the credentials of the next provider. A provider keeps its
credentials until `refresh` seconds before their expiration, 5 minutes as
the SDK of JavaScript has it, and `credentials_p` gives the calls while it
gets them the same promise, so that a burst of requests gets them once.
`Pyjo.AWS.Credentials.Environment` never keeps them, as the environment may
change. `__repr__` of the credentials has no secret, as a log or a traceback
shows it.

A profile of the argument `profile` of `Pyjo.AWS.Config`, its
`explicit_profile`, takes the environment and the web identity of the
environment out of the providers of the chain, as `create_credential_resolver`
of botocore does for a profile of the session, as `--profile` of the AWS CLI:
a shell with `AWS_ACCESS_KEY_ID` of other credentials gets the ones of the
profile that a program names. `AWS_PROFILE` alone does not, as in botocore,
so that the keys of the environment come over the profile of the
environment. A program that takes the option `--profile`, as
`examples/s3.py`, gives it to `Pyjo.AWS.Config`, not to `AWS_PROFILE`.

## The Client

`Pyjo.AWS.Client` calls an API with a call of `Pyjo.AWS.Protocol`, an
object of the protocol, not a method of the client of each protocol: the
call builds the transaction for the endpoint and reads the result of its
response or the error, so that a protocol is a class that is tested and
replaced alone, and the client has `call`, `call_p` and `steps`, which a
provider of credentials awaits, as a role of STS does. Without the models of
the APIs, which the SDKs of AWS are generated from, the call takes the names
and the structure of the API as its documentation has them, and gives the
result as the response has it: the JSON, or a `Pyjo.DOM` of the XML, with
the semantics of XML, whose tags keep their case.

`Pyjo.AWS.Protocol` is generic in its result, as `Protocol.object[T]`, so
that `call` of a `Query` gives a `Pyjo.DOM` to pyright, and the others
`Any`.

The credentials are resolved before the transaction starts, of `steps` of
the provider, or of `credentials_p` in `call_p`, so that calls at once wait
for the same promise, which `steps` alone does not share. The request is
signed in the event `start` of the user agent of the client, as `Request`
names it, and of that transaction only, which unsubscribes itself: the
request is complete then, with its absolute URL, as a relative endpoint, of
the server of a test, is resolved to the server of the blocking or the
non-blocking requests only when it starts. `t/AWS_Client.py` uses a relative
endpoint for that reason, as `ua.server.url()` is the server of the
blocking requests, which the non-blocking ones never reach.

The endpoint is `endpoint` of the client, the one that `Pyjo.AWS.Config`
resolves of the ID of the service, or the regional one of its prefix,
`amazonaws.com.cn` in the regions `cn-`, as the partitions `aws` and
`aws-cn` have it; the others, as GovCloud, FIPS and dual-stack, take
`endpoint`. The three names of a service are its name in the signature, the
prefix of its endpoint and its ID, which are the same for most services,
and differ for SSO, `awsssoportal`, `portal.sso` and `SSO`. The signer of S3
signs the path as it is, with the hash of the body, as S3 wants.

## SSO

`Pyjo.AWS.Credentials.SSO` takes the token of `aws sso login` of the cache
of the AWS CLI, `~/.aws/sso/cache/<SHA-1>.json`, of the name of the section
`sso-session` or of the start URL of a legacy profile, as botocore names it,
and gets the credentials of the role with `GetRoleCredentials` of SSO,
unsigned, with the token in `X-Amz-Sso_bearer_token`. It does not log in:
the device authorization of a login needs a browser, which is the job of
the AWS CLI, so a missing or expired token is an error that tells to run
`aws sso login`.

The token of a section `sso-session` is refreshed with `CreateToken` of SSO
OIDC, `refresh` seconds before it expires, as the credentials are, and only
with the client of its registration that is not expired, as the AWS CLI
writes the client and the refresh token for those only; a legacy token is
not refreshed. A failed refresh keeps the old token while it is valid, as
the SDKs of AWS do, so that a failure of SSO OIDC does not end a session
before its time. The new token is written back to the same file, replaced
at once and readable by its owner only, as the AWS CLI shares it.

The endpoints are those of the IDs `SSO` and `SSO OIDC`, the prefixes
`portal.sso` and `oidc`, in the `sso_region` of the session, not the region
of the profile. `Pyjo.AWS.Credentials.Profile` takes SSO before the keys of
the profile, after the roles of the next steps, as botocore orders them.
The profile and the section must agree on `sso_start_url` and `sso_region`
where the profile has them too, which is an error otherwise, as in botocore.

`Pyjo.AWS.Client` imports `Pyjo.AWS.Credentials.Chain` in its constructor,
not at the top of the module, as the chain imports the profile, which
imports SSO, which imports the client.

`str` of a `Pyjo.Exception` ends with a new line, as `Mojo::Exception` does,
so a message that includes another exception takes its `message`.

## aws login

`Pyjo.AWS.Credentials.Login` takes the credentials of a session of the
console of `aws login`, of the cache of the AWS CLI,
`~/.aws/login/cache/<SHA-256>.json` of the `login_session` of the profile, or
of `AWS_LOGIN_CACHE_DIRECTORY`, as botocore names it, of `LoginProvider` of
`botocore/credentials.py`, which is the reference, as the API of the sign-in
service has no documentation of its own. The cache has the credentials, of 15
minutes, and the refresh token and the key of DPoP of the session, which the
fields of botocore require, all of them, even while the credentials are
valid.

The credentials are refreshed `refresh` seconds before they expire with
`CreateOAuth2Token` of the sign-in service, of the model `signin/2023-01-01`
of botocore: `POST /v1/token` of REST-JSON, unsigned, whose body is the
`tokenInput` and whose response is the `tokenOutput`, as their `payload`, on
`https://<region>.signin.aws.amazon.com`, of the region of the profile, as the
rules of the endpoints of the model have it for the operations that are not
of the control plane, or the one of the ID `Signin` that `Pyjo.AWS.Config`
resolves. The request has the header `DPoP`, of RFC 9449, a JWT of ES256 of
the key of the cache, with its public key, the method and the URL of the
request, the time and a UUID, as botocore makes it. The refreshed token is
written back to the same file, with the account and the other fields of the
cache, as SSO writes its token, of `write_cache` of
`Pyjo.AWS.Credentials.Provider`; a failed refresh keeps the old credentials
while they are valid. `TOKEN_EXPIRED` and `USER_CREDENTIALS_CHANGED` of the
field `error` of `AccessDeniedException` end the session, which tells to run
`aws login`.

`Pyjo.AWS.Credentials.Profile` takes `login_session` after the keys of the
profile and before `credential_process`, as botocore orders them, after SSO.

`Pyjo.AWS.ECDSA` signs ES256 with the package `cryptography` when it is
installed, of the extra `cryptography` of `pyproject.toml`, as botocore needs
`botocore[crt]`, and in Python otherwise, so that the distribution depends on
nothing but Pyjoyment. The package is imported with `importlib`, so that
pyright, without it in `.venv`, takes its modules as `Any`. The signature of
Python is of the affine coordinates of P-256 and of the nonce of RFC 6979,
deterministic, so that no random number of the machine makes it, and is not
constant-time: the key and the proof are made on the machine of the key, once
a refresh, which is not an oracle of a remote timing. It may move to a
distribution of its own, as Pyjo.Crypto, once something else needs it.

`t/AWS_ECDSA.py` checks the signature of Python with the vectors of RFC 6979,
A.2.5, both backends against each other, and the signatures with
`openssl dgst -verify`. `t/login-provider-test-cases` has the cases of
`tests/unit/login/login-provider-test-cases.json` of botocore, kept as they
are, under the Apache License 2.0 of their own, which `biome.jsonc` leaves out:
their key of DPoP is a key of the test, and their time of a refresh is the one
of the mock of botocore, so `t/AWS_Credentials_Login.py` checks the expiration
of `expiresIn` against the time of the test. Its sign-in service checks the
proof of each request as the service does, with the public key of its header.
The workflow Tests runs without `cryptography`, so its backend is checked with
`uv run --with cryptography` in development.

## Roles

A profile of `role_arn` is resolved as botocore resolves it, which comes
before its SSO, its keys and its `credential_process`: `source_profile` or
`credential_source`, both of which are an error, for `AssumeRole`, signed
with the credentials of the source, or `web_identity_token_file`, without
them, for `AssumeRoleWithWebIdentity`, unsigned. A source profile with keys
of its own gives those, without its role, and a source profile without them
is resolved with its role, whose cycle is an error; so a profile may be the
source of its own role, a common way of a role of the keys of the same
profile. `Pyjo.AWS.Credentials.Profile` keeps the profiles that lead to it in
`visited`, and `roles=False` makes it give the keys of a source profile.

`credential_source` takes the credentials of the environment, of the
container or of IMDS. `mfa_serial` is an error, as botocore prompts
for the code on the terminal, which a library of a server has not.

The region of STS is the one of the profile of the role, or of the shared
files, or `us-east-1`, whose regional endpoint is the global one, as the
regional endpoints of STS are the default of the SDKs of AWS now. The name of
the session is `role_session_name`, or `pyjo-aws-` and the time, as botocore
names it `botocore-session-` and the time.

`Pyjo.AWS.Credentials.WebIdentity` takes the role, the token file and the
name of the session of the environment, `AWS_ROLE_ARN`,
`AWS_WEB_IDENTITY_TOKEN_FILE` and `AWS_ROLE_SESSION_NAME`, only without
`role_arn` and `token_file`, so that a profile does not get the name of the
session of the environment. It reads the file at each fetch, as EKS rotates
the token. It comes after the environment and before the profile in
`Pyjo.AWS.Credentials.Chain`, as the order of the SDKs of AWS of the
Reference Guide has it.

The credentials of a role are kept by the provider of the profile, and the
credentials of the source by the provider of the source, which is a new one
at each fetch of the role, as the role is got again only when its
credentials expire.

## The Container and the Instance Metadata

`Pyjo.AWS.Credentials.Container` and `Pyjo.AWS.Credentials.InstanceMetadata`
have user agents of their own, with short timeouts, 2 seconds and 3
attempts of the container, as botocore has them, and 1 second and 1 attempt
of IMDS, of `metadata_service_timeout` and `metadata_service_num_attempts`.
They keep no connections, `max_connections=0`, as the credentials come once
an hour: a connection kept by a chain, which lives as long as its client,
would be a socket open to the agent or IMDS, and `__del__` of
`Pyjo.UserAgent` does not close it at the exit of the interpreter, which
`ResourceWarning` of the workflow Tests reports.
`Pyjo.AWS.Credentials.Chain` does not give them its user agent, which is the
one of the client, of the timeouts of `Pyjo.UserAgent`: a machine that is
not an instance of EC2 has nothing on `169.254.169.254`, where a request
would wait for the connect timeout of the client, at each call without
credentials.

A full URI of the container of HTTP is one of an agent of ECS or EKS Pod
Identity or of the loopback, as the SDKs of AWS allow it, so that a variable
of the environment does not send the token of the container to another
host. The token file comes over the token and is read at each fetch, as EKS
rotates it. An error of the agent of 5xx and of the connection is tried
again, one of 4xx is not.

IMDS without an answer, as of a machine that is not EC2, or without a role,
has no credentials, as the SDKs of AWS have it, so that the chain ends
without them, and the token of IMDSv2 that is forbidden falls back to IMDSv1,
unless `AWS_EC2_METADATA_V1_DISABLED`; the credentials of a role that the
service does not give are an error. The extended credentials of IMDS, with
the account, and the static stability of expired credentials are left out.

The tests set `AWS_EC2_METADATA_DISABLED=true` in their environment, as a
runner of GitHub Actions has the IMDS of Azure on `169.254.169.254`.
`t/AWS_Credentials_Metadata.py` serves the agent of the container, IMDS and
STS with an application of Pyjoyment.Lite in a process of its own, of a
script that the test writes, as a server of a user agent of the test is not
reached by the user agents of the providers, and a server in a thread is
not either, as the event loops of Pyjo are not safe in threads; the
endpoints are those of the environment, as in production.

## The Examples

`examples/` has the scripts that show what the distribution is for, a few
calls of AWS with the credentials of any kind that the AWS CLI finds, as
`examples/` of Pyjoyment has them, and `docs/examples.rst` includes them.
`examples/s3.py` is the counterpart of `examples/aws/s3.py` of Pyjoyment,
which serves a bucket with aiobotocore: the same application, with
`Pyjo.AWS.Client` and no SDK.

The content of an object goes to the client as it comes, of `GetObject`, a
subclass of `Pyjo.AWS.Protocol.RestXML` in the example, whose transaction
forwards the chunks of a response of `200` in the event `read` of its
content, each one once the client has read the one before, as the helper
`proxy.start_p` of Pyjoyment does, and whose result is `None`, so that the
body is not kept; the error of S3, as `NoSuchKey`, is read as for any call.
`proxy.start_p` itself does not do, as it starts the transaction with the
user agent of the application, and the request of a client is signed and
started by the client. A client that goes away before the end of the object
closes the connection to S3, whose error the action ignores.

The event `read` comes with an empty chunk too, when the headers come in a
read of their own, as S3 sends them in a record of TLS of their own, which
the example skips, as `proxy.start_p` does: `write` of an empty chunk ends
the response, with the headers only, and the client waits for the rest of
the object until the server closes the connection.

The example has a client of S3 for each thread, as each thread has an event
loop of its own, whose connections the user agent of the client keeps, and
the bucket in the path of the endpoint, as S3 and the servers of its API, as
MinIO, serve it.

`t/examples/s3.py` runs the example and S3 of its own in processes of
their own, as `t/AWS_Credentials_Metadata.py` runs its server, with the key of
a profile of the files of the test, whose signature S3 checks with
`Pyjo.AWS.SigV4` of the request as it comes, before the router reads its
path. S3 does not compress its responses, as Pyjoyment does for a user agent
that accepts gzip, so that the large object comes in chunks, and a client
that goes away before its end is the case of the closed connection. The
content of `slow.txt` comes after its headers, as of S3 over TLS, whose empty
chunk a server on the loopback without TLS does not send otherwise.

## Imports of the Package

The modules of the distribution import the package and each other relatively,
`from .. import AWS` and `from . import SigV4`, not as `import Pyjo.AWS.SigV4`:
pyright takes `Pyjo` for the regular package of Pyjoyment in `.venv`, which
hides the namespace that `extend_path` keeps open, so it does not find
`Pyjo.AWS` of the checkout. The tests and the documentation import them as
`Pyjo.AWS.SigV4`, which Python finds through `extend_path`.

The package and the tests take what Pyjoyment has, as the distribution
depends on it already: the hashes, HMAC and Base64 of `Pyjo.Util`, as
`sha256_sum`, `hmac_sha256_bytes` of the keys of SigV4 and of the nonce of
RFC 6979, and `b64url_encode`, and the times of `Pyjo.Date`, of RFC 3339 and
of the format of `X-Amz-Date`, `f'{date:%Y%m%dT%H%M%SZ}'`, and the paths of
`Pyjo.File`, of the shared files and the caches, with `expanduser` and
`child`, not `hashlib`, `hmac`, `base64`, the formats of `datetime` and
`os.path`, but `os.path.expandvars` of `AWS_LOGIN_CACHE_DIRECTORY`, which
`Pyjo.File` does not have.

## Security

The files of secrets of Pyjoyment are git-ignored in `.gitignore` and denied
to Claude Code in `.claude/settings.json`, and so are the credentials of the
machine, `~/.aws/credentials` and the caches of the tokens of SSO, of the
sessions of `aws login`, with their keys of DPoP, and of the roles of the AWS
CLI, `~/.aws/sso/cache`, `~/.aws/login/cache` and `~/.aws/cli/cache`. A test
never reads the files of the machine: it sets `AWS_CONFIG_FILE`,
`AWS_SHARED_CREDENTIALS_FILE`, `AWS_LOGIN_CACHE_DIRECTORY` and `HOME` to files
of its own, with keys of the examples of AWS, as `AKIDEXAMPLE`, and serves the
endpoints of AWS that it needs with an application of Pyjoyment.

## Development

The distribution depends on the release of Pyjoyment on PyPI, with the lowest
version that has what it uses, which `uv.lock` pins. A change of Pyjoyment that
is not released yet would be its Git repository in `[tool.uv.sources]` of
`pyproject.toml`, until its release, and not a path to the checkout next to
this one: uv applies the sources of a dependency of Git, so whoever installs
the distribution from Git would get a subdirectory of this repository that
does not exist. The lowest version is then the one of Git, as `0.2.1.dev1`,
which PyPI does not have, so that an installation of PyPI fails to resolve it
rather than to import what the release has not, and the workflow Build
installs the wheel with the Pyjoyment of `uv.lock`, of `uv export`, as the
wheel does not name the source. The tests lay the checkout next to this one over it with
`--with-editable`, so that they test what is there:

```sh
mise exec -- uv sync
mise exec -- uv run --with-editable ../Pyjoyment python -m Pyjo.Prove -l -r t
```

Perl's `prove` runs them too, with `.proverc`, under `uv run`, whose `python`
is the one of the environment, where Pyjoyment and the distribution are
installed, so that it needs no `PYTHONPATH`, unlike in Pyjoyment:

```sh
mise exec -- uv run --with-editable ../Pyjoyment prove -r t
```

The package is in the namespace `Pyjo` of Pyjoyment, which `extend_path` keeps
open, but it changes nothing of Pyjoyment, so the suite of Pyjoyment is not
run with it installed, unlike the one of a distribution of a reactor, which
runs on the reactor. What the distribution could break is the namespace, with
an `__init__.py` of `Pyjo` of its own, which the workflow Build checks.

The workflow Tests runs the tests of the distribution against the release of
`uv.lock`, without `--with-editable`, so that a pull request tests what an
installation gets. A dispatch with `pyjoyment-ref` lays a checkout of the ref
over it, as in development, so that what the next release of Pyjoyment breaks
is known before the release.

Trunk checks the files with the linters of Pyjoyment, from `.trunk/trunk.yaml`:

```sh
trunk check --all
```

actionlint is the one of the maintained fork kjanat/actionlint, whose releases
continue those of rhysd/actionlint after 1.7.12, as in Pyjoyment: `downloads`
in `.trunk/trunk.yaml` replaces the URLs of the plugin with those of the fork,
whose files have the same names.

Biome formats and lints JSON, Markdown and YAML, with `biome.jsonc`, in the
place of prettier, markdownlint and yamlfmt, as in Pyjoyment, and yamllint
checks what Biome does not, as the duplicated keys. The version of Biome is
the pinned one of `.trunk/trunk.yaml`, where `!` keeps it from
`trunk upgrade`, and which Renovate bumps, as in the repositories of
freelensapp: the repository has no `package.json` of its own. Renovate cannot
run `biome migrate`, so the workflow Biome Migrate runs it with
`npx --yes @biomejs/biome@<version>` of that version, migrates `biome.jsonc` on
the branch of Renovate and commits it with the token of the workflow, as the
author that `gitIgnoredAuthors` of `.renovaterc.json` names, so that Renovate
keeps updating the branch, and starts the checks of the commit with
`workflow_dispatch`; anywhere else, a `biome.jsonc` that this Biome would
migrate fails the check. The definition of Biome in `.trunk/trunk.yaml` is
the one of Pyjoyment, which explains why it is not the one of the plugin of
Trunk.

Its pyright needs the environment of `uv sync`, `.venv`, which `tool.pyright` of
`pyproject.toml` names, as the package imports Pyjoyment; Trunk Check of CI
runs `uv sync` first. The tests and `docs/conf.py` are not checked by pyright:
for them it takes the regular package `Pyjo` of Pyjoyment, which hides
`Pyjo.AWS` of the checkout.

The wheel has only the package `Pyjo.AWS` (`only-include` of hatchling), not
the `__init__.py` of `Pyjo`, which is the one of Pyjoyment; the workflow Build
checks it.

The documentation is on Read the Docs, a subproject of the one of Pyjoyment:
the docstrings of the package, which autodoc imports, as in Pyjoyment. Read the
Docs installs it with `uv sync` of `uv.lock` and the group `docs`, not with pip
and a `docs/requirements.txt` as Pyjoyment does, so that it builds with the
versions of the lock, as the workflow Docs does. The links to the
modules of Pyjoyment come from intersphinx. The workflow Docs builds it with
`-W`, as Read the Docs does, with the Pyjoyment of `uv.lock`:

```sh
mise exec -- uv run --group docs --with-editable ../Pyjoyment sphinx-build -W --keep-going -b html docs docs/_build/html
```

The workflow Tests ends with the job `Tests`, the one check of it that the
ruleset of `main` requires, as in Pyjoyment: it fails when a job of the
matrix failed or was cancelled, so a new version of Python needs no change of
the ruleset.

## Releases

The releases are those of Pyjoyment, with its workflows: a release is a tag of
the version of `pyproject.toml`, without a `v`, as `0.1.0`, which Automated
version sets with `uv version`, the components of its `--bump` from a list, as
`patch dev` or `minor rc`, or the version of `manual`, in the pull request of
the branch `automated/version`. After a release, a pre-release goes with the
release that it comes before, as PEP 440 orders `0.2.0.dev1` before `0.2.0`,
so `dev` alone after `0.2.0` fails. Automated tag tags the merge commit of that pull
request when it is merged, or with a comment `/tag` of a maintainer on it, and
starts Release on the tag. A development version, as `0.1.1.dev1`, is not
tagged. The version is static in `pyproject.toml`, as `uv version` cannot set a
dynamic one, and `__version__` of the package reads it from the metadata of
the distribution.

Release builds the sdist and the wheel, attests their build provenance with
`actions/attest`, and makes a draft of the GitHub release with them, whose
notes are rewritten before it is published, and an SBOM in SPDX, attested
with them. The package bundles nothing, unlike the one of Pyjoyment, whose SBOM
lists the JavaScript libraries of its package, so the SBOM is what an
installation of the wheel gets: the distribution and its dependencies at the
versions of `uv.lock`, installed in a virtual environment of their own, which
Syft scans. Syft on `uv.lock` itself would take its dependency groups too, as
Sphinx, which an installation does not get. The sdist does not
carry the SBOM, as the one of Pyjoyment does, as it is made of the wheel,
which is built after the sdist.

The workflow PyPI, run manually, publishes the files of the latest published
release, or of the release of the tag of its input, on PyPI once their
attestations of Release verify, in the environment `publishing`, which waits
for an approval and takes `main` and tags only. The trusted publisher of PyPI
names `pypi.yaml` and that environment.

```sh
gh attestation verify pyjo_aws-0.1.0.tar.gz -R pyjoyment/Pyjo-AWS
```
