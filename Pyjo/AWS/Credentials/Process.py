"""
Pyjo.AWS.Credentials.Process - Credentials of an external program
=================================================================
::

    from Pyjo.AWS.Credentials.Process import Process

    credentials = Process(command='aws configure export-credentials --profile dev').credentials()

    # Or import the module, as in Google Python Style Guide

    import Pyjo.AWS.Credentials.Process

    provider = Pyjo.AWS.Credentials.Process.new(command='/opt/bin/credentials --role admin')
    provider.credentials_p().then(lambda credentials: print(credentials.expiration)).wait()

:mod:`Pyjo.AWS.Credentials.Process` is the provider of the credentials that
an external program prints, as the setting ``credential_process`` of a
profile runs it: the command is split as a shell splits it, but run without
a shell, and prints the credentials as JSON: ::

    {
      "Version": 1,
      "AccessKeyId": "AKIDEXAMPLE",
      "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY",
      "SessionToken": "token",
      "Expiration": "2026-11-03T12:00:00Z"
    }

A program that exits with an error, or prints something else, is an error,
with what the program prints on its standard error.

See also
--------

:mod:`Pyjo.AWS.Credentials.Provider`, :mod:`Pyjo.AWS.Credentials.Profile`,
https://docs.aws.amazon.com/sdkref/latest/guide/feature-process-credentials.html.

Classes
-------
"""

import Pyjo.Exception
import Pyjo.JSON

from .. import Credentials
from . import Provider

import shlex

from typing import Any, cast


class Pyjo_AWS_Credentials_Process(Provider.object):
    """
    :mod:`Pyjo.AWS.Credentials.Process` inherits all attributes and methods
    from :mod:`Pyjo.AWS.Credentials.Provider` and implements the following
    new ones.
    """

    def __init__(self, *, command: str, **kwargs: Any) -> None:
        """::

            provider = Pyjo.AWS.Credentials.Process.new(command='/opt/bin/credentials')

        Construct a new :mod:`Pyjo.AWS.Credentials.Process` object, with the
        options of :mod:`Pyjo.AWS.Credentials.Provider`.
        """
        super().__init__(**kwargs)

        self.command = command
        """::

            command = provider.command
            provider.command = '/opt/bin/credentials --role admin'

        The command of the program, with its arguments.
        """

    async def fetch(self) -> Credentials.object | None:
        """::

            credentials = await provider.fetch()

        The credentials that the program prints.
        """
        args = shlex.split(self.command)
        if not args:
            raise Pyjo.Exception.new('Empty credential_process of AWS')
        code, out, err = await self.run(args)
        name = args[0]
        if code != 0:
            message = err.decode(errors='replace').strip()
            raise Pyjo.Exception.new(f'credential_process {name} failed with {code}: {message}')
        try:
            data = Pyjo.JSON.decode_json(out)
        except Exception as e:
            raise Pyjo.Exception.new(f'credential_process {name} printed no JSON: {e}') from e
        if not isinstance(data, dict):
            raise Pyjo.Exception.new(f'credential_process {name} printed no JSON object')
        fields = cast(dict[str, Any], data)
        if fields.get('Version') != 1:
            raise Pyjo.Exception.new(
                f'credential_process {name} printed an unsupported Version: {fields.get("Version")}'
            )
        for field in ('AccessKeyId', 'SecretAccessKey'):
            if not isinstance(fields.get(field), str) or not fields[field]:
                raise Pyjo.Exception.new(f'credential_process {name} printed no {field}')
        expiration = fields.get('Expiration')
        return Credentials.new(
            access_key_id=fields['AccessKeyId'],
            secret_access_key=fields['SecretAccessKey'],
            session_token=fields.get('SessionToken') or None,
            expiration=Credentials.parse_time(expiration) if isinstance(expiration, str) and expiration else None,
            account_id=fields.get('AccountId') or None,
            provider='process',
        )


new = Pyjo_AWS_Credentials_Process.new
object = Pyjo_AWS_Credentials_Process
Process = Pyjo_AWS_Credentials_Process
