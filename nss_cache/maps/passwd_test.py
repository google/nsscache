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

"""Unit tests for passwd.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import time
import unittest

from nss_cache import maps


class TestPasswdMap(unittest.TestCase):
  """Tests for the PasswdMap class."""

  def __init__(self, obj):
    """Set some default avalible data for testing."""
    super(TestPasswdMap, self).__init__(obj)
    self._good_entry = maps.PasswdMapEntry()
    self._good_entry.name = 'foo'
    self._good_entry.passwd = 'x'
    self._good_entry.uid = 10
    self._good_entry.gid = 10
    self._good_entry.gecos = 'How Now Brown Cow'
    self._good_entry.dir = '/home/foo'
    self._good_entry.shell = '/bin/bash'

  def testInit(self):
    """Construct an empty or seeded PasswdMap."""
    self.assertEquals(maps.PasswdMap, type(maps.PasswdMap()),
                      msg='failed to create emtpy PasswdMap')
    pmap = maps.PasswdMap([self._good_entry])
    self.assertEquals(self._good_entry, pmap.PopItem(),
                      msg='failed to seed PasswdMap with list')
    self.assertRaises(TypeError, maps.PasswdMap, ['string'])

  def testAdd(self):
    """Add raises exceptions for objects it can't add or verify."""
    pmap = maps.PasswdMap()
    entry = self._good_entry
    self.assert_(pmap.Add(entry),
                 msg='failed to add new entry.')

    self.assertEquals(1, len(pmap),
                      msg='unexpected size for Map.')

    ret_entry = pmap.PopItem()
    self.assertEquals(ret_entry, entry,
                      msg='failed to pop existing entry.')

    gentry = maps.GroupMapEntry()
    gentry.name = 'foo'
    gentry.gid = 10
    self.assertRaises(TypeError, pmap.Add, gentry)

  def testAddRegister(self):
    """Test that Add(MapEntry) calls MapEntry.Register(self)."""
    pmap = maps.PasswdMap()
    entry = self._good_entry
    pmap.Add(entry)
    self.assertTrue(pmap in entry._registered,
                    msg='Could not find pmap in registered list')
    pmap.PopItem()
    self.assertFalse(pmap in entry._registered,
                     msg='MapEntry still registered')
    pmap.Add(entry)
    pmap.Add(entry)
    self.assertEquals(len(entry._registered), 1,
                      msg='Registered twice without UnRegister')

  def testContains(self):
    """Verify __contains__ works, and does a deep compare."""
    pentry_good = self._good_entry
    pentry_bad = maps.PasswdMapEntry()
    pentry_bad.name = 'bar'
    pentry_likegood = maps.PasswdMapEntry(pentry_good._data)
    
    pmap = maps.PasswdMap([pentry_good])
    
    self.assertTrue(pentry_good in pmap,
                    msg='expected entry to be in map')
    self.assertFalse(pentry_bad in pmap,
                     msg='did not expect entry to be in map')
    self.assertTrue(pentry_likegood in pmap,
                    msg='__contains__ not doing a deep compare')

  def testIterate(self):
    """Check that we can iterate over PasswdMap."""
    pmap = maps.PasswdMap()
    pmap.Add(self._good_entry)
    ret_entries = []
    for entry in pmap:
      ret_entries.append(entry)
    self.assertEquals(len(ret_entries), 1,
                      msg='iterated over wrong count')
    self.assertEquals(ret_entries[0], self._good_entry,
                      msg='got the wrong entry back')

  def testLen(self):
    """Verify we have correctly overridden __len__ in MapEntry."""
    pmap = maps.PasswdMap()
    self.assertEquals(len(pmap), 0,
                      msg='expected len(pmap) to be 0')
    pmap.Add(self._good_entry)
    self.assertEquals(len(pmap), 1,
                      msg='expected len(pmap) to be 1')

  def testExists(self):
    """Verify Exists() checks for presence of MapEntry objects."""
    pmap = maps.PasswdMap()
    entry = self._good_entry
    self.assertFalse(pmap.Exists(entry))
    pmap.Add(entry)
    self.assertTrue(pmap.Exists(entry))

  def testMerge(self):
    """Verify Merge() throws TypeError and correctly merges objects."""
    
    # Setup some MapEntry objects with distinct Key()s
    pentry1 = maps.PasswdMapEntry(self._good_entry._data)
    pentry2 = maps.PasswdMapEntry(self._good_entry._data)
    pentry2.name = 'john'
    pentry3 = maps.PasswdMapEntry(self._good_entry._data)
    pentry3.name = 'jane'

    # Setup some Map objects
    pmap_big = maps.PasswdMap([pentry1, pentry2])
    pmap_small = maps.PasswdMap([pentry3])

    # Merge small into big
    self.assertTrue(pmap_big.Merge(pmap_small),
                    msg='Merging small into big failed!')
    self.assertTrue(pmap_big.Exists(pentry1),
                    msg='pentry1 not found in Map')
    self.assertTrue(pmap_big.Exists(pentry2),
                    msg='pentry1 not found in Map')
    self.assertTrue(pmap_big.Exists(pentry3),
                    msg='pentry1 not found in Map')

    # A second merge should do nothing
    self.assertFalse(pmap_big.Merge(pmap_small),
                     msg='Re-merging small into big succeeded.')

    # An empty merge should do nothing
    self.assertFalse(pmap_big.Merge(maps.PasswdMap()),
                     msg='Empty Merge should have done nothing.')

    # Merge a GroupMap should throw TypeError
    gmap = maps.GroupMap()
    self.assertRaises(TypeError, pmap_big.Merge, gmap)

  def testPopItem(self):
    """Verify you can retrieve MapEntry with PopItem."""
    pmap = maps.PasswdMap([self._good_entry])
    self.assertEquals(pmap.PopItem(), self._good_entry)

  def testRemove(self):
    """Verify you can remove a specific MapEntry from a Map."""

    # Setup some maps and entries
    pmap = maps.PasswdMap()
    pentry_good = self._good_entry
    pentry_likegood = maps.PasswdMapEntry(pentry_good._data)
    pentry_bad1 = maps.PasswdMapEntry()
    pentry_bad1.name = 'bar'
    pentry_bad1.uid = 10
    pentry_bad1.gid = 10
    pentry_bad2 = maps.PasswdMapEntry(pentry_good._data)
    pentry_bad2.uid = 11

    pmap.Add(pentry_good)
    self.assertEquals(pmap.Remove(pentry_good), pentry_good,
                      msg='Failed to remove same entry')
  
    pmap.Add(pentry_good)
    self.assertEquals(pmap.Remove(pentry_bad1), None,
                      msg='Expected None for pentry_bad1')
    self.assertEquals(pmap.Remove(pentry_bad2), None,
                      msg='Expected None for pentry_bad2')
    self.assertEquals(pmap.Remove(pentry_likegood), pentry_good,
                      msg='Failed to do deep compare on Remove')
  
  def testUpdateKey(self):
    """Verify that UpdateKey changes the indexed key MapEntry objects."""

    # Setup some maps and entries
    pmap = maps.PasswdMap()
    entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    pmap.Add(entry)

    # Test UpdateKey directly
    entry._data['name'] = 'bar'  # the sneaky way, avoiding Set()!
    self.assertTrue(pmap.UpdateKey('foo', 'bar'),
                    msg='failed to update key from foo to bar')
    self.assertEquals(pmap.Remove(entry), entry,
                      msg='failed to retrieve modified entry')
    
    # Test UpdateKey via Set() and Register()
    pmap.Add(entry)
    entry.name = 'jane'
    self.assertTrue(pmap.Exists(entry),
                    msg='changed MapEntry, lost index')
    self.assertEquals(pmap.Remove(entry), entry,
                      msg='failed to retrieve modified entry')

  def testLastModificationTimestamp(self):
    """Test setting/getting of timestamps on maps."""
    
    m = maps.PasswdMap()
    
    # we only work in whole-second resolution
    now = int(time.time())
    
    m.SetModifyTimestamp(now)
    
    self.assertEqual(now, m._last_modification_timestamp)

    ts = m.GetModifyTimestamp()
    
    self.assertEqual(now, ts)


class TestPasswdMapEntry(unittest.TestCase):
  """Tests for the PasswdMapEntry class."""
  
  def testInit(self):
    """Construct empty and seeded PasswdMapEntry."""
    entry = maps.PasswdMapEntry()
    self.assertEquals(type(entry), maps.PasswdMapEntry,
                      msg='Could not create empty PasswdMapEntry')
    seed = {'name': 'foo', 'uid': 10, 'gid': 10}
    entry = maps.PasswdMapEntry(seed)
    self.assert_(entry.Verify(),
                 msg='Could not verify seeded PasswdMapEntry')
    self.assertEquals(entry.name, 'foo',
                      msg='Entry returned wrong value for name')
    self.assertEquals(entry.passwd, 'x',
                      msg='Entry returned wrong value for passwd')
    self.assertEquals(entry.uid, 10,
                      msg='Entry returned wrong value for uid')
    self.assertEquals(entry.gid, 10,
                      msg='Entry returned wrong value for gid')
    self.assertEquals(entry.gecos, '',
                      msg='Entry returned wrong value for gecos')
    self.assertEquals(entry.dir, '',
                      msg='Entry returned wrong value for dir')
    self.assertEquals(entry.shell, '',
                      msg='Entry returned wrong value for shell')

  def testAttributes(self):
    """Test that we can get and set all expected attributes."""
    entry = maps.PasswdMapEntry()
    entry.name = 'foo'
    self.assertEquals(entry.name, 'foo',
                      msg='Could not set attribute: name')
    entry.passwd = 'x'
    self.assertEquals(entry.passwd, 'x',
                      msg='Could not set attribute: passwd')
    entry.uid = 10
    self.assertEquals(entry.uid, 10,
                      msg='Could not set attribute: uid')
    entry.gid = 10
    self.assertEquals(entry.gid, 10,
                      msg='Could not set attribute: gid')
    entry.gecos = 'How Now Brown Cow'
    self.assertEquals(entry.gecos, 'How Now Brown Cow',
                      msg='Could not set attribute: gecos')
    entry.dir = '/home/foo'
    self.assertEquals(entry.dir, '/home/foo',
                      msg='Could not set attribute: dir')
    entry.shell = '/bin/bash'
    self.assertEquals(entry.shell, '/bin/bash',
                      msg='Could not set attribute: shell')

  def testEq(self):
    """Verify we are doing a deep compare in __eq__."""
    
    # Setup some things to compare
    entry_good = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    entry_likegood = maps.PasswdMapEntry(entry_good._data)
    entry_bad = maps.PasswdMapEntry(entry_good._data)
    entry_bad.name = 'bar'
    
    self.assertEquals(entry_good, entry_good,
                      msg='entry_good not equal to itself')
    self.assertEquals(entry_good, entry_likegood,
                      msg='__eq__ not doing deep compare')
    self.assertNotEqual(entry_good, entry_bad,
                        msg='unexpected equality')
    
  def testRegister(self):
    """Test that we can register a Map with a MapEntry."""
    pmap = maps.PasswdMap()
    entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    entry.Register(pmap)
    self.assertEquals(entry._registered, [pmap],
                      msg='Unexpected value for _registered')

  def testUnRegister(self):
    """Test that we can unregister a Map with a MapEntry."""
    pmap = maps.PasswdMap()
    entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    entry.Register(pmap)
    entry.UnRegister(pmap)
    self.assertEquals(entry._registered, [],
                      msg='Unexpected value for _registered')

  def testVerify(self):
    """Test that the object can verify it's attributes and itself."""
    entry = maps.PasswdMapEntry()
    
    # Pass bad values for each entry.
    self.assertRaises(AttributeError, entry.Set, 'name', None)
    self.assertRaises(AttributeError, entry.Set, 'passwd', None)
    self.assertRaises(AttributeError, entry.Set, 'uid', None)
    self.assertRaises(AttributeError, entry.Set, 'gid', None)
    self.assertRaises(AttributeError, entry.Set, 'gecos', None)
    self.assertRaises(AttributeError, entry.Set, 'dir', None)
    self.assertRaises(AttributeError, entry.Set, 'shell', None)
    
    # Note that the above Set() calls actuall leave bad data behind.
    # So the emtpy object should bomb below.
    self.failIf(entry.Verify())

  def testKey(self):
    """Key() should return the value of the 'name' attribute."""
    entry = maps.PasswdMapEntry()
    entry.name = 'foo'
    self.assertEquals(entry.Key(), entry.name)

  def testColonCancer(self):
    """Test that attributes of type string will not accept ':' as valid."""
    entry = maps.PasswdMapEntry()
    self.assertRaises(AttributeError, entry.Set, 'name', 'foo:bar')

if __name__ == '__main__':
  unittest.main()
