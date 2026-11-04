"""
__DATA__

@@ folder.html.ep
<!DOCTYPE html>
<html>
  <head><title>/<%= prefix %></title></head>
  <body>
    <h1>/<%= prefix %></h1>
    <ul>
      % if prefix:
      <li><a href="../">../</a></li>
      % end
      % for name in names:
      <li><a href="<%= url_for('object', key=prefix + name) %>"><%= name %></a></li>
      % end
    </ul>
  </body>
</html>
"""

import Pyjo.AWS.Client
import Pyjo.AWS.Error
import Pyjo.AWS.Protocol.RestXML
import Pyjo.Exception
import Pyjo.GetOpt
import Pyjo.IOLoop

from Pyjo.Util import die, getopt, url_escape
from Pyjoyment.Lite import *

import os
import threading


# The options before the command, with the names of the AWS CLI, which set the environment variables that the
# application and Pyjo.AWS read: python s3.py --profile myprofile --bucket mybucket daemon
getopt(
    {
        'bucket=s': Pyjo.GetOpt.env('S3_BUCKET'),
        'endpoint-url=s': Pyjo.GetOpt.env('AWS_ENDPOINT_URL'),
        'profile=s': Pyjo.GetOpt.env('AWS_PROFILE'),
        'region=s': Pyjo.GetOpt.env('AWS_REGION'),
    },
    pass_through=True,
    require_order=True,
)

# The bucket, whose objects the application serves, in the path of the endpoint, as S3 and the servers of its API, as
# MinIO, serve it
bucket = os.environ.get('S3_BUCKET') or die(
    'Usage: s3.py --bucket BUCKET [--profile PROFILE] [--region REGION] [--endpoint-url URL] COMMAND [OPTIONS]'
)
root = '/' + url_escape(bucket)

# A client of S3 for each event loop, as the connections of its user agent belong to one, with the region, the endpoint
# and the credentials that the AWS CLI finds: of the environment, of a profile with its keys, SSO, aws login, a role
# or credential_process, of a web identity, of the container of ECS or EKS Pod Identity, or of the instance of EC2
local = threading.local()


def s3():
    if not hasattr(local, 's3'):
        local.s3 = Pyjo.AWS.Client.new(service='s3')
    return local.s3


# The client closes its connections once the server stops
@hook('after_server_stop')
def after_server_stop(server, app):
    if hasattr(local, 's3'):
        local.s3.ua.close()
        del local.s3


# The path of a key, percent-encoded but its slashes, as S3 signs it
def path(key):
    return root + '/' + url_escape(key, r'^A-Za-z0-9\-._~/')


def list_objects(prefix, **query):
    return Pyjo.AWS.Protocol.RestXML.new('GET', root, query={'list-type': 2, 'prefix': prefix, **query})


# The headers of an object that the response has, as S3 gives them
HEADERS = (
    'Cache-Control',
    'Content-Disposition',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Type',
    'ETag',
    'Last-Modified',
)


# GetObject, whose content goes to the client as it comes, each chunk once the client has read the one before, so that
# an object of any size is not kept in memory; the error of S3, as NoSuchKey, is its XML, which the call reads
class GetObject(Pyjo.AWS.Protocol.RestXML.object):
    def __init__(self, c, key):
        super().__init__('GET', path(key))
        self.c = c
        self.gone = False

    def build_tx(self, ua, url):
        tx = super().build_tx(ua, url)
        tx.res.content.set(auto_upgrade=False, auto_decompress=False).once('body', lambda content: self.forward(tx))
        return tx

    def forward(self, tx):
        if tx.res.code != 200:
            return
        c, res = self.c, tx.res
        for name in HEADERS:
            if (value := res.headers.header(name)) is not None:
                c.res.headers.header(name, value)
        if res.headers.content_length == '0':
            return c.rendered()

        source = Pyjo.IOLoop.stream(tx.connection)

        # The content emits an empty chunk too, of the end of the headers that come before it, as S3 sends them in
        # records of TLS of their own, which would end the response
        def read(content, chunk):
            if not chunk:
                return
            source.stop()
            c.write(chunk, lambda c: source.start())

        res.content.unsubscribe('read').on('read', read)

        # A client that goes away before the end of the object closes the connection to S3, which reads no more
        def finish(c):
            if not res.is_finished:
                self.gone = True
                Pyjo.IOLoop.remove(tx.connection)

        c.on('finish', finish)

    def parse(self, tx):
        return None


async def send_object(c, key):
    call = GetObject(c, key)
    try:
        await s3().call_p(call)
    except Pyjo.Exception.object:
        if not call.gone:
            raise


# The folders and the objects under a prefix, of the pages of ListObjectsV2, as S3 has no folders, only keys with
# slashes, and a folder that the console of S3 makes, an empty object of the prefix, which the list leaves out
async def send_folder(c, prefix):
    names, count, token = [], 0, None
    while True:
        dom = await s3().call_p(list_objects(prefix, delimiter='/', **{'continuation-token': token}))
        count += int(dom.at('KeyCount').text)
        names += [e.text.removeprefix(prefix) for e in dom.find('CommonPrefixes > Prefix')]
        names += [e.text.removeprefix(prefix) for e in dom.find('Contents > Key') if e.text != prefix]
        if (next_token := dom.at('NextContinuationToken')) is None:
            break
        token = next_token.text
    if prefix and not count:
        return c.reply.not_found()
    c.render('folder', prefix=prefix, names=sorted(names))


def not_found(e):
    return e.code in ('NoSuchKey', '404')


# An object, "index.html" or the list of a folder, for a key that ends with a slash
@get('/*key', {'key': ''}, 'object')
async def serve(c):
    key = c.param('key')
    if key and not key.endswith('/'):
        try:
            return await send_object(c, key)
        except Pyjo.AWS.Error.object as e:
            if not not_found(e):
                raise

        # A folder without its slash
        dom = await s3().call_p(list_objects(f'{key}/', **{'max-keys': 1}))
        if int(dom.at('KeyCount').text):
            return c.redirect_to('object', key=f'{key}/')
        return c.reply.not_found()

    try:
        await send_object(c, f'{key}index.html')
    except Pyjo.AWS.Error.object as e:
        if not not_found(e):
            raise
        await send_folder(c, key)


app.start()
