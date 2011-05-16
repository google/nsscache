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

"""Unit tests for nss_cache/command.py."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import grp
import os
import pwd
import shutil
import StringIO
import sys
import tempfile
import time
import unittest

from nss_cache import caches
from nss_cache import command
from nss_cache import config
from nss_cache import error
from nss_cache import lock
from nss_cache import maps
from nss_cache import nss
from nss_cache import sources
from nss_cache import update

import pmock


class TestCommand(pmock.MockTestCase):
  """Unit tests for the Command class."""

  def testDestructor(self):
    mock_unlock = self.mock()
    mock_unlock.expects(pmock.once())._Unlock()
    c = command.Command()
    c._Unlock = mock_unlock._Unlock
    # Invoke the destructor
    del c

  def testRunCommand(self):
    c = command.Command()
    self.assertRaises(NotImplementedError, c.Run, [], {})

  def testLock(self):

    def FakePidFile(filename):
      """Stub routine for testing."""
      self.assertEquals(filename, None)
      return self.mock_lock

    mock_lock = self.mock()
    invocation = mock_lock.expects(pmock.once())
    invocation = invocation.Lock(force=pmock.eq(False))
    invocation.will(pmock.return_value('LOCK')).id('first')

    invocation = mock_lock.expects(pmock.once())
    invocation = invocation.Lock(force=pmock.eq(False))
    invocation.will(pmock.return_value('MORLOCK')).after('first')

    self.mock_lock = mock_lock

    original_pidfile = lock.PidFile
    lock.PidFile = FakePidFile

    c = command.Command()

    # First test that we create a lock and lock it.
    self.assertEquals(c._Lock(), 'LOCK')
    lock.PidFile = original_pidfile

    # Then we test that we lock the existing one a second time.
    self.assertEquals(c._Lock(), 'MORLOCK')  # haha morlocks!!

    # Remove locker so object destructor doesn't invoke it again.
    c.lock = None

  def testForceLock(self):

    mock_lock = self.mock()

    invocation = mock_lock.expects(pmock.once())
    invocation = invocation.Lock(force=pmock.eq(True))
    invocation.will(pmock.return_value('LOCK'))

    c = command.Command()
    c.lock = mock_lock

    self.assertEquals(c._Lock(force=True), 'LOCK')

    # Remove locker so object destructor doesn't invoke it again.
    c.lock = None

  def testUnlock(self):
    mock_lock = self.mock()
    mock_lock.expects(pmock.once()).Locked().will(pmock.return_value(True))
    mock_lock.expects(pmock.once()).Unlock()
    c = command.Command()
    c.lock = mock_lock
    c._Unlock()
    # Remove lock object or destructor will kick in when we tear down.
    c.lock = None

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
    self.failIfEqual(None, c.Help())


class TestUpdateCommand(pmock.MockTestCase):
  """Unit tests for the Update command class."""

  def setUp(self):
    class DummyConfig(object):
      pass

    class DummySource(sources.base.Source):
      name = 'dummy'
      UPDATER = config.UPDATER_MAP

      def GetPasswdMap(self, since=None):
        return maps.passwd.PasswdMap()

    class DummyUpdater(update.base.Updater):

      def UpdateFromSource(self, source, incremental=True, force_write=False):
        return 0

    # Add dummy source to the set if implementations of sources
    sources.base.RegisterImplementation(DummySource)

    # Instead of a DummyCache, we will override caches.base.Create so
    # we can return a pmock cache object.
    self.original_create = caches.base.Create

    # Get our dummy updater to be returned instead
    self.original_master_map_updater = update.maps.AutomountUpdater
    self.original_single_map_updater = update.maps.SingleMapUpdater
    update.maps.AutomountUpdater = DummyUpdater
    update.maps.SingleMapUpdater = DummyUpdater

    # working dir
    self.workdir = tempfile.mkdtemp()

    self.conf = DummyConfig()
    self.conf.options = {config.MAP_PASSWORD: config.MapOptions(),
                         config.MAP_AUTOMOUNT: config.MapOptions()}
    self.conf.options[config.MAP_PASSWORD].cache = {'name': 'dummy',
                                                    'dir': self.workdir}
    self.conf.options[config.MAP_PASSWORD].source = {'name': 'dummy'}
    self.conf.options[config.MAP_AUTOMOUNT].cache = {'name': 'dummy',
                                                     'dir': self.workdir}
    self.conf.options[config.MAP_AUTOMOUNT].source = {'name': 'dummy'}
    self.conf.timestamp_dir = ''
    self.conf.lockfile = None

  def tearDown(self):
    shutil.rmtree(self.workdir)
    caches.base.Create = self.original_create
    update.maps.AutomountUpdater = self.original_master_map_updater
    update.maps.SingleMapUpdater = self.original_single_map_updater

  def testConstructor(self):
    c = command.Update()
    self.failIfEqual(None, c)

  def testHelp(self):
    c = command.Update()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      """Stub routine to test Run()."""
      self.assertEquals(conf, self.conf,
                        msg='UpdateMaps received wrong config object')
      self.assertTrue(incremental,
                      msg='UpdateMaps received False for incremental')
      self.assertFalse(force_write,
                       msg='UpdateMaps received True for forced writes')
      self.assertFalse(force_lock,
                       msg='UpdateMaps received True for forcing locks')
      return 0

    c = command.Update()
    c.UpdateMaps = FakeUpdateMaps

    self.assertEquals(0, c.Run(self.conf, []))

  def testRunWithBadParameters(self):
    c = command.Update()
    # Trap stderr so the unit test runs clean,
    # since unit test status is printed on stderr.
    dev_null = StringIO.StringIO()
    stderr = sys.stderr
    sys.stderr = dev_null
    self.assertEquals(2, c.Run(None, ['--invalid']))
    sys.stderr = stderr

  def testRunWithFlags(self):

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      self.assertEquals(conf, self.conf,
                        msg='UpdateMaps received wrong config object')
      self.assertFalse(incremental,
                       msg='UpdateMaps received True for incremental')
      self.assertTrue(force_write,
                      msg='UpdateMaps received False for forced writes')
      self.assertTrue(force_lock,
                      msg='UpdateMaps received False for forced writes')
      return 0

    c = command.Update()
    c.UpdateMaps = FakeUpdateMaps

    self.assertEquals(0, c.Run(self.conf,
                               ['-m', config.MAP_PASSWORD, '-f',
                                '--force-write', '--force-lock']))
    self.assertEqual(['passwd'], self.conf.maps)

  def testUpdateSingleMaps(self):

    def FakeCreate(conf, map_name):
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      return 'cache'

    lock_mock = self.mock()
    invocation = lock_mock.expects(pmock.once())
    invocation = invocation._Lock(path=pmock.eq(None), force=pmock.eq(False))
    invocation.will(pmock.return_value(True))

    self.conf.maps = [config.MAP_PASSWORD]
    self.conf.cache = 'dummy'

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.assertEquals(0, c.UpdateMaps(self.conf,
                                      incremental=True, force_write=False))

  def testUpdateAutomounts(self):

    def FakeCreate(conf, map_name):
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      return 'cache'

    lock_mock = self.mock()
    invocation = lock_mock.expects(pmock.once())
    invocation = invocation._Lock(path=pmock.eq(None), force=pmock.eq(False))
    invocation.will(pmock.return_value(True))

    self.conf.maps = [config.MAP_AUTOMOUNT]
    self.conf.cache = 'dummy'

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.assertEquals(0, c.UpdateMaps(self.conf,
                                      incremental=True, force_write=False))

  def testUpdateMapsTrapsPermissionDenied(self):

    class BrokenUpdater(update.base.Updater):

      def UpdateFromSource(self, source, incremental=True, force_write=False):
        raise error.PermissionDenied

    def FakeCreate(conf, map_name):
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      return 'cache'

    # tearDown will restore this
    update.maps.SingleMapUpdater = BrokenUpdater

    lock_mock = self.mock()
    invocation = lock_mock.expects(pmock.once())
    invocation = invocation._Lock(path=pmock.eq(None), force=pmock.eq(False))
    invocation.will(pmock.return_value(True))

    self.conf.maps = [config.MAP_PASSWORD]
    self.conf.cache = 'dummy'

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.assertEquals(1, c.UpdateMaps(self.conf, incremental=True,
                                      force_write=False))

  def testUpdateMapsCanForceLock(self):
    lock_mock = self.mock()
    invocation = lock_mock.expects(pmock.once())
    invocation = invocation._Lock(path=pmock.eq(None), force=pmock.eq(True))
    invocation.will(pmock.return_value(False))

    c = command.Update()
    c._Lock = lock_mock._Lock
    self.assertEquals(c.UpdateMaps(self.conf, False, force_lock=True),
                      c.ERR_LOCK)

  def testSleep(self):

    def FakeSleep(seconds):
      """Stub routine proving we were invoked."""
      self.assertEquals(seconds, 1)

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      """Stub routine proving that we were invoked."""
      self.assertEquals(conf, self.conf)
      self.assertEquals(incremental, True)

    sleep = time.sleep
    time.sleep = FakeSleep

    c = command.Update()
    c.UpdateMaps = FakeUpdateMaps

    c.Run(self.conf, ['-s', '1'])

    time.sleep = sleep

  def testForceWriteFlag(self):
    c = command.Update()
    (options, _) = c.parser.parse_args([])
    self.assertEqual(False, options.force_write)
    (options, _) = c.parser.parse_args(['--force-write'])
    self.assertEqual(True, options.force_write)

  def testForceLockFlag(self):
    c = command.Update()
    (options, _) = c.parser.parse_args([])
    self.assertEqual(False, options.force_lock)
    (options, _) = c.parser.parse_args(['--force-lock'])
    self.assertEqual(True, options.force_lock)

  def testForceWriteFlagCallsUpdateMapsWithForceWriteTrue(self):
    c = command.Update()

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      self.assertEquals(True, force_write)
      return 0

    c.UpdateMaps = FakeUpdateMaps
    self.assertEqual(0, c.Run(self.conf, ['--force-write']))

  def testForceWriteFlagCallsCacheMapHandlerUpdateWithForceWriteTrue(self):

    def FakeCreate(cache_options, map_name):
      return 'cache'

    lock_mock = self.mock()
    invocation = lock_mock.expects(pmock.once())
    invocation = invocation._Lock(path=pmock.eq(None), force=pmock.eq(False))
    invocation.will(pmock.return_value(True))

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.conf.maps = [config.MAP_PASSWORD]
    self.conf.cache = 'dummy'
    self.assertEquals(0, c.Run(self.conf, ['--force-write']))

  def testForceLockFlagCallsUpdateMapsWithForceLockTrue(self):
    c = command.Update()

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      self.assertEquals(True, force_lock)
      return 0

    c.UpdateMaps = FakeUpdateMaps
    self.assertEqual(0, c.Run(self.conf, ['--force-lock']))


class TestVerifyCommand(pmock.MockTestCase):

  def setUp(self):

    class DummyConfig(object):
      pass

    class DummySource(sources.base.Source):
      name = 'dummy'

      def Verify(self):
        return 0

    # Instead of a DummyCache, we will override caches.base.Create so
    # we can return a pmock cache object.
    self.original_caches_create = caches.base.Create
    self.original_sources_create = sources.base.Create

    # Add dummy source to the set if implementations of sources.
    sources.base.RegisterImplementation(DummySource)

    # Create a config with a section for a passwd map.
    self.conf = DummyConfig()
    self.conf.options = {config.MAP_PASSWORD: config.MapOptions()}
    self.conf.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.conf.options[config.MAP_PASSWORD].source = {'name': 'dummy'}

    self.original_verify_configuration = config.VerifyConfiguration
    self.original_getmap = nss.GetMap
    self.original_getpwall = pwd.getpwall
    self.original_getgrall = grp.getgrall

    # Setup maps used by VerifyMap testing.
    big_map = maps.PasswdMap()
    map_entry1 = maps.PasswdMapEntry()
    map_entry1.name = 'foo'
    map_entry1.uid = 10
    map_entry1.gid = 10
    big_map.Add(map_entry1)
    map_entry2 = maps.PasswdMapEntry()
    map_entry2.name = 'bar'
    map_entry2.uid = 20
    map_entry2.gid = 20
    big_map.Add(map_entry2)

    small_map = maps.PasswdMap()
    small_map.Add(map_entry1)

    self.big_map = big_map
    self.small_map = small_map

  def tearDown(self):
    config.VerifyConfiguration = self.original_verify_configuration
    caches.base.Create = self.original_caches_create
    nss.getmap = self.original_getmap
    sources.base.Create = self.original_sources_create
    pwd.getpwall = self.original_getpwall
    grp.getgrall = self.original_getgrall

  def testConstructor(self):
    c = command.Verify()
    self.assertTrue(isinstance(c, command.Verify))

  def testHelp(self):
    c = command.Verify()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):

    def FakeVerifyConfiguration(conf):
      """Assert that we call VerifyConfiguration correctly."""
      self.assertEquals(conf, self.conf)
      return (0, 0)

    def FakeVerifyMaps(conf):
      """Assert that VerifyMaps is called with a config object."""
      self.assertEquals(conf, self.conf)
      return 0

    config.VerifyConfiguration = FakeVerifyConfiguration

    c = command.Verify()
    c.VerifyMaps = FakeVerifyMaps

    self.conf.maps = []

    self.assertEquals(1, c.Run(self.conf, []))

  def testRunWithBadParameters(self):
    c = command.Verify()
    # Trap stderr so the unit test runs clean,
    # since unit test status is printed on stderr.
    dev_null = StringIO.StringIO()
    stderr = sys.stderr
    sys.stderr = dev_null
    self.assertEquals(2, c.Run(None, ['--invalid']))
    sys.stderr = stderr

  def testRunWithParameters(self):

    def FakeVerifyConfiguration(conf):
      """Assert that we call VerifyConfiguration correctly."""
      self.assertEquals(conf, self.conf)
      return (0, 0)

    def FakeVerifyMaps(conf):
      """Assert that VerifyMaps is called with a config object."""
      self.assertEquals(conf, self.conf)
      return 0

    config.VerifyConfiguration = FakeVerifyConfiguration

    c = command.Verify()
    c.VerifyMaps = FakeVerifyMaps

    self.assertEquals(0, c.Run(self.conf, ['-m',
                                           config.MAP_PASSWORD]))

  def testVerifyMapsSucceedsOnGoodMaps(self):

    def FakeGetMap(map_name):
      """Assert that GetMap is called with an appropriate map name."""
      self.assertEquals(map_name, config.MAP_PASSWORD)
      return self.big_map

    cache_map_handler_mock = self.mock()
    invocation = cache_map_handler_mock.expects(pmock.once())
    invocation.GetMap().will(pmock.return_value(self.small_map))

    def FakeCreate(conf, map_name):
      """Stub routine returning a pmock to test VerifyMaps."""
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      return cache_map_handler_mock

    self.conf.maps = [config.MAP_PASSWORD]

    old_caches_base_create = caches.base.Create
    caches.base.Create = FakeCreate
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(0, c.VerifyMaps(self.conf))

    nss.GetMap = old_nss_getmap
    caches.base.Create = old_caches_base_create

  def testVerifyMapsBad(self):

    def FakeGetMap(map_name):
      """Assert that GetMap is called with an appropriate map name."""
      self.assertEquals(map_name, config.MAP_PASSWORD)
      return self.small_map

    cache_map_handler_mock = self.mock()
    invocation = cache_map_handler_mock.expects(pmock.once())
    invocation.GetMap().will(pmock.return_value(self.big_map))

    def FakeCreate(conf, map_name):
      """Stub routine returning a pmock to test VerifyMaps."""
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      return cache_map_handler_mock

    self.conf.maps = [config.MAP_PASSWORD]

    old_caches_base_create = caches.base.Create
    caches.base.Create = FakeCreate
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(1, c.VerifyMaps(self.conf))

    nss.GetMap = old_nss_getmap
    caches.base.Create = old_caches_base_create

  def testVerifyMapsException(self):

    def FakeGetMap(map_name):
      """Assert that GetMap is called with an appropriate map name."""
      self.assertEquals(map_name, config.MAP_PASSWORD)
      return self.small_map

    cache_map_handler_mock = self.mock()
    invocation = cache_map_handler_mock.expects(pmock.once())
    invocation.GetMap().will(pmock.raise_exception(error.CacheNotFound))

    def FakeCreate(conf, map_name):
      """Stub routine returning a pmock to test VerifyMaps."""
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      self.assertEquals(conf, self.conf.options[map_name].cache)
      self.assertTrue(map_name in self.conf.maps)
      return cache_map_handler_mock

    self.conf.maps = [config.MAP_PASSWORD]

    old_caches_base_create = caches.base.Create
    caches.base.Create = FakeCreate
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(1, c.VerifyMaps(self.conf))

    nss.GetMap = old_nss_getmap
    caches.base.Create = old_caches_base_create

  def testVerifyMapsSkipsNetgroups(self):

    def FakeGetMap(map_name):
      """We should never get here for netgroups, so fail."""
      self.fail('GetMap was invoked for netgroups')

    self.conf.maps = [config.MAP_NETGROUP]
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(0, c.VerifyMaps(self.conf))

    nss.GetMap = old_nss_getmap

  def testVerifySourcesGood(self):

    def FakeCreate(conf):
      """Stub routine returning a pmock to test VerifySources."""
      self.assertEquals(conf,
                        self.conf.options[config.MAP_PASSWORD].source)
      return self.source_mock

    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation.Verify().will(pmock.return_value(0))

    self.source_mock = source_mock

    old_source_base_create = sources.base.Create
    sources.base.Create = FakeCreate
    self.conf.maps = [config.MAP_PASSWORD]

    self.assertEquals(0, command.Verify().VerifySources(self.conf))

    sources.base.Create = old_source_base_create

  def testVerifySourcesBad(self):

    self.conf.maps = []
    self.assertEquals(1, command.Verify().VerifySources(self.conf))

    # bad source gives us a bad code
    def FakeCreate(conf):
      """Stub routine returning a pmock to test VerifySources."""
      self.assertEquals(conf,
                        self.conf.options[config.MAP_PASSWORD].source)
      return self.source_mock

    source_mock = self.mock()
    invocation = source_mock.expects(pmock.once())
    invocation.Verify().will(pmock.return_value(1))

    self.source_mock = source_mock

    old_source_base_create = sources.base.Create
    sources.base.Create = FakeCreate
    self.conf.maps = [config.MAP_PASSWORD]

    self.assertEquals(1, command.Verify().VerifySources(self.conf))

    sources.base.Create = old_source_base_create

  def testVerifySourcesTrapsSourceUnavailable(self):
    self.conf.maps = []
    self.assertEquals(1, command.Verify().VerifySources(self.conf))

    def FakeCreate(conf):
      """Stub routine returning a pmock to test VerifySources."""
      self.assertEquals(conf,
                        self.conf.options[config.MAP_PASSWORD].source)
      raise error.SourceUnavailable

    old_source_base_create = sources.base.Create
    sources.base.Create = FakeCreate
    self.conf.maps = [config.MAP_PASSWORD]

    self.assertEquals(1, command.Verify().VerifySources(self.conf))

    sources.base.Create = old_source_base_create


class TestRepairCommand(unittest.TestCase):

  def setUp(self):

    class DummyConfig(object):
      pass

    class DummySource(sources.base.Source):
      name = 'dummy'

      def Verify(self):
        return 0

    # Add dummy source to the set if implementations of sources
    sources.base.RegisterImplementation(DummySource)

    self.conf = DummyConfig()
    self.conf.options = {config.MAP_PASSWORD: config.MapOptions()}
    self.conf.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.conf.options[config.MAP_PASSWORD].source = {'name': 'dummy'}

    self.original_verify_configuration = config.VerifyConfiguration

  def tearDown(self):
    config.VerifyConfiguration = self.original_verify_configuration

  def testCreate(self):
    c = command.Repair()
    self.assertTrue(isinstance(c, command.Repair))

  def testHelp(self):
    c = command.Repair()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):
    c = command.Repair()

    def FakeVerifyConfiguration(conf):
      """Assert that we call VerifyConfiguration correctly."""
      self.assertEquals(conf, self.conf)
      return (0, 1)

    config.VerifyConfiguration = FakeVerifyConfiguration

    self.conf.maps = []

    self.assertEquals(1, c.Run(self.conf, []))

  def testRunWithBadParameters(self):
    c = command.Repair()
    # Trap stderr so the unit test runs clean,
    # since unit test status is printed on stderr.
    dev_null = StringIO.StringIO()
    stderr = sys.stderr
    sys.stderr = dev_null
    self.assertEquals(2, c.Run(None, ['--invalid']))
    sys.stderr = stderr

  def testRunWithParameters(self):

    def FakeVerifyConfiguration(conf):
      """Assert that we call VerifyConfiguration correctly."""
      self.assertEquals(conf, self.conf)
      return (0, 1)

    config.VerifyConfiguration = FakeVerifyConfiguration

    c = command.Repair()

    self.assertEquals(1, c.Run(self.conf, ['-m',
                                           config.MAP_PASSWORD]))


class TestHelpCommand(unittest.TestCase):

  def testHelp(self):
    c = command.Help()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):
    c = command.Help()
    self.assertEquals(0, c.Run(None, []))

  def testRunHelpHelp(self):
    c = command.Help()
    self.assertEquals(0, c.Run(None, ['help']))


class TestStatusCommand(pmock.MockTestCase):

  def setUp(self):

    class DummyConfig(object):
      pass

    class DummySource(sources.base.Source):
      name = 'dummy'

      def Verify(self):
        return 0

    # stub out parts of update.SingleMapUpdater
    class DummyUpdater(update.maps.SingleMapUpdater):
      def GetModifyTimestamp(self):
        return time.gmtime(1)

      def GetUpdateTimestamp(self):
        return time.gmtime(2)

    # Add dummy source to the set if implementations of sources
    sources.base.RegisterImplementation(DummySource)

    self.conf = DummyConfig()
    self.conf.timestamp_dir = 'TEST_DIR'
    self.conf.options = {config.MAP_PASSWORD: config.MapOptions(),
                         config.MAP_AUTOMOUNT: config.MapOptions()}
    self.conf.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.conf.options[config.MAP_PASSWORD].source = {'name': 'dummy'}
    self.conf.options[config.MAP_AUTOMOUNT].cache = {'name': 'dummy'}
    self.conf.options[config.MAP_AUTOMOUNT].source = {'name': 'dummy'}

    self.original_verify_configuration = config.VerifyConfiguration
    self.original_create = caches.base.Create
    self.original_updater = update.maps.SingleMapUpdater

    # stub this out for all tests
    update.maps.SingleMapUpdater = DummyUpdater

  def tearDown(self):
    config.VerifyConfiguration = self.original_verify_configuration
    caches.base.Create = self.original_create
    update.maps.SingleMapUpdater = self.original_updater

  def testHelp(self):
    c = command.Status()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):
    c = command.Status()
    self.conf.maps = []
    self.assertEquals(0, c.Run(self.conf, []))

  def testRunWithBadParameters(self):
    c = command.Status()
    # Trap stderr so the unit test runs clean,
    # since unit test status is printed on stderr.
    dev_null = StringIO.StringIO()
    stderr = sys.stderr
    sys.stderr = dev_null
    self.assertEquals(2, c.Run(None, ['--invalid']))
    sys.stderr = stderr

  def testEpochFormatParameter(self):
    c = command.Status()
    (options, args) = c.parser.parse_args([])
    self.assertEqual(False, options.epoch)
    self.assertEqual([], args)

  def testObeysMapsFlag(self):

    stdout_buffer = StringIO.StringIO()

    old_stdout = sys.stdout
    sys.stdout = stdout_buffer

    c = command.Status()
    self.assertEqual(0, c.Run(self.conf, ['-m', 'passwd']))
    sys.stdout = old_stdout

    self.failIfEqual(0, len(stdout_buffer.getvalue()))
    self.failIf(stdout_buffer.getvalue().find('group') >= 0)

  def testGetSingleMapMetadata(self):
    # test both automount and non-automount maps.

    # cache mock is returned by FakeCreate() for automount maps
    cache_mock = self.mock()
    invocation = cache_mock.expects(pmock.once())
    invocation.GetMapLocation().will(pmock.return_value('/etc/auto.master'))

    self.cache_mock = cache_mock

    # FakeCreate() is to be called by GetSingleMapMetadata for automount maps
    def FakeCreate(conf, map_name, automount_mountpoint=None):
      self.assertEquals(map_name, config.MAP_AUTOMOUNT)
      self.assertEquals(automount_mountpoint, 'automount_mountpoint')
      return self.cache_mock

    caches.base.Create = FakeCreate

    c = command.Status()

    values = c.GetSingleMapMetadata(config.MAP_PASSWORD, self.conf)
    self.failUnless('map' in values[0])
    self.failUnless('key' in values[0])
    self.failUnless('value' in values[0])

    values = c.GetSingleMapMetadata(
        config.MAP_AUTOMOUNT, self.conf,
        automount_mountpoint='automount_mountpoint')

    self.failUnless('map' in values[0])
    self.failUnless('key' in values[0])
    self.failUnless('value' in values[0])
    self.failUnless('automount' in values[0])

  def testGetSingleMapMetadataTimestampEpoch(self):
    c = command.Status()
    values = c.GetSingleMapMetadata(config.MAP_PASSWORD, self.conf,
                                    epoch=True)
    self.failUnless('map' in values[0])
    self.failUnless('key' in values[0])
    self.failUnless('value' in values[0])
    # values below are returned by dummyupdater
    self.assertEqual(1, values[0]['value'])
    self.assertEqual(2, values[1]['value'])

  def testGetSingleMapMetadataTimestampEpochFalse(self):
    # set the timezone so we get a consistent return value
    os.environ['TZ'] = 'US/Pacific'
    time.tzset()

    c = command.Status()
    values = c.GetSingleMapMetadata(config.MAP_PASSWORD, self.conf,
                                    epoch=False)
    self.failUnlessEqual('Thu Jan  1 00:00:02 1970',
                         values[1]['value'])

  def testGetAutomountMapMetadata(self):
    # need to stub out GetSingleMapMetadata (tested above) and then
    # stub out caches.base.Create to return a cache mock that spits
    # out an iterable map for the function to use.

    # stub out GetSingleMapMetadata
    class DummyStatus(command.Status):
      def GetSingleMapMetadata(self, unused_map_name, unused_conf,
                               automount_mountpoint=None, epoch=False):
        return {'map': 'map_name', 'last-modify-timestamp': 'foo',
                'last-update-timestamp': 'bar'}

    # the master map to loop over
    master_map = maps.AutomountMap()
    master_map.Add(maps.AutomountMapEntry({'key': '/home',
                                           'location': '/etc/auto.home'}))
    master_map.Add(maps.AutomountMapEntry({'key': '/auto',
                                           'location': '/etc/auto.auto'}))

    # mock out a cache to return the master map
    cache_mock = self.mock()
    invocation = cache_mock.expects(pmock.once())
    invocation.will(pmock.return_value(master_map))
    self.cache_mock = cache_mock

    # stub out caches.base.Create(), is restored in tearDown()
    def FakeCreate(unused_cache_options, unused_map_name,
                   automount_mountpoint=None):
      return self.cache_mock

    caches.base.Create = FakeCreate

    c = DummyStatus()
    value_list = c.GetAutomountMapMetadata(self.conf)

    self.assertEqual(9, len(value_list))

if __name__ == '__main__':
  unittest.main()
