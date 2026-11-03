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

`Pyjo.DOM` of Pyjoyment 0.2.0 annotates its arguments of CSS and HTML as
`object`, which is its alias of `Pyjo_DOM` in that module, so pyright strict
rejects a string there: `_dom` of `Pyjo.AWS.Protocol` casts it to `Any`,
until a release of Pyjoyment fixes it
([pyjoyment/Pyjoyment#498](https://github.com/pyjoyment/Pyjoyment/issues/498)).

## Imports of the Package

The modules of the distribution import the package and each other relatively,
`from .. import AWS` and `from . import SigV4`, not as `import Pyjo.AWS.SigV4`:
pyright takes `Pyjo` for the regular package of Pyjoyment in `.venv`, which
hides the namespace that `extend_path` keeps open, so it does not find
`Pyjo.AWS` of the checkout. The tests and the documentation import them as
`Pyjo.AWS.SigV4`, which Python finds through `extend_path`.

## Security

The files of secrets of Pyjoyment are git-ignored in `.gitignore` and denied
to Claude Code in `.claude/settings.json`, and so are the credentials of the
machine, `~/.aws/credentials` and the caches of the tokens of SSO and of the
roles of the AWS CLI, `~/.aws/sso/cache` and `~/.aws/cli/cache`. A test never
reads the files of the machine: it sets `AWS_CONFIG_FILE`,
`AWS_SHARED_CREDENTIALS_FILE` and `HOME` to files of its own, with keys of
the examples of AWS, as `AKIDEXAMPLE`, and serves the endpoints of AWS that it
needs with an application of Pyjoyment.

## Development

The distribution depends on the release of Pyjoyment on PyPI, with the lowest
version that has what it uses, which `uv.lock` pins. A change of Pyjoyment that
is not released yet would be its Git repository in `[tool.uv.sources]` of
`pyproject.toml`, until its release, and not a path to the checkout next to
this one: uv applies the sources of a dependency of Git, so whoever installs
the distribution from Git would get a subdirectory of this repository that
does not exist. The tests lay the checkout next to this one over it with
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
