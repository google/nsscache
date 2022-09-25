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
"""Unit tests for nss_cache/nss.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import grp
import pwd
import subprocess
import unittest
from unittest import mock

from nss_cache import config
from nss_cache import error
from nss_cache import nss

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow


class TestNSS(unittest.TestCase):
    """Tests for the NSS library."""

    def testGetMap(self):
        """that GetMap is calling the right GetFooMap routines."""

        # stub, retval, arg
        maps = (
            ('nss.GetPasswdMap', 'TEST_PASSWORD', config.MAP_PASSWORD),
            ('nss.GetGroupMap', 'TEST_GROUP', config.MAP_GROUP),
            ('nss.GetShadowMap, "TEST_SHADOW', config.MAP_SHADOW),
        )

        for t in maps:
            with mock.patch(t[0]) as mock_map:
                mock_map.return_value = t[1]
                self.assertEqual(t[1], nss.GetMap(t[2]))

    def testGetMapException(self):
        """GetMap throws error.UnsupportedMap for unsupported maps."""
        self.assertRaises(error.UnsupportedMap, nss.GetMap, 'ohio')

    def testGetPasswdMap(self):
        """Verify we build a correct password map from nss calls."""
        # mocks
        entry1 = passwd.PasswdMapEntry()
        entry1.name = 'foo'
        entry1.uid = 10
        entry1.gid = 10
        entry1.gecos = 'foo bar'
        entry1.dir = '/home/foo'
        entry1.shell = '/bin/shell'

        entry2 = passwd.PasswdMapEntry()
        entry2.name = 'bar'
        entry2.uid = 20
        entry2.gid = 20
        entry2.gecos = 'foo bar'
        entry2.dir = '/home/monkeyboy'
        entry2.shell = '/bin/shell'
        foo = ('foo', 'x', 10, 10, 'foo bar', '/home/foo', '/bin/shell')
        bar = ('bar', 'x', 20, 20, 'foo bar', '/home/monkeyboy', '/bin/shell')

        # stubs
        with mock.patch('pwd.getpwall') as mock_pwall:
            mock_pwall.return_value = [foo, bar]
            password_map = nss.GetPasswdMap()
            self.assertTrue(isinstance(password_map, passwd.PasswdMap))
            self.assertEqual(len(password_map), 2)
            self.assertTrue(password_map.Exists(entry1))
            self.assertTrue(password_map.Exists(entry2))

    def testGetGroupMap(self):
        """Verify we build a correct group map from nss calls."""

        # mocks
        entry1 = group.GroupMapEntry()
        entry1.name = 'foo'
        entry1.passwd = '*'
        entry1.gid = 10
        entry1.members = ['']
        entry2 = group.GroupMapEntry()
        entry2.name = 'bar'
        entry2.passwd = '*'
        entry2.gid = 20
        entry2.members = ['foo', 'bar']
        foo = ('foo', '*', 10, [])
        bar = ('bar', '*', 20, ['foo', 'bar'])

        # stubs
        with mock.patch('grp.getgrall') as mock_grpall:
            mock_grpall.return_value = [foo, bar]
            group_map = nss.GetGroupMap()
            self.assertTrue(isinstance(group_map, group.GroupMap))
            self.assertEqual(len(group_map), 2)
            self.assertTrue(group_map.Exists(entry1))
            self.assertTrue(group_map.Exists(entry2))

    def testGetShadowMap(self):
        """Verify we build a correct shadow map from nss calls."""
        line1 = b'foo:!!::::::::'
        line2 = b'bar:!!::::::::'

        entry1 = shadow.ShadowMapEntry()
        entry1.name = 'foo'
        entry2 = shadow.ShadowMapEntry()
        entry2.name = 'bar'

        with mock.patch('nss._SpawnGetent') as mock_getent:
            # stub
            mock_process = mock.create_autospec(subprocess.Popen)
            mock_getent.return_value = mock_process
            mock_process.communicate.return_value = [b'\n'.join([line1, line2]), b'']
            mock_process.return_code = 0
            # test
            shadow_map = nss.GetShadowMap()
            self.assertTrue(isinstance(shadow_map, shadow.ShadowMap))
            self.assertEqual(len(shadow_map), 2)
            self.assertTrue(shadow_map.Exists(entry1))
            self.assertTrue(shadow_map.Exists(entry2))


if __name__ == '__main__':
    unittest.main()
