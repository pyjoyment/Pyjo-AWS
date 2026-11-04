# Examples

Short scripts that show what Pyjo-AWS does, with the credentials that the AWS
CLI finds, of any kind: the environment, a profile with its keys, SSO, a
session of `aws login`, a role or `credential_process`, a web identity, the
container of ECS or EKS Pod Identity, or the instance of EC2.

## Layout

| Script  | What it does                                                         |
| ------- | -------------------------------------------------------------------- |
| `s3.py` | serves a bucket of S3 as a website, an application of Pyjoyment.Lite |

## Running

Run the scripts from the root of the repository with `uv run`, which runs them
with Pyjo-AWS of the checkout, and without an SDK of AWS.

The application of `s3.py` serves a bucket of S3 as a website: the content
of an object, as it comes, `index.html` of a folder, or the list of its
folders and objects. Its options before the command have the names of the AWS
CLI, `--bucket`, `--profile`, `--region` and `--endpoint-url`, or the
environment variables `S3_BUCKET`, `AWS_PROFILE`, `AWS_REGION` and
`AWS_ENDPOINT_URL` in their place:

```sh
uv run python examples/s3.py --profile myprofile --bucket mybucket daemon
```

The profile of `--profile` comes over the keys of `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` of the environment, as the option `--profile` of the
AWS CLI does, and the one of `AWS_PROFILE` does not.

A profile of SSO needs a token of `aws sso login --profile myprofile` first,
and a profile of a session of the console `aws login --profile myprofile`.

The tests in [`t/examples/`](../t/examples) check the scripts, and the
documentation shows them on its page of examples.
