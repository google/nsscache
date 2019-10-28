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

"""Unit tests for automount.py.

We only test what is overridden in the automount subclasses, most
functionality is in base.py and tested in passwd_test.py since a
subclass is required to test the abstract class functionality.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import unittest

from nss_cache.maps import automount
from nss_cache.maps import passwd


class TestAutomountMap(unittest.TestCase):
  """Tests for the AutomountMap class."""
  
  def __init__(self, obj):
    """Set some default avalible data for testing."""
    super(TestAutomountMap, self).__init__(obj)
    self._good_entry = automount.AutomountMapEntry()
    self._good_entry.key = 'foo'
    self._good_entry.options = '-tcp'
    self._good_entry.location = 'nfsserver:/mah/stuff'
    
  def testInit(self):
    """Construct an empty or seeded AutomountMap."""
    self.assertEqual(automount.AutomountMap, type(automount.AutomountMap()),
                      msg='failed to create an empty AutomountMap')
    amap = automount.AutomountMap([self._good_entry])
    self.assertEqual(self._good_entry, amap.PopItem(),
                      msg='failed to seed AutomountMap with list')
    self.assertRaises(TypeError, automount.AutomountMap, ['string'])

  def testAdd(self):
    """Add throws an error for objects it can't verify."""
    amap = automount.AutomountMap()
    entry = self._good_entry
    self.assertTrue(amap.Add(entry), msg='failed to append new entry.')

    self.assertEqual(1, len(amap), msg='unexpected size for Map.')
        
    ret_entry = amap.PopItem()
    self.assertEqual(ret_entry, entry, msg='failed to pop correct entry.')

    pentry = passwd.PasswdMapEntry()
    pentry.name = 'foo'
    pentry.uid = 10
    pentry.gid = 10
    self.assertRaises(TypeError, amap.Add, pentry)


class TestAutomountMapEntry(unittest.TestCase):
  """Tests for the AutomountMapEntry class."""
    
  def testInit(self):
    """Construct an empty and seeded AutomountMapEntry."""
    self.assertTrue(automount.AutomountMapEntry(),
                 msg='Could not create empty AutomountMapEntry')
    seed = {'key': 'foo', 'location': '/dev/sda1'}
    entry = automount.AutomountMapEntry(seed)
    self.assertTrue(entry.Verify(),
                 msg='Could not verify seeded AutomountMapEntry')
    self.assertEqual(entry.key, 'foo',
                      msg='Entry returned wrong value for name')
    self.assertEqual(entry.options, None,
                      msg='Entry returned wrong value for options')
    self.assertEqual(entry.location, '/dev/sda1',
                      msg='Entry returned wrong value for location')

  def testAttributes(self):
    """Test that we can get and set all expected attributes."""
    entry = automount.AutomountMapEntry()
    entry.key = 'foo'
    self.assertEqual(entry.key, 'foo',
                      msg='Could not set attribute: key')
    entry.options = 'noatime'
    self.assertEqual(entry.options, 'noatime',
                      msg='Could not set attribute: options')
    entry.location = '/dev/ipod'
    self.assertEqual(entry.location, '/dev/ipod',
                      msg='Could not set attribute: location')

  def testVerify(self):
    """Test that the object can verify it's attributes and itself."""
    entry = automount.AutomountMapEntry()
        
    # Empty object should bomb
    self.assertFalse(entry.Verify())

  def testKey(self):
    """Key() should return the value of the 'key' attribute."""
    entry = automount.AutomountMapEntry()
    entry.key = 'foo'
    self.assertEqual(entry.Key(), entry.key)


if __name__ == '__main__':
  unittest.main()
