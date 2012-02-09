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
import os
import unittest

import mox
import pyme.core
import zsync

from nss_cache import error
from nss_cache.sources import zsyncsource
from nss_cache.util import curl



class TestZsyncsource(mox.MoxTestBase):

  def setUp(self):
    """Initialize a basic config dict."""
    super(TestZsyncsource, self).setUp()
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
    self.mox.StubOutWithMock(curl, 'CurlFetch')
    curl.CurlFetch('remote_sig', source.conn, source.log).AndReturn((200, 'headers', 'body'))

    sig = 1
    signed = 2
    self.mox.StubOutWithMock(pyme.core, 'Data')
    pyme.core.Data('body').AndReturn(sig)
    pyme.core.Data(file='local_file').AndReturn(signed)

    result = self.mox.CreateMockAnything()
    result.signatures = [ self.mox.CreateMockAnything() ]
    result.signatures[0].fpr = 'AAA'
    key_mock = self.mox.CreateMockAnything()
    key_mock.uids = [ self.mox.CreateMockAnything() ]
    key_mock.uids[0].uid = 'Foobar'
    context = self.mox.CreateMockAnything()
    context.op_verify(sig, signed, None)
    context.op_verify_result().AndReturn(result)
    context.get_key('AAA', 0).AndReturn(key_mock)

    self.mox.ReplayAll()

    self.assertTrue(source._GPGVerify('local_file', 'remote_sig', context))

  def testGPGVerifyNoMatch(self):
    """Test the GPG Verify method."""
    conf = {'gpg_fingerprint': 'AAA',
            'gpg': True}
    source = zsyncsource.ZSyncSource(conf)

    self.mox.StubOutWithMock(curl, 'CurlFetch')
    curl.CurlFetch('remote_sig', source.conn, source.log).AndReturn((200, 'headers', 'body'))

    sig = 1
    signed = 2
    self.mox.StubOutWithMock(pyme.core, 'Data')
    pyme.core.Data('body').AndReturn(sig)
    pyme.core.Data(file='local_file').AndReturn(signed)

    result = self.mox.CreateMockAnything()
    result.signatures = [ self.mox.CreateMockAnything() ]
    result.signatures[0].fpr = 'BBB'
    result.signatures[0].next = None
    key_mock = self.mox.CreateMockAnything()
    key_mock.uids = self.mox.CreateMockAnything()
    key_mock.uids.uid = 'Foobar'
    context = self.mox.CreateMockAnything()
    context.op_verify(sig, signed, None)
    context.op_verify_result().AndReturn(result)

    self.mox.ReplayAll()

    self.assertFalse(source._GPGVerify('local_file', 'remote_sig', context))

  def testGPGVerifyMatchMultiple(self):
    """Test the GPG Verify method when there are multiple signatures."""

    conf = {'gpg_fingerprint': 'AAA',
            'gpg': True}
    source = zsyncsource.ZSyncSource(conf)

    self.mox.StubOutWithMock(curl, 'CurlFetch')
    curl.CurlFetch('remote_sig', source.conn, source.log).AndReturn((200, 'headers', 'body'))

    sig = 1
    signed = 2
    self.mox.StubOutWithMock(pyme.core, 'Data')
    pyme.core.Data('body').AndReturn(sig)
    pyme.core.Data(file='local_file').AndReturn(signed)

    result = self.mox.CreateMockAnything()
    result.signatures = [ self.mox.CreateMockAnything() ]
    result.signatures[0].fpr = 'BBB'
    result2 = self.mox.CreateMockAnything()
    result.signatures[0].next = result2
    result2.fpr = 'AAA'
    key_mock = self.mox.CreateMockAnything()
    key_mock.uids = [ self.mox.CreateMockAnything() ]
    key_mock.uids[0].uid = 'Foobar'

    context = self.mox.CreateMockAnything()
    context.op_verify(sig, signed, None)
    context.op_verify_result().AndReturn(result)
    context.get_key('AAA', 0).AndReturn(key_mock)

    self.mox.ReplayAll()

    self.assertTrue(source._GPGVerify('local_file', 'remote_sig', context))

  def testGetFileNoGPG(self):
    """Test the GetFile method."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'

    self.mox.StubOutWithMock(os.path, 'exists')
    os.path.exists(current_file).AndReturn(True)
    os.path.exists(local).AndReturn(True)


    zsync_mock = self.mox.CreateMockAnything()
    zsync_mock.Begin(remote + '.zsync')
    zsync_mock.SubmitSource(current_file)
    zsync_mock.Fetch(local)

    self.mox.StubOutWithMock(zsync, 'Zsync')
    zsync.Zsync(conn=mox.IgnoreArg(), retry_delay=5, retry_max=3).AndReturn(zsync_mock)

    self.mox.ReplayAll()

    source = zsyncsource.ZSyncSource({})

    self.assertEquals(source._GetFile(remote, local, current_file), local)

  def testGetFileNoGPGEmptyMap(self):
    """Test the GetFile method with an empty map."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'

    self.mox.StubOutWithMock(os.path, 'exists')
    os.path.exists(current_file).AndReturn(True)
    os.path.exists(local).AndReturn(False)

    zsync_mock = self.mox.CreateMockAnything()
    zsync_mock.Begin(remote + '.zsync')
    zsync_mock.SubmitSource(current_file)
    zsync_mock.Fetch(local)

    self.mox.StubOutWithMock(zsync, 'Zsync')
    zsync.Zsync(conn=mox.IgnoreArg(), retry_delay=5, retry_max=3).AndReturn(zsync_mock)

    source = zsyncsource.ZSyncSource({})

    self.mox.ReplayAll()

    self.assertRaises(error.EmptyMap, source._GetFile, remote, local,
                      current_file)

  def testGetFileGPG(self):
    """Test the GetFile method with gpg verification."""
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'

    self.mox.StubOutWithMock(os.path, 'exists')
    os.path.exists(current_file).AndReturn(True)
    os.path.exists(local).AndReturn(True)

    zsync_object_mock = self.mox.CreateMock(zsync.Zsync)
    zsync_object_mock.Begin(remote + '.zsync')
    zsync_object_mock.SubmitSource(current_file)
    zsync_object_mock.Fetch(local)
    self.mox.StubOutWithMock(zsync, 'Zsync')
    zsync.Zsync(conn=mox.IgnoreArg(),
                retry_delay=5, retry_max=3).AndReturn(zsync_object_mock)

    source = zsyncsource.ZSyncSource({'gpg': True})

    self.mox.StubOutWithMock(source, '_GPGVerify')
    source._GPGVerify(local, remote + '.asc').AndReturn(True)

    self.mox.ReplayAll()

    self.assertEquals(local,
                      source._GetFile(remote, local, current_file))

  def testGetFileGPGFail(self):
    """Test the GetFile method with gpg verification failing."""
    # TODO(jaq): the duplicate calls in this test indicate that GetFileViaZsync is bad.
    remote = 'https://www/nss_cache'
    local = '/tmp/nss_cache'
    current_file = '/etc/nss_cache'

    self.mox.StubOutWithMock(os.path, 'exists')
    os.path.exists(current_file).AndReturn(True)
    os.path.exists(local).AndReturn(True)
    os.path.exists(local).AndReturn(True)    

    zsync_mock1 = self.mox.CreateMock(zsync.Zsync)
    zsync_mock1.Begin(remote + '.zsync')
    zsync_mock1.SubmitSource(current_file)
    zsync_mock1.Fetch(local)

    zsync_mock2 = self.mox.CreateMock(zsync.Zsync)
    zsync_mock2.Begin(remote + '.zsync')
    zsync_mock2.Fetch(local)

    self.mox.StubOutWithMock(zsync, 'Zsync')
    zsync.Zsync(conn=mox.IgnoreArg(), retry_delay=5, retry_max=3).AndReturn(zsync_mock1)
    zsync.Zsync(conn=mox.IgnoreArg(), retry_delay=5, retry_max=3).AndReturn(zsync_mock2)

    source = zsyncsource.ZSyncSource({'gpg': True})

    self.mox.StubOutWithMock(source, '_GPGVerify')
    source._GPGVerify(mox.IgnoreArg(), mox.IgnoreArg()).AndReturn(False)
    source._GPGVerify(mox.IgnoreArg(), mox.IgnoreArg()).AndReturn(False)    

    self.mox.ReplayAll()

    self.assertRaises(error.InvalidMap, source._GetFile,
                      remote, local, current_file)


if __name__ == '__main__':
  unittest.main()
