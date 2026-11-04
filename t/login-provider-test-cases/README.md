# Login Provider Test Cases

The cases of the provider of the credentials of `aws login`, from
`tests/unit/login/login-provider-test-cases.json` of
[boto/botocore](https://github.com/boto/botocore) at the commit
`2fb7e3f4c10a133dcba2606c96550df56100c2f7`. They are under the Apache License 2.0 of `LICENSE`, with the
`NOTICE` of botocore, and are kept as they are.

Each case has the configuration file, `configContents`, the files of the cache
of the sessions, `cacheContents`, the calls of the sign-in service that it
expects, `mockApiCalls`, and its outcomes, the credentials, the cache after
them or an error.
