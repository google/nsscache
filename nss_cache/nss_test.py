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

__author__ = "vasilios@google.com (Vasilios Hoffman)"

import grp
import pwd
import unittest
from mox3 import mox

from nss_cache import config
from nss_cache import error
from nss_cache import nss

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow


class TestNSS(mox.MoxTestBase):
    """Tests for the NSS library."""

    def testGetMap(self):
        """that GetMap is calling the right GetFooMap routines."""
        self.mox.StubOutWithMock(nss, "GetPasswdMap")
        nss.GetPasswdMap().AndReturn("TEST_PASSWORD")
        self.mox.StubOutWithMock(nss, "GetGroupMap")
        nss.GetGroupMap().AndReturn("TEST_GROUP")
        self.mox.StubOutWithMock(nss, "GetShadowMap")
        nss.GetShadowMap().AndReturn("TEST_SHADOW")

        self.mox.ReplayAll()

        self.assertEqual("TEST_PASSWORD", nss.GetMap(config.MAP_PASSWORD))
        self.assertEqual("TEST_GROUP", nss.GetMap(config.MAP_GROUP))
        self.assertEqual("TEST_SHADOW", nss.GetMap(config.MAP_SHADOW))

    def testGetMapException(self):
        """GetMap throws error.UnsupportedMap for unsupported maps."""
        self.assertRaises(error.UnsupportedMap, nss.GetMap, "ohio")

    def testGetPasswdMap(self):
        """Verify we build a correct password map from nss calls."""

        foo = ("foo", "x", 10, 10, "foo bar", "/home/foo", "/bin/shell")
        bar = ("bar", "x", 20, 20, "foo bar", "/home/monkeyboy", "/bin/shell")

        self.mox.StubOutWithMock(pwd, "getpwall")
        pwd.getpwall().AndReturn([foo, bar])

        entry1 = passwd.PasswdMapEntry()
        entry1.name = "foo"
        entry1.uid = 10
        entry1.gid = 10
        entry1.gecos = "foo bar"
        entry1.dir = "/home/foo"
        entry1.shell = "/bin/shell"

        entry2 = passwd.PasswdMapEntry()
        entry2.name = "bar"
        entry2.uid = 20
        entry2.gid = 20
        entry2.gecos = "foo bar"
        entry2.dir = "/home/monkeyboy"
        entry2.shell = "/bin/shell"

        self.mox.ReplayAll()

        password_map = nss.GetPasswdMap()

        self.assertTrue(isinstance(password_map, passwd.PasswdMap))
        self.assertEqual(len(password_map), 2)
        self.assertTrue(password_map.Exists(entry1))
        self.assertTrue(password_map.Exists(entry2))

    def testGetGroupMap(self):
        """Verify we build a correct group map from nss calls."""

        foo = ("foo", "*", 10, [])
        bar = ("bar", "*", 20, ["foo", "bar"])

        self.mox.StubOutWithMock(grp, "getgrall")
        grp.getgrall().AndReturn([foo, bar])

        entry1 = group.GroupMapEntry()
        entry1.name = "foo"
        entry1.passwd = "*"
        entry1.gid = 10
        entry1.members = [""]

        entry2 = group.GroupMapEntry()
        entry2.name = "bar"
        entry2.passwd = "*"
        entry2.gid = 20
        entry2.members = ["foo", "bar"]

        self.mox.ReplayAll()

        group_map = nss.GetGroupMap()

        self.assertTrue(isinstance(group_map, group.GroupMap))
        self.assertEqual(len(group_map), 2)
        self.assertTrue(group_map.Exists(entry1))
        self.assertTrue(group_map.Exists(entry2))

    def testGetShadowMap(self):
        """Verify we build a correct shadow map from nss calls."""
        line1 = b"foo:!!::::::::"
        line2 = b"bar:!!::::::::"
        lines = [line1, line2]

        mock_getent = self.mox.CreateMockAnything()
        mock_getent.communicate().AndReturn([b"\n".join(lines), b""])
        mock_getent.returncode = 0

        entry1 = shadow.ShadowMapEntry()
        entry1.name = "foo"
        entry2 = shadow.ShadowMapEntry()
        entry2.name = "bar"

        self.mox.StubOutWithMock(nss, "_SpawnGetent")
        nss._SpawnGetent(config.MAP_SHADOW).AndReturn(mock_getent)

        self.mox.ReplayAll()

        shadow_map = nss.GetShadowMap()

        self.assertTrue(isinstance(shadow_map, shadow.ShadowMap))
        self.assertEqual(len(shadow_map), 2)
        self.assertTrue(shadow_map.Exists(entry1))
        self.assertTrue(shadow_map.Exists(entry2))


if __name__ == "__main__":
    unittest.main()
