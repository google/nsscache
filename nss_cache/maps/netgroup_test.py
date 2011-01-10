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

"""Unit tests for netgroup.py.

We only test what is overridden in the netgroup subclasses, most
functionality is in base.py and tested in passwd_test.py since a
subclass is required to test the abstract class functionality.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import unittest

from nss_cache import maps


class TestNetgroupMap(unittest.TestCase):
  """Tests for the NetgroupMap class."""
  
  def __init__(self, obj):
    """Set some default avalible data for testing."""
    super(TestNetgroupMap, self).__init__(obj)
    self._good_entry = maps.NetgroupMapEntry()
    self._good_entry.name = 'foo'
    self._good_entry.entries = [('-', 'bob', None), 'othernetgroup']
    
  def testInit(self):
    """Construct an empty or seeded NetgroupMap."""
    self.assertEquals(maps.NetgroupMap, type(maps.NetgroupMap()),
                      msg='failed to create an empty NetgroupMap')
    nmap = maps.NetgroupMap([self._good_entry])
    self.assertEquals(self._good_entry, nmap.PopItem(),
                      msg='failed to seed NetgroupMap with list')
    self.assertRaises(TypeError, maps.NetgroupMap, ['string'])

  def testAdd(self):
    """Add throws an error for objects it can't verify."""
    nmap = maps.NetgroupMap()
    entry = self._good_entry
    self.assert_(nmap.Add(entry), msg='failed to append new entry.')

    self.assertEquals(1, len(nmap), msg='unexpected size for Map.')
        
    ret_entry = nmap.PopItem()
    self.assertEquals(ret_entry, entry, msg='failed to pop correct entry.')

    pentry = maps.PasswdMapEntry()
    pentry.name = 'foo'
    pentry.uid = 10
    pentry.gid = 10
    self.assertRaises(TypeError, nmap.Add, pentry)


class TestNetgroupMapEntry(unittest.TestCase):
  """Tests for the NetgroupMapEntry class."""
    
  def testInit(self):
    """Construct an empty and seeded NetgroupMapEntry."""
    self.assert_(maps.NetgroupMapEntry(),
                 msg='Could not create empty NetgroupMapEntry')
    entries = ['bar', ('baz', '-', None)]
    seed = {'name': 'foo', 'entries': entries}
    entry = maps.NetgroupMapEntry(seed)
    self.assert_(entry.Verify(),
                 msg='Could not verify seeded NetgroupMapEntry')
    self.assertEquals(entry.name, 'foo',
                      msg='Entry returned wrong value for name')
    self.assertEquals(entry.entries, entries,
                      msg='Entry returned wrong value for entries')

  def testAttributes(self):
    """Test that we can get and set all expected attributes."""
    entry = maps.NetgroupMapEntry()
    entry.name = 'foo'
    self.assertEquals(entry.name, 'foo',
                      msg='Could not set attribute: name')
    entries = ['foo', '(-,bar,)']
    entry.entries = entries
    self.assertEquals(entry.entries, entries,
                      msg='Could not set attribute: entries')

  def testVerify(self):
    """Test that the object can verify it's attributes and itself."""
    entry = maps.NetgroupMapEntry()
    
    # Empty object should bomb
    self.failIf(entry.Verify())

  def testKey(self):
    """Key() should return the value of the 'name' attribute."""
    entry = maps.NetgroupMapEntry()
    entry.name = 'foo'
    self.assertEquals(entry.Key(), entry.name)

if __name__ == '__main__':
  unittest.main()
