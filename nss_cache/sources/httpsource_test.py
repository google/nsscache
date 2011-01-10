#!/usr/bin/python
#
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

import logging
import time
import unittest
import StringIO

from nss_cache import error
from nss_cache import maps
from nss_cache.sources import httpsource
from nss_cache.util import files

import pmock
import pycurl

class TestHttpFilesSource(pmock.MockTestCase):

  def setUp(self):
    """Initialize a basic config dict."""
    self.config = {
                   'passwd_url': 'PASSWD_URL',
                   'shadow_url': 'SHADOW_URL',
                   'group_url': 'GROUP_URL',
                   'retry_delay': 'TEST_RETRY_DELAY',
                   'retry_max': 'TEST_RETRY_MAX',
                   'tls_cacertfile': 'TEST_TLS_CACERTFILE',
                  }

    logging.disable(logging.CRITICAL)

  #
  # Our tests are defined below here.
  #

  def testDefaults(self):
    """Test that we set the expected defaults for HTTP connections."""
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

  def testOverrideDefaults(self):
    """Test that we override the defaults for HTTP connections."""
    source = httpsource.HttpFilesSource(self.config)
    self.assertEquals(source.conf['passwd_url'], 'PASSWD_URL')
    self.assertEquals(source.conf['group_url'], 'GROUP_URL')
    self.assertEquals(source.conf['shadow_url'], 'SHADOW_URL')
    self.assertEquals(source.conf['retry_delay'], 'TEST_RETRY_DELAY')
    self.assertEquals(source.conf['retry_max'], 'TEST_RETRY_MAX')
    self.assertEquals(source.conf['tls_cacertfile'], 'TEST_TLS_CACERTFILE')


class TestHttpUpdateGetter(pmock.MockTestCase):
  def setUp(self):
    """Set up a basic getter, standard config and some timestamps."""
    self.getter = httpsource.UpdateGetter()
    self.ts = 1259641025
    self.http_ts = 'Tue, 01 Dec 2009 04:17:05 GMT'
    self.config = {
                   'passwd_url': 'PASSWD_URL',
                   'shadow_url': 'SHADOW_URL',
                   'group_url': 'GROUP_URL',
                   'retry_delay': 'TEST_RETRY_DELAY',
                   'retry_max': 'TEST_RETRY_MAX',
                   'tls_cacertfile': 'TEST_TLS_CACERTFILE',
                  }



  def mockConnection(self, url, rcode, numtries=1):
    """Mock connection.

    Args:
      url: URL it should expect
      rcode: HTTP response code to return.
      numtries: Number of times we should expect to go through the
                perform/getinfo cycle.
    """
    conn_mock = self.mock()
    conn_mock.expects(pmock.at_least_once()).method('setopt')
    for _ in range(numtries):
      conn_mock.expects(pmock.once()).perform()
      conn_mock.expects(pmock.once()).getinfo(
          pmock.eq(pycurl.RESPONSE_CODE)).will(pmock.return_value(rcode))
    return conn_mock

  def testFromTimestampToHttp(self):
    """Transform ticks to HTTP timestamp."""
    self.assertEquals(self.getter.FromTimestampToHttp(self.ts), self.http_ts)

  def testFromHttpToTimestamp(self):
    """Transform HTTP timestamp to ticks."""
    self.assertEquals(self.getter.FromHttpToTimestamp(self.http_ts), self.ts)

  def testGetUpdatesTimestampWorking(self):
    """No updates on a 304 return code."""
    mock_conn = self.mockConnection('https://TEST_URL', 304)
    source = httpsource.HttpFilesSource({}, conn=mock_conn)
    result = self.getter.GetUpdates(source, 'https://TEST_URL', 1)
    self.assertEquals(result, [])

  def testGetUpdatesTimestampNotMatch(self):
    """Update if we give a timestamp and it doesn't match."""
    def StubbedGetMap(cache_info):
      map_mock = self.mock()
      map_mock.expects(pmock.once()).SetModifyTimestamp(pmock.eq(self.ts))
      return map_mock
    mock_conn = self.mockConnection('https://TEST_URL', 200)
    mock_conn.expects(pmock.once()).getinfo(
        pmock.eq(pycurl.INFO_FILETIME)).will(pmock.return_value(self.ts))
    source = httpsource.HttpFilesSource({}, conn=mock_conn)
    self.getter.GetMap = StubbedGetMap
    result = self.getter.GetUpdates(source, 'https://TEST_URL', 1)

  def testRetryErrorCode(self):
    """We retry as per configuration if we get a non 200/304 response code."""
    self.config['retry_delay'] = 5
    self.config['retry_max'] = 3
    mock_conn = self.mockConnection('https://TEST_URL', 400, 3)

    sleep_mock = self.mock()
    sleep_mock.expects(pmock.once()).sleep(pmock.eq(5))
    sleep_mock.expects(pmock.once()).sleep(pmock.eq(5))
    original_sleep = time.sleep
    time.sleep = sleep_mock.sleep

    source_mock = self.mock()
    source_mock.conf = self.config
    source_mock.conn = mock_conn
    log_stub = self.mock()
    log_stub.set_default_stub(pmock.return_value(True))
    source_mock.log = log_stub

    self.assertRaises(error.SourceUnavailable, self.getter.GetUpdates,
                      source=source_mock, url='https://TEST_URL', since=None)
    time.sleep = original_sleep

  def testHttpProtocol(self):
    """We accept HTTP"""
    # We use code 304 since it basically shortcuts to the end of the method.
    mock_conn = self.mockConnection('http://TEST_URL', 304)
    source = httpsource.HttpFilesSource({}, conn=mock_conn)
    self.getter.GetUpdates(source, 'http://TEST_URL', None)

  def testHttpsProtocol(self):
    """We accept HTTPS"""
    mock_conn = self.mockConnection('https://TEST_URL', 304)
    source = httpsource.HttpFilesSource({}, conn=mock_conn)
    self.getter.GetUpdates(source, 'https://TEST_URL', None)

  def testInvalidProtocol(self):
    """Raise error.ConfigurationError on unsupported protocol."""
    # connection should never be used in this case.
    mock_conn = None
    source = httpsource.HttpFilesSource({}, conn=mock_conn)
    self.assertRaises(error.ConfigurationError, self.getter.GetUpdates,
                      source, 'ftp://test_url', None)


class TestPasswdUpdateGetter(pmock.MockTestCase):

  def setUp(self):
    self.updater = httpsource.PasswdUpdateGetter()

  def testGetParser(self):
    """Get a passwd file parser."""
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               files.FilesPasswdMapParser))

  def testCreateMap(self):
    """Create a passwd map."""
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               maps.PasswdMap))


class TestShadowUpdateGetter(pmock.MockTestCase):

  def setUp(self):
    self.updater = httpsource.ShadowUpdateGetter()

  def testGetParser(self):
    """Get a shadow file parser."""
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               files.FilesShadowMapParser))

  def testCreateMap(self):
    """Create a shadow map."""
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               maps.ShadowMap))


class TestGroupUpdateGetter(pmock.MockTestCase):

  def setUp(self):
    self.updater = httpsource.GroupUpdateGetter()

  def testGetParser(self):
    """Get a group file parser."""
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               files.FilesGroupMapParser))

  def testCreateMap(self):
    """Create a group map."""
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               maps.GroupMap))


class TestNetgroupUpdateGetter(pmock.MockTestCase):

  def setUp(self):
    self.updater = httpsource.NetgroupUpdateGetter()

  def testGetParser(self):
    """Get a netgroup file parser."""
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               files.FilesNetgroupMapParser))

  def testCreateMap(self):
    """Create a netgroup map."""
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               maps.NetgroupMap))


class TestAutomountUpdateGetter(pmock.MockTestCase):

  def setUp(self):
    self.updater = httpsource.AutomountUpdateGetter()

  def testGetParser(self):
    """Get a automount file parser."""
    parser = self.updater.GetParser()
    self.assertTrue(isinstance(self.updater.GetParser(),
                               files.FilesAutomountMapParser))

  def testCreateMap(self):
    """Create a automount map."""
    self.assertTrue(isinstance(self.updater.CreateMap(),
                               maps.AutomountMap))


if __name__ == '__main__':
  unittest.main()
