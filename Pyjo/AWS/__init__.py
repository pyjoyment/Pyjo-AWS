"""
Pyjo.AWS - Amazon Web Services for Pyjoyment
============================================
::

    import Pyjo.AWS.SigV4
    import Pyjo.UserAgent

    signer = Pyjo.AWS.SigV4.new(service='lambda', region='eu-central-1')
    ua = Pyjo.UserAgent.new()
    ua.on('start', lambda ua, tx: signer.sign(tx.req))
    print(ua.get('https://lambda.eu-central-1.amazonaws.com/2018-10-31/layers').result.json())

:mod:`Pyjo.AWS` is the namespace of the APIs of Amazon Web Services for
:mod:`Pyjoyment`, which :mod:`Pyjo.UserAgent` calls, without an SDK:
:mod:`Pyjo.AWS.SigV4` signs its requests.

It is for a program that needs a few calls of AWS and no dependency for them,
not a replacement of the SDKs of AWS, which have every API.

See also
--------

:mod:`Pyjo.AWS.SigV4`, :mod:`Pyjo.UserAgent`, :mod:`Pyjoyment`,
https://github.com/pyjoyment/Pyjoyment.
"""

import importlib.metadata


__version__ = importlib.metadata.version('Pyjo-AWS')
"""The version of the distribution, of its metadata, which the workflow Automated version sets in pyproject.toml."""
