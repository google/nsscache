#!/usr/bin/python2.4
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

"""Unit tests for nss_cache/update.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'


import logging
import os
import tempfile
import unittest
from nss_cache import caches
from nss_cache import config
from nss_cache import error
from nss_cache import maps
from nss_cache import update
import pmock

logging.disable(logging.CRITICAL)


class TestUpdater(pmock.MockTestCase):
  """Unit tests for Updater class."""

  def setUp(self):
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    os.rmdir(self.workdir)

  def testTimestampDir(self):
    """We read and write timestamps to the specified directory."""
    updater = update.Updater(config.MAP_PASSWORD, self.workdir, {})
    update_time = 1199149400  # epoch
    modify_time = 1199149200
    
    updater.WriteUpdateTimestamp(update_time)
    updater.WriteModifyTimestamp(modify_time)
    
    update_stamp = updater.GetUpdateTimestamp()
    modify_stamp = updater.GetModifyTimestamp()

    self.assertEqual(update_time, update_stamp,
                     msg='retrieved a different update time than we stored.')
    self.assertEqual(modify_time, modify_stamp,
                     msg='retrieved a different modify time than we stored.')
    
    os.unlink(updater.update_file)
    os.unlink(updater.modify_file)

  def testTimestampDefaultsToNone(self):
    """Missing or unreadable timestamps return None."""
    updater = update.Updater(config.MAP_PASSWORD, self.workdir, {})
    
    update_stamp = updater.GetUpdateTimestamp()
    modify_stamp = updater.GetModifyTimestamp()

    self.assertEqual(None, update_stamp,
                     msg='update time did not default to None')
    self.assertEqual(None, modify_stamp,
                     msg='modify time did not default to None')

    # touch a file, make it unreadable
    update_file = open(updater.update_file, 'w')
    modify_file = open(updater.modify_file, 'w')
    update_file.close()
    modify_file.close()
    os.chmod(updater.update_file, 0000)
    os.chmod(updater.modify_file, 0000)

    update_stamp = updater.GetUpdateTimestamp()
    modify_stamp = updater.GetModifyTimestamp()

    self.assertEqual(None, update_stamp,
                     msg='unreadable update time did not default to None')
    self.assertEqual(None, modify_stamp,
                     msg='unreadable modify time did not default to None')
    
    os.unlink(updater.update_file)
    os.unlink(updater.modify_file)


class SingleMapUpdater(pmock.MockTestCase):
  """Unit tests for SingleMapUpdater class."""

  def setUp(self):
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    os.rmdir(self.workdir)

  def testFullUpdate(self):
    """A full update reads the source, writes to cache, and updates times."""
    original_modify_stamp = 1
    new_modify_stamp = 2
    updater = update.SingleMapUpdater(config.MAP_PASSWORD, self.workdir, {})
    updater.WriteModifyTimestamp(original_modify_stamp)

    map_entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    password_map = maps.PasswdMap([map_entry])
    password_map.SetModifyTimestamp(new_modify_stamp)

    cache_mock = self.mock()
    cache_mock\
                .expects(pmock.once())\
                .WriteMap(map_data=pmock.eq(password_map))\
                .will(pmock.return_value(0))
    
    source_mock = self.mock()
    source_mock\
                 .expects(pmock.once())\
                 .GetMap(pmock.eq(config.MAP_PASSWORD),
                         location=pmock.eq(None))\
                         .will(pmock.return_value(password_map))

    self.assertEqual(0, updater.UpdateCacheFromSource(cache_mock,
                                                      source_mock,
                                                      incremental=False,
                                                      force_write=False,
                                                      location=None))
    self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
    self.assertNotEqual(updater.GetUpdateTimestamp(), None)

    if os.path.exists(updater.modify_file):
      os.unlink(updater.modify_file)
    if os.path.exists(updater.update_file):
      os.unlink(updater.update_file)

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
    updater = update.SingleMapUpdater(config.MAP_PASSWORD, self.workdir, {})
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
    cache_mock\
                .expects(pmock.once())\
                .GetMap()\
                .will(pmock.return_value(cache_map))
    cache_mock\
                .expects(pmock.once())\
                .WriteMap(map_data=pmock.functor(compare_functor))\
                .will(pmock.return_value(0))
    
    source_mock = self.mock()
    source_mock\
                 .expects(pmock.once())\
                 .GetMap(pmock.eq(config.MAP_PASSWORD),
                         location=pmock.eq(None),
                         since=pmock.eq(original_modify_stamp))\
                         .will(pmock.return_value(source_map))

    self.assertEqual(0, updater.UpdateCacheFromSource(cache_mock,
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
    self.assertNotEqual(updater.GetUpdateTimestamp(), None)

    if os.path.exists(updater.modify_file):
      os.unlink(updater.modify_file)
    if os.path.exists(updater.update_file):
      os.unlink(updater.update_file)

  def testFullUpdateOnMissingCache(self):
    """We fault to a full update if our cache is missing."""
    
    class DummyUpdater(update.SingleMapUpdater):
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
    updater.WriteModifyTimestamp(original_modify_stamp)
    
    source_mock = self.mock()
    source_mock\
                 .expects(pmock.once())\
                 .GetMap(pmock.eq(config.MAP_PASSWORD),
                         location=pmock.eq(None),
                         since=pmock.eq(original_modify_stamp))\
                         .will(pmock.return_value('first map'))
    source_mock\
                 .expects(pmock.once())\
                 .GetMap(pmock.eq(config.MAP_PASSWORD),
                         location=pmock.eq(None))\
                         .will(pmock.return_value('second map'))

    self.assertEqual(0, updater.UpdateCacheFromSource('cache',
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertTrue(updater.full_update)  # the main point of the test is here
    
    if os.path.exists(updater.modify_file):
      os.unlink(updater.modify_file)
    if os.path.exists(updater.update_file):
      os.unlink(updater.update_file)

  def testFullUpdateOnMissingTimestamp(self):
    """We fault to a full update if our modify timestamp is missing."""
    
    class DummyUpdater(update.SingleMapUpdater):
      """Stubs functions we aren't specifically testing."""
      full_update = False
      
      def FullUpdateFromMap(self, unused_cache, new_map,
                            unused_force_write=False):
        if new_map == 'second map':
          self.full_update = True
        return 0

    updater = DummyUpdater(config.MAP_PASSWORD, self.workdir, {})
    # We do not call WriteModifyTimestamp() so we force a full sync.

    source_mock = self.mock()
    source_mock\
                 .expects(pmock.once())\
                 .GetMap(pmock.eq(config.MAP_PASSWORD),
                         location=pmock.eq(None))\
                         .will(pmock.return_value('second map'))

    self.assertEqual(0, updater.UpdateCacheFromSource('cache',
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertTrue(updater.full_update)
    
    if os.path.exists(updater.modify_file):
      os.unlink(updater.modify_file)
    if os.path.exists(updater.update_file):
      os.unlink(updater.update_file)


class AutomountUpdater(pmock.MockTestCase):
  """Unit tests for AutomountUpdater class."""
  
  def setUp(self):
    # register a dummy SingleMapUpdater, because that is tested above,
    
    class DummyUpdater(update.SingleMapUpdater):
      """Stubs functions we aren't specifically testing."""
      
      def UpdateCacheFromSource(self, cache, source, unused_incremental,
                                unused_force_write, unused_location):
        """Notify our mock cache and source we were called."""
        cache._CalledUpdateCacheFromSource()
        source._CalledUpdateCacheFromSource()
        return 0
      
      def FullUpdateFromMap(self, cache, unused_new_map,
                            unused_force_write=False):
        """Notify our mock cache we were called."""
        cache._CalledFullUpdateFromMap()
        return 0
      
    self.original_single_map_updater = update.SingleMapUpdater
    update.SingleMapUpdater = DummyUpdater

    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    update.SingleMapUpdater = self.original_single_map_updater
    os.rmdir(self.workdir)

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
    source_mock\
                 .expects(pmock.once())\
                 .GetAutomountMasterMap()\
                 .will(pmock.return_value(master_map))
    # we should get called inside the DummyUpdater
    source_mock\
                 .expects(pmock.once())\
                 ._CalledUpdateCacheFromSource()
    # twice :)
    source_mock\
                 .expects(pmock.once())\
                 ._CalledUpdateCacheFromSource()

    # the auto.home cache
    cache_mock1 = self.mock()
    # GetMapLocation() is called, and set to the master map map_entry
    cache_mock1\
                 .expects(pmock.once())\
                 .GetMapLocation()\
                 .will(pmock.return_value('/etc/auto.home'))
    # we should get called inside the DummyUpdater
    cache_mock1\
                 .expects(pmock.once())\
                 ._CalledUpdateCacheFromSource()

    # the auto.auto cache
    cache_mock2 = self.mock()
    # GetMapLocation() is called, and set to the master map map_entry
    cache_mock2\
                 .expects(pmock.once())\
                 .GetMapLocation()\
                 .will(pmock.return_value('/etc/auto.auto'))
    # we should get called inside the DummyUpdater
    cache_mock2\
                 .expects(pmock.once())\
                 ._CalledUpdateCacheFromSource()
    
    # the auto.master cache
    cache_mock3 = self.mock()
    # and we get a full update by the DummyUpdater
    cache_mock3\
                 .expects(pmock.once())\
                 ._CalledFullUpdateFromMap()

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

    updater = update.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, {})
    updater.UpdateFromSource(source_mock)

    caches.base.Create = original_create

    self.assertEqual(map_entry1.location, '/etc/auto.home')
    self.assertEqual(map_entry2.location, '/etc/auto.auto')
    
if __name__ == '__main__':
  unittest.main()
