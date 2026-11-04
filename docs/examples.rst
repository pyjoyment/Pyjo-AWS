Examples
========

The scripts of the directory ``examples`` of the repository, with the
credentials that the AWS CLI finds, of any kind, as
:mod:`Pyjo.AWS.Credentials.Chain` finds them.


Amazon S3
---------

A bucket of Amazon S3 as a website, with :mod:`Pyjo.AWS.Client` and the
calls of :mod:`Pyjo.AWS.Protocol.RestXML`, whose requests the actions await in
the event loop of the server, without an SDK of AWS: the content of an object,
as it comes, of a call whose protocol forwards it to the client, ``index.html``
of a folder, or the list of its folders and objects. ::

    uv run python examples/s3.py --profile myprofile --bucket mybucket daemon

.. include:: ../examples/s3.py
   :code: python
