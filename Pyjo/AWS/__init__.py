"""
Pyjo.AWS - Amazon Web Services for Pyjoyment
============================================
::

    import Pyjo.AWS.Client
    import Pyjo.AWS.Protocol.Query
    import Pyjo.AWS.Protocol.RestJSON

    sts = Pyjo.AWS.Client.new(service='sts')
    print(sts.call(Pyjo.AWS.Protocol.Query.new('GetCallerIdentity', version='2011-06-15')).at('Arn').text)

    lambda_ = Pyjo.AWS.Client.new(service='lambda', region='eu-central-1')
    print(lambda_.call(Pyjo.AWS.Protocol.RestJSON.new('GET', '/2018-10-31/layers'))['Layers'])

:mod:`Pyjo.AWS` is the namespace of the APIs of Amazon Web Services for
:mod:`Pyjoyment`, which :mod:`Pyjo.UserAgent` calls, without an SDK:
:mod:`Pyjo.AWS.Client` calls them, blocking and non-blocking, with the
protocols of :mod:`Pyjo.AWS.Protocol`, :mod:`Pyjo.AWS.SigV4` signs its
requests, with the credentials of
:mod:`Pyjo.AWS.Credentials`, which :mod:`Pyjo.AWS.Credentials.Chain` finds as
the SDKs of AWS do, and :mod:`Pyjo.AWS.Config` reads the shared configuration
files of AWS.

It is for a program that needs a few calls of AWS and no dependency for them,
not a replacement of the SDKs of AWS, which have every API.

See also
--------

:mod:`Pyjo.AWS.Client`, :mod:`Pyjo.AWS.SigV4`, :mod:`Pyjo.AWS.Credentials`,
:mod:`Pyjo.AWS.Config`, :mod:`Pyjo.UserAgent`, :mod:`Pyjoyment`, https://github.com/pyjoyment/Pyjoyment.
"""

import importlib.metadata


__version__ = importlib.metadata.version('Pyjo-AWS')
"""The version of the distribution, of its metadata, which the workflow Automated version sets in pyproject.toml."""
