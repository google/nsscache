#!/usr/bin/python
#
# Copyright 2010 Google Inc.
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

import cStringIO
import logging

from nss_cache import error
from nss_cache.sources import zsyncsource

import pmock


class TestZsyncsource(pmock.MockTestCase):

  def setUp(self):
    """Initialize a basic config dict."""
    self.config = {'passwd_url': 'PASSWD_URL',
                   'shadow_url': 'SHADOW_URL',
                   'group_url': 'GROUP_URL',
                   'retry_delay': 'TEST_RETRY_DELAY',
                   'retry_max': 'TEST_RETRY_MAX',
                   'tls_cacertfile': 'TEST_TLS_CACERTFILE',
                   'automount_base_url': 'AUTOMOUNT_BASE_URL',
                   'gpg': 'GPG',
                   'gpg_pubkeyfile': 'GPG_PUBKEYFILE',
                   'zsync_suffix': 'ZSYNC_SUFFIX',
                   'http_proxy': 'HTTP_PROXY',
                   'gpg_suffix': 'GPG_SUFFIX',
                   }

    logging.disable(logging.CRITICAL)

  #
  # Our tests are defined below here.
  #

  def testDefaults(self):
    """Test that we set the expected defaults for HTTP connections."""
    source = zsyncsource.ZSyncSource({})
    self.assertEquals(source.conf['passwd_url'],
                      zsyncsource.ZSyncSource.PASSWD_URL)
    self.assertEquals(source.conf['shadow_url'],
                      zsyncsource.ZSyncSource.SHADOW_URL)
    self.assertEquals(source.conf['group_url'],
                      zsyncsource.ZSyncSource.GROUP_URL)
    self.assertEquals(source.conf['retry_max'],
                      zsyncsource.ZSyncSource.RETRY_MAX)
    self.assertEquals(source.conf['retry_delay'],
                      zsyncsource.ZSyncSource.RETRY_DELAY)
    self.assertEquals(source.conf['tls_cacertfile'],
                      zsyncsource.ZSyncSource.TLS_CACERTFILE)
    self.assertEquals(source.conf['zsync_suffix'],
                      zsyncsource.ZSyncSource.ZSYNC_SUFFIX)
    self.assertEquals(source.conf['automount_base_url'],
                      zsyncsource.ZSyncSource.AUTOMOUNT_BASE_URL)
    self.assertEquals(source.conf['gpg_pubkeyfile'],
                      zsyncsource.ZSyncSource.GPG_PUBKEYFILE)
    self.assertEquals(source.conf['gpg'],
                      zsyncsource.ZSyncSource.GPG)
    self.assertEquals(source.conf['gpg_suffix'],
                      zsyncsource.ZSyncSource.GPG_SUFFIX)
    self.assertEquals(source.conf['http_proxy'], None)

  def testOverrideDefaults(self):
    """Test that we override the defaults for HTTP connections."""
    source = zsyncsource.ZSyncSource(self.config)
    self.assertEquals(source.conf['passwd_url'], 'PASSWD_URL')
    self.assertEquals(source.conf['group_url'], 'GROUP_URL')
    self.assertEquals(source.conf['shadow_url'], 'SHADOW_URL')
    self.assertEquals(source.conf['retry_delay'], 'TEST_RETRY_DELAY')
    self.assertEquals(source.conf['retry_max'], 'TEST_RETRY_MAX')
    self.assertEquals(source.conf['tls_cacertfile'], 'TEST_TLS_CACERTFILE')
    self.assertEquals(source.conf['automount_base_url'], 'AUTOMOUNT_BASE_URL')
    self.assertEquals(source.conf['gpg'], 'GPG')
    self.assertEquals(source.conf['gpg_pubkeyfile'], 'GPG_PUBKEYFILE')
    self.assertEquals(source.conf['zsync_suffix'], 'ZSYNC_SUFFIX')
    self.assertEquals(source.conf['gpg_suffix'], 'GPG_SUFFIX')
    self.assertEquals(source.conf['http_proxy'], 'HTTP_PROXY')

  def testGPGVerify(self):
    """Test the GPG Verify method."""
    conf = {'gpg_fingerprint': 'AAA',
            'gpg': True}
    source = zsyncsource.ZSyncSource(conf)
    curl_orig = zsyncsource.curl
    curl_mock = self.mock()
    curl_return = (200, 'headers', 'body')
    curl_mock.expects(pmock.once()).CurlFetch(
        pmock.eq('remote_sig'), pmock.eq(source.conn),
        pmock.eq(source.log)).will(pmock.return_value(curl_return))
    zsyncsource.curl = curl_mock

    sig = 1
    signed = 2
    pyme_core = self.mock()
    pyme_core.expects(pmock.once()).Data(pmock.eq(curl_return[2])).will(
        pmock.return_value(sig))
    pyme_core.expects(pmock.once()).Data(file=pmock.eq('local_file')).will(
        pmock.return_value(signed))
    core_orig = zsyncsource.pyme.core
    zsyncsource.pyme.core = pyme_core

    result = self.mock()
    result.signatures = [ self.mock() ]
    result.signatures[0].fpr = 'AAA'
    key_mock = self.mock()
    key_mock.uids = [ self.mock() ]
    key_mock.uids[0].uid = 'Foobar'
    context = self.mock()
    context.expects(pmock.once()).op_verify(pmock.eq(sig),
                                            pmock.eq(signed),
                                            pmock.eq(None))
    context.expects(pmock.once()).op_verify_result().will(
        pmock.return_value(result))
    context.expects(pmock.once()).get_key(pmock.eq('AAA'), pmock.eq(0)).will(
        pmock.return_value(key_mock))
    self.assertTrue(source._GPGVerify('local_file', 'remote_sig', context))

    zsyncsource.curl = curl_orig
    zsyncsource.pyme.core = pyme_core

  def testGPGVerifyNoMatch(self):
    """Test the GPG Verify method."""
    conf = {'gpg_fingerprint': 'AAA',
            'gpg': True}
    source = zsyncsource.ZSyncSource(conf)

    curl_orig = zsyncsource.curl
    curl_mock = self.mock()
    curl_return = (200, 'headers', 'body')
    curl_mock.expects(pmock.once()).CurlFetch(
        pmock.eq('remote_sig'),
        pmock.eq(source.conn),
        pmock.eq(source.log)).will(pmock.return_value(curl_return))
    zsyncsource.curl = curl_mock

    sig = 1
    signed = 2
    pyme_core = self.mock()
    pyme_core.expects(pmock.once()).Data(pmock.eq(curl_return[2])).will(
        pmock.return_value(sig))
    pyme_core.expects(pmock.once()).Data(file=pmock.eq('local_file')).will(
        pmock.return_value(signed))
    core_orig = zsyncsource.pyme.core
    zsyncsource.pyme.core = pyme_core

    result = self.mock()
    result.signatures = [ self.mock() ]
    result.signatures[0].fpr = 'BBB'
    result.signatures[0].next = None
    key_mock = self.mock()
    key_mock.uids = self.mock()
    key_mock.uids.uid = 'Foobar'
    context = self.mock()
    context.expects(pmock.once()).op_verify(
        pmock.eq(sig), pmock.eq(signed), pmock.eq(None))
    context.expects(pmock.once()).op_verify_result().will(
        pmock.return_value(result))
    self.assertFalse(source._GPGVerify('local_file', 'remote_sig', context))

    zsyncsource.curl = curl_orig
    zsyncsource.pyme.core = pyme_core

  def testGPGVerifyMatchMultiple(self):
    """Test the GPG Verify method when there are multiple signatures."""

    conf = {'gpg_fingerprint': 'AAA',
            'gpg': True}
    source = zsyncsource.ZSyncSource(conf)

    curl_orig = zsyncsource.curl
    curl_mock = self.mock()
    curl_return = (200, 'headers', 'body')
    curl_mock.expects(pmock.once()).CurlFetch(
        pmock.eq('remote_sig'), pmock.eq(source.conn),
        pmock.eq(source.log)).will(pmock.return_value(curl_return))
    zsyncsource.curl = curl_mock

    sig = 1
    signed = 2
    pyme_core = self.mock()
    pyme_core.expects(pmock.once()).Data(pmock.eq(curl_return[2])).will(
        pmock.return_value(sig))
    pyme_core.expects(pmock.once()).Data(file=pmock.eq('local_file')).will(
        pmock.return_value(signed))
    core_orig = zsyncsource.pyme.core
    zsyncsource.pyme.core = pyme_core

    result = self.mock()
    result.signatures = [ self.mock() ]
    result.signatures[0] .fpr = 'BBB'
    result2 = self.mock()
    result.signatures[0].next = result2
    result2.fpr = 'AAA'
    key_mock = self.mock()
    key_mock.uids = [ self.mock() ]
    key_mock.uids[0].uid = 'Foobar'

    context = self.mock()
    context.expects(pmock.once()).op_verify(pmock.eq(sig),
                                            pmock.eq(signed),
                                            pmock.eq(None))
    context.expects(pmock.once()).op_verify_result().will(
        pmock.return_value(result))
    context.expects(pmock.once()).get_key(
        pmock.eq('AAA'), pmock.eq(0)).will(pmock.return_value(key_mock))
    self.assertTrue(source._GPGVerify('local_file', 'remote_sig', context))

    zsyncsource.curl = curl_orig
    zsyncsource.pyme.core = pyme_core

  def testGetFileNoGPG(self):
    """Test the GetFile method."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'
    path_orig = zsyncsource.os.path
    path = self.mock()
    path.expects(pmock.once()).exists(pmock.eq(current_file)).will(
        pmock.return_value(True))
    path.expects(pmock.once()).exists(pmock.eq(local)).will(
        pmock.return_value(True))
    zsyncsource.os.path = path

    zsync_orig = zsyncsource.zsync
    zsync_mock = self.mock()
    zsync_object_mock = self.mock()
    zsync_mock.expects(pmock.once()).method('Zsync').will(
        pmock.return_value(zsync_object_mock))
    zsync_object_mock.expects(pmock.once()).Begin(pmock.eq(remote + '.zsync'))
    zsync_object_mock.expects(pmock.once()).SubmitSource(pmock.eq(current_file))
    zsync_object_mock.expects(pmock.once()).Fetch(pmock.eq(local))
    zsyncsource.zsync = zsync_mock

    source = zsyncsource.ZSyncSource({})

    self.assertEquals(source._GetFile(remote, local, current_file), local)
    zsyncsource.os.path = path_orig
    zsyncsource.zsync = zsync_orig

  def testGetFileNoGPGEmptyMap(self):
    """Test the GetFile method with an empty map."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'
    path_orig = zsyncsource.os.path
    path = self.mock()
    path.expects(pmock.once()).exists(pmock.eq(current_file)).will(
        pmock.return_value(True))
    path.expects(pmock.once()).exists(pmock.eq(local)).will(
        pmock.return_value(False))
    zsyncsource.os.path = path

    zsync_orig = zsyncsource.zsync
    zsync_mock = self.mock()
    zsync_object_mock = self.mock()
    zsync_mock.expects(pmock.once()).method('Zsync').will(
        pmock.return_value(zsync_object_mock))
    zsync_object_mock.expects(pmock.once()).Begin(pmock.eq(remote + '.zsync'))
    zsync_object_mock.expects(pmock.once()).SubmitSource(pmock.eq(current_file))
    zsync_object_mock.expects(pmock.once()).Fetch(pmock.eq(local))
    zsyncsource.zsync = zsync_mock

    source = zsyncsource.ZSyncSource({})

    self.assertRaises(error.EmptyMap, source._GetFile, remote, local,
                      current_file)
    zsyncsource.os.path = path_orig
    zsyncsource.zsync = zsync_orig

  def testGetFileGPG(self):
    """Test the GetFile method with gpg verification."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'
    path_orig = zsyncsource.os.path
    path = self.mock()
    path.expects(pmock.once()).exists(pmock.eq(current_file)).will(
        pmock.return_value(True))
    path.expects(pmock.once()).exists(pmock.eq(local)).will(
        pmock.return_value(True))
    zsyncsource.os.path = path

    zsync_orig = zsyncsource.zsync
    zsync_mock = self.mock()
    zsync_object_mock = self.mock()
    zsync_mock.expects(pmock.once()).method('Zsync').will(
        pmock.return_value(zsync_object_mock))
    zsync_object_mock.expects(pmock.once()).Begin(pmock.eq(remote + '.zsync'))
    zsync_object_mock.expects(pmock.once()).SubmitSource(pmock.eq(current_file))
    zsync_object_mock.expects(pmock.once()).Fetch(pmock.eq(local))
    zsyncsource.zsync = zsync_mock
    self.gpg_called = False
    source = zsyncsource.ZSyncSource({'gpg': True})

    def MockGPGVerify(local_path, remote_sig):
      self.assertEquals(local_path, local)
      self.assertEquals(remote_sig, remote + '.asc')
      self.gpg_called = True
      return True

    source._GPGVerify = MockGPGVerify
    self.assertEquals(source._GetFile(remote, local, current_file), local)
    self.assertTrue(self.gpg_called)
    zsyncsource.os.path = path_orig
    zsyncsource.zsync = zsync_orig

  def testGetFileGPGFail(self):
    """Test the GetFile method with gpg verification failing."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'
    path_orig = zsyncsource.os.path
    path = self.mock()
    path.expects(pmock.once()).exists(pmock.eq(current_file)).will(
        pmock.return_value(True))
    zsyncsource.os.path = path

    zsync_orig = zsyncsource.zsync
    zsync_mock = self.mock()
    zsync_object_mock = self.mock()
    zsync_mock.expects(pmock.once()).method('Zsync').will(
        pmock.return_value(zsync_object_mock))
    zsync_object_mock.expects(pmock.once()).Begin(pmock.eq(remote + '.zsync'))
    zsync_object_mock.expects(pmock.once()).SubmitSource(pmock.eq(current_file))
    zsync_object_mock.expects(pmock.once()).Fetch(pmock.eq(local))
    zsyncsource.zsync = zsync_mock
    self.gpg_called = False
    source = zsyncsource.ZSyncSource({'gpg': True})
    def MockGPGVerify(local_path, remote_sig):
      self.gpg_called = True
      return False

    source._GPGVerify = MockGPGVerify
    self.assertRaises(error.InvalidMap, source._GetFile, remote,
                      local, current_file)
    self.assertTrue(self.gpg_called)
    zsyncsource.os.path = path_orig
    zsyncsource.zsync = zsync_orig

