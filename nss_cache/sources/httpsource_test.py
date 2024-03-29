# Copyright 2007 Google Inc.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
"""An implementation of a mock http data source for nsscache."""

__author__ = "blaedd@google.com (David MacKinnon)"

import base64
import time
import unittest
import pycurl
from unittest import mock

from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import netgroup
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.maps import sshkey

from nss_cache.sources import httpsource
from nss_cache.util import file_formats
from nss_cache.util import curl


class TestHttpSource(unittest.TestCase):
    def setUp(self):
        """Initialize a basic config dict."""
        super(TestHttpSource, self).setUp()
        self.config = {
            "passwd_url": "PASSWD_URL",
            "shadow_url": "SHADOW_URL",
            "group_url": "GROUP_URL",
            "sshkey_url": "SSHKEY_URL",
            "retry_delay": "TEST_RETRY_DELAY",
            "retry_max": "TEST_RETRY_MAX",
            "tls_cacertfile": "TEST_TLS_CACERTFILE",
            "http_proxy": "HTTP_PROXY",
        }

    def testDefaultConfiguration(self):
        source = httpsource.HttpFilesSource({})
        self.assertEqual(
            source.conf["passwd_url"], httpsource.HttpFilesSource.PASSWD_URL
        )
        self.assertEqual(
            source.conf["shadow_url"], httpsource.HttpFilesSource.SHADOW_URL
        )
        self.assertEqual(source.conf["group_url"], httpsource.HttpFilesSource.GROUP_URL)
        self.assertEqual(
            source.conf["sshkey_url"], httpsource.HttpFilesSource.SSHKEY_URL
        )
        self.assertEqual(source.conf["retry_max"], httpsource.HttpFilesSource.RETRY_MAX)
        self.assertEqual(
            source.conf["retry_delay"], httpsource.HttpFilesSource.RETRY_DELAY
        )
        self.assertEqual(
            source.conf["tls_cacertfile"], httpsource.HttpFilesSource.TLS_CACERTFILE
        )
        self.assertEqual(source.conf["http_proxy"], None)

    def testOverrideDefaultConfiguration(self):
        source = httpsource.HttpFilesSource(self.config)
        self.assertEqual(source.conf["passwd_url"], "PASSWD_URL")
        self.assertEqual(source.conf["group_url"], "GROUP_URL")
        self.assertEqual(source.conf["shadow_url"], "SHADOW_URL")
        self.assertEqual(source.conf["sshkey_url"], "SSHKEY_URL")
        self.assertEqual(source.conf["retry_delay"], "TEST_RETRY_DELAY")
        self.assertEqual(source.conf["retry_max"], "TEST_RETRY_MAX")
        self.assertEqual(source.conf["tls_cacertfile"], "TEST_TLS_CACERTFILE")
        self.assertEqual(source.conf["http_proxy"], "HTTP_PROXY")


class TestHttpUpdateGetter(unittest.TestCase):
    def setUp(self):
        super().setUp()
        curl_patcher = mock.patch.object(pycurl, "Curl")
        self.addCleanup(curl_patcher.stop)
        self.curl_mock = curl_patcher.start()

    def testFromTimestampToHttp(self):
        ts = 1259641025
        expected_http_ts = "Tue, 01 Dec 2009 04:17:05 GMT"
        self.assertEqual(
            expected_http_ts, httpsource.UpdateGetter().FromTimestampToHttp(ts)
        )

    def testFromHttpToTimestamp(self):
        expected_ts = 1259641025
        http_ts = "Tue, 01 Dec 2009 04:17:05 GMT"
        self.assertEqual(
            expected_ts, httpsource.UpdateGetter().FromHttpToTimestamp(http_ts)
        )

    def testAcceptHttpProtocol(self):
        mock_conn = mock.Mock()
        # We use code 304 since it basically shortcuts to the end of the method.
        mock_conn.getinfo.return_value = 304
        self.curl_mock.return_value = mock_conn
        config = {}
        source = httpsource.HttpFilesSource(config)

        self.assertEqual(
            [], httpsource.UpdateGetter().GetUpdates(source, "http://TEST_URL", None)
        )

    def testAcceptHttpsProtocol(self):
        mock_conn = mock.Mock()
        # We use code 304 since it basically shortcuts to the end of the method.
        mock_conn.getinfo.return_value = 304
        self.curl_mock.return_value = mock_conn
        config = {}
        source = httpsource.HttpFilesSource(config)

        self.assertEqual(
            [], httpsource.UpdateGetter().GetUpdates(source, "https://TEST_URL", None)
        )

    def testRaiseConfigurationErrorOnUnsupportedProtocol(self):
        # connection should never be used in this case.
        mock_conn = mock.Mock()
        self.curl_mock.return_value = mock_conn
        source = httpsource.HttpFilesSource({})

        self.assertRaises(
            error.ConfigurationError,
            httpsource.UpdateGetter().GetUpdates,
            source,
            "ftp://test_url",
            None,
        )

    def testNoUpdatesForTemporaryFailure(self):
        mock_conn = mock.Mock()
        mock_conn.getinfo.return_value = 304
        self.curl_mock.return_value = mock_conn
        config = {}
        source = httpsource.HttpFilesSource(config)

        self.assertEqual(
            [], httpsource.UpdateGetter().GetUpdates(source, "https://TEST_URL", 37)
        )

    def testGetUpdatesIfTimestampNotMatch(self):
        ts = 1259641025
        mock_conn = mock.Mock()
        mock_conn.getinfo.side_effect = [200, ts]
        self.curl_mock.return_value = mock_conn
        mock_map = mock.Mock()
        getter = httpsource.UpdateGetter()
        getter.GetMap = mock.Mock(return_value=mock_map)
        config = {}
        source = httpsource.HttpFilesSource(config)

        self.assertEqual(mock_map, getter.GetUpdates(source, "https://TEST_URL", 1))

        mock_conn.getinfo.assert_has_calls(
            [mock.call(pycurl.RESPONSE_CODE), mock.call(pycurl.INFO_FILETIME)]
        )
        mock_map.SetModifyTimestamp.assert_called_with(ts)

    def testGetUpdatesWithoutTimestamp(self):
        mock_conn = mock.Mock()
        mock_conn.getinfo.side_effect = [200, -1]
        self.curl_mock.return_value = mock_conn
        mock_map = mock.Mock()
        getter = httpsource.UpdateGetter()
        getter.GetMap = mock.Mock(return_value=mock_map)
        config = {}
        source = httpsource.HttpFilesSource(config)
        result = getter.GetUpdates(source, "https://TEST_URL", 1)
        self.assertEqual(mock_map, result)

        mock_conn.getinfo.assert_has_calls(
            [mock.call(pycurl.RESPONSE_CODE), mock.call(pycurl.INFO_FILETIME)]
        )

    def testRetryOnErrorCodeResponse(self):
        config = {"retry_delay": 5, "retry_max": 3}
        mock_conn = mock.Mock()
        mock_conn.getinfo.return_value = 400
        self.curl_mock.return_value = mock_conn
        time.sleep = mock.Mock()
        source = httpsource.HttpFilesSource(config)

        self.assertRaises(
            error.SourceUnavailable,
            httpsource.UpdateGetter().GetUpdates,
            source,
            url="https://TEST_URL",
            since=None,
        )

        time.sleep.assert_has_calls([mock.call(5), mock.call(5)])


class TestPasswdUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestPasswdUpdateGetter, self).setUp()
        self.updater = httpsource.PasswdUpdateGetter()

    def testGetParser(self):
        parser = self.updater.GetParser()
        self.assertTrue(
            isinstance(self.updater.GetParser(), file_formats.FilesPasswdMapParser)
        )

    def testCreateMap(self):
        self.assertTrue(isinstance(self.updater.CreateMap(), passwd.PasswdMap))


class TestShadowUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestShadowUpdateGetter, self).setUp()
        self.updater = httpsource.ShadowUpdateGetter()
        curl_patcher = mock.patch.object(curl, "CurlFetch")
        self.addCleanup(curl_patcher.stop)
        self.curl_fetch_mock = curl_patcher.start()

    def testGetParser(self):
        parser = self.updater.GetParser()
        self.assertTrue(
            isinstance(self.updater.GetParser(), file_formats.FilesShadowMapParser)
        )

    def testCreateMap(self):
        self.assertTrue(isinstance(self.updater.CreateMap(), shadow.ShadowMap))

    def testShadowGetUpdatesWithContent(self):
        self.curl_fetch_mock.return_value = (
            200,
            "",
            b"""usera:x:::::::
userb:x:::::::
""",
        )

        config = {}
        source = httpsource.HttpFilesSource(config)
        result = self.updater.GetUpdates(source, "https://TEST_URL", 1)
        print(result)
        self.assertEqual(len(result), 2)

    def testShadowGetUpdatesWithBz2Content(self):
        self.curl_fetch_mock.return_value = (
            200,
            "",
            base64.b64decode(
                "QlpoOTFBWSZTWfm+rXYAAAvJgAgQABAyABpAIAAhKm1GMoQAwRSpHIXejGQgz4u5IpwoSHzfVrsA"
            ),
        )

        config = {}
        source = httpsource.HttpFilesSource(config)
        result = self.updater.GetUpdates(source, "https://TEST_URL", 1)
        print(result)
        self.assertEqual(len(result), 2)


class TestGroupUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestGroupUpdateGetter, self).setUp()
        self.updater = httpsource.GroupUpdateGetter()

    def testGetParser(self):
        parser = self.updater.GetParser()
        self.assertTrue(
            isinstance(self.updater.GetParser(), file_formats.FilesGroupMapParser)
        )

    def testCreateMap(self):
        self.assertTrue(isinstance(self.updater.CreateMap(), group.GroupMap))


class TestNetgroupUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestNetgroupUpdateGetter, self).setUp()
        self.updater = httpsource.NetgroupUpdateGetter()

    def testGetParser(self):
        parser = self.updater.GetParser()
        self.assertTrue(
            isinstance(self.updater.GetParser(), file_formats.FilesNetgroupMapParser)
        )

    def testCreateMap(self):
        self.assertTrue(isinstance(self.updater.CreateMap(), netgroup.NetgroupMap))


class TestAutomountUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestAutomountUpdateGetter, self).setUp()
        self.updater = httpsource.AutomountUpdateGetter()

    def testGetParser(self):
        parser = self.updater.GetParser()
        self.assertTrue(
            isinstance(self.updater.GetParser(), file_formats.FilesAutomountMapParser)
        )

    def testCreateMap(self):
        self.assertTrue(isinstance(self.updater.CreateMap(), automount.AutomountMap))


class TestSshkeyUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestSshkeyUpdateGetter, self).setUp()
        self.updater = httpsource.SshkeyUpdateGetter()

    def testGetParser(self):
        parser = self.updater.GetParser()
        self.assertTrue(
            isinstance(self.updater.GetParser(), file_formats.FilesSshkeyMapParser)
        )

    def testCreateMap(self):
        self.assertTrue(isinstance(self.updater.CreateMap(), sshkey.SshkeyMap))


if __name__ == "__main__":
    unittest.main()
