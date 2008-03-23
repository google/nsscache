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

"""Unit tests for nss_cache/command.py."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import grp
import pwd
import StringIO
import sys
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

    self.mock_lock = self.mock()
    self.mock_lock\
                    .expects(pmock.once())\
                    .Lock(force=pmock.eq(False))\
                    .will(pmock.return_value('LOCK'))\
                    .id('first')
    self.mock_lock\
                    .expects(pmock.once())\
                    .Lock(force=pmock.eq(False))\
                    .will(pmock.return_value('MORLOCK'))\
                    .after('first')

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
    mock_lock\
               .expects(pmock.once())\
               .Lock(force=pmock.eq(True))\
               .will(pmock.return_value('LOCK'))\

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

    # Add dummy source to the set if implementations of sources
    sources.base.RegisterImplementation(DummySource)

    # Instead of a DummyCache, we will override caches.base.Create so
    # we can return a pmock cache object.
    self.original_create = caches.base.Create

    self.config = DummyConfig()
    self.config.options = {config.MAP_PASSWORD: config.MapOptions()}
    self.config.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.config.options[config.MAP_PASSWORD].source = {'name': 'dummy'}
    self.config.lockfile = None

  def tearDown(self):
    caches.base.Create = self.original_create

  def testConstructor(self):
    c = command.Update()
    self.failIfEqual(None, c)

  def testHelp(self):
    c = command.Update()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      """Stub routine to test Run()."""
      self.assertEquals(conf, self.config,
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

    self.assertEquals(0, c.Run(self.config, []))

  def testRunWithBadParameters(self):
    c = command.Update()
    self.assertEquals(2, c.Run(None, ['--invalid']))

  def testRunWithFlags(self):

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      self.assertEquals(conf, self.config,
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

    self.assertEquals(0, c.Run(self.config,
                               ['-m', config.MAP_PASSWORD, '-f',
                                '--force-write', '--force-lock']))
    self.assertEqual(['passwd'], self.config.maps)

  def testUpdateMaps(self):
    cache_map_handler_mock = self.mock()
    cache_map_handler_mock\
                     .expects(pmock.once())\
                     .method('Update')\
                     .will(pmock.return_value(0))

    def FakeCreate(conf, map_name):
      self.assertEquals(conf, self.config.options[map_name].cache)
      self.assertTrue(map_name in self.config.maps)
      return cache_map_handler_mock

    lock_mock = self.mock()
    lock_mock\
               .expects(pmock.once())\
               ._Lock(path=pmock.eq(None), force=pmock.eq(False))\
               .will(pmock.return_value(True))

    self.config.maps = [config.MAP_PASSWORD]
    self.config.cache = 'dummy'

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.assertEquals(0, c.UpdateMaps(self.config,
                                      incremental=True, force_write=False))

  def testUpdateMapsTrapsPermissionDenied(self):
    cache_map_handler_mock = self.mock()
    cache_map_handler_mock\
           .expects(pmock.once())\
           .method('Update')\
           .will(pmock.raise_exception(error.PermissionDenied))

    def FakeCreate(cache_options, map_name):
      return cache_map_handler_mock

    lock_mock = self.mock()
    lock_mock\
               .expects(pmock.once())\
               ._Lock(path=pmock.eq(None), force=pmock.eq(False))\
               .will(pmock.return_value(True))

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.config.maps = [config.MAP_PASSWORD]
    self.config.cache = 'dummy'

    self.assertEquals(1, c.UpdateMaps(self.config,
                                      incremental=True, force_write=False))

  def testUpdateMapsCanForceLock(self):
    lock_mock = self.mock()
    lock_mock\
               .expects(pmock.once())\
               ._Lock(path=pmock.eq(None), force=pmock.eq(True))\
               .will(pmock.return_value(False))

    c = command.Update()
    c._Lock = lock_mock._Lock
    self.assertEquals(c.UpdateMaps(self.config, False, force_lock=True),
                      c.ERR_LOCK)

  def testSleep(self):

    def FakeSleep(seconds):
      """Stub routine proving we were invoked."""
      self.assertEquals(seconds, 1)

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      """Stub routine proving that we were invoked."""
      self.assertEquals(conf, self.config)
      self.assertEquals(incremental, True)

    sleep = time.sleep
    time.sleep = FakeSleep

    update = command.Update()
    update.UpdateMaps = FakeUpdateMaps

    update.Run(self.config, ['-s', '1'])

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
    self.assertEqual(0, c.Run(self.config, ['--force-write']))

  def testForceWriteFlagCallsCacheMapHandlerUpdateWithForceWriteTrue(self):
    cache_map_handler_mock = self.mock()
    cache_map_handler_mock\
           .expects(pmock.once())\
           .Update(pmock.functor(lambda x: True),  # ignore first argument
                   incremental=pmock.eq(True),
                   force_write=pmock.eq(True))\
           .will(pmock.return_value(0))

    def FakeCreate(cache_options, map_name):
      return cache_map_handler_mock

    lock_mock = self.mock()
    lock_mock\
               .expects(pmock.once())\
               ._Lock(path=pmock.eq(None), force=pmock.eq(False))\
               .will(pmock.return_value(True))

    caches.base.Create = FakeCreate
    c = command.Update()
    c._Lock = lock_mock._Lock
    self.config.maps = [config.MAP_PASSWORD]
    self.config.cache = 'dummy'
    self.assertEquals(0, c.Run(self.config, ['--force-write']))

  def testForceLockFlagCallsUpdateMapsWithForceLockTrue(self):
    c = command.Update()

    def FakeUpdateMaps(conf, incremental, force_write, force_lock):
      self.assertEquals(True, force_lock)
      return 0

    c.UpdateMaps = FakeUpdateMaps
    self.assertEqual(0, c.Run(self.config, ['--force-lock']))


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
    self.config = DummyConfig()
    self.config.options = {config.MAP_PASSWORD: config.MapOptions()}
    self.config.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.config.options[config.MAP_PASSWORD].source = {'name': 'dummy'}

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
      self.assertEquals(conf, self.config)
      return (0, 0)

    def FakeVerifyMaps(conf):
      """Assert that VerifyMaps is called with a config object."""
      self.assertEquals(conf, self.config)
      return 0

    config.VerifyConfiguration = FakeVerifyConfiguration

    c = command.Verify()
    c.VerifyMaps = FakeVerifyMaps

    self.config.maps = []

    self.assertEquals(1, c.Run(self.config, []))

  def testRunWithBadParameters(self):
    c = command.Verify()
    self.assertEquals(2, c.Run(None, ['--invalid']))

  def testRunWithParameters(self):

    def FakeVerifyConfiguration(conf):
      """Assert that we call VerifyConfiguration correctly."""
      self.assertEquals(conf, self.config)
      return (0, 0)

    def FakeVerifyMaps(conf):
      """Assert that VerifyMaps is called with a config object."""
      self.assertEquals(conf, self.config)
      return 0

    config.VerifyConfiguration = FakeVerifyConfiguration

    c = command.Verify()
    c.VerifyMaps = FakeVerifyMaps

    self.assertEquals(0, c.Run(self.config, ['-m',
                                             config.MAP_PASSWORD]))

  def testVerifyMapsSucceedsOnGoodMaps(self):

    def FakeGetMap(map_name):
      """Assert that GetMap is called with an appropriate map name."""
      self.assertEquals(map_name, config.MAP_PASSWORD)
      return self.big_map

    cache_map_handler_mock = self.mock()
    cache_map_handler_mock\
                            .expects(pmock.once())\
                            .GetCacheMap()\
                            .will(pmock.return_value(self.small_map))

    def FakeCreate(conf, map_name):
      """Stub routine returning a pmock to test VerifyMaps."""
      self.assertEquals(conf, self.config.options[map_name].cache)
      self.assertTrue(map_name in self.config.maps)
      return cache_map_handler_mock

    self.config.maps = [config.MAP_PASSWORD]

    old_caches_base_create = caches.base.Create
    caches.base.Create = FakeCreate
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(0, c.VerifyMaps(self.config))

    nss.GetMap = old_nss_getmap
    caches.base.Create = old_caches_base_create

  def testVerifyMapsBad(self):

    def FakeGetMap(map_name):
      """Assert that GetMap is called with an appropriate map name."""
      self.assertEquals(map_name, config.MAP_PASSWORD)
      return self.small_map

    cache_map_handler_mock = self.mock()
    cache_map_handler_mock\
                            .expects(pmock.once())\
                            .GetCacheMap()\
                            .will(pmock.return_value(self.big_map))

    def FakeCreate(conf, map_name):
      """Stub routine returning a pmock to test VerifyMaps."""
      self.assertEquals(conf, self.config.options[map_name].cache)
      self.assertTrue(map_name in self.config.maps)
      return cache_map_handler_mock

    self.config.maps = [config.MAP_PASSWORD]

    old_caches_base_create = caches.base.Create
    caches.base.Create = FakeCreate
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(1, c.VerifyMaps(self.config))

    nss.GetMap = old_nss_getmap
    caches.base.Create = old_caches_base_create

  def testVerifyMapsException(self):

    def FakeGetMap(map_name):
      """Assert that GetMap is called with an appropriate map name."""
      self.assertEquals(map_name, config.MAP_PASSWORD)
      return self.small_map

    cache_map_handler_mock = self.mock()
    cache_map_handler_mock\
                            .expects(pmock.once())\
                            .GetCacheMap()\
                            .will(pmock.raise_exception(error.CacheNotFound))

    def FakeCreate(config, map_name):
      """Stub routine returning a pmock to test VerifyMaps."""
      self.assertEquals(config, self.config.options[map_name].cache)
      self.assertTrue(map_name in self.config.maps)
      self.assertEquals(config, self.config.options[map_name].cache)
      self.assertTrue(map_name in self.config.maps)
      return cache_map_handler_mock

    self.config.maps = [config.MAP_PASSWORD]

    old_caches_base_create = caches.base.Create
    caches.base.Create = FakeCreate
    old_nss_getmap = nss.GetMap
    nss.GetMap = FakeGetMap

    c = command.Verify()

    self.assertEquals(1, c.VerifyMaps(self.config))

    nss.GetMap = old_nss_getmap
    caches.base.Create = old_caches_base_create

  def testVerifySourcesGood(self):

    def FakeCreate(conf):
      """Stub routine returning a pmock to test VerifySources."""
      self.assertEquals(conf,
                        self.config.options[config.MAP_PASSWORD].source)
      return self.source_mock

    self.source_mock = self.mock()
    self.source_mock\
                      .expects(pmock.once())\
                      .Verify()\
                      .will(pmock.return_value(0))

    old_source_base_create = sources.base.Create
    sources.base.Create = FakeCreate
    self.config.maps = [config.MAP_PASSWORD]

    self.assertEquals(0, command.Verify().VerifySources(self.config))

    sources.base.Create = old_source_base_create

  def testVerifySourcesBad(self):

    self.config.maps = []
    self.assertEquals(1, command.Verify().VerifySources(self.config))

    # bad source gives us a bad code
    def FakeCreate(conf):
      """Stub routine returning a pmock to test VerifySources."""
      self.assertEquals(conf,
                        self.config.options[config.MAP_PASSWORD].source)
      return self.source_mock

    self.source_mock = self.mock()
    self.source_mock\
                      .expects(pmock.once())\
                      .Verify()\
                      .will(pmock.return_value(1))

    old_source_base_create = sources.base.Create
    sources.base.Create = FakeCreate
    self.config.maps = [config.MAP_PASSWORD]

    self.assertEquals(1, command.Verify().VerifySources(self.config))

    sources.base.Create = old_source_base_create

  def testVerifySourcesTrapsSourceUnavailable(self):
    self.config.maps = []
    self.assertEquals(1, command.Verify().VerifySources(self.config))

    def FakeCreate(conf):
      """Stub routine returning a pmock to test VerifySources."""
      self.assertEquals(conf,
                        self.config.options[config.MAP_PASSWORD].source)
      raise error.SourceUnavailable

    old_source_base_create = sources.base.Create
    sources.base.Create = FakeCreate
    self.config.maps = [config.MAP_PASSWORD]

    self.assertEquals(1, command.Verify().VerifySources(self.config))

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

    self.config = DummyConfig()
    self.config.options = {config.MAP_PASSWORD: config.MapOptions()}
    self.config.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.config.options[config.MAP_PASSWORD].source = {'name': 'dummy'}

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
      self.assertEquals(conf, self.config)
      return (0, 1)

    config.VerifyConfiguration = FakeVerifyConfiguration

    self.config.maps = []

    self.assertEquals(1, c.Run(self.config, []))

  def testRunWithBadParameters(self):
    c = command.Repair()
    self.assertEquals(2, c.Run(None, ['--invalid']))

  def testRunWithParameters(self):

    def FakeVerifyConfiguration(conf):
      """Assert that we call VerifyConfiguration correctly."""
      self.assertEquals(conf, self.config)
      return (0, 1)

    config.VerifyConfiguration = FakeVerifyConfiguration

    c = command.Repair()

    self.assertEquals(1, c.Run(self.config, ['-m',
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

    # Add dummy source to the set if implementations of sources
    sources.base.RegisterImplementation(DummySource)

    self.config = DummyConfig()
    self.config.options = {config.MAP_PASSWORD: config.MapOptions()}
    self.config.options[config.MAP_PASSWORD].cache = {'name': 'dummy'}
    self.config.options[config.MAP_PASSWORD].source = {'name': 'dummy'}

    self.original_verify_configuration = config.VerifyConfiguration
    self.original_create = caches.base.Create

  def tearDown(self):
    config.VerifyConfiguration = self.original_verify_configuration
    caches.base.Create = self.original_create

  def testHelp(self):
    c = command.Status()
    self.failIfEqual(None, c.Help())

  def testRunWithNoParameters(self):
    c = command.Status()
    self.config.maps = []
    self.assertEquals(0, c.Run(self.config, []))

  def testRunWithBadParameters(self):
    c = command.Status()
    self.assertEquals(2, c.Run(None, ['--invalid']))

  def testValuesOnlyParameter(self):
    c = command.Status()
    (options, args) = c.parser.parse_args([])
    self.assertEqual(False, options.values_only)
    self.assertEqual([], args)
    (options, args) = c.parser.parse_args(['--values-only'])
    self.assertEqual(True, options.values_only)
    self.assertEqual([], args)

  def testEpochFormatParameter(self):
    c = command.Status()
    (options, args) = c.parser.parse_args([])
    self.assertEqual(False, options.epoch)
    self.assertEqual([], args)

  def testObeysMapsFlag(self):

    def FakeCreate(conf, map_name):
      """Stub routine returning a mock object to test status output."""
      self.assertEquals(self.config.options[map_name].cache, conf)
      self.failUnless(map_name in self.config.maps)
      return cache_mock

    stdout_buffer = StringIO.StringIO()
    dummy_map = maps.PasswdMap()
    cache_mock = self.mock()
    cache_mock\
                .expects(pmock.once())\
                .method('GetModifyTimestamp')
    cache_mock\
                .expects(pmock.once())\
                .method('GetUpdateTimestamp')
    self.config.maps = [config.MAP_PASSWORD, config.MAP_GROUP]
    caches.base.Create = FakeCreate
    old_stdout = sys.stdout
    sys.stdout = stdout_buffer
    c = command.Status()
    self.assertEqual(0, c.Run(self.config, ['-m', 'passwd']))
    sys.stdout = old_stdout

    self.failIfEqual(0, len(stdout_buffer.getvalue()))
    self.failIf(stdout_buffer.getvalue().find('group') >= 0)

  def testStatParameter(self):
    c = command.Status()
    (options, args) = c.parser.parse_args([])
    self.assertEqual(None, options.stat)
    self.assertEqual([], args)
    (options, args) = c.parser.parse_args(['--stat=foo'])
    self.assertEqual('foo', options.stat)
    self.assertEqual([], args)
    (options, args) = c.parser.parse_args(['--stat', 'foo'])
    self.assertEqual('foo', options.stat)
    self.assertEqual([], args)

  def testGetOutputTemplateValuesOnly(self):
    c = command.Status()
    template = c.GetOutputTemplate(values_only=True)
    self.failIfEqual(0, len(template))
    self.failUnless(template.find('%(last-modify-timestamp)s') >= 0)
    self.failIf(template.find('(UTC)') >= 0)

  def testGetOutputTemplateStat(self):
    c = command.Status()
    template = c.GetOutputTemplate(only_key='last-modify-timestamp')
    self.failIfEqual(0, len(template))
    self.failUnless(template.find('%(last-modify-timestamp)s') >= 0)
    self.failIf(template.find('\n') >= 0, 'too many lines returned')

  def testGetMapMetadata(self):
    cache_mock = self.mock()
    cache_mock\
                .expects(pmock.once())\
                .GetModifyTimestamp()
    cache_mock\
                .expects(pmock.once())\
                .GetUpdateTimestamp()

    def FakeCreate(conf, map_name):
      self.assertEquals(self.config.options[map_name].cache, conf)
      self.failUnless(map_name in self.config.maps)
      return cache_mock

    self.config.maps = [config.MAP_PASSWORD]
    caches.base.Create = FakeCreate
    c = command.Status()
    value_dict = c.GetMapMetadata('passwd', self.config)
    self.failUnless('map' in value_dict)
    self.failUnless('last-modify-timestamp' in value_dict)
    self.failUnless('last-update-timestamp' in value_dict)

  def testGetMapMetadataTimestampEpoch(self):
    cache_mock = self.mock()
    cache_mock\
                .expects(pmock.once())\
                .GetModifyTimestamp()
    cache_mock\
                .expects(pmock.once())\
                .GetUpdateTimestamp()

    def FakeCreate(conf, map_name):
      self.assertEquals(self.config.options[map_name].cache, conf)
      self.failUnless(map_name in self.config.maps)
      return cache_mock

    self.config.maps = [config.MAP_PASSWORD]
    caches.base.Create = FakeCreate
    c = command.Status()
    value_dict = c.GetMapMetadata('passwd', self.config, epoch=True)
    self.failUnless('map' in value_dict)
    self.failUnless('last-modify-timestamp' in value_dict)
    self.failUnless('last-update-timestamp' in value_dict)
    self.failUnlessEqual(None, value_dict['last-modify-timestamp'])

  def testGetMapMetadataTimestampEpochFalse(self):
    cache_mock = self.mock()
    cache_mock\
                .expects(pmock.once())\
                .GetModifyTimestamp()
    cache_mock\
                .expects(pmock.once())\
                .GetUpdateTimestamp()

    def FakeCreate(conf, map_name):
      self.assertEquals(self.config.options[map_name].cache, conf)
      self.failUnless(map_name in self.config.maps)
      return cache_mock

    self.config.maps = [config.MAP_PASSWORD]
    caches.base.Create = FakeCreate
    c = command.Status()
    value_dict = c.GetMapMetadata('passwd', self.config, epoch=False)
    self.failUnlessEqual('Unknown', value_dict['last-update-timestamp'])


if __name__ == '__main__':
  unittest.main()
