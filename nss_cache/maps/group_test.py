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

"""Unit tests for group.py.

We only test what is overridden in the group subclasses, most
functionality is in base.py and tested in passwd_test.py since a
subclass is required to test the abstract class functionality.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import unittest

from nss_cache.maps import group
from nss_cache.maps import passwd


class TestGroupMap(unittest.TestCase):
  """Tests for the GroupMap class."""
  
  def __init__(self, obj):
    """Set some default avalible data for testing."""
    super(TestGroupMap, self).__init__(obj)
    self._good_entry = group.GroupMapEntry()
    self._good_entry.name = 'foo'
    self._good_entry.passwd = 'x'
    self._good_entry.gid = 10
    self._good_entry.members = ['foo', 'bar']
    
  def testInit(self):
    """Construct an empty or seeded GroupMap."""
    self.assertEqual(group.GroupMap, type(group.GroupMap()),
                      msg='failed to create an empty GroupMap')
    gmap = group.GroupMap([self._good_entry])
    self.assertEqual(self._good_entry, gmap.PopItem(),
                      msg='failed to seed GroupMap with list')
    self.assertRaises(TypeError, group.GroupMap, ['string'])

  def testAdd(self):
    """Add throws an error for objects it can't verify."""
    gmap = group.GroupMap()
    entry = self._good_entry
    self.assertTrue(gmap.Add(entry), msg='failed to append new entry.')

    self.assertEqual(1, len(gmap), msg='unexpected size for Map.')
        
    ret_entry = gmap.PopItem()
    self.assertEqual(ret_entry, entry, msg='failed to pop correct entry.')

    pentry = passwd.PasswdMapEntry()
    pentry.name = 'foo'
    pentry.uid = 10
    pentry.gid = 10
    self.assertRaises(TypeError, gmap.Add, pentry)


class TestGroupMapEntry(unittest.TestCase):
  """Tests for the GroupMapEntry class."""
    
  def testInit(self):
    """Construct an empty and seeded GroupMapEntry."""
    self.assertTrue(group.GroupMapEntry(),
                 msg='Could not create empty GroupMapEntry')
    seed = {'name': 'foo', 'gid': 10}
    entry = group.GroupMapEntry(seed)
    self.assertTrue(entry.Verify(),
                 msg='Could not verify seeded PasswdMapEntry')
    self.assertEqual(entry.name, 'foo',
                      msg='Entry returned wrong value for name')
    self.assertEqual(entry.passwd, 'x',
                      msg='Entry returned wrong value for passwd')
    self.assertEqual(entry.gid, 10,
                      msg='Entry returned wrong value for gid')
    self.assertEqual(entry.members, [],
                      msg='Entry returned wrong value for members')

  def testAttributes(self):
    """Test that we can get and set all expected attributes."""
    entry = group.GroupMapEntry()
    entry.name = 'foo'
    self.assertEqual(entry.name, 'foo',
                      msg='Could not set attribute: name')
    entry.passwd = 'x'
    self.assertEqual(entry.passwd, 'x',
                      msg='Could not set attribute: passwd')
    entry.gid = 10
    self.assertEqual(entry.gid, 10,
                      msg='Could not set attribute: gid')
    members = ['foo', 'bar']
    entry.members = members
    self.assertEqual(entry.members, members,
                      msg='Could not set attribute: members')

  def testVerify(self):
    """Test that the object can verify it's attributes and itself."""
    entry = group.GroupMapEntry()
    
    # Empty object should bomb
    self.assertFalse(entry.Verify())

  def testKey(self):
    """Key() should return the value of the 'name' attribute."""
    entry = group.GroupMapEntry()
    entry.name = 'foo'
    self.assertEqual(entry.Key(), entry.name)


if __name__ == '__main__':
  unittest.main()
