#
# Copyright 2013 Red Hat, Inc.
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import httplib
import json
import mox
import testtools
import StringIO

from heat_cfntools.cfntools import http_client
from heat_cfntools.tests import fakes


class TestHttp(testtools.TestCase):

    def setUp(self):
        super(TestHttp, self).setUp()
        self.m = mox.Mox()
        self.m.StubOutClassWithMocks(httplib, 'HTTPConnection')
        self.m.StubOutClassWithMocks(httplib, 'HTTPSConnection')
        self.addCleanup(self.m.UnsetStubs)

    def test_http_request(self):
        conn = httplib.HTTPConnection(host='localhost', port=None)
        conn.request(
            'GET',
            '/path',
            None,
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(200, 'yo'))
        self.m.ReplayAll()

        resp, body = http_client.http_request('GET', 'http://localhost/path')
        self.assertEqual(200, resp.status)
        self.assertEqual('yo', body)

        self.assertEqual(
            '\nHTTP/1.0 200 because\n\nyo\n', http_client._log_http_response(
                resp, body))
        self.m.VerifyAll()

    def test_https_request(self):
        conn = httplib.HTTPSConnection(host='localhost', port=None)
        conn.request(
            'GET',
            '/path',
            None,
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(200, 'yo'))
        self.m.ReplayAll()

        resp, body = http_client.http_request('GET', 'https://localhost/path')
        self.assertEqual(200, resp.status)
        self.assertEqual('yo', body)

        self.assertEqual(
            '\nHTTP/1.0 200 because\n\nyo\n', http_client._log_http_response(
                resp, body))
        self.m.VerifyAll()


    def test_http_request_body(self):
        conn = httplib.HTTPConnection(host='localhost', port=None)
        conn.request(
            'POST',
            '/path',
            '{"foo": "bar"}',
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(200, '{"bar": "baz"}'))
        self.m.ReplayAll()

        resp, body = http_client.http_request(
            'POST', 'http://localhost/path', json.dumps({"foo": "bar"}))
        self.assertEqual(200, resp.status)
        self.assertEqual({"bar": "baz"}, json.loads(body))

        self.m.VerifyAll()

    def test_http_request_error(self):
        conn = httplib.HTTPConnection(host='localhost', port=None)
        conn.request(
            'GET',
            '/path',
            None,
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(404, reason='Not Found'))

        conn = httplib.HTTPConnection(host='localhost', port=None)
        conn.request(
            'GET',
            '/path',
            None,
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(300, reason='Requested version not available'))

        self.m.ReplayAll()
        self.assertRaisesRegexp(
            http_client.HTTPException,
            'Not Found \(404\)',
            http_client.http_request, 'GET', 'http://localhost/path')

        self.assertRaisesRegexp(
            http_client.HTTPException,
            'Requested version not available \(300\)',
            http_client.http_request, 'GET', 'http://localhost/path')

    def test_http_request_redirect(self):
        conn = httplib.HTTPConnection(host='localhost', port=None)
        conn.request(
            'GET',
            '/path',
            None,
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(301, reason='Go here', headers={
                'location': 'http://localhost/path2'}))

        conn = httplib.HTTPConnection(host='localhost', port=None)
        conn.request(
            'GET',
            '/path2',
            None,
            {'User-Agent': 'heat-cfntools', 'Accept': '*/*'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(200, 'yo'))

        self.m.ReplayAll()
        resp, body = http_client.http_request('GET', 'http://localhost/path')
        self.assertEqual(200, resp.status)
        self.assertEqual('yo', body)
