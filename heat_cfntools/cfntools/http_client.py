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
import socket
try:
    import ssl
except ImportError:
    pass
import os
import urlparse

logger = logging.getLogger(__name__)
USER_AGENT = 'heat-cfntools'
CHUNKSIZE = 1024 * 64  # 64kB


def http_request(method, url, body=None, headers={}, **kwargs):
    """ Send an http request with the specified characteristics.

    Wrapper around httplib.HTTP(S)Connection.request to handle tasks such
    as setting headers and error handling.
    """
    parts = urlparse.urlparse(url)

    conn_args = {
        'host': parts.hostname,
        'port': parts.port
    }
    if parts.scheme == 'https':
        conn_class = VerifiedHTTPSConnection
        conn_args['ca_file'] = kwargs.get('ca_file', None)
        conn_args['cert_file'] = kwargs.get('cert_file', None)
        conn_args['key_file'] = kwargs.get('key_file', None)
        conn_args['insecure'] = kwargs.get('insecure', False)
    elif parts.scheme == 'http':
        conn_class = httplib.HTTPConnection

    headers.setdefault('User-Agent', USER_AGENT)
    headers.setdefault('Accept', '*/*')

    logger.debug(
        _curl_request(method, url, body, headers, conn_args))
    conn = conn_class(**conn_args)

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


def _curl_request(method, url, body, headers, conn_args):
    curl = ['curl -i -X %s' % method]

    for (key, value) in headers.items():
        header = '-H \'%s: %s\'' % (key, value)
        curl.append(header)

    conn_params_fmt = [
        ('key_file', '--key %s'),
        ('cert_file', '--cert %s'),
        ('ca_file', '--cacert %s')]
    for (key, fmt) in conn_params_fmt:
        value = conn_args.get(key)
        if value:
            curl.append(fmt % value)

    if conn_args.get('insecure'):
        curl.append('-k')

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


class VerifiedHTTPSConnection(httplib.HTTPSConnection):
    """httplib-compatibile connection using client-side SSL authentication

    :see http://code.activestate.com/recipes/
            577548-https-httplib-client-connection-with-certificate-v/
    """

    def __init__(self, host, port, key_file=None, cert_file=None,
                 ca_file=None, timeout=None, insecure=False):
        httplib.HTTPSConnection.__init__(
            self, host, port, key_file=key_file, cert_file=cert_file)
        self.key_file = key_file
        self.cert_file = cert_file
        if ca_file is not None:
            self.ca_file = ca_file
        else:
            self.ca_file = self.get_system_ca_file()
        self.timeout = timeout
        self.insecure = insecure

    def connect(self):
        """
        Connect to a host on a given (SSL) port.
        If ca_file is pointing somewhere, use it to check Server Certificate.

        Redefined/copied and extended from httplib.py:1105 (Python 2.6.x).
        This is needed to pass cert_reqs=ssl.CERT_REQUIRED as parameter to
        ssl.wrap_socket(), which forces SSL to check server certificate against
        our client certificate.
        """
        sock = socket.create_connection((self.host, self.port), self.timeout)

        if self._tunnel_host:
            self.sock = sock
            self._tunnel()

        if self.insecure is True:
            kwargs = {'cert_reqs': ssl.CERT_NONE}
        else:
            kwargs = {'cert_reqs': ssl.CERT_REQUIRED, 'ca_certs': self.ca_file}

        if self.cert_file:
            kwargs['certfile'] = self.cert_file
            if self.key_file:
                kwargs['keyfile'] = self.key_file

        self.sock = ssl.wrap_socket(sock, **kwargs)

    @staticmethod
    def get_system_ca_file():
        """"Return path to system default CA file"""
        # Standard CA file locations for Debian/Ubuntu, RedHat/Fedora,
        # Suse, FreeBSD/OpenBSD
        ca_path = ['/etc/ssl/certs/ca-certificates.crt',
                   '/etc/pki/tls/certs/ca-bundle.crt',
                   '/etc/ssl/ca-bundle.pem',
                   '/etc/ssl/cert.pem']
        for ca in ca_path:
            if os.path.exists(ca):
                return ca
        return None


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
