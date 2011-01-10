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

"""Unit tests for nss_cache/update.maps.py."""

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)')


import logging
import os
import pmock
import tempfile
import unittest
from nss_cache import caches
from nss_cache import config
from nss_cache import error
from nss_cache import maps
from nss_cache.update import maps

logging.disable(logging.CRITICAL)


class SingleMapUpdaterTest(pmock.MockTestCase):
  """Unit tests for SingleMapUpdater class."""

  def setUp(self):
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    if os.path.exists(self.updater.modify_file):
      os.unlink(self.updater.modify_file)
    if os.path.exists(self.updater.update_file):
      os.unlink(self.updater.update_file)
    os.rmdir(self.workdir)

  def testFullUpdate(self):
    """A full update reads the source, writes to cache, and updates times."""
    original_modify_stamp = 1
    new_modify_stamp = 2
    updater = maps.SingleMapUpdater(config.MAP_PASSWORD, self.workdir, {})
    self.updater = updater
    updater.WriteModifyTimestamp(original_modify_stamp)

    map_entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    password_map = maps.PasswdMap([map_entry])
    password_map.SetModifyTimestamp(new_modify_stamp)

    cache_mock = self.mock()
    invocation = cache_mock.expects(pmock.once())
    invocation = invocation.WriteMap(map_data=pmock.eq(password_map))
    invocation.will(pmock.return_value(0))
    
    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetMap(pmock.eq(config.MAP_PASSWORD),
                                   location=pmock.eq(None))
    invocation.will(pmock.return_value(password_map))

    self.assertEqual(0, updater.UpdateCacheFromSource(cache_mock,
                                                      source_mock,
                                                      incremental=False,
                                                      force_write=False,
                                                      location=None))
    self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
    self.assertNotEqual(updater.GetUpdateTimestamp(), None)

  def testIncrementalUpdate(self):
    """An incremental update reads a partial map and merges it."""
    # Unlike in a full update, we create a cache map and a source map, and
    # let it merge them.  If it goes to write the merged map, we're good.
    # Also check that timestamps were updated, as in testFullUpdate above.
    
    class MapFunctor(object):
      """Verifies the test maps have been merged."""
      
      def __call__(self, map_object):
        if len(map_object) < 2:
          return False
        return True

    original_modify_stamp = 1
    new_modify_stamp = 2
    updater = maps.SingleMapUpdater(config.MAP_PASSWORD, self.workdir, {})
    self.updater = updater
    updater.WriteModifyTimestamp(original_modify_stamp)

    cache_map_entry = maps.PasswdMapEntry({'name': 'bar', 'uid': 20, 'gid': 20})
    cache_map = maps.PasswdMap([cache_map_entry])
    cache_map.SetModifyTimestamp(original_modify_stamp)

    source_map_entry = maps.PasswdMapEntry({'name': 'foo',
                                            'uid': 10,
                                            'gid': 10})
    source_map = maps.PasswdMap([source_map_entry])
    source_map.SetModifyTimestamp(new_modify_stamp)

    compare_functor = MapFunctor()

    cache_mock = self.mock()
    invocation = cache_mock.expects(pmock.once())
    invocation = invocation.GetMap().will(pmock.return_value(cache_map))
    
    invocation = cache_mock.expects(pmock.once())
    invocation = invocation.WriteMap(map_data=pmock.functor(compare_functor))
    invocation.will(pmock.return_value(0))
    
    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetMap(pmock.eq(config.MAP_PASSWORD),
                                   location=pmock.eq(None),
                                   since=pmock.eq(original_modify_stamp))
    invocation.will(pmock.return_value(source_map))

    self.assertEqual(0, updater.UpdateCacheFromSource(cache_mock,
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
    self.assertNotEqual(updater.GetUpdateTimestamp(), None)

  def testFullUpdateOnMissingCache(self):
    """We fault to a full update if our cache is missing."""
    
    class DummyUpdater(maps.SingleMapUpdater):
      """Stubs functions we aren't specifically testing."""
      full_update = False

      def IncrementalUpdateFromMap(self, cache, new_map):
        raise error.CacheNotFound

      def FullUpdateFromMap(self, unused_cache, new_map,
                            unused_force_write=False):
        if new_map == 'second map':
          self.full_update = True
        return 0

    original_modify_stamp = 1
    updater = DummyUpdater(config.MAP_PASSWORD, self.workdir, {})
    self.updater = updater
    updater.WriteModifyTimestamp(original_modify_stamp)
    
    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetMap(pmock.eq(config.MAP_PASSWORD),
                                   location=pmock.eq(None),
                                   since=pmock.eq(original_modify_stamp))
    invocation.will(pmock.return_value('first map'))
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetMap(pmock.eq(config.MAP_PASSWORD),
                                   location=pmock.eq(None))
    invocation.will(pmock.return_value('second map'))

    self.assertEqual(0, updater.UpdateCacheFromSource('cache',
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertTrue(updater.full_update)  # the main point of the test is here

  def testFullUpdateOnMissingTimestamp(self):
    """We fault to a full update if our modify timestamp is missing."""

    class DummyUpdater(maps.SingleMapUpdater):
      """Stubs functions we aren't specifically testing."""
      full_update = False

      def FullUpdateFromMap(self, unused_cache, new_map,
                            unused_force_write=False):
        if new_map == 'second map':
          self.full_update = True
        return 0

    updater = DummyUpdater(config.MAP_PASSWORD, self.workdir, {})
    self.updater = updater
    # We do not call WriteModifyTimestamp() so we force a full sync.

    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetMap(pmock.eq(config.MAP_PASSWORD),
                                   location=pmock.eq(None))
    invocation.will(pmock.return_value('second map'))

    self.assertEqual(0, updater.UpdateCacheFromSource('cache',
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertTrue(updater.full_update)


class AutomountUpdaterTest(pmock.MockTestCase):
  """Unit tests for AutomountUpdater class."""

  class DummyUpdater(maps.SingleMapUpdater):
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

    self.original_single_map_updater = maps.SingleMapUpdater
    maps.SingleMapUpdater = AutomountUpdaterTest.DummyUpdater

    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    maps.SingleMapUpdater = self.original_single_map_updater
    os.rmdir(self.workdir)

  def testInit(self):
    """An automount object correctly sets map-specific attributes."""
    updater = maps.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, {})
    self.assertEqual(updater.local_master, False)

    conf = {maps.AutomountUpdater.OPT_LOCAL_MASTER: 'yes'}
    updater = maps.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, conf)
    self.assertEqual(updater.local_master, True)
    
    conf = {maps.AutomountUpdater.OPT_LOCAL_MASTER: 'no'}
    updater = maps.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, conf)
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
    invocation = invocation.GetAutomountMasterMap()
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
    cache_mock3.expects(pmock.once())._CalledFullUpdateFromMap()

    # key automount_info to the right cache mocks, where None is what we expect
    # for the master_map
    cache_mocks = {'/home': cache_mock1,
                   '/auto': cache_mock2,
                   None: cache_mock3}
    
    # Create needs to return our mock_caches
    def DummyCreate(unused_cache_options, unused_map_name, automount_info=None):
      # the order of the master_map iterable is not predictable, so we use the
      # automount_info as the key to return the right one.
      return cache_mocks[automount_info]

    original_create = caches.base.Create
    caches.base.Create = DummyCreate

    updater = maps.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, {})
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
    # return the source master map
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetAutomountMasterMap()
    invocation.will(pmock.return_value(source_master))
    # we should get called inside the DummyUpdater, too.
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

    # the auto.master cache, which should not be written to
    cache_mock3 = self.mock()
    invocation = cache_mock3.expects(pmock.once())
    invocation = invocation.GetMap()
    invocation.will(pmock.return_value(local_master))

    cache_mocks = {'/home': cache_mock1, '/auto': cache_mock2,
                   None: cache_mock3}
    
    # Create needs to return our mock_caches
    def DummyCreate(unused_cache_options, unused_map_name, automount_info=None):
      # the order of the master_map iterable is not predictable, so we use the
      # automount_info as the key to return the right one.
      return cache_mocks[automount_info]

    original_create = caches.base.Create
    caches.base.Create = DummyCreate

    skip = maps.AutomountUpdater.OPT_LOCAL_MASTER
    updater = maps.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir,
                                    {skip: 'yes'})
    updater.UpdateFromSource(source_mock)

    caches.base.Create = original_create

  def testUpdateCatchesMissingMaster(self):
    """Gracefully handle a missing local master maps."""
    # use an empty master map from the source, to avoid mocking out already
    # tested code
    master_map = maps.AutomountMap()

    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation = invocation.GetAutomountMasterMap()
    invocation.will(pmock.return_value(master_map))

    cache_mock = self.mock()
    # raise error on GetMap()
    invocation = cache_mock.expects(pmock.once()).GetMap()
    invocation.will(pmock.raise_exception(error.CacheNotFound))

    # Create needs to return our mock_cache
    def DummyCreate(unused_cache_options, unused_map_name, automount_info=None):
      # the order of the master_map iterable is not predictable, so we use the
      # automount_info as the key to return the right one.
      return cache_mock

    original_create = caches.base.Create
    caches.base.Create = DummyCreate

    skip = maps.AutomountUpdater.OPT_LOCAL_MASTER
    updater = maps.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir,
                                    {skip: 'yes'})

    return_value = updater.UpdateFromSource(source_mock)

    self.assertEqual(return_value, 1)

    caches.base.Create = original_create

if __name__ == '__main__':
  unittest.main()
