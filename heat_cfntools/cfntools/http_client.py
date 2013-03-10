# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import httplib
import logging
import urlparse

logger = logging.getLogger(__name__)
USER_AGENT = 'heat-cfntools'
CHUNKSIZE = 1024 * 64  # 64kB


def http_request(method, url, body=None, headers={}):
    """ Send an http request with the specified characteristics.

    Wrapper around httplib.HTTP(S)Connection.request to handle tasks such
    as setting headers and error handling.
    """
    parts = urlparse.urlparse(url)

    if parts.scheme == 'https':
        conn_class = httplib.HTTPSConnection
    elif parts.scheme == 'http':
        conn_class = httplib.HTTPConnection

    headers.setdefault('User-Agent', USER_AGENT)
    headers.setdefault('Accept', '*/*')

    logger.debug(
        _curl_request(method, url, body, headers))
    conn = conn_class(
        host=parts.hostname,
        port=parts.port)

    path = urlparse.urlunparse((
        None, None, parts.path, parts.params, parts.query, None))
    conn.request(method, path, body, headers)
    resp = conn.getresponse()

    body_iter = ResponseBodyIterator(resp)
    body_str = ''.join([chunk for chunk in body_iter])

    logger.debug(_log_http_response(resp, body_str))

    if 400 <= resp.status < 600:
        raise HTTPException(resp.reason, resp.status)
    elif resp.status in (301, 302, 305):
        # Redirected. Reissue the request to the new location.
        location = resp.getheader('location', None)
        return http_request(method, location, body, headers)
    elif resp.status == 300:
        raise HTTPException(resp.reason, resp.status)

    return resp, body_str


def _curl_request(method, url, body, headers):
    curl = ['curl -i -X %s' % method]

    for (key, value) in headers.items():
        header = '-H \'%s: %s\'' % (key, value)
        curl.append(header)

    if body:
        curl.append('-d \'%s\'' % body)

    curl.append('"%s"' % url)
    return ' '.join(curl)


def _log_http_response(resp, body=None):
    status = (resp.version / 10.0, resp.status, resp.reason)
    dump = ['\nHTTP/%.1f %s %s' % status]
    dump.extend(['%s: %s' % (k, v) for k, v in resp.getheaders()])
    dump.append('')
    if body:
        dump.extend([body, ''])
    return '\n'.join(dump)


class HTTPException(Exception):
    """An error occurred."""
    def __init__(self, reason, status):
        self.reason = reason
        self.status = status

    def __str__(self):
        return '%s (%d)' % (self.reason, self.status)


class ResponseBodyIterator(object):
    """A class that acts as an iterator over an HTTP response."""

    def __init__(self, resp):
        self.resp = resp

    def __iter__(self):
        while True:
            yield self.next()

    def next(self):
        chunk = self.resp.read(CHUNKSIZE)
        if chunk:
            return chunk
        else:
            raise StopIteration()
