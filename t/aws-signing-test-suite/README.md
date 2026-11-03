# AWS Signing Test Suite

The cases of Signature Version 4 in the header `Authorization`, from
`tests/aws-signing-test-suite/v4` of
[awslabs/aws-c-auth](https://github.com/awslabs/aws-c-auth) at the commit
`e86db3ac3274b8ec514c09e68adc2ac7ead0d184`, without the files of the signatures
in the query string. They are under the Apache License 2.0 of `LICENSE`, with the
`NOTICE` of aws-c-auth, and are kept as they are.

Each case has its request, `request.txt`, the options of the signer,
`context.json`, and what it signs to: `header-canonical-request.txt`,
`header-string-to-sign.txt`, `header-signature.txt` and
`header-signed-request.txt`.
