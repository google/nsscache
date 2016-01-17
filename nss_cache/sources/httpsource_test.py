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

__author__ = 'blaedd@google.com (David MacKinnon)'

import time
import unittest

import mox
import pycurl

from nss_cache import error

from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import netgroup
from nss_cache.maps import passwd
from nss_cache.maps import shadow

from nss_cache.sources import httpsource
from nss_cache.util import file_formats


class TestHttpSource(unittest.TestCase):

  def setUp(self):
    """Initialize a basic config dict."""
    super(TestHttpSource, self).setUp()
    self.config = {'passwd_url': 'PASSWD_URL',
                   'shadow_url': 'SHADOW_URL',
                   'group_url': 'GROUP_URL',
                   'retry_delay': 'TEST_RETRY_DELAY',
                   'retry_max': 'TEST_RETRY_MAX',
                   'tls_cacertfile': 'TEST_TLS_CACERTFILE',
                   'http_proxy': 'HTTP_PROXY',
                  }

  def testDefaultConfiguration(self):
    source = httpsource.HttpFilesSource({})
    self.assertEquals(source.conf['passwd_url'],
                      httpsource.HttpFilesSource.PASSWD_URL)
    self.assertEquals(source.conf['shadow_url'],
                      httpsource.HttpFilesSource.SHADOW_URL)
    self.assertEquals(source.conf['group_url'],
                      httpsource.HttpFilesSource.GROUP_URL)
    self.assertEquals(source.conf['retry_max'],
                      httpsource.HttpFilesSource.RETRY_MAX)
    self.assertEquals(source.conf['retry_delay'],
                      httpsource.HttpFilesSource.RETRY_DELAY)
    self.assertEquals(source.conf['tls_cacertfile'],
                      httpsource.HttpFilesSource.TLS_CACERTFILE)
    self.assertEquals(source.conf['http_proxy'], None)

  def testOverrideDefaultConfiguration(self):
    source = httpsource.HttpFilesSource(self.config)
    self.assertEquals(source.conf['passwd_url'], 'PASSWD_URL')
    self.assertEquals(source.conf['group_url'], 'GROUP_URL')
    self.assertEquals(source.conf['shadow_url'], 'SHADOW_URL')
    self.assertEquals(source.conf['retry_delay'], 'TEST_RETRY_DELAY')
    self.assertEquals(source.conf['retry_max'], 'TEST_RETRY_MAX')
    self.assertEquals(source.conf['tls_cacertfile'], 'TEST_TLS_CACERTFILE')
    self.assertEquals(source.conf['http_proxy'], 'HTTP_PROXY')


class TestHttpUpdateGetter(mox.MoxTestBase):

  def testFromTimestampToHttp(self):
    ts = 1259641025
    expected_http_ts = 'Tue, 01 Dec 2009 04:17:05 GMT'
    self.assertEquals(expected_http_ts,
                      httpsource.UpdateGetter().FromTimestampToHttp(ts))

  def testFromHttpToTimestamp(self):
    expected_ts = 1259641025
    http_ts = 'Tue, 01 Dec 2009 04:17:05 GMT'
    self.assertEquals(expected_ts,
                      httpsource.UpdateGetter().FromHttpToTimestamp(http_ts))

  def testAcceptHttpProtocol(self):
    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()
    mock_conn.perform()
    # We use code 304 since it basically shortcuts to the end of the method.
    mock_conn.getinfo(pycurl.RESPONSE_CODE).AndReturn(304)

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    self.mox.ReplayAll()
    config = {}
    source = httpsource.HttpFilesSource(config)
    result = httpsource.UpdateGetter().GetUpdates(
        source, 'http://TEST_URL', None)
    self.assertEqual([], result)

  def testAcceptHttpsProtocol(self):
    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()
    mock_conn.perform()
    # We use code 304 since it basically shortcuts to the end of the method.
    mock_conn.getinfo(pycurl.RESPONSE_CODE).AndReturn(304)

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    self.mox.ReplayAll()
    config = {}
    source = httpsource.HttpFilesSource(config)
    result = httpsource.UpdateGetter().GetUpdates(
        source, 'https://TEST_URL', None)
    self.assertEqual([], result)

  def testRaiseConfigurationErrorOnUnsupportedProtocol(self):
    # connection should never be used in this case.
    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    self.mox.ReplayAll()
    source = httpsource.HttpFilesSource({})
    self.assertRaises(error.ConfigurationError,
                      httpsource.UpdateGetter().GetUpdates,
                      source, 'ftp://test_url', None)

  def testNoUpdatesForTemporaryFailure(self):
    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()
    mock_conn.perform()
    mock_conn.getinfo(pycurl.RESPONSE_CODE).AndReturn(304)

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    self.mox.ReplayAll()
    config = {}
    source = httpsource.HttpFilesSource(config)
    result = httpsource.UpdateGetter().GetUpdates(
        source, 'https://TEST_URL', 37)
    self.assertEquals(result, [])

  def testGetUpdatesIfTimestampNotMatch(self):
    ts = 1259641025

    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()
    mock_conn.perform()
    mock_conn.getinfo(pycurl.RESPONSE_CODE).AndReturn(200)
    mock_conn.getinfo(pycurl.INFO_FILETIME).AndReturn(ts)

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    mock_map = self.mox.CreateMockAnything()
    mock_map.SetModifyTimestamp(ts)

    getter = httpsource.UpdateGetter()
    self.mox.StubOutWithMock(getter, 'GetMap')
    getter.GetMap(cache_info=mox.IgnoreArg()).AndReturn(mock_map)

    self.mox.ReplayAll()
    config = {}
    source = httpsource.HttpFilesSource(config)
    result = getter.GetUpdates(source, 'https://TEST_URL', 1)
    self.assertEqual(mock_map, result)

  def testGetUpdatesWithoutTimestamp(self):
    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()
    mock_conn.perform()
    mock_conn.getinfo(pycurl.RESPONSE_CODE).AndReturn(200)
    mock_conn.getinfo(pycurl.INFO_FILETIME).AndReturn(-1)

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    mock_map = self.mox.CreateMockAnything()

    getter = httpsource.UpdateGetter()
    self.mox.StubOutWithMock(getter, 'GetMap')
    getter.GetMap(cache_info=mox.IgnoreArg()).AndReturn(mock_map)

    self.mox.ReplayAll()
    config = {}
    source = httpsource.HttpFilesSource(config)
    result = getter.GetUpdates(source, 'https://TEST_URL', 1)
    self.assertEqual(mock_map, result)

  def testRetryOnErrorCodeResponse(self):
    config = {'retry_delay': 5,
              'retry_max': 3}
    mock_conn = self.mox.CreateMockAnything()
    mock_conn.setopt(mox.IgnoreArg(), mox.IgnoreArg()).MultipleTimes()
    mock_conn.perform().MultipleTimes()
    mock_conn.getinfo(pycurl.RESPONSE_CODE).MultipleTimes().AndReturn(400)

    self.mox.StubOutWithMock(time, 'sleep')
    time.sleep(5)
    time.sleep(5)

    self.mox.StubOutWithMock(pycurl, 'Curl')
    pycurl.Curl().AndReturn(mock_conn)

    self.mox.ReplayAll()
    source = httpsource.HttpFilesSource(config)

    self.assertRaises(error.SourceUnavailable,
                      httpsource.UpdateGetter().GetUpdates,
                      source, url='https://TEST_URL', since=None)


class TestPasswdUpdateGetter(unittest.TestCase):

  def setUp(self):
    super(TestPasswdUpdateGetter, self).setUp()
    self.updater = httpsource.PasswdUpdateGetter()

  def testGetParser(self):
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               file_formats.FilesPasswdMapParser))

  def testCreateMap(self):
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               passwd.PasswdMap))


class TestShadowUpdateGetter(unittest.TestCase):

  def setUp(self):
    super(TestShadowUpdateGetter, self).setUp()
    self.updater = httpsource.ShadowUpdateGetter()

  def testGetParser(self):
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               file_formats.FilesShadowMapParser))

  def testCreateMap(self):
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               shadow.ShadowMap))


class TestGroupUpdateGetter(unittest.TestCase):

  def setUp(self):
    super(TestGroupUpdateGetter, self).setUp()
    self.updater = httpsource.GroupUpdateGetter()

  def testGetParser(self):
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               file_formats.FilesGroupMapParser))

  def testCreateMap(self):
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               group.GroupMap))


class TestNetgroupUpdateGetter(unittest.TestCase):

  def setUp(self):
    super(TestNetgroupUpdateGetter, self).setUp()
    self.updater = httpsource.NetgroupUpdateGetter()

  def testGetParser(self):
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               file_formats.FilesNetgroupMapParser))

  def testCreateMap(self):
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               netgroup.NetgroupMap))


class TestAutomountUpdateGetter(unittest.TestCase):

  def setUp(self):
    super(TestAutomountUpdateGetter, self).setUp()
    self.updater = httpsource.AutomountUpdateGetter()

  def testGetParser(self):
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               file_formats.FilesAutomountMapParser))

  def testCreateMap(self):
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               automount.AutomountMap))


if __name__ == '__main__':
  unittest.main()
