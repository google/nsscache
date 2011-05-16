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

"""Unit tests for nss_cache/update.files.py."""

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)',
              'blaedd@google.com (David MacKinnon)')


import os
import shutil
import tempfile
import time
import unittest

import pmock

from nss_cache import caches
from nss_cache import config
from nss_cache import error
from nss_cache import maps
from nss_cache import update


class SingleMapUpdaterTest(pmock.MockTestCase):
  """Unit tests for SingleMapUpdater class."""

  def setUp(self):
    self.workdir = tempfile.mkdtemp()
    self.workdir2 = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.exists(self.updater.modify_file):
      os.unlink(self.updater.modify_file)
    if os.path.exists(self.updater.update_file):
      os.unlink(self.updater.update_file)
    shutil.rmtree(self.workdir)
    shutil.rmtree(self.workdir2)

  def testFullUpdate(self):
    """A full update reads the source, writes to cache, and updates times."""
    original_modify_stamp = time.gmtime(1)
    new_modify_stamp = time.gmtime(2)

    # Construct an updater.
    self.updater = update.files.SingleMapUpdater(config.MAP_PASSWORD,
                                                 self.workdir,
                                                 {'name': 'files',
                                                  'dir': self.workdir2})
    self.updater.WriteModifyTimestamp(original_modify_stamp)

    # Construct the cache.
    cache = caches.files.FilesPasswdMapHandler({'dir': self.workdir2})
    map_entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    password_map = maps.PasswdMap()
    password_map.SetModifyTimestamp(new_modify_stamp)
    password_map.Add(map_entry)
    cache.Write(password_map)

    # Construct a fake source.
    class MockSource(pmock.Mock):
      def GetFile(self, map_name, dst_file, current_file, location=None):
        f = open(dst_file, 'w')
        f.write('root:x:0:0:root:/root:/bin/bash\n')
        f.close()
        os.utime(dst_file, (1, 2))
        return dst_file

    source_mock = MockSource()
    self.assertEqual(0, self.updater.UpdateCacheFromSource(cache,
                                                           source_mock,
                                                           force_write=False,
                                                           location=None))
    self.assertEqual(new_modify_stamp, self.updater.GetModifyTimestamp())
    self.assertNotEqual(None, self.updater.GetUpdateTimestamp())

  def testFullUpdateOnEmptyCache(self):
    """A full update as above, but the initial cache is empty."""
    original_modify_stamp = time.gmtime(1)
    new_modify_stamp = time.gmtime(2)
    # Construct an updater
    self.updater = update.files.SingleMapUpdater(config.MAP_PASSWORD,
                                                 self.workdir,
                                                 {'name': 'files',
                                                  'dir': self.workdir2})
    self.updater.WriteModifyTimestamp(original_modify_stamp)

    # Construct a cache
    cache = caches.files.FilesPasswdMapHandler({'dir': self.workdir2})

    class MockSource(pmock.Mock):
      def GetFile(self, map_name, dst_file, current_file, location=None):
        assert location is None
        assert map_name == config.MAP_PASSWORD
        f = open(dst_file, 'w')
        f.write('root:x:0:0:root:/root:/bin/bash\n')
        f.close()
        os.utime(dst_file, (1, 2))
        return dst_file

    source_mock = MockSource()
    self.assertEqual(0, self.updater.UpdateCacheFromSource(cache,
                                                           source_mock,
                                                           force_write=False,
                                                           location=None))
    self.assertEqual(new_modify_stamp, self.updater.GetModifyTimestamp())
    self.assertNotEqual(None, self.updater.GetUpdateTimestamp())

  def testFullUpdateOnEmptySource(self):
    """A full update as above, but instead, the initial source is empty."""
    original_modify_stamp = time.gmtime(1)
    new_modify_stamp = time.gmtime(2)
    # Construct an updater
    self.updater = update.files.SingleMapUpdater(config.MAP_PASSWORD,
                                                 self.workdir,
                                                 {'name': 'files',
                                                  'dir': self.workdir2})
    self.updater.WriteModifyTimestamp(original_modify_stamp)

    # Construct a cache
    cache = caches.files.FilesPasswdMapHandler({'dir': self.workdir2})
    map_entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    password_map = maps.PasswdMap()
    password_map.SetModifyTimestamp(new_modify_stamp)
    password_map.Add(map_entry)
    cache.Write(password_map)

    class MockSource(pmock.Mock):
      def GetFile(self, map_name, dst_file, current_file, location=None):
        assert location is None
        assert map_name == config.MAP_PASSWORD
        f = open(dst_file, 'w')
        f.write('')
        f.close()
        os.utime(dst_file, (1, 2))
        return dst_file

    source_mock = MockSource()
    self.assertRaises(error.EmptyMap,
                      self.updater.UpdateCacheFromSource,
                      cache,
                      source_mock,
                      force_write=False,
                      location=None)
    self.assertNotEqual(new_modify_stamp, self.updater.GetModifyTimestamp())
    self.assertEqual(None, self.updater.GetUpdateTimestamp())

  def testFullUpdateOnEmptySourceForceWrite(self):
    """A full update as above, but instead, the initial source is empty."""
    original_modify_stamp = time.gmtime(1)
    new_modify_stamp = time.gmtime(2)
    # Construct an updater
    self.updater = update.files.SingleMapUpdater(config.MAP_PASSWORD,
                                                 self.workdir,
                                                 {'name': 'files',
                                                  'dir': self.workdir2})
    self.updater.WriteModifyTimestamp(original_modify_stamp)

    # Construct a cache
    cache = caches.files.FilesPasswdMapHandler({'dir': self.workdir2})
    map_entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    password_map = maps.PasswdMap()
    password_map.SetModifyTimestamp(new_modify_stamp)
    password_map.Add(map_entry)
    cache.Write(password_map)

    class MockSource(pmock.Mock):
      def GetFile(self, map_name, dst_file, current_file, location=None):
        assert location is None
        assert map_name == config.MAP_PASSWORD
        f = open(dst_file, 'w')
        f.write('')
        f.close()
        os.utime(dst_file, (1, 2))
        return dst_file

    source_mock = MockSource()
    self.assertEqual(0, self.updater.UpdateCacheFromSource(cache,
                                                           source_mock,
                                                           force_write=True,
                                                           location=None))
    self.assertEqual(new_modify_stamp, self.updater.GetModifyTimestamp())
    self.assertNotEqual(None, self.updater.GetUpdateTimestamp())


class AutomountUpdaterTest(pmock.MockTestCase):
  """Unit tests for AutomountUpdater class."""

  class DummyUpdater(update.files.SingleMapUpdater):
    """Stubs functions we aren't specifically testing."""

    def UpdateCacheFromSource(self, cache, source, unused_incremental,
                              unused_force_write, unused_location=None):
      """Notify our mock cache and source we were called."""
      cache._CalledUpdateCacheFromSource()
      source._CalledUpdateCacheFromSource()
      return 0

    def FullUpdateFromMap(self, cache, unused_new_map,
                          unused_force_write=False):
      """Notify our mock cache we were called."""
      cache._CalledFullUpdateFromMap()
      return 0

  def setUp(self):
    # register a dummy SingleMapUpdater, because that is tested above,
    self.original_single_map_updater = update.files.SingleMapUpdater
    update.files.SingleMapUpdater = AutomountUpdaterTest.DummyUpdater

    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    update.files.SingleMapUpdater = self.original_single_map_updater
    os.rmdir(self.workdir)

  def testInit(self):
    """An automount object correctly sets map-specific attributes."""
    updater = update.files.AutomountUpdater(config.MAP_AUTOMOUNT,
                                            self.workdir, {})
    self.assertEqual(updater.local_master, False)

    conf = {update.files.AutomountUpdater.OPT_LOCAL_MASTER: 'yes'}
    updater = update.files.AutomountUpdater(config.MAP_AUTOMOUNT,
                                            self.workdir, conf)
    self.assertEqual(updater.local_master, True)

    conf = {update.files.AutomountUpdater.OPT_LOCAL_MASTER: 'no'}
    updater = update.files.AutomountUpdater(config.MAP_AUTOMOUNT,
                                            self.workdir, conf)
    self.assertEqual(updater.local_master, False)

  def testUpdate(self):
    """An update gets a master map and updates each entry."""
    map_entry1 = maps.AutomountMapEntry()
    map_entry2 = maps.AutomountMapEntry()
    map_entry1.key = '/home'
    map_entry2.key = '/auto'
    map_entry1.location = 'ou=auto.home,ou=automounts'
    map_entry2.location = 'ou=auto.auto,ou=automounts'
    master_map = maps.AutomountMap([map_entry1, map_entry2])

    source_mock = self.mock()
    # return the master map
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.method('GetAutomountMasterFile')
    invocation.will(pmock.return_value(master_map))
    # we should get called inside the DummyUpdater, too.
    invocation = source_mock.expects(pmock.once())
    invocation._CalledUpdateCacheFromSource()
    # twice :)
    invocation = source_mock.expects(pmock.once())
    invocation._CalledUpdateCacheFromSource()

    # the auto.home cache
    cache_mock1 = self.mock()
    # GetMapLocation() is called, and set to the master map map_entry
    invocation = cache_mock1.expects(pmock.once()).GetMapLocation()
    invocation.will(pmock.return_value('/etc/auto.home'))
    # we should get called inside the DummyUpdater
    cache_mock1.expects(pmock.once())._CalledUpdateCacheFromSource()

    # the auto.auto cache
    cache_mock2 = self.mock()
    # GetMapLocation() is called, and set to the master map map_entry
    invocation = cache_mock2.expects(pmock.once()).GetMapLocation()
    invocation.will(pmock.return_value('/etc/auto.auto'))
    # we should get called inside the DummyUpdater
    invocation = cache_mock2.expects(pmock.once())
    invocation._CalledUpdateCacheFromSource()

    # the auto.master cache
    cache_mock3 = self.mock()
    # and we get a full update by the DummyUpdater
    cache_mock3.expects(pmock.once()).GetMap().will(
        pmock.return_value(master_map))
    cache_mock3.expects(pmock.once())._CalledFullUpdateFromMap()

    # key automount_mountpoint to the right cache mocks, where None is
    # what we expect for the master_map
    cache_mocks = {'/home': cache_mock1,
                   '/auto': cache_mock2,
                   None: cache_mock3}

    # Create needs to return our mock_caches
    def DummyCreate(unused_cache_options, unused_map_name,
                    automount_mountpoint=None):
      # the order of the master_map iterable is not predictable, so we use the
      # automount_mountpoint as the key to return the right one.
      return cache_mocks[automount_mountpoint]

    original_create = caches.base.Create
    caches.base.Create = DummyCreate

    options = {'name': 'files', 'dir': self.workdir}
    updater = update.files.AutomountUpdater(config.MAP_AUTOMOUNT,
                                            self.workdir, options)
    updater.UpdateFromSource(source_mock)

    caches.base.Create = original_create

    self.assertEqual(map_entry1.location, '/etc/auto.home')
    self.assertEqual(map_entry2.location, '/etc/auto.auto')

  def testUpdateNoMaster(self):
    """An update skips updating the master map, and approprate sub maps."""
    source_entry1 = maps.AutomountMapEntry()
    source_entry2 = maps.AutomountMapEntry()
    source_entry1.key = '/home'
    source_entry2.key = '/auto'
    source_entry1.location = 'ou=auto.home,ou=automounts'
    source_entry2.location = 'ou=auto.auto,ou=automounts'
    source_master = maps.AutomountMap([source_entry1, source_entry2])

    local_entry1 = maps.AutomountMapEntry()
    local_entry2 = maps.AutomountMapEntry()
    local_entry1.key = '/home'
    local_entry2.key = '/auto'
    local_entry1.location = '/etc/auto.home'
    local_entry2.location = '/etc/auto.null'
    local_master = maps.AutomountMap([local_entry1, local_entry2])
    source_mock = self.mock()
    invocation = source_mock.expects(pmock.at_least_once())
    invocation._CalledUpdateCacheFromSource()
    # we should get called inside the DummyUpdater, too.

    # the auto.home cache
    cache_mock1 = self.mock()
    # GetMapLocation() is called, and set to the master map map_entry
    invocation = cache_mock1.expects(pmock.at_least_once()).GetMapLocation()
    invocation.will(pmock.return_value('/etc/auto.home'))
    # we should get called inside the DummyUpdater
    cache_mock1.expects(pmock.at_least_once())._CalledUpdateCacheFromSource()

    # the auto.auto cache
    cache_mock2 = self.mock()
    # GetMapLocation() is called, and set to the master map map_entry
    invocation = cache_mock2.expects(pmock.at_least_once()).GetMapLocation()
    invocation.will(pmock.return_value('/etc/auto.auto'))
    invocation = cache_mock2.expects(
        pmock.at_least_once())._CalledUpdateCacheFromSource()
    # the auto.master cache, which should not be written to
    cache_mock3 = self.mock()
    invocation = cache_mock3.expects(pmock.once())
    invocation = invocation.method('GetMap')
    invocation.will(pmock.return_value(local_master))
    invocation = cache_mock3.expects(pmock.once())
    invocation = invocation.method('GetMap')
    invocation.will(pmock.return_value(local_master))

    cache_mocks = {'/home': cache_mock1, '/auto': cache_mock2,
                   None: cache_mock3}

    # Create needs to return our mock_caches
    def DummyCreate(unused_cache_options, unused_map_name,
                    automount_mountpoint=None):
      # the order of the master_map iterable is not predictable, so we use the
      # automount_mountpoint as the key to return the right one.
      return cache_mocks[automount_mountpoint]

    original_create = caches.base.Create
    caches.base.Create = DummyCreate

    skip = update.files.AutomountUpdater.OPT_LOCAL_MASTER
    options = {skip: 'yes', 'dir': self.workdir}
    updater = update.files.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir,
                                            options)
    updater.UpdateFromSource(source_mock)

    caches.base.Create = original_create

  def testUpdateCatchesMissingMaster(self):
    """Gracefully handle a missing local master map."""
    # use an empty master map from the source, to avoid mocking out already
    # tested code
    source_mock = self.mock()

    cache_mock = self.mock()
    # raise error on GetMap()
    invocation = cache_mock.expects(pmock.once()).GetMap()
    invocation.will(pmock.raise_exception(error.CacheNotFound))

    # Create needs to return our mock_cache
    def DummyCreate(unused_cache_options, unused_map_name,
                    automount_mountpoint=None):
      # the order of the master_map iterable is not predictable, so we use the
      # automount_mountpoint as the key to return the right one.
      return cache_mock

    original_create = caches.base.Create
    caches.base.Create = DummyCreate

    skip = update.files.AutomountUpdater.OPT_LOCAL_MASTER
    options = {skip: 'yes', 'dir': self.workdir}
    updater = update.files.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir,
                                            options)

    return_value = updater.UpdateFromSource(source_mock)

    self.assertEqual(return_value, 1)

    caches.base.Create = original_create

if __name__ == '__main__':
  unittest.main()
