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
"""Unit tests for netgroup.py.

We only test what is overridden in the netgroup subclasses, most
functionality is in base.py and tested in passwd_test.py since a
subclass is required to test the abstract class functionality.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import unittest

from nss_cache.maps import netgroup
from nss_cache.maps import passwd


class TestNetgroupMap(unittest.TestCase):
  """Tests for the NetgroupMap class."""

  def __init__(self, obj):
    """Set some default avalible data for testing."""
    super(TestNetgroupMap, self).__init__(obj)
    self._good_entry = netgroup.NetgroupMapEntry()
    self._good_entry.name = 'foo'
    self._good_entry.entries = [('-', 'bob', None), 'othernetgroup']

  def testInit(self):
    """Construct an empty or seeded NetgroupMap."""
    self.assertEqual(
        netgroup.NetgroupMap,
        type(netgroup.NetgroupMap()),
        msg='failed to create an empty NetgroupMap')
    nmap = netgroup.NetgroupMap([self._good_entry])
    self.assertEqual(
        self._good_entry,
        nmap.PopItem(),
        msg='failed to seed NetgroupMap with list')
    self.assertRaises(TypeError, netgroup.NetgroupMap, ['string'])

  def testAdd(self):
    """Add throws an error for objects it can't verify."""
    nmap = netgroup.NetgroupMap()
    entry = self._good_entry
    self.assertTrue(nmap.Add(entry), msg='failed to append new entry.')

    self.assertEqual(1, len(nmap), msg='unexpected size for Map.')

    ret_entry = nmap.PopItem()
    self.assertEqual(ret_entry, entry, msg='failed to pop correct entry.')

    pentry = passwd.PasswdMapEntry()
    pentry.name = 'foo'
    pentry.uid = 10
    pentry.gid = 10
    self.assertRaises(TypeError, nmap.Add, pentry)


class TestNetgroupMapEntry(unittest.TestCase):
  """Tests for the NetgroupMapEntry class."""

  def testInit(self):
    """Construct an empty and seeded NetgroupMapEntry."""
    self.assertTrue(
        netgroup.NetgroupMapEntry(),
        msg='Could not create empty NetgroupMapEntry')
    entries = ['bar', ('baz', '-', None)]
    seed = {'name': 'foo', 'entries': entries}
    entry = netgroup.NetgroupMapEntry(seed)
    self.assertTrue(
        entry.Verify(), msg='Could not verify seeded NetgroupMapEntry')
    self.assertEqual(
        entry.name, 'foo', msg='Entry returned wrong value for name')
    self.assertEqual(
        entry.entries, entries, msg='Entry returned wrong value for entries')

  def testAttributes(self):
    """Test that we can get and set all expected attributes."""
    entry = netgroup.NetgroupMapEntry()
    entry.name = 'foo'
    self.assertEqual(entry.name, 'foo', msg='Could not set attribute: name')
    entries = ['foo', '(-,bar,)']
    entry.entries = entries
    self.assertEqual(
        entry.entries, entries, msg='Could not set attribute: entries')

  def testVerify(self):
    """Test that the object can verify it's attributes and itself."""
    entry = netgroup.NetgroupMapEntry()

    # Empty object should bomb
    self.assertFalse(entry.Verify())

  def testKey(self):
    """Key() should return the value of the 'name' attribute."""
    entry = netgroup.NetgroupMapEntry()
    entry.name = 'foo'
    self.assertEqual(entry.Key(), entry.name)


if __name__ == '__main__':
  unittest.main()
