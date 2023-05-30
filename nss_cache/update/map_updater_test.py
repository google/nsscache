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

__author__ = ("vasilios@google.com (V Hoffman)", "jaq@google.com (Jamie Wilkinson)")

import os
import shutil
import tempfile
import unittest
from unittest import mock

from nss_cache.caches import caches
from nss_cache.caches import files
from nss_cache.sources import source
from nss_cache.caches import cache_factory
from nss_cache import config
from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import passwd

from nss_cache.update import map_updater


class SingleMapUpdaterTest(unittest.TestCase):
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
        """A full update reads the source, writes to cache, and updates
        times."""
        original_modify_stamp = 1
        new_modify_stamp = 2

        updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
        updater.WriteModifyTimestamp(original_modify_stamp)

        map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        password_map = passwd.PasswdMap([map_entry])
        password_map.SetModifyTimestamp(new_modify_stamp)

        cache_mock = mock.create_autospec(files.FilesCache, instance=True)
        cache_mock.WriteMap.return_value = 0

        source_mock = mock.create_autospec(source.Source, instance=True)
        source_mock.GetMap.return_value = password_map

        result = updater.UpdateCacheFromSource(
            cache_mock, source_mock, False, False, None
        )
        cache_mock.WriteMap.assert_called_with(map_data=password_map, force_write=False)
        source_mock.GetMap.assert_called_with(config.MAP_PASSWORD, location=None)
        self.assertEqual(0, result)

        self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
        self.assertNotEqual(updater.GetUpdateTimestamp(), None)

    def testFullUpdateWithEmptySourceMap(self):
        """A full update reads the source, which returns an empty map.
        Need to provide force write flag to proceed."""
        original_modify_stamp = 1
        new_modify_stamp = 2

        updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
        updater.WriteModifyTimestamp(original_modify_stamp)

        password_map = passwd.PasswdMap()
        password_map.SetModifyTimestamp(new_modify_stamp)

        cache_mock = mock.create_autospec(files.FilesCache)
        cache_mock.WriteMap.return_value = 0

        source_mock = mock.create_autospec(source.Source)
        source_mock.GetMap.return_value = password_map

        self.assertEqual(
            0, updater.UpdateCacheFromSource(cache_mock, source_mock, False, True, None)
        )

        self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
        self.assertNotEqual(updater.GetUpdateTimestamp(), None)
        cache_mock.WriteMap.assert_called_with(map_data=password_map, force_write=True)
        source_mock.GetMap.assert_called_with(config.MAP_PASSWORD, location=None)

    def testIncrementalUpdate(self):
        """An incremental update reads a partial map and merges it."""

        # Unlike in a full update, we create a cache map and a source map, and
        # let it merge them.  If it goes to write the merged map, we're good.
        # Also check that timestamps were updated, as in testFullUpdate above.

        original_modify_stamp = 1
        new_modify_stamp = 2
        updater = map_updater.MapUpdater(
            config.MAP_PASSWORD, self.workdir, {}, can_do_incremental=True
        )
        updater.WriteModifyTimestamp(original_modify_stamp)

        cache_map_entry = passwd.PasswdMapEntry({"name": "bar", "uid": 20, "gid": 20})
        cache_map = passwd.PasswdMap([cache_map_entry])
        cache_map.SetModifyTimestamp(original_modify_stamp)

        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMap.return_value = cache_map
        cache_mock.WriteMap.return_value = 0

        source_map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        source_map = passwd.PasswdMap([source_map_entry])
        source_map.SetModifyTimestamp(new_modify_stamp)

        source_mock = mock.create_autospec(source.Source)
        source_mock.GetMap.return_value = source_map

        self.assertEqual(
            0,
            updater.UpdateCacheFromSource(
                cache_mock,
                source_mock,
                incremental=True,
                force_write=False,
                location=None,
            ),
        )
        self.assertEqual(updater.GetModifyTimestamp(), new_modify_stamp)
        self.assertNotEqual(updater.GetUpdateTimestamp(), None)
        cache_mock.WriteMap.assert_called()
        source_mock.GetMap.assert_called_with(
            config.MAP_PASSWORD, location=None, since=original_modify_stamp
        )

    def testFullUpdateOnMissingCache(self):
        """We fault to a full update if our cache is missing."""

        original_modify_stamp = 1
        updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
        updater.WriteModifyTimestamp(original_modify_stamp)

        source_mock = mock.create_autospec(source.Source)
        # Try incremental first, try full second.
        source_mock.GetMap.side_effect = ["first map", "second map"]

        updater = map_updater.MapUpdater(
            config.MAP_PASSWORD, self.workdir, {}, can_do_incremental=True
        )
        updater.GetModifyTimestamp = mock.Mock(return_value=original_modify_stamp)
        # force a cache not found on incremental
        updater._IncrementalUpdateFromMap = mock.Mock(side_effect=error.CacheNotFound)
        updater.FullUpdateFromMap = mock.Mock(return_value=0)

        self.assertEqual(
            0,
            updater.UpdateCacheFromSource(
                "cache", source_mock, incremental=True, force_write=False, location=None
            ),
        )

        get_map_expected_calls = [
            mock.call(config.MAP_PASSWORD, location=None, since=original_modify_stamp),
            mock.call(config.MAP_PASSWORD, location=None),
        ]
        source_mock.GetMap.assert_has_calls(get_map_expected_calls)
        updater._IncrementalUpdateFromMap.assert_called_with("cache", "first map")
        updater.FullUpdateFromMap.assert_called_with(mock.ANY, "second map", False)

    def testFullUpdateOnMissingTimestamp(self):
        """We fault to a full update if our modify timestamp is missing."""

        updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
        # We do not call WriteModifyTimestamp() so we force a full sync.

        source_mock = mock.create_autospec(source.Source)
        source_mock.GetMap.return_value = "second map"
        updater = map_updater.MapUpdater(config.MAP_PASSWORD, self.workdir, {})
        updater.FullUpdateFromMap = mock.Mock(return_value=0)

        self.assertEqual(
            0, updater.UpdateCacheFromSource("cache", source_mock, True, False, None)
        )

        updater.FullUpdateFromMap.assert_called_with(mock.ANY, "second map", False)


class MapAutomountUpdaterTest(unittest.TestCase):
    """Unit tests for AutomountUpdater class."""

    def setUp(self):
        super(MapAutomountUpdaterTest, self).setUp()
        self.workdir = tempfile.mkdtemp()

    def tearDown(self):
        super(MapAutomountUpdaterTest, self).tearDown()
        os.rmdir(self.workdir)

    def testInit(self):
        """An automount object correctly sets map-specific attributes."""
        updater = map_updater.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, {})
        self.assertEqual(updater.local_master, False)

        conf = {map_updater.AutomountUpdater.OPT_LOCAL_MASTER: "yes"}
        updater = map_updater.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, conf)
        self.assertEqual(updater.local_master, True)

        conf = {map_updater.AutomountUpdater.OPT_LOCAL_MASTER: "no"}
        updater = map_updater.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, conf)
        self.assertEqual(updater.local_master, False)

    @mock.patch.object(map_updater, "MapUpdater", autospec=True)
    def testUpdate(self, map_updater_factory):
        """An update gets a master map and updates each entry."""
        map_entry1 = automount.AutomountMapEntry()
        map_entry2 = automount.AutomountMapEntry()
        map_entry1.key = "/home"
        map_entry2.key = "/auto"
        map_entry1.location = "ou=auto.home,ou=automounts"
        map_entry2.location = "ou=auto.auto,ou=automounts"
        master_map = automount.AutomountMap([map_entry1, map_entry2])

        source_mock = mock.create_autospec(source.Source)
        # return the master map
        source_mock.GetAutomountMasterMap.return_value = master_map

        # the auto.home cache
        cache_home = mock.create_autospec(caches.Cache)
        # GetMapLocation() is called, and set to the master map map_entry
        cache_home.GetMapLocation.return_value = "/etc/auto.home"

        # the auto.auto cache
        cache_auto = mock.create_autospec(caches.Cache)
        # GetMapLocation() is called, and set to the master map map_entry
        cache_auto.GetMapLocation.return_value = "/etc/auto.auto"

        # the auto.master cache
        cache_master = mock.create_autospec(caches.Cache)

        cache_factory.Create = mock.Mock(
            side_effect=[cache_home, cache_auto, cache_master]
        )

        map_updater_mock = map_updater_factory.return_value
        map_updater_mock.UpdateCacheFromSource.return_value = 0
        map_updater_mock.FullUpdateFromMap.return_value = 0

        updater = map_updater.AutomountUpdater(config.MAP_AUTOMOUNT, self.workdir, {})
        updater.UpdateFromSource(source_mock)

        self.assertEqual(map_entry1.location, "/etc/auto.home")
        self.assertEqual(map_entry2.location, "/etc/auto.auto")
        cache_factory.Create.assert_has_calls(
            [
                mock.call(mock.ANY, "automount", automount_mountpoint="/home"),
                mock.call(mock.ANY, "automount", automount_mountpoint="/auto"),
                mock.call(mock.ANY, "automount", automount_mountpoint=None),
            ]
        )
        map_updater_factory.assert_has_calls(
            [
                mock.call(
                    config.MAP_AUTOMOUNT, self.workdir, {}, automount_mountpoint="/home"
                ),
                mock.call().UpdateCacheFromSource(
                    cache_home, source_mock, True, False, "ou=auto.home,ou=automounts"
                ),
                mock.call(
                    config.MAP_AUTOMOUNT, self.workdir, {}, automount_mountpoint="/auto"
                ),
                mock.call().UpdateCacheFromSource(
                    cache_auto, source_mock, True, False, "ou=auto.auto,ou=automounts"
                ),
                mock.call(config.MAP_AUTOMOUNT, self.workdir, {}),
                mock.call().FullUpdateFromMap(cache_master, master_map),
            ]
        )

    @mock.patch.object(map_updater, "MapUpdater", autospec=True)
    def testUpdateNoMaster(self, map_updater_factory):
        """An update skips updating the master map, and approprate sub maps."""
        source_entry1 = automount.AutomountMapEntry()
        source_entry2 = automount.AutomountMapEntry()
        source_entry1.key = "/home"
        source_entry2.key = "/auto"
        source_entry1.location = "ou=auto.home,ou=automounts"
        source_entry2.location = "ou=auto.auto,ou=automounts"
        source_master = automount.AutomountMap([source_entry1, source_entry2])

        local_entry1 = automount.AutomountMapEntry()
        local_entry2 = automount.AutomountMapEntry()
        local_entry1.key = "/home"
        local_entry2.key = "/auto"
        local_entry1.location = "/etc/auto.home"
        local_entry2.location = "/etc/auto.null"
        local_master = automount.AutomountMap([local_entry1, local_entry2])

        source_mock = mock.create_autospec(source.Source)
        # return the source master map
        source_mock.GetAutomountMasterMap.return_value = source_master

        # the auto.home cache
        cache_home = mock.create_autospec(caches.Cache)
        # GetMapLocation() is called, and set to the master map map_entry
        cache_home.GetMapLocation.return_value = "/etc/auto.home"

        # the auto.auto cache
        cache_auto = mock.create_autospec(caches.Cache)
        # GetMapLocation() is called, and set to the master map map_entry
        cache_auto.GetMapLocation.return_value = "/etc/auto.auto"

        # the auto.master cache, which should not be written to
        cache_master = mock.create_autospec(caches.Cache)
        cache_master.GetMap.return_value = local_master

        cache_factory.Create = mock.Mock(
            side_effect=[cache_master, cache_home, cache_auto]
        )

        skip = map_updater.AutomountUpdater.OPT_LOCAL_MASTER
        updater = map_updater.AutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, {skip: "yes"}
        )

        updater_home = map_updater_factory.return_value
        updater_home.UpdateCacheFromSource.return_value = 0

        updater.UpdateFromSource(source_mock)

        cache_factory.Create.assert_has_calls(
            [
                mock.call(mock.ANY, mock.ANY, automount_mountpoint=None),
                mock.call(mock.ANY, mock.ANY, automount_mountpoint="/home"),
                mock.call(mock.ANY, mock.ANY, automount_mountpoint="/auto"),
            ]
        )
        map_updater_factory.assert_has_calls(
            [
                mock.call(
                    config.MAP_AUTOMOUNT,
                    self.workdir,
                    {"local_automount_master": "yes"},
                    automount_mountpoint="/home",
                ),
                mock.call().UpdateCacheFromSource(
                    cache_home, source_mock, True, False, "ou=auto.home,ou=automounts"
                ),
            ]
        )


class AutomountUpdaterTest(unittest.TestCase):
    def setUp(self):
        super(AutomountUpdaterTest, self).setUp()
        self.workdir = tempfile.mkdtemp()

    def tearDown(self):
        super(AutomountUpdaterTest, self).tearDown()
        shutil.rmtree(self.workdir)

    def testUpdateCatchesMissingMaster(self):
        """Gracefully handle a missing local master maps."""
        # use an empty master map from the source, to avoid mocking out already
        # tested code
        master_map = automount.AutomountMap()

        source_mock = mock.Mock()
        source_mock.GetAutomountMasterMap.return_value = master_map

        cache_mock = mock.create_autospec(caches.Cache)
        # raise error on GetMap()
        cache_mock.GetMap.side_effect = error.CacheNotFound

        skip = map_updater.AutomountUpdater.OPT_LOCAL_MASTER
        cache_options = {skip: "yes"}

        cache_factory.Create = mock.Mock(return_value=cache_mock)

        updater = map_updater.AutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, cache_options
        )

        return_value = updater.UpdateFromSource(source_mock)

        self.assertEqual(return_value, 1)

        cache_factory.Create.assert_called_with(
            cache_options, "automount", automount_mountpoint=None
        )


if __name__ == "__main__":
    unittest.main()
