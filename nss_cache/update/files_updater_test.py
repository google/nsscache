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
"""Unit tests for nss_cache/files_updater.py."""

__author__ = (
    "vasilios@google.com (V Hoffman)",
    "jaq@google.com (Jamie Wilkinson)",
    "blaedd@google.com (David MacKinnon)",
)

import os
import shutil
import tempfile
import unittest
from unittest import mock

from nss_cache import config
from nss_cache import error

from nss_cache.caches import cache_factory
from nss_cache.caches import files
from nss_cache.maps import automount
from nss_cache.maps import passwd
from nss_cache.sources import source

from nss_cache.update import files_updater


class SingleFileUpdaterTest(unittest.TestCase):
    """Unit tests for FileMapUpdater."""

    def setUp(self):
        super(SingleFileUpdaterTest, self).setUp()
        self.workdir = tempfile.mkdtemp()
        self.workdir2 = tempfile.mkdtemp()

    def tearDown(self):
        super(SingleFileUpdaterTest, self).tearDown()
        shutil.rmtree(self.workdir)
        shutil.rmtree(self.workdir2)

    @unittest.skip("timestamp isnt propagaged correctly")
    def testFullUpdate(self):
        original_modify_stamp = 1
        new_modify_stamp = 2

        # Construct a fake source.
        def GetFile(map_name, dst_file, current_file, location):
            print(("GetFile: %s" % dst_file))
            f = open(dst_file, "w")
            f.write("root:x:0:0:root:/root:/bin/bash\n")
            f.close()
            os.utime(dst_file, (1, 2))
            os.system("ls -al %s" % dst_file)
            return dst_file

        source_mock = mock.create_autospec(source.FileSource)
        source_mock.GetFile.side_effect = GetFile

        # Construct the cache.
        cache = files.FilesPasswdMapHandler({"dir": self.workdir2})
        map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        password_map = passwd.PasswdMap()
        password_map.SetModifyTimestamp(new_modify_stamp)
        password_map.Add(map_entry)
        cache.Write(password_map)

        updater = files_updater.FileMapUpdater(
            config.MAP_PASSWORD, self.workdir, {"name": "files", "dir": self.workdir2}
        )
        updater.WriteModifyTimestamp(original_modify_stamp)

        self.assertEqual(
            0,
            updater.UpdateCacheFromSource(
                cache, source_mock, force_write=False, location=None
            ),
        )

        self.assertEqual(new_modify_stamp, updater.GetModifyTimestamp())
        self.assertNotEqual(None, updater.GetUpdateTimestamp())
        source_mock.GetFile.assert_called_with(
            config.MAP_PASSWORD,
            mock.ANY,
            current_file=mock.ANY,
            location=mock.ANY,
        )

    @unittest.skip("raises EmptyMap, is that intended?")
    def testFullUpdateOnEmptyCache(self):
        """A full update as above, but the initial cache is empty."""
        original_modify_stamp = 1
        new_modify_stamp = 2
        # Construct an updater
        self.updater = files_updater.FileMapUpdater(
            config.MAP_PASSWORD, self.workdir, {"name": "files", "dir": self.workdir2}
        )
        self.updater.WriteModifyTimestamp(original_modify_stamp)

        # Construct a cache
        cache = files.FilesPasswdMapHandler({"dir": self.workdir2})

        def GetFileEffects(map_name, dst_file, current_file, location):
            f = open(dst_file, "w")
            f.write("root:x:0:0:root:/root:/bin/bash\n")
            f.close()
            os.utime(dst_file, (1, 2))
            return dst_file

        source_mock = mock.create_autospec(source.FileSource)
        source_mock.GetFile.side_effects = GetFileEffects

        self.assertEqual(
            0,
            self.updater.UpdateCacheFromSource(
                cache, source_mock, force_write=False, location=None
            ),
        )

        self.assertEqual(new_modify_stamp, self.updater.GetModifyTimestamp())
        self.assertNotEqual(None, self.updater.GetUpdateTimestamp())
        source_mock.GetFile.assert_called_with(
            config.MAP_PASSWORD, mock.ANY, mock.ANY, location=None
        )

    def testFullUpdateOnEmptySource(self):
        """A full update as above, but instead, the initial source is empty."""
        original_modify_stamp = 1
        new_modify_stamp = 2
        # Construct an updater
        self.updater = files_updater.FileMapUpdater(
            config.MAP_PASSWORD, self.workdir, {"name": "files", "dir": self.workdir2}
        )
        self.updater.WriteModifyTimestamp(original_modify_stamp)

        # Construct a cache
        cache = files.FilesPasswdMapHandler({"dir": self.workdir2})
        map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        password_map = passwd.PasswdMap()
        password_map.SetModifyTimestamp(new_modify_stamp)
        password_map.Add(map_entry)
        cache.Write(password_map)

        source_mock = mock.create_autospec(source.FileSource)
        source_mock.GetFile.return_value = None

        self.assertRaises(
            error.EmptyMap,
            self.updater.UpdateCacheFromSource,
            cache,
            source_mock,
            force_write=False,
            location=None,
        )

        self.assertNotEqual(new_modify_stamp, self.updater.GetModifyTimestamp())
        self.assertEqual(None, self.updater.GetUpdateTimestamp())
        source_mock.GetFile.assert_called_with(
            config.MAP_PASSWORD,
            mock.ANY,
            current_file=mock.ANY,
            location=None,
        )

    def testFullUpdateOnEmptySourceForceWrite(self):
        """A full update as above, but instead, the initial source is empty."""
        original_modify_stamp = 1
        new_modify_stamp = 2
        # Construct an updater
        self.updater = files_updater.FileMapUpdater(
            config.MAP_PASSWORD, self.workdir, {"name": "files", "dir": self.workdir2}
        )
        self.updater.WriteModifyTimestamp(original_modify_stamp)

        # Construct a cache
        cache = files.FilesPasswdMapHandler({"dir": self.workdir2})
        map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        password_map = passwd.PasswdMap()
        password_map.SetModifyTimestamp(new_modify_stamp)
        password_map.Add(map_entry)
        cache.Write(password_map)

        source_mock = mock.create_autospec(source.FileSource)
        source_mock.GetFile.return_value = None

        self.assertEqual(
            0,
            self.updater.UpdateCacheFromSource(
                cache, source_mock, force_write=True, location=None
            ),
        )

        self.assertNotEqual(original_modify_stamp, self.updater.GetModifyTimestamp())
        self.assertNotEqual(None, self.updater.GetUpdateTimestamp())
        source_mock.GetFile.assert_called_with(
            config.MAP_PASSWORD,
            mock.ANY,
            current_file=mock.ANY,
            location=None,
        )


@unittest.skip("disabled")
class AutomountUpdaterTest(unittest.TestCase):
    """Unit tests for FileAutomountUpdater class."""

    def setUp(self):
        super(AutomountUpdaterTest, self).setUp()
        self.workdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.workdir)
        super(AutomountUpdaterTest, self).tearDown()

    def testInit(self):
        """An automount object correctly sets map-specific attributes."""
        updater = files_updater.FileAutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, {}
        )
        self.assertEqual(updater.local_master, False)

        conf = {files_updater.FileAutomountUpdater.OPT_LOCAL_MASTER: "yes"}
        updater = files_updater.FileAutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, conf
        )
        self.assertEqual(updater.local_master, True)

        conf = {files_updater.FileAutomountUpdater.OPT_LOCAL_MASTER: "no"}
        updater = files_updater.FileAutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, conf
        )
        self.assertEqual(updater.local_master, False)

    @mock.patch.object(cache_factory, "Create")
    def testUpdate(self, cache_factory_create_mock):
        """An update gets a master map and updates each entry."""
        map_entry1 = automount.AutomountMapEntry()
        map_entry2 = automount.AutomountMapEntry()
        map_entry1.key = "/home"
        map_entry2.key = "/auto"
        map_entry1.location = "ou=auto.home,ou=automounts"
        map_entry2.location = "ou=auto.auto,ou=automounts"
        master_map = automount.AutomountMap([map_entry1, map_entry2])

        source_mock = mock.Mock()
        source_mock.GetAutomountMasterFile.return_value = master_map

        # the auto.home cache
        cache_mock1 = mock.create_autospec(files.FilesCache)
        cache_mock1.GetCacheFilename.return_value = None
        cache_mock1.GetMapLocation.return_value = "/etc/auto.home"

        # the auto.auto cache
        cache_mock2 = mock.create_autospec(files.FilesCache)
        cache_mock2.GetMapLocation.return_value = "/etc/auto.auto"
        cache_mock2.GetCacheFilename.return_value = None

        # the auto.master cache
        cache_mock3 = mock.create_autospec(files.FilesCache)
        cache_mock3.GetMap.return_value = master_map

        cache_factory_create_mock.Create.side_effect = [
            cache_mock3,
            cache_mock2,
            cache_mock1,
        ]

        options = {"name": "files", "dir": self.workdir}
        updater = files_updater.FileAutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, options
        )
        updater.UpdateFromSource(source_mock)

        self.assertEqual(map_entry1.location, "/etc/auto.home")
        self.assertEqual(map_entry2.location, "/etc/auto.auto")
        cache_factory_create_mock.assert_has_calls(
            [
                mock.call(mock.ANY, mock.ANY, None),
                mock.call(mock.ANY, mock.ANY, automount_mountpoint="/auto"),
                mock.call(mock.ANY, mock.ANY, automount_mountpoint="/home"),
            ]
        )

    @mock.patch.object(cache_factory, "Create")
    def testUpdateNoMaster(self, cache_factory_create_mock):
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

        source_mock = mock.Mock()
        # we should get called inside the DummyUpdater, too.

        # the auto.home cache
        cache_mock1 = mock.Mock()
        # GetMapLocation() is called, and set to the master map map_entry
        cache_mock1.GetMapLocation.return_value = "/etc/auto.home"

        # the auto.auto cache
        cache_mock2 = mock.Mock()
        # GetMapLocation() is called, and set to the master map map_entry
        cache_mock2.GetMapLocation.return_value = "/etc/auto.auto"
        # the auto.master cache, which should not be written to
        cache_mock3 = mock.Mock()
        cache_mock3.GetMap.return_value = local_master

        cache_factory_create_mock.side_effect = [cache_mock1, cache_mock2, cache_mock3]

        skip = files_updater.FileAutomountUpdater.OPT_LOCAL_MASTER
        options = {skip: "yes", "dir": self.workdir}
        updater = files_updater.FileAutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, options
        )
        updater.UpdateFromSource(source_mock)

        source_mock._CalledUpdateCacheFromSource.assert_called_once()
        # we should get called inside the DummyUpdater
        cache_mock1._CalledUpdateCacheFromSource.assert_called_once()
        cache_mock2._CalledUpdateCacheFromSource().assert_called_once()

    @mock.patch.object(cache_factory, "Create")
    def testUpdateCatchesMissingMaster(self, cache_factory_create_mock):
        """Gracefully handle a missing local master map."""
        # use an empty master map from the source, to avoid mocking out already
        # tested code
        source_mock = mock.Mock

        cache_mock = mock.Mock()
        # raise error on GetMap()
        cache_mock.GetMap.side_effect = error.CacheNotFound

        cache_factory_create_mock.return_value = cache_mock

        skip = files_updater.FileAutomountUpdater.OPT_LOCAL_MASTER
        options = {skip: "yes", "dir": self.workdir}
        updater = files_updater.FileAutomountUpdater(
            config.MAP_AUTOMOUNT, self.workdir, options
        )

        self.assertEqual(1, updater.UpdateFromSource(source_mock))


if __name__ == "__main__":
    unittest.main()
