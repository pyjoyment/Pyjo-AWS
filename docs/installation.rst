Installation
============

Pyjo-AWS is installed from `PyPI <https://pypi.org/project/Pyjo-AWS/>`_, with
:doc:`Pyjoyment <pyjoyment:installation>`, which it depends on: ::

    pip install Pyjo-AWS

or, in a project managed with `uv <https://docs.astral.sh/uv/>`_: ::

    uv add Pyjo-AWS

The credentials of ``aws login`` are refreshed with a signature of ECDSA,
which the package ``cryptography`` makes, of the extra ``cryptography``, or
Python itself without it: ::

    pip install 'Pyjo-AWS[cryptography]'

The development version is installed from the Git repository with uv, which
takes the version of Pyjoyment that it needs from Git too, before its
release: ::

    uv pip install git+https://github.com/pyjoyment/Pyjo-AWS
