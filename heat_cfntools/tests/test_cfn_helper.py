#
# Copyright 2013 Hewlett-Packard Development Company, L.P.
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

from datetime import date
import httplib
import json
import mox
import subprocess
import tempfile
import testtools
import testtools.matchers as ttm

from heat_cfntools.cfntools import cfn_helper
from heat_cfntools.tests import fakes
import time


class FakePOpen():
    def __init__(self, stdout='', stderr='', returncode=0):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

    def communicate(self):
        return (self.stdout, self.stderr)

    def wait(self):
        pass


class MockPopenTestCase(testtools.TestCase):

    def mock_cmd_run(self, command, cwd=None, env=None):
        return subprocess.Popen(
            command, cwd=cwd, env=env, stderr=-1, stdout=-1)

    def setUp(self):
        super(MockPopenTestCase, self).setUp()
        self.m = mox.Mox()
        self.m.StubOutWithMock(subprocess, 'Popen')
        self.addCleanup(self.m.UnsetStubs)


class TestCommandRunner(MockPopenTestCase):

    def test_command_runner(self):
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command1']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/command2']).AndReturn(
            FakePOpen('Doing something', 'error', -1))
        self.m.ReplayAll()
        cmd2 = cfn_helper.CommandRunner('/bin/command2')
        cmd1 = cfn_helper.CommandRunner('/bin/command1', cmd2)
        cmd1.run('root')
        self.assertEqual(
            'CommandRunner:\n\tcommand: /bin/command1\n\tstdout: All good',
            str(cmd1))
        self.assertEqual(
            'CommandRunner:\n\tcommand: /bin/command2\n\tstatus: -1\n'
            '\tstdout: Doing something\n\tstderr: error',
            str(cmd2))
        self.m.VerifyAll()


class TestServicesHandler(MockPopenTestCase):

    def test_services_handler_systemd(self):
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl enable httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl enable mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start mysqld.service']
        ).AndReturn(FakePOpen())

        # monitor_services not running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl start mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())

        # monitor_services running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen())

        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "systemd": {
                "mysqld": {"enabled": "true", "ensureRunning": "true"},
                "httpd": {"enabled": "true", "ensureRunning": "true"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()
        # services not running
        sh.monitor_services()

        # services running
        sh.monitor_services()

        self.m.VerifyAll()

    def test_services_handler_systemd_disabled(self):
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl disable httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl stop httpd.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl disable mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl status mysqld.service']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/systemctl stop mysqld.service']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "systemd": {
                "mysqld": {"enabled": "false", "ensureRunning": "false"},
                "httpd": {"enabled": "false", "ensureRunning": "false"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()

        self.m.VerifyAll()

    def test_services_handler_sysv(self):
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/chkconfig httpd on']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd start']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/chkconfig mysqld on']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld start']
        ).AndReturn(FakePOpen())

        # monitor_services not running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd start']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld status']
        ).AndReturn(FakePOpen(returncode=-1))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld start']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/services_restarted']
        ).AndReturn(FakePOpen())

        # monitor_services running
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen())

        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld status']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "mysqld": {"enabled": "true", "ensureRunning": "true"},
                "httpd": {"enabled": "true", "ensureRunning": "true"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()
        # services not running
        sh.monitor_services()

        # services running
        sh.monitor_services()

        self.m.VerifyAll()

    def test_services_handler_sysv_disabled(self):
        # apply_services
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/chkconfig httpd off']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd status']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service httpd stop']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/chkconfig mysqld off']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld status']
        ).AndReturn(FakePOpen())
        self.mock_cmd_run(
            ['su', 'root', '-c', '/sbin/service mysqld stop']
        ).AndReturn(FakePOpen())

        self.m.ReplayAll()

        services = {
            "sysvinit": {
                "mysqld": {"enabled": "false", "ensureRunning": "false"},
                "httpd": {"enabled": "false", "ensureRunning": "false"}
            }
        }
        hooks = [
            cfn_helper.Hook(
                'hook1',
                'service.restarted',
                'Resources.resource1.Metadata',
                'root',
                '/bin/services_restarted')
        ]
        sh = cfn_helper.ServicesHandler(services, 'resource1', hooks)
        sh.apply_services()

        self.m.VerifyAll()


class TestHupConfig(MockPopenTestCase):

    def test_load_main_section(self):
        fcreds = tempfile.NamedTemporaryFile()
        fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
        fcreds.flush()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write('''[main]
stack=teststack
credential-file=%s''' % fcreds.name)
        main_conf.flush()
        mainconfig = cfn_helper.HupConfig([open(main_conf.name)])
        self.assertEqual(
            '{stack: teststack, credential_file: %s, '
            'region: nova, interval:10}' % fcreds.name,
            str(mainconfig))
        main_conf.close()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write('''[main]
stack=teststack
region=region1
credential-file=%s-invalid
interval=120''' % fcreds.name)
        main_conf.flush()
        self.assertRaisesRegexp(
            Exception,
            'invalid credentials file',
            cfn_helper.HupConfig,
            [open(main_conf.name)])

        fcreds.close()

    def test_hup_config(self):
        self.mock_cmd_run(['su', 'root', '-c', '/bin/hook2']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/hook1']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(['su', 'root', '-c', '/bin/hook3']).AndReturn(
            FakePOpen('All good'))
        self.mock_cmd_run(
            ['su', 'root', '-c', '/bin/cfn-http-restarted']).AndReturn(
                FakePOpen('All good'))
        self.m.ReplayAll()

        hooks_conf = tempfile.NamedTemporaryFile()

        def write_hook_conf(f, name, triggers, path, action):
            f.write(
                '[%s]\ntriggers=%s\npath=%s\naction=%s\nrunas=root\n\n' % (
                    name, triggers, path, action))

        write_hook_conf(
            hooks_conf,
            'hook2',
            'service2.restarted',
            'Resources.resource2.Metadata',
            '/bin/hook2')
        write_hook_conf(
            hooks_conf,
            'hook1',
            'service1.restarted',
            'Resources.resource1.Metadata',
            '/bin/hook1')
        write_hook_conf(
            hooks_conf,
            'hook3',
            'service3.restarted',
            'Resources.resource3.Metadata',
            '/bin/hook3')
        write_hook_conf(
            hooks_conf,
            'cfn-http-restarted',
            'service.restarted',
            'Resources.resource.Metadata',
            '/bin/cfn-http-restarted')
        hooks_conf.flush()

        fcreds = tempfile.NamedTemporaryFile()
        fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
        fcreds.flush()

        main_conf = tempfile.NamedTemporaryFile()
        main_conf.write('''[main]
stack=teststack
credential-file=%s
region=region1
interval=120''' % fcreds.name)
        main_conf.flush()

        mainconfig = cfn_helper.HupConfig([
            open(main_conf.name),
            open(hooks_conf.name)])
        unique_resources = mainconfig.unique_resources_get()
        self.assertSequenceEqual([
            'resource2',
            'resource1',
            'resource3',
            'resource'
        ], unique_resources)

        hooks = mainconfig.hooks
        self.assertEqual(
            '{hook2, service2.restarted, Resources.resource2.Metadata,'
            ' root, /bin/hook2}', str(hooks[0]))
        self.assertEqual(
            '{hook1, service1.restarted, Resources.resource1.Metadata,'
            ' root, /bin/hook1}', str(hooks[1]))
        self.assertEqual(
            '{hook3, service3.restarted, Resources.resource3.Metadata,'
            ' root, /bin/hook3}', str(hooks[2]))
        self.assertEqual(
            '{cfn-http-restarted, service.restarted,'
            ' Resources.resource.Metadata, root, /bin/cfn-http-restarted}',
            str(hooks[3]))

        for hook in mainconfig.hooks:
            hook.event(hook.triggers, None, hook.resource_name_get())

        hooks_conf.close()
        fcreds.close()
        main_conf.close()
        self.m.VerifyAll()


class TestCfnHelper(testtools.TestCase):

    def _check_metadata_content(self, content, value):
        with tempfile.NamedTemporaryFile() as metadata_info:
            metadata_info.write(content)
            metadata_info.flush()
            one_line = cfn_helper.read_one_line_file(metadata_info.name)
            self.assertEquals(value, one_line)

    def test_read_one_line_file(self):
        self._check_metadata_content(
            "http://172.20.42.42:8000\n", 'http://172.20.42.42:8000')

    def test_read_one_line_file_emptyfile(self):
        self._check_metadata_content("\n", None)
        self._check_metadata_content("", None)

    def test_read_one_line_file_nofile(self):
        random_filename = self.getUniqueString()
        self.assertEquals(None,
                          cfn_helper.read_one_line_file(random_filename))

    def test_to_boolean(self):
        self.assertTrue(cfn_helper.to_boolean(True))
        self.assertTrue(cfn_helper.to_boolean('true'))
        self.assertTrue(cfn_helper.to_boolean('yes'))
        self.assertTrue(cfn_helper.to_boolean('1'))
        self.assertTrue(cfn_helper.to_boolean(1))

        self.assertFalse(cfn_helper.to_boolean(False))
        self.assertFalse(cfn_helper.to_boolean('false'))
        self.assertFalse(cfn_helper.to_boolean('no'))
        self.assertFalse(cfn_helper.to_boolean('0'))
        self.assertFalse(cfn_helper.to_boolean(0))
        self.assertFalse(cfn_helper.to_boolean(None))
        self.assertFalse(cfn_helper.to_boolean('fingle'))

    def test_parse_creds_file(self):
        def parse_creds_test(file_contents, creds_match):
            with tempfile.NamedTemporaryFile(mode='w') as fcreds:
                fcreds.write(file_contents)
                fcreds.flush()
                creds = cfn_helper.parse_creds_file(fcreds.name)
                self.assertDictEqual(creds_match, creds)
        parse_creds_test(
            'AWSAccessKeyId=foo\nAWSSecretKey=bar\n',
            {'AWSAccessKeyId': 'foo', 'AWSSecretKey': 'bar'}
        )
        parse_creds_test(
            'AWSAccessKeyId =foo\nAWSSecretKey= bar\n',
            {'AWSAccessKeyId': 'foo', 'AWSSecretKey': 'bar'}
        )
        parse_creds_test(
            'AWSAccessKeyId    =    foo\nAWSSecretKey    =    bar\n',
            {'AWSAccessKeyId': 'foo', 'AWSSecretKey': 'bar'}
        )


class TestMetadataRetrieve(testtools.TestCase):

    def test_metadata_retrieve_files(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)

        with tempfile.NamedTemporaryFile() as last_file:
            pass

        with tempfile.NamedTemporaryFile(mode='w+') as default_file:
            default_file.write(md_str)
            default_file.flush()
            self.assertThat(default_file.name, ttm.FileContains(md_str))

            md.retrieve(
                default_path=default_file.name,
                last_path=last_file.name)

            self.assertThat(last_file.name, ttm.FileContains(md_str))
            self.assertDictEqual(md_data, md._metadata)

        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(
            default_path=default_file.name,
            last_path=last_file.name)
        self.assertDictEqual(md_data, md._metadata)

    def test_metadata_retrieve_none(self):

        md = cfn_helper.Metadata('teststack', None)
        with tempfile.NamedTemporaryFile() as last_file:
            pass
        with tempfile.NamedTemporaryFile() as default_file:
            pass

        md.retrieve(
            default_path=default_file.name,
            last_path=last_file.name)
        self.assertIsNone(md._metadata)

    def test_metadata_retrieve_passed(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md_str = json.dumps(md_data)

        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(meta_str=md_str)
        self.assertDictEqual(md_data, md._metadata)

        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(meta_str=md_data)
        self.assertDictEqual(md_data, md._metadata)
        self.assertEqual(md_str, str(md))

    def test_is_valid_metadata(self):
        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        md = cfn_helper.Metadata('teststack', None)
        md.retrieve(meta_str=md_data)

        self.assertDictEqual(md_data, md._metadata)
        self.assertTrue(md._is_valid_metadata())
        self.assertDictEqual(
            md_data['AWS::CloudFormation::Init'], md._metadata)

    def test_remote_metadata(self):

        md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
            "/tmp/foo": {"content": "bar"}}}}}
        tstamp = time.strptime("12 Mar 13", "%d %b %y")
        m = mox.Mox()
        m.StubOutClassWithMocks(httplib, 'HTTPConnection')
        m.StubOutWithMock(time, 'localtime')

        describe_response = '''{"DescribeStackResourceResponse": {
            "DescribeStackResourceResult": {
                "StackResourceDetail": {
                    "StackId": "arn:openstack:heat::3715b9c86f1744208486abfe34426b2c:stacks/stack-0947-10/7eae185f-d6f0-487f-819f-e52efad4f529",
                    "ResourceStatus": "CREATE_COMPLETE",
                    "Description": "",
                    "ResourceType": "AWS::EC2::Instance",
                    "ResourceStatusReason": "state changed",
                    "LastUpdatedTimestamp": "2013-03-12T20:48:39Z",
                    "StackName": "stack-0947-10",
                    "PhysicalResourceId": "0ad002c9-c360-4258-8b86-d711bdbd8980",
                    "Metadata": {"AWS::CloudFormation::Init": {"config": {"files": {"/tmp/foo": {"content": "bar"}}}}},
                    "LogicalResourceId": "WikiDatabase"
                }
            }
        }}'''

        time.localtime().AndReturn(tstamp)
        conn = httplib.HTTPConnection(host='localhost', port=8000)
        conn.request(
            'GET',
             '/v1/?StackName=teststack&SignatureMethod=HmacSHA256&AWSAccessKeyId=foo&ContentType=JSON&Signature=zuvuT%2FR1sSVtqEqbejw%2FPphwkAnmdT9QnlK%2BsPst3K8%3D&Action=DescribeStackResource&Timestamp=2013-03-12T00%3A00%3A00Z&SignatureVersion=2&LogicalResourceId=None',
            None,
            {'Accept': '*/*', 'User-Agent': 'heat-cfntools'}).AndReturn(None)
        conn.getresponse().AndReturn(
            fakes.FakeHTTPResponse(200, describe_response))
        m.ReplayAll()
        try:
            md = cfn_helper.Metadata(
                'teststack',
                None,
                access_key='foo',
                secret_key='bar')
            md.retrieve()
            self.assertDictEqual(md_data, md._metadata)

            metadata_info = tempfile.NamedTemporaryFile()
            metadata_info.write('http://localhost:8000\n')
            metadata_info.flush()
            fcreds = tempfile.NamedTemporaryFile(mode='w')
            fcreds.write('AWSAccessKeyId=foo\nAWSSecretKey=bar\n')
            fcreds.flush()
            md = cfn_helper.Metadata(
                'teststack', None, credentials_file=fcreds.name)
            md.retrieve(metadata_server_path=metadata_info.name)

            self.assertDictEqual(md_data, md._metadata)

            fcreds.close()
            metadata_info.close()

            m.VerifyAll()
        finally:
            m.UnsetStubs()

    def test_cfn_init(self):

        with tempfile.NamedTemporaryFile(mode='w+') as foo_file:
            md_data = {"AWS::CloudFormation::Init": {"config": {"files": {
                foo_file.name: {"content": "bar"}}}}}

            md = cfn_helper.Metadata('teststack', None)
            md.retrieve(meta_str=md_data)
            md.cfn_init()
            self.assertThat(foo_file.name, ttm.FileContains('bar'))


class TestMetricData(testtools.TestCase):

    def test_build_dimension_param(self):
        md = cfn_helper.MetricData()
        self.assertDictEqual({
            'Dimensions.member.1.Name': 'foo',
            'Dimensions.member.1.Value': 'bar'}, md.build_dimension_param({
                'foo': 'bar'}))
        self.assertDictEqual({
            'Dimensions.member.1.Name': 'foo',
            'Dimensions.member.2.Name': 'bar'}, md.build_dimension_param({
                'foo': None, 'bar': None}))
        self.assertDictEqual({
            'Dimensions.member.1.Name': 'foo',
            'Dimensions.member.1.Value': 'first',
            'Dimensions.member.2.Name': 'foo',
            'Dimensions.member.2.Value': 'second',
            'Dimensions.member.3.Name': 'foo',
            'Dimensions.member.3.Value': 'third'}, md.build_dimension_param({
                'foo': ['first', 'second', 'third']}))

        self.assertDictEqual({
            'Dimensions.member.1.Name': 'foo',
            'Dimensions.member.1.Value': 1,
            'Dimensions.member.2.Name': 'foo',
            'Dimensions.member.2.Value': 2,
            'Dimensions.member.3.Name': 'foo',
            'Dimensions.member.3.Value': 3,
            'Dimensions.member.4.Name': 'bar',
            'Dimensions.member.4.Value': 3,
            'Dimensions.member.5.Name': 'bar',
            'Dimensions.member.5.Value': 2,
            'Dimensions.member.6.Name': 'bar',
            'Dimensions.member.6.Value': 1}, md.build_dimension_param({
                'foo': [1, 2, 3],
                'bar': [3, 2, 1]}))

    def test_put_metric_data(self):
        md = cfn_helper.MetricData()
        # {'statistics': None, 'name': 'DiskSpaceUsed', 'timestamp': None, 'namespace': 'system/linux', 'value': 1588, 'unit': 'megabytes', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'SwapUsed', 'timestamp': None, 'namespace': 'system/linux', 'value': 0, 'unit': 'megabytes', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'MemoryUsed', 'timestamp': None, 'namespace': 'system/linux', 'value': 917L, 'unit': 'megabytes', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'Heartbeat', 'timestamp': None, 'namespace': 'system/linux', 'value': 1, 'unit': 'Counter', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'DiskSpaceUtilization', 'timestamp': None, 'namespace': 'system/linux', 'value': 19.0, 'unit': 'Percent', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'MemoryUtilization', 'timestamp': None, 'namespace': 'system/linux', 'value': 15.4, 'unit': 'Percent', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'DiskSpaceAvailable', 'timestamp': None, 'namespace': 'system/linux', 'value': 6333, 'unit': 'megabytes', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'CPUUtilization', 'timestamp': None, 'namespace': 'system/linux', 'value': 7.0, 'unit': 'Percent', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'MemoryAvailable', 'timestamp': None, 'namespace': 'system/linux', 'value': 78L, 'unit': 'megabytes', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}
        # {'statistics': None, 'name': 'SwapUtilization', 'timestamp': None, 'namespace': 'system/linux', 'value': 0.0, 'unit': 'Percent', 'dimensions': [{'AlarmName': 'stack-1009-22.HeartbeatFailureAlarm'}]}

    def test_build_put_params(self):
        md = cfn_helper.MetricData()
        self.assertDictEqual({
            'MetricData.member.1.Dimensions.member.1.Name': 'AlarmName',
            'MetricData.member.1.Dimensions.member.1.Value': 'alarm1',
            'MetricData.member.1.MetricName': 'Heartbeat',
            'MetricData.member.1.Unit': 'Counter',
            'MetricData.member.1.Value': 1}, md.build_put_params(**{
                'statistics': None,
                'name': 'Heartbeat',
                'timestamp': None,
                'value': 1,
                'unit': 'Counter',
                'dimensions':
                    [{'AlarmName': 'alarm1'}]}))

        self.assertDictEqual({
            'MetricData.member.1.Dimensions.member.1.Name': 'AlarmName',
            'MetricData.member.1.Dimensions.member.1.Value': 'alarm1',
            'MetricData.member.1.MetricName': 'DiskSpaceUsed',
            'MetricData.member.1.Timestamp': '2013-03-13',
            'MetricData.member.1.Unit': 'megabytes',
            'MetricData.member.1.Value': 1588}, md.build_put_params(**{
                'statistics': None,
                'name': 'DiskSpaceUsed',
                'timestamp': date(2013, 03, 13),
                'value': 1588,
                'unit': 'megabytes',
                'dimensions':
                    [{'AlarmName': 'alarm1'}]}))

        self.assertDictEqual({
            'MetricData.member.1.MetricName': 'DiskSpaceUsed',
            'MetricData.member.1.StatisticValues.Maximum': 1111,
            'MetricData.member.1.StatisticValues.Minimum': 999,
            'MetricData.member.1.StatisticValues.SampleCount': 50,
            'MetricData.member.1.StatisticValues.Sum': 50000,
            'MetricData.member.1.Timestamp': '2013-03-13',
            'MetricData.member.1.Unit': 'megabytes'}, md.build_put_params(**{
                'name': 'DiskSpaceUsed',
                'timestamp': date(2013, 03, 13),
                'unit': 'megabytes',
                'statistics': {
                    'maximum': 1111,
                    'minimum': 999,
                    'samplecount': 50,
                    'sum': 50000}}))

        self.assertDictEqual({
            'MetricData.member.1.MetricName': 'SwapUsed',
            'MetricData.member.1.Unit': 'megabytes',
            'MetricData.member.1.Value': 1000,
            'MetricData.member.2.MetricName': 'DiskSpaceUsed',
            'MetricData.member.2.Unit': 'megabytes',
            'MetricData.member.2.Value': 2000,
            'MetricData.member.3.MetricName': 'MemoryUsed',
            'MetricData.member.3.Unit': 'megabytes',
            'MetricData.member.3.Value': 3000}, md.build_put_params(**{
                'name': ['SwapUsed', 'DiskSpaceUsed', 'MemoryUsed'],
                'value': [1000, 2000, 3000],
                'unit': ['megabytes', 'megabytes', 'megabytes']}))

        self.assertRaisesRegexp(
            Exception, 'Must specify equal .*', md.build_put_params, **{
                'name': ['SwapUsed', 'DiskSpaceUsed', 'MemoryUsed'],
                'value': [1000, 2000, 3000],
                'unit': ['megabytes', 'megabytes']})

        self.assertRaisesRegexp(
            Exception, 'Must specify a value .*', md.build_put_params, **{
                'name': 'SwapUsed'})
