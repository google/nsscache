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
"""Unit tests for nss_cache/command.py."""

__author__ = (
    "jaq@google.com (Jamie Wilkinson)",
    "vasilios@google.com (Vasilios Hoffman)",
)

import grp
import os
import pwd
import shutil
from io import StringIO
import sys
import tempfile
import time
import unittest
from unittest import mock

from nss_cache import command
from nss_cache import config
from nss_cache import error
from nss_cache import lock
from nss_cache import nss

from nss_cache.caches import caches
from nss_cache.caches import cache_factory
from nss_cache.maps import automount
from nss_cache.maps import passwd
from nss_cache.sources import source
from nss_cache.sources import source_factory

from nss_cache.update import updater
from nss_cache.update import files_updater
from nss_cache.update import map_updater


class TestCommand(unittest.TestCase):
    """Unit tests for the Command class."""

    def testRunCommand(self):
        c = command.Command()
        self.assertRaises(NotImplementedError, c.Run, [], {})

    @mock.patch.object(lock, "PidFile")
    def testLock(self, pidfile_mock):
        pidfile_mock.return_value.Lock.side_effect = ["LOCK", "MORLOCK"]
        pidfile_mock.return_value.Locked.return_value = True

        c = command.Command()

        # First test that we create a lock and lock it.
        self.assertEqual("LOCK", c._Lock())

        # Then we test that we lock the existing one a second time.
        self.assertEqual("MORLOCK", c._Lock())

    @mock.patch.object(lock, "PidFile")
    def testForceLock(self, pidfile_mock):
        pidfile_mock.return_value.Lock.return_value = "LOCK"
        pidfile_mock.return_value.Locked.return_value = True

        c = command.Command()

        self.assertEqual("LOCK", c._Lock(force=True))

    @mock.patch.object(lock, "PidFile")
    def testUnlock(self, pidfile_mock):
        pidfile_mock.return_value.Lock.return_value = "LOCK"
        pidfile_mock.return_value.Locked.side_effect = [True, False]

        c = command.Command()
        c._Lock()
        c._Unlock()

        pidfile_mock.return_value.Unlock.assert_called_once()

    def testCommandHelp(self):
        c = command.Command()
        self.assertNotEqual(None, c)
        self.assertEqual(None, c.Help())

    def testDummyCommand(self):
        class Dummy(command.Command):
            """Dummy docstring for dummy command."""

            def Run(self):
                return 0

        c = Dummy()
        self.assertTrue(isinstance(c, command.Command))
        self.assertNotEqual(None, c.Help())


class TestUpdateCommand(unittest.TestCase):
    """Unit tests for the Update command class."""

    def setUp(self):
        super(TestUpdateCommand, self).setUp()
        self.workdir = tempfile.mkdtemp()

        class DummyConfig(object):
            pass

        self.conf = DummyConfig()
        self.conf.options = {
            config.MAP_PASSWORD: config.MapOptions(),
            config.MAP_AUTOMOUNT: config.MapOptions(),
        }
        self.conf.options[config.MAP_PASSWORD].cache = {
            "name": "dummy",
            "dir": self.workdir,
        }
        self.conf.options[config.MAP_PASSWORD].source = {"name": "dummy"}
        self.conf.options[config.MAP_AUTOMOUNT].cache = {
            "name": "dummy",
            "dir": self.workdir,
        }
        self.conf.options[config.MAP_AUTOMOUNT].source = {"name": "dummy"}
        self.conf.timestamp_dir = self.workdir
        self.conf.lockfile = None

    def tearDown(self):
        super(TestUpdateCommand, self).tearDown()
        shutil.rmtree(self.workdir)

    def testConstructor(self):
        c = command.Update()
        self.assertNotEqual(None, c)

    def testHelp(self):
        c = command.Update()
        self.assertNotEqual(None, c.Help())

    def testRunWithNoParameters(self):
        c = command.Update()

        c.UpdateMaps = mock.Mock(return_value=0)

        self.assertEqual(0, c.Run(self.conf, []))

        c.UpdateMaps.assert_called_with(
            self.conf, incremental=True, force_lock=False, force_write=False
        )

    def testRunWithBadParameters(self):
        c = command.Update()
        # Trap stderr so the unit test runs clean,
        # since unit test status is printed on stderr.
        dev_null = StringIO()
        stderr = sys.stderr
        sys.stderr = dev_null
        self.assertEqual(2, c.Run(None, ["--invalid"]))
        sys.stderr = stderr

    def testRunWithFlags(self):
        c = command.Update()

        c.UpdateMaps = mock.Mock(return_value=0)

        self.assertEqual(
            0,
            c.Run(
                self.conf,
                ["-m", config.MAP_PASSWORD, "-f", "--force-write", "--force-lock"],
            ),
        )
        self.assertEqual(["passwd"], self.conf.maps)
        c.UpdateMaps.assert_called_with(
            self.conf, incremental=False, force_lock=True, force_write=True
        )

    @mock.patch.object(cache_factory, "Create")
    @mock.patch.object(source_factory, "Create")
    @mock.patch.object(lock, "PidFile")
    def testUpdateSingleMaps(
        self, pidfile_mock, source_factory_create_mock, cache_factory_create_mock
    ):
        pidfile_mock.return_value.Lock.return_value = True
        pidfile_mock.return_value.Locked.return_value = True

        self.conf.maps = [config.MAP_PASSWORD]
        self.conf.cache = "dummy"

        modify_stamp = 1
        map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        passwd_map = passwd.PasswdMap([map_entry])
        passwd_map.SetModifyTimestamp(modify_stamp)

        source_mock = mock.create_autospec(source.Source)
        source_mock.GetMap.return_value = passwd_map
        source_factory_create_mock.return_value = source_mock

        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.WriteMap.return_value = 0
        cache_factory_create_mock.return_value = cache_mock

        c = command.Update()
        self.assertEqual(
            0, c.UpdateMaps(self.conf, incremental=True, force_write=False)
        )

        pidfile_mock.assert_has_calls(
            [
                mock.call(filename=None),
                mock.call().Lock(force=False),
                # mock.call().Locked(),
                # mock.call().Unlock(),
            ]
        )
        source_mock.GetMap.assert_called_with(config.MAP_PASSWORD, location=None)
        source_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].source
        )
        cache_mock.WriteMap.assert_called_with(map_data=passwd_map, force_write=False)
        cache_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].cache, config.MAP_PASSWORD
        )

    @mock.patch.object(cache_factory, "Create")
    @mock.patch.object(source_factory, "Create")
    @mock.patch.object(lock, "PidFile")
    def testUpdateAutomounts(
        self, pidfile_mock, source_factory_create_mock, cache_factory_create_mock
    ):
        pidfile_mock.return_value.Lock.return_value = True
        pidfile_mock.return_value.Locked.return_value = True

        self.conf.maps = [config.MAP_AUTOMOUNT]
        self.conf.cache = "dummy"

        modify_stamp = 1
        map_entry = automount.AutomountMapEntry()
        map_entry.key = "/home"
        map_entry.location = "foo"
        automount_map = automount.AutomountMap([map_entry])
        automount_map.SetModifyTimestamp(modify_stamp)

        source_mock = mock.create_autospec(source.Source)
        source_mock.GetAutomountMasterMap.return_value = automount_map
        source_mock.GetMap.return_value = automount_map

        source_factory_create_mock.return_value = source_mock

        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMapLocation.return_value = "home"
        cache_mock.WriteMap.return_value = 0

        cache_factory_create_mock.return_value = cache_mock

        c = command.Update()
        self.assertEqual(
            0, c.UpdateMaps(self.conf, incremental=True, force_write=False)
        )

        source_mock.GetMap.assert_called_with(config.MAP_AUTOMOUNT, location="foo")
        source_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].source
        )
        cache_factory_create_mock.assert_has_calls(
            [
                mock.call(
                    self.conf.options[config.MAP_AUTOMOUNT].cache,
                    config.MAP_AUTOMOUNT,
                    automount_mountpoint="/home",
                ),
                mock.call().GetMapLocation(),
                mock.call().WriteMap(map_data=automount_map, force_write=False),
                mock.call(
                    self.conf.options[config.MAP_AUTOMOUNT].cache,
                    config.MAP_AUTOMOUNT,
                    automount_mountpoint=None,
                ),
                mock.call().WriteMap(map_data=automount_map, force_write=False),
            ]
        )

    @mock.patch.object(source_factory, "Create")
    @mock.patch.object(lock, "PidFile")
    @mock.patch.object(map_updater.MapUpdater, "UpdateFromSource")
    def testUpdateMapsTrapsPermissionDenied(
        self, update_from_source_mock, pidfile_mock, source_factory_create_mock
    ):
        update_from_source_mock.side_effect = error.PermissionDenied

        self.conf.maps = [config.MAP_PASSWORD]
        self.conf.cache = "dummy"
        modify_stamp = 1
        map_entry = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        passwd_map = passwd.PasswdMap([map_entry])
        passwd_map.SetModifyTimestamp(modify_stamp)

        source_mock = mock.create_autospec(source.Source)
        source_factory_create_mock.return_value = source_mock

        c = command.Update()
        self.assertEqual(
            1, c.UpdateMaps(self.conf, incremental=True, force_write=False)
        )

        update_from_source_mock.assert_called_with(
            mock.ANY, incremental=True, force_write=False
        )
        source_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].source
        )

    @mock.patch.object(lock, "PidFile")
    def testUpdateMapsCanForceLock(self, pidfile_mock):
        pidfile_mock.return_value.Lock.return_value = False
        pidfile_mock.return_value.Locked.return_value = True

        c = command.Update()
        self.assertEqual(c.ERR_LOCK, c.UpdateMaps(self.conf, False, force_lock=True))

    @mock.patch.object(time, "sleep")
    def testSleep(self, sleep_mock):
        c = command.Update()
        c.UpdateMaps = mock.Mock(return_value=0)

        c.Run(self.conf, ["-s", "1"])

        c.UpdateMaps.assert_called_with(
            self.conf, incremental=True, force_lock=mock.ANY, force_write=mock.ANY
        )

    def testForceWriteFlag(self):
        c = command.Update()
        (options, _) = c.parser.parse_args([])
        self.assertEqual(False, options.force_write)
        (options, _) = c.parser.parse_args(["--force-write"])
        self.assertEqual(True, options.force_write)

    def testForceLockFlag(self):
        c = command.Update()
        (options, _) = c.parser.parse_args([])
        self.assertEqual(False, options.force_lock)
        (options, _) = c.parser.parse_args(["--force-lock"])
        self.assertEqual(True, options.force_lock)

    def testForceWriteFlagCallsUpdateMapsWithForceWriteTrue(self):
        c = command.Update()
        c.UpdateMaps = mock.Mock(return_value=0)

        self.assertEqual(0, c.Run(self.conf, ["--force-write"]))

        c.UpdateMaps.assert_called_with(
            self.conf,
            incremental=mock.ANY,
            force_lock=mock.ANY,
            force_write=True,
        )

    def testForceLockFlagCallsUpdateMapsWithForceLockTrue(self):
        c = command.Update()
        c.UpdateMaps = mock.Mock(return_value=0)

        self.assertEqual(0, c.Run(self.conf, ["--force-lock"]))

        c.UpdateMaps.assert_called_with(
            self.conf,
            incremental=mock.ANY,
            force_lock=True,
            force_write=mock.ANY,
        )

    def testUpdateMapsWithBadMapName(self):
        c = command.Update()
        c._Lock = mock.Mock(return_value=True)

        # Create an invalid map name.
        self.assertEqual(1, c.Run(self.conf, ["-m", config.MAP_PASSWORD + "invalid"]))

        c._Lock.assert_called_with(force=False, path=None)


class TestVerifyCommand(unittest.TestCase):
    def setUp(self):
        super(TestVerifyCommand, self).setUp()

        class DummyConfig(object):
            pass

        class DummySource(source.Source):
            name = "dummy"

            def Verify(self):
                return 0

        # Instead of a DummyCache, we will override cache_factory.Create so
        # we can return a pmock cache object.
        self.original_caches_create = cache_factory.Create
        self.original_sources_create = source_factory.Create

        # Add dummy source to the set if implementations of sources.
        source_factory.RegisterImplementation(DummySource)

        # Create a config with a section for a passwd map.
        self.conf = DummyConfig()
        self.conf.options = {config.MAP_PASSWORD: config.MapOptions()}
        self.conf.options[config.MAP_PASSWORD].cache = {"name": "dummy"}
        self.conf.options[config.MAP_PASSWORD].source = {"name": "dummy"}

        self.original_verify_configuration = config.VerifyConfiguration
        self.original_getmap = nss.GetMap
        self.original_getpwall = pwd.getpwall
        self.original_getgrall = grp.getgrall

        # Setup maps used by VerifyMap testing.
        big_map = passwd.PasswdMap()
        map_entry1 = passwd.PasswdMapEntry()
        map_entry1.name = "foo"
        map_entry1.uid = 10
        map_entry1.gid = 10
        big_map.Add(map_entry1)
        map_entry2 = passwd.PasswdMapEntry()
        map_entry2.name = "bar"
        map_entry2.uid = 20
        map_entry2.gid = 20
        big_map.Add(map_entry2)

        small_map = passwd.PasswdMap()
        small_map.Add(map_entry1)

        self.big_map = big_map
        self.small_map = small_map

    def tearDown(self):
        super(TestVerifyCommand, self).tearDown()
        config.VerifyConfiguration = self.original_verify_configuration
        cache_factory.Create = self.original_caches_create
        nss.getmap = self.original_getmap
        source_factory.Create = self.original_sources_create
        pwd.getpwall = self.original_getpwall
        grp.getgrall = self.original_getgrall

    def testConstructor(self):
        c = command.Verify()
        self.assertTrue(isinstance(c, command.Verify))

    def testHelp(self):
        c = command.Verify()
        self.assertNotEqual(None, c.Help())

    def testRunWithNoParameters(self):
        def FakeVerifyConfiguration(conf):
            """Assert that we call VerifyConfiguration correctly."""
            self.assertEqual(conf, self.conf)
            return (0, 0)

        def FakeVerifyMaps(conf):
            """Assert that VerifyMaps is called with a config object."""
            self.assertEqual(conf, self.conf)
            return 0

        config.VerifyConfiguration = FakeVerifyConfiguration

        c = command.Verify()
        c.VerifyMaps = FakeVerifyMaps

        self.conf.maps = []

        self.assertEqual(1, c.Run(self.conf, []))

    def testRunWithBadParameters(self):
        c = command.Verify()
        # Trap stderr so the unit test runs clean,
        # since unit test status is printed on stderr.
        dev_null = StringIO()
        stderr = sys.stderr
        sys.stderr = dev_null
        self.assertEqual(2, c.Run(None, ["--invalid"]))
        sys.stderr = stderr

    def testRunWithParameters(self):
        def FakeVerifyConfiguration(conf):
            """Assert that we call VerifyConfiguration correctly."""
            self.assertEqual(conf, self.conf)
            return (0, 0)

        def FakeVerifyMaps(conf):
            """Assert that VerifyMaps is called with a config object."""
            self.assertEqual(conf, self.conf)
            return 0

        config.VerifyConfiguration = FakeVerifyConfiguration

        c = command.Verify()
        c.VerifyMaps = FakeVerifyMaps

        self.assertEqual(0, c.Run(self.conf, ["-m", config.MAP_PASSWORD]))

    @mock.patch.object(nss, "GetMap")
    @mock.patch.object(cache_factory, "Create")
    def testVerifyMapsSucceedsOnGoodMaps(
        self, cache_factory_create_mock, nss_getmap_mock
    ):
        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMap.return_value = self.small_map
        cache_factory_create_mock.return_value = cache_mock
        self.conf.maps = [config.MAP_PASSWORD]
        nss_getmap_mock.return_value = self.big_map
        c = command.Verify()

        self.assertEqual(0, c.VerifyMaps(self.conf))

        cache_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].cache, config.MAP_PASSWORD
        )
        nss_getmap_mock.assert_called_with(config.MAP_PASSWORD)

    @mock.patch.object(nss, "GetMap")
    @mock.patch.object(cache_factory, "Create")
    def testVerifyMapsBad(self, cache_factory_create_mock, nss_getmap_mock):
        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMap.return_value = self.big_map
        cache_factory_create_mock.return_value = cache_mock
        self.conf.maps = [config.MAP_PASSWORD]
        nss_getmap_mock.return_value = self.small_map
        c = command.Verify()

        self.assertEqual(1, c.VerifyMaps(self.conf))

        cache_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].cache, config.MAP_PASSWORD
        )
        nss_getmap_mock.assert_called_with(config.MAP_PASSWORD)

    @mock.patch.object(nss, "GetMap")
    @mock.patch.object(cache_factory, "Create")
    def testVerifyMapsException(self, cache_factory_create_mock, nss_getmap_mock):
        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMap.side_effect = error.CacheNotFound
        cache_factory_create_mock.return_value = cache_mock
        self.conf.maps = [config.MAP_PASSWORD]
        nss_getmap_mock.return_value = self.small_map
        c = command.Verify()

        self.assertEqual(1, c.VerifyMaps(self.conf))
        cache_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].cache, config.MAP_PASSWORD
        )
        nss_getmap_mock.assert_called_with(config.MAP_PASSWORD)

    def testVerifyMapsSkipsNetgroups(self):
        with mock.patch.object(cache_factory, "Create"), mock.patch.object(
            nss, "GetMap"
        ):
            self.conf.maps = [config.MAP_NETGROUP]
            c = command.Verify()

            self.assertEqual(0, c.VerifyMaps(self.conf))

    @mock.patch.object(source_factory, "Create")
    def testVerifySourcesGood(self, source_factory_create_mock):
        source_mock = mock.create_autospec(source.Source)
        source_mock.Verify.return_value = 0
        source_factory_create_mock.return_value = source_mock
        self.conf.maps = [config.MAP_PASSWORD]

        self.assertEqual(0, command.Verify().VerifySources(self.conf))

    @mock.patch.object(source_factory, "Create")
    def testVerifySourcesBad(self, source_factory_create_mock):
        self.conf.maps = []

        self.assertEqual(1, command.Verify().VerifySources(self.conf))

        source_mock = mock.create_autospec(source.Source)
        source_mock.Verify.return_value = 1
        source_factory_create_mock.return_value = source_mock
        self.conf.maps = [config.MAP_PASSWORD]

        self.assertEqual(1, command.Verify().VerifySources(self.conf))

        source_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_PASSWORD].cache
        )

    def testVerifySourcesTrapsSourceUnavailable(self):
        self.conf.maps = []
        self.assertEqual(1, command.Verify().VerifySources(self.conf))

        def FakeCreate(conf):
            """Stub routine returning a pmock to test VerifySources."""
            self.assertEqual(conf, self.conf.options[config.MAP_PASSWORD].source)
            raise error.SourceUnavailable

        old_source_base_create = source_factory.Create
        source_factory.Create = FakeCreate
        self.conf.maps = [config.MAP_PASSWORD]

        self.assertEqual(1, command.Verify().VerifySources(self.conf))

        source_factory.Create = old_source_base_create


class TestRepairCommand(unittest.TestCase):
    def setUp(self):
        class DummyConfig(object):
            pass

        class DummySource(source.Source):
            name = "dummy"

            def Verify(self):
                return 0

        # Add dummy source to the set if implementations of sources
        source_factory.RegisterImplementation(DummySource)

        self.conf = DummyConfig()
        self.conf.options = {config.MAP_PASSWORD: config.MapOptions()}
        self.conf.options[config.MAP_PASSWORD].cache = {"name": "dummy"}
        self.conf.options[config.MAP_PASSWORD].source = {"name": "dummy"}

        self.original_verify_configuration = config.VerifyConfiguration

    def tearDown(self):
        config.VerifyConfiguration = self.original_verify_configuration

    def testCreate(self):
        c = command.Repair()
        self.assertTrue(isinstance(c, command.Repair))

    def testHelp(self):
        c = command.Repair()
        self.assertNotEqual(None, c.Help())

    def testRunWithNoParameters(self):
        c = command.Repair()

        def FakeVerifyConfiguration(conf):
            """Assert that we call VerifyConfiguration correctly."""
            self.assertEqual(conf, self.conf)
            return (0, 1)

        config.VerifyConfiguration = FakeVerifyConfiguration

        self.conf.maps = []

        self.assertEqual(1, c.Run(self.conf, []))

    def testRunWithBadParameters(self):
        c = command.Repair()
        # Trap stderr so the unit test runs clean,
        # since unit test status is printed on stderr.
        dev_null = StringIO()
        stderr = sys.stderr
        sys.stderr = dev_null
        self.assertEqual(2, c.Run(None, ["--invalid"]))
        sys.stderr = stderr

    def testRunWithParameters(self):
        def FakeVerifyConfiguration(conf):
            """Assert that we call VerifyConfiguration correctly."""
            self.assertEqual(conf, self.conf)
            return (0, 1)

        config.VerifyConfiguration = FakeVerifyConfiguration

        c = command.Repair()

        self.assertEqual(1, c.Run(self.conf, ["-m", config.MAP_PASSWORD]))


class TestHelpCommand(unittest.TestCase):
    def setUp(self):
        self.stdout = sys.stdout
        sys.stdout = StringIO()

    def tearDown(self):
        sys.stdout = self.stdout

    def testHelp(self):
        c = command.Help()
        self.assertNotEqual(None, c.Help())

    def testRunWithNoParameters(self):
        c = command.Help()
        self.assertEqual(0, c.Run(None, []))

    def testRunHelpHelp(self):
        c = command.Help()
        self.assertEqual(0, c.Run(None, ["help"]))


class TestStatusCommand(unittest.TestCase):
    def setUp(self):
        super(TestStatusCommand, self).setUp()

        class DummyConfig(object):
            pass

        class DummySource(source.Source):
            name = "dummy"

            def Verify(self):
                return 0

        # stub out parts of update.MapUpdater
        class DummyUpdater(map_updater.MapUpdater):
            def GetModifyTimestamp(self):
                return 1

            def GetUpdateTimestamp(self):
                return 2

        # Add dummy source to the set if implementations of sources
        source_factory.RegisterImplementation(DummySource)

        self.conf = DummyConfig()
        self.conf.timestamp_dir = "TEST_DIR"
        self.conf.options = {
            config.MAP_PASSWORD: config.MapOptions(),
            config.MAP_AUTOMOUNT: config.MapOptions(),
        }
        self.conf.options[config.MAP_PASSWORD].cache = {"name": "dummy"}
        self.conf.options[config.MAP_PASSWORD].source = {"name": "dummy"}
        self.conf.options[config.MAP_AUTOMOUNT].cache = {"name": "dummy"}
        self.conf.options[config.MAP_AUTOMOUNT].source = {"name": "dummy"}

        self.original_verify_configuration = config.VerifyConfiguration
        self.original_create = cache_factory.Create
        self.original_updater = map_updater.MapUpdater

        # stub this out for all tests
        map_updater.MapUpdater = DummyUpdater

    def tearDown(self):
        super(TestStatusCommand, self).tearDown()
        config.VerifyConfiguration = self.original_verify_configuration
        cache_factory.Create = self.original_create
        map_updater.MapUpdater = self.original_updater

    def testHelp(self):
        c = command.Status()
        self.assertNotEqual(None, c.Help())

    def testRunWithNoParameters(self):
        c = command.Status()
        self.conf.maps = []
        self.assertEqual(0, c.Run(self.conf, []))

    def testRunWithBadParameters(self):
        c = command.Status()
        # Trap stderr so the unit test runs clean,
        # since unit test status is printed on stderr.
        dev_null = StringIO()
        stderr = sys.stderr
        sys.stderr = dev_null
        self.assertEqual(2, c.Run(None, ["--invalid"]))
        sys.stderr = stderr

    def testEpochFormatParameter(self):
        c = command.Status()
        (options, args) = c.parser.parse_args([])
        self.assertEqual(False, options.epoch)
        self.assertEqual([], args)

    def testObeysMapsFlag(self):
        stdout_buffer = StringIO()

        old_stdout = sys.stdout
        sys.stdout = stdout_buffer

        c = command.Status()
        self.assertEqual(0, c.Run(self.conf, ["-m", "passwd"]))
        sys.stdout = old_stdout

        self.assertNotEqual(0, len(stdout_buffer.getvalue()))
        self.assertFalse(stdout_buffer.getvalue().find("group") >= 0)

    @mock.patch.object(cache_factory, "Create")
    def testGetSingleMapMetadata(self, cache_factory_create_mock):
        # test both automount and non-automount maps.

        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMapLocation.return_value = "/etc/auto.master"
        cache_factory_create_mock.return_value = cache_mock

        c = command.Status()

        values = c.GetSingleMapMetadata(config.MAP_PASSWORD, self.conf)
        self.assertTrue("map" in values[0])
        self.assertTrue("key" in values[0])
        self.assertTrue("value" in values[0])

        values = c.GetSingleMapMetadata(
            config.MAP_AUTOMOUNT, self.conf, automount_mountpoint="automount_mountpoint"
        )

        self.assertTrue("map" in values[0])
        self.assertTrue("key" in values[0])
        self.assertTrue("value" in values[0])
        self.assertTrue("automount" in values[0])

        cache_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_AUTOMOUNT].cache,
            config.MAP_AUTOMOUNT,
            automount_mountpoint="automount_mountpoint",
        )

    def testGetSingleMapMetadataTimestampEpoch(self):
        c = command.Status()
        values = c.GetSingleMapMetadata(config.MAP_PASSWORD, self.conf, epoch=True)
        self.assertTrue("map" in values[0])
        self.assertTrue("key" in values[0])
        self.assertTrue("value" in values[0])
        # values below are returned by dummyupdater
        self.assertEqual(1, values[0]["value"])
        self.assertEqual(2, values[1]["value"])

    def testGetSingleMapMetadataTimestampEpochFalse(self):
        # set the timezone so we get a consistent return value
        os.environ["TZ"] = "MST"
        time.tzset()

        c = command.Status()
        values = c.GetSingleMapMetadata(config.MAP_PASSWORD, self.conf, epoch=False)
        self.assertEqual("Wed Dec 31 17:00:02 1969", values[1]["value"])

    @mock.patch.object(cache_factory, "Create")
    def testGetAutomountMapMetadata(self, cache_factory_create_mock):
        # need to stub out GetSingleMapMetadata (tested above) and then
        # stub out cache_factory.Create to return a cache mock that spits
        # out an iterable map for the function to use.

        # stub out GetSingleMapMetadata
        class DummyStatus(command.Status):
            def GetSingleMapMetadata(
                self,
                unused_map_name,
                unused_conf,
                automount_mountpoint=None,
                epoch=False,
            ):
                return {
                    "map": "map_name",
                    "last-modify-timestamp": "foo",
                    "last-update-timestamp": "bar",
                }

        # the master map to loop over
        master_map = automount.AutomountMap()
        master_map.Add(
            automount.AutomountMapEntry({"key": "/home", "location": "/etc/auto.home"})
        )
        master_map.Add(
            automount.AutomountMapEntry({"key": "/auto", "location": "/etc/auto.auto"})
        )

        # mock out a cache to return the master map
        cache_mock = mock.create_autospec(caches.Cache)
        cache_mock.GetMap.return_value = master_map
        cache_factory_create_mock.return_value = cache_mock

        c = DummyStatus()
        value_list = c.GetAutomountMapMetadata(self.conf)

        self.assertEqual(9, len(value_list))
        cache_factory_create_mock.assert_called_with(
            self.conf.options[config.MAP_AUTOMOUNT].cache,
            config.MAP_AUTOMOUNT,
            automount_mountpoint=None,
        )


if __name__ == "__main__":
    unittest.main()
