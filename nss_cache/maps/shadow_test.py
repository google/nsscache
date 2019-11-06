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
"""Unit tests for shadow.py.

We only test what is overridden in the shadow subclasses, most
functionality is in base.py and tested in passwd_test.py since a
subclass is required to test the abstract class functionality.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import unittest

from nss_cache.maps import passwd
from nss_cache.maps import shadow


class TestShadowMap(unittest.TestCase):
    """Tests for the ShadowMap class."""

    def __init__(self, obj):
        """Set some default avalible data for testing."""
        super(TestShadowMap, self).__init__(obj)
        self._good_entry = shadow.ShadowMapEntry()
        self._good_entry.name = 'foo'
        self._good_entry.lstchg = None
        self._good_entry.min = None
        self._good_entry.max = None
        self._good_entry.warn = None
        self._good_entry.inact = None
        self._good_entry.expire = None
        self._good_entry.flag = None

    def testInit(self):
        """Construct an empty or seeded ShadowMap."""
        self.assertEqual(shadow.ShadowMap,
                         type(shadow.ShadowMap()),
                         msg='failed to create emtpy ShadowMap')
        smap = shadow.ShadowMap([self._good_entry])
        self.assertEqual(self._good_entry,
                         smap.PopItem(),
                         msg='failed to seed ShadowMap with list')
        self.assertRaises(TypeError, shadow.ShadowMap, ['string'])

    def testAdd(self):
        """Add throws an error for objects it can't verify."""
        smap = shadow.ShadowMap()
        entry = self._good_entry
        self.assertTrue(smap.Add(entry), msg='failed to append new entry.')

        self.assertEqual(1, len(smap), msg='unexpected size for Map.')

        ret_entry = smap.PopItem()
        self.assertEqual(ret_entry, entry, msg='failed to pop existing entry.')

        pentry = passwd.PasswdMapEntry()
        pentry.name = 'foo'
        pentry.uid = 10
        pentry.gid = 10
        self.assertRaises(TypeError, smap.Add, pentry)


class TestShadowMapEntry(unittest.TestCase):
    """Tests for the ShadowMapEntry class."""

    def testInit(self):
        """Construct empty and seeded ShadowMapEntry."""
        self.assertTrue(shadow.ShadowMapEntry(),
                        msg='Could not create empty ShadowMapEntry')
        seed = {'name': 'foo'}
        entry = shadow.ShadowMapEntry(seed)
        self.assertTrue(entry.Verify(),
                        msg='Could not verify seeded ShadowMapEntry')
        self.assertEqual(entry.name,
                         'foo',
                         msg='Entry returned wrong value for name')
        self.assertEqual(entry.passwd,
                         '!!',
                         msg='Entry returned wrong value for passwd')
        self.assertEqual(entry.lstchg,
                         None,
                         msg='Entry returned wrong value for lstchg')
        self.assertEqual(entry.min,
                         None,
                         msg='Entry returned wrong value for min')
        self.assertEqual(entry.max,
                         None,
                         msg='Entry returned wrong value for max')
        self.assertEqual(entry.warn,
                         None,
                         msg='Entry returned wrong value for warn')
        self.assertEqual(entry.inact,
                         None,
                         msg='Entry returned wrong value for inact')
        self.assertEqual(entry.expire,
                         None,
                         msg='Entry returned wrong value for expire')
        self.assertEqual(entry.flag,
                         None,
                         msg='Entry returned wrong value for flag')

    def testAttributes(self):
        """Test that we can get and set all expected attributes."""
        entry = shadow.ShadowMapEntry()
        entry.name = 'foo'
        self.assertEqual(entry.name, 'foo', msg='Could not set attribute: name')
        entry.passwd = 'seekret'
        self.assertEqual(entry.passwd,
                         'seekret',
                         msg='Could not set attribute: passwd')
        entry.lstchg = 0
        self.assertEqual(entry.lstchg, 0, msg='Could not set attribute: lstchg')
        entry.min = 0
        self.assertEqual(entry.min, 0, msg='Could not set attribute: min')
        entry.max = 0
        self.assertEqual(entry.max, 0, msg='Could not set attribute: max')
        entry.warn = 0
        self.assertEqual(entry.warn, 0, msg='Could not set attribute: warn')
        entry.inact = 0
        self.assertEqual(entry.inact, 0, msg='Could not set attribute: inact')
        entry.expire = 0
        self.assertEqual(entry.expire, 0, msg='Could not set attribute: expire')
        entry.flag = 0
        self.assertEqual(entry.flag, 0, msg='Could not set attribute: flag')

    def testVerify(self):
        """Test that the object can verify it's attributes and itself."""
        entry = shadow.ShadowMapEntry()

        # Emtpy object should bomb
        self.assertFalse(entry.Verify())

    def testKey(self):
        """Key() should return the value of the 'name' attribute."""
        entry = shadow.ShadowMapEntry()
        entry.name = 'foo'
        self.assertEqual(entry.Key(), entry.name)


if __name__ == '__main__':
    unittest.main()
