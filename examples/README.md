# Examples

Short scripts that show what Pyjo-AWS does, with the credentials that the AWS
CLI finds, of any kind: the environment, a profile with its keys, SSO, a role
or `credential_process`, a web identity, the container of ECS or EKS Pod
Identity, or the instance of EC2.

## Layout

| Directory | What it holds                                              |
| --------- | ---------------------------------------------------------- |
| `aws/`    | applications of `Pyjoyment.Lite` that call the APIs of AWS |

## Running

Run the scripts from the root of the repository with `uv run`, which runs them
with Pyjo-AWS of the checkout, and without an SDK of AWS.

The application of `aws/s3.py` serves a bucket of S3 as a website: the content
of an object, as it comes, `index.html` of a folder, or the list of its
folders and objects. Its options before the command have the names of the AWS
CLI, `--bucket`, `--profile`, `--region` and `--endpoint-url`, or the
environment variables `S3_BUCKET`, `AWS_PROFILE`, `AWS_REGION` and
`AWS_ENDPOINT_URL` in their place:

```sh
uv run python examples/aws/s3.py --profile myprofile --bucket mybucket daemon
```

A profile of SSO needs a token of `aws sso login --profile myprofile` first.

The tests in [`t/examples/`](../t/examples), in the same groups, check the
scripts, and the documentation shows them on its page of examples.
