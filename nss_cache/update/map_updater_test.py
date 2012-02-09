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

"""Unit tests for nss_cache/map_updater.py."""

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)')


import os
import shutil
import tempfile
import time
import unittest

import mox

from nss_cache.caches import caches
from nss_cache.caches import files
from nss_cache.sources import source
from nss_cache.caches import cache_factory
from nss_cache import config
from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import passwd

from nss_cache.update import map_updater

class SingleMapUpdaterTest(mox.MoxTestBase):
  """Unit tests for FileMapUpdater class."""

  def setUp(self):
    super(SingleMapUpdaterTest, self).setUp()
    self.workdir = tempfile.mkdtemp()
    self.workdir2 = tempfile.mkdtemp()

  def tearDown(self):
    super(SingleMapUpdaterTest, self).tearDown()
    shutil.rmtree(self.workdir)
    shutil.rmtree(self.workdir2)

  def testFullUpdate(self):
    """A full update reads the source, writes to cache, and updates times."""
    original_modify_stamp = time.gmtime(1)
    new_modify_stamp = time.gmtime(2)

    updater = map_updater.MapUpdater(
        config.MAP_PASSWORD, self.workdir, {})
    updater.WriteModifyTimestamp(original_modify_stamp)

    map_entry = passwd.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    password_map = passwd.PasswdMap([map_entry])
    password_map.SetModifyTimestamp(new_modify_stamp)

    cache_mock = self.mox.CreateMock(files.FilesCache)
    cache_mock.WriteMap(map_data=password_map).AndReturn(0)

    source_mock = self.mox.CreateMock(source.Source)
    source_mock.GetMap(config.MAP_PASSWORD,
                       location=None).AndReturn(password_map)

    self.mox.ReplayAll()

    self.assertEqual(0, updater.UpdateCacheFromSource(cache_mock,
                                                      source_mock,
                                                      False,
                                                      False,
                                                      None))
    self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
    self.assertNotEqual(updater.GetUpdateTimestamp(), None)

  def testIncrementalUpdate(self):
    """An incremental update reads a partial map and merges it."""
    # Unlike in a full update, we create a cache map and a source map, and
    # let it merge them.  If it goes to write the merged map, we're good.
    # Also check that timestamps were updated, as in testFullUpdate above.

    def compare_function(map_object):
      print map_object
      return len(map_object) == 2

    original_modify_stamp = time.gmtime(1)
    new_modify_stamp = time.gmtime(2)
    updater = map_updater.MapUpdater(
        config.MAP_PASSWORD, self.workdir, {}, can_do_incremental=True)
    updater.WriteModifyTimestamp(original_modify_stamp)

    cache_map_entry = passwd.PasswdMapEntry({'name': 'bar', 'uid': 20, 'gid': 20})
    cache_map = passwd.PasswdMap([cache_map_entry])
    cache_map.SetModifyTimestamp(original_modify_stamp)

    cache_mock = self.mox.CreateMock(caches.Cache)
    cache_mock.GetMap().AndReturn(cache_map)
    cache_mock.WriteMap(map_data=mox.Func(compare_function)).AndReturn(0)

    source_map_entry = passwd.PasswdMapEntry({'name': 'foo',
                                              'uid': 10,
                                              'gid': 10})
    source_map = passwd.PasswdMap([source_map_entry])
    source_map.SetModifyTimestamp(new_modify_stamp)

    source_mock = self.mox.CreateMock(source.Source)
    source_mock.GetMap(config.MAP_PASSWORD,
                       location=None,
                       since=original_modify_stamp).AndReturn(source_map)

    self.mox.ReplayAll()

    self.assertEqual(0, updater.UpdateCacheFromSource(cache_mock,
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))
    self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
    self.assertNotEqual(updater.GetUpdateTimestamp(), None)

  def testFullUpdateOnMissingCache(self):
    """We fault to a full update if our cache is missing."""

    original_modify_stamp = time.gmtime(1)
    updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
    updater.WriteModifyTimestamp(original_modify_stamp)

    source_mock = self.mox.CreateMock(source.Source)
    # Try incremental first.
    source_mock.GetMap(config.MAP_PASSWORD,
                       location=None,
                       since=original_modify_stamp).AndReturn('first map')
    # Try full second.
    source_mock.GetMap(config.MAP_PASSWORD,
                       location=None).AndReturn('second map')

    updater = map_updater.MapUpdater(config.MAP_PASSWORD,
                                     self.workdir,
                                     {},
                                     can_do_incremental=True)
    self.mox.StubOutWithMock(updater, 'GetModifyTimestamp')
    updater.GetModifyTimestamp().AndReturn(original_modify_stamp)
    self.mox.StubOutWithMock(updater, '_IncrementalUpdateFromMap')
    # force a cache not found on incremental
    updater._IncrementalUpdateFromMap('cache', 'first map').AndRaise(error.CacheNotFound)
    self.mox.StubOutWithMock(updater, 'FullUpdateFromMap')
    updater.FullUpdateFromMap(mox.IgnoreArg(), 'second map', False).AndReturn(0)

    self.mox.ReplayAll()

    self.assertEqual(0, updater.UpdateCacheFromSource('cache',
                                                      source_mock,
                                                      incremental=True,
                                                      force_write=False,
                                                      location=None))

  def testFullUpdateOnMissingTimestamp(self):
    """We fault to a full update if our modify timestamp is missing."""

    updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
    # We do not call WriteModifyTimestamp() so we force a full sync.

    source_mock = self.mox.CreateMock(source.Source)
    source_mock.GetMap(config.MAP_PASSWORD,
                       location=None).AndReturn('second map')
    updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
    self.mox.StubOutWithMock(updater, 'FullUpdateFromMap')
    updater.FullUpdateFromMap(mox.IgnoreArg(), 'second map', False).AndReturn(0)

    self.mox.ReplayAll()
    self.assertEqual(0, updater.UpdateCacheFromSource('cache',
                                                      source_mock,
                                                      True,
                                                      False,
                                                      None))


class MapAutomountUpdaterTest(mox.MoxTestBase):
  """Unit tests for AutomountUpdater class."""

  def setUp(self):
    super(MapAutomountUpdaterTest, self).setUp()
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    super(MapAutomountUpdaterTest, self).tearDown()
    os.rmdir(self.workdir)

  def testInit(self):
    """An automount object correctly sets map-specific attributes."""
    updater = map_updater.AutomountUpdater(
        config.MAP_AUTOMOUNT, self.workdir, {})
    self.assertEqual(updater.local_master, False)

    conf = {map_updater.AutomountUpdater.OPT_LOCAL_MASTER: 'yes'}
    updater = map_updater.AutomountUpdater(
        config.MAP_AUTOMOUNT, self.workdir, conf)
    self.assertEqual(updater.local_master, True)

    conf = {map_updater.AutomountUpdater.OPT_LOCAL_MASTER: 'no'}
    updater = map_updater.AutomountUpdater(
        config.MAP_AUTOMOUNT, self.workdir, conf)
    self.assertEqual(updater.local_master, False)

  def testUpdate(self):
    """An update gets a master map and updates each entry."""
    map_entry1 = automount.AutomountMapEntry()
    map_entry2 = automount.AutomountMapEntry()
    map_entry1.key = '/home'
    map_entry2.key = '/auto'
    map_entry1.location = 'ou=auto.home,ou=automounts'
    map_entry2.location = 'ou=auto.auto,ou=automounts'
    master_map = automount.AutomountMap([map_entry1, map_entry2])

    source_mock = self.mox.CreateMock(source.Source)
    # return the master map
    source_mock.GetAutomountMasterMap().AndReturn(master_map)

    # the auto.home cache
    cache_home = self.mox.CreateMock(caches.Cache)
    # GetMapLocation() is called, and set to the master map map_entry
    cache_home.GetMapLocation().AndReturn('/etc/auto.home')

    # the auto.auto cache
    cache_auto = self.mox.CreateMock(caches.Cache)
    # GetMapLocation() is called, and set to the master map map_entry
    cache_auto.GetMapLocation().AndReturn('/etc/auto.auto')

    # the auto.master cache
    cache_master = self.mox.CreateMock(caches.Cache)

    self.mox.StubOutWithMock(cache_factory, 'Create')
    cache_factory.Create(mox.IgnoreArg(), mox.IgnoreArg(), automount_mountpoint='/auto').AndReturn(cache_auto)
    cache_factory.Create(mox.IgnoreArg(), mox.IgnoreArg(), automount_mountpoint='/home').AndReturn(cache_home)
    cache_factory.Create(mox.IgnoreArg(), mox.IgnoreArg(), automount_mountpoint=None).AndReturn(cache_master)

    updater = map_updater.AutomountUpdater(
        config.MAP_AUTOMOUNT, self.workdir, {})

    self.mox.StubOutClassWithMocks(map_updater, 'MapUpdater')
    updater_auto = map_updater.MapUpdater(config.MAP_AUTOMOUNT, self.workdir, {}, automount_mountpoint='/auto')
    updater_auto.UpdateCacheFromSource(cache_auto, source_mock, True, False, 'ou=auto.auto,ou=automounts').AndReturn(0)
    updater_home = map_updater.MapUpdater(config.MAP_AUTOMOUNT, self.workdir, {}, automount_mountpoint='/home')
    updater_home.UpdateCacheFromSource(cache_home, source_mock, True, False, 'ou=auto.home,ou=automounts').AndReturn(0)
    updater_master = map_updater.MapUpdater(config.MAP_AUTOMOUNT, self.workdir, {})
    updater_master.FullUpdateFromMap(cache_master, master_map).AndReturn(0)

    self.mox.ReplayAll()

    updater.UpdateFromSource(source_mock)

    self.assertEqual(map_entry1.location, '/etc/auto.home')
    self.assertEqual(map_entry2.location, '/etc/auto.auto')

  def testUpdateNoMaster(self):
    """An update skips updating the master map, and approprate sub maps."""
    source_entry1 = automount.AutomountMapEntry()
    source_entry2 = automount.AutomountMapEntry()
    source_entry1.key = '/home'
    source_entry2.key = '/auto'
    source_entry1.location = 'ou=auto.home,ou=automounts'
    source_entry2.location = 'ou=auto.auto,ou=automounts'
    source_master = automount.AutomountMap([source_entry1, source_entry2])

    local_entry1 = automount.AutomountMapEntry()
    local_entry2 = automount.AutomountMapEntry()
    local_entry1.key = '/home'
    local_entry2.key = '/auto'
    local_entry1.location = '/etc/auto.home'
    local_entry2.location = '/etc/auto.null'
    local_master = automount.AutomountMap([local_entry1, local_entry2])

    source_mock = self.mox.CreateMock(source.Source)
    # return the source master map
    source_mock.GetAutomountMasterMap().AndReturn(source_master)

    # the auto.home cache
    cache_home = self.mox.CreateMock(caches.Cache)
    # GetMapLocation() is called, and set to the master map map_entry
    cache_home.GetMapLocation().AndReturn('/etc/auto.home')

    # the auto.auto cache
    cache_auto = self.mox.CreateMock(caches.Cache)
    # GetMapLocation() is called, and set to the master map map_entry
    cache_auto.GetMapLocation().AndReturn('/etc/auto.auto')

    # the auto.master cache, which should not be written to
    cache_master = self.mox.CreateMock(caches.Cache)
    cache_master.GetMap().AndReturn(local_master)

    self.mox.StubOutWithMock(cache_factory, 'Create')
    cache_factory.Create(mox.IgnoreArg(), mox.IgnoreArg(), automount_mountpoint=None).AndReturn(cache_master)
    cache_factory.Create(mox.IgnoreArg(), mox.IgnoreArg(), automount_mountpoint='/auto').AndReturn(cache_auto)
    cache_factory.Create(mox.IgnoreArg(), mox.IgnoreArg(), automount_mountpoint='/home').AndReturn(cache_home)

    skip = map_updater.AutomountUpdater.OPT_LOCAL_MASTER
    updater = map_updater.AutomountUpdater(
        config.MAP_AUTOMOUNT, self.workdir, {skip: 'yes'})

    self.mox.StubOutClassWithMocks(map_updater, 'MapUpdater')
    updater_home = map_updater.MapUpdater(config.MAP_AUTOMOUNT, self.workdir, {'local_automount_master': 'yes'}, automount_mountpoint='/home')
    updater_home.UpdateCacheFromSource(cache_home, source_mock, True, False, 'ou=auto.home,ou=automounts').AndReturn(0)

    self.mox.ReplayAll()

    updater.UpdateFromSource(source_mock)


class AutomountUpdaterMoxTest(mox.MoxTestBase):

  def setUp(self):
    super(AutomountUpdaterMoxTest, self).setUp()
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    super(AutomountUpdaterMoxTest, self).tearDown()
    shutil.rmtree(self.workdir)

  def testUpdateCatchesMissingMaster(self):
    """Gracefully handle a missing local master maps."""
    # use an empty master map from the source, to avoid mocking out already
    # tested code
    master_map = automount.AutomountMap()

    source_mock = self.mox.CreateMockAnything()
    source_mock.GetAutomountMasterMap().AndReturn(master_map)

    cache_mock = self.mox.CreateMock(caches.Cache)
    # raise error on GetMap()
    cache_mock.GetMap().AndRaise(error.CacheNotFound)

    skip = map_updater.AutomountUpdater.OPT_LOCAL_MASTER
    cache_options = {skip: 'yes'}

    self.mox.StubOutWithMock(cache_factory, 'Create')
    cache_factory.Create(
        cache_options, 'automount',
        automount_mountpoint=None).AndReturn(cache_mock)

    self.mox.ReplayAll()

    updater = map_updater.AutomountUpdater(
        config.MAP_AUTOMOUNT, self.workdir, cache_options)

    return_value = updater.UpdateFromSource(source_mock)

    self.assertEqual(return_value, 1)

if __name__ == '__main__':
  unittest.main()
