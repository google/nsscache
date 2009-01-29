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

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import grp
import pwd
import unittest

from nss_cache import config
from nss_cache import error
from nss_cache import maps
from nss_cache import nss

import pmock


class TestNSS(pmock.MockTestCase):
  """Tests for the NSS library"""

  def setUp(self):
    """Save some class callables that we override in testing."""
    self.original_getpwall = pwd.getpwall
    self.original_getgrall = grp.getgrall

  def tearDown(self):
    """Restore state of class callables."""
    pwd.getpwall = self.original_getpwall
    grp.getgrall = self.original_getgrall

  def testGetMap(self):
    """that GetMap is calling the right GetFooMap routines."""

    def FakeGetPasswdMap():
      """Stub entry for testing."""
      return 'TEST_PASSWORD'

    def FakeGetGroupMap():
      """Stub entry for testing."""
      return 'TEST_GROUP'

    def FakeGetShadowMap():
      """Stub entry for testing."""
      return 'TEST_SHADOW'

    orig_getnsspasswdmap = nss.GetPasswdMap
    orig_getnssgroupmap = nss.GetGroupMap
    orig_getnssshadowmap = nss.GetShadowMap

    nss.GetPasswdMap = FakeGetPasswdMap
    nss.GetGroupMap = FakeGetGroupMap
    nss.GetShadowMap = FakeGetShadowMap

    self.assertEquals('TEST_PASSWORD', nss.GetMap(config.MAP_PASSWORD))
    self.assertEquals('TEST_GROUP', nss.GetMap(config.MAP_GROUP))
    self.assertEquals('TEST_SHADOW', nss.GetMap(config.MAP_SHADOW))

    nss.GetPasswdMap = orig_getnsspasswdmap
    nss.GetGroupMap = orig_getnssgroupmap
    nss.GetShadowMap = orig_getnssshadowmap

  def testGetMapException(self):
    """GetMap throws error.UnsupportedMap for unsupported maps."""
    self.assertRaises(error.UnsupportedMap, nss.GetMap, 'ohio')

  def testGetPasswdMap(self):
    """Verify we build a correct password map from nss calls."""

    def FakeGetPwAll():
      foo = ('foo', 'x', 10, 10, 'foo bar', '/home/foo', '/bin/shell')
      bar = ('bar', 'x', 20, 20, 'foo bar', '/home/monkeyboy', '/bin/shell')
      return [foo, bar]

    entry1 = maps.PasswdMapEntry()
    entry1.name = 'foo'
    entry1.uid = 10
    entry1.gid = 10
    entry1.gecos = 'foo bar'
    entry1.dir = '/home/foo'
    entry1.shell = '/bin/shell'

    entry2 = maps.PasswdMapEntry()
    entry2.name = 'bar'
    entry2.uid = 20
    entry2.gid = 20
    entry2.gecos = 'foo bar'
    entry2.dir = '/home/monkeyboy'
    entry2.shell = '/bin/shell'

    pwd.getpwall = FakeGetPwAll

    password_map = nss.GetPasswdMap()

    self.assertTrue(isinstance(password_map, maps.PasswdMap))
    self.assertEquals(len(password_map), 2)
    self.assertTrue(password_map.Exists(entry1))
    self.assertTrue(password_map.Exists(entry2))

  def testGetGroupMap(self):
    """Verify we build a correct group map from nss calls."""

    def FakeGetGrAll():
      foo = ('foo', '*', 10, [])
      bar = ('bar', '*', 20, ['foo', 'bar'])
      return [foo, bar]

    entry1 = maps.GroupMapEntry()
    entry1.name = 'foo'
    entry1.passwd = '*'
    entry1.gid = 10
    entry1.members = ['']

    entry2 = maps.GroupMapEntry()
    entry2.name = 'bar'
    entry2.passwd = '*'
    entry2.gid = 20
    entry2.members = ['foo', 'bar']

    grp.getgrall = FakeGetGrAll

    group_map = nss.GetGroupMap()

    self.assertTrue(isinstance(group_map, maps.GroupMap))
    self.assertEquals(len(group_map), 2)
    self.assertTrue(group_map.Exists(entry1))
    self.assertTrue(group_map.Exists(entry2))

  def testGetShadowMap(self):
    """Verify we build a correct shadow map from nss calls."""

    def FakeSpawnGetent(map_name):
      self.assertEquals(config.MAP_SHADOW, map_name)
      return self.mock_getent

    line1 = 'foo:!!::::::::'
    line2 = 'bar:!!::::::::'
    lines = [line1, line2]

    self.mock_getent = self.mock()
    self.mock_getent\
                      .expects(pmock.once())\
                      .wait()\
                      .will(pmock.return_value(0))

    mock_read = self.mock()
    mock_read\
               .expects(pmock.once())\
               .read()\
               .will(pmock.return_value(None))

    self.mock_getent.fromchild = lines
    self.mock_getent.childerr = mock_read

    entry1 = maps.ShadowMapEntry()
    entry1.name = 'foo'
    entry2 = maps.ShadowMapEntry()
    entry2.name = 'bar'

    orig_spawngetent = nss._SpawnGetent
    nss._SpawnGetent = FakeSpawnGetent

    shadow_map = nss.GetShadowMap()

    nss._SpawnGetEnt = orig_spawngetent

    self.assertTrue(isinstance(shadow_map, maps.ShadowMap))
    self.assertEquals(len(shadow_map), 2)
    self.assertTrue(shadow_map.Exists(entry1))
    self.assertTrue(shadow_map.Exists(entry2))


if __name__ == '__main__':
  unittest.main()
