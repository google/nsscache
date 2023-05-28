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

__author__ = "vasilios@google.com (Vasilios Hoffman)"

import time
import unittest

from nss_cache import error
from nss_cache.maps import group
from nss_cache.maps import passwd


class TestPasswdMap(unittest.TestCase):
    """Tests for the PasswdMap class."""

    def setUp(self):
        """Set some default avalible data for testing."""
        self._good_entry = passwd.PasswdMapEntry()
        self._good_entry.name = "foo"
        self._good_entry.passwd = "x"
        self._good_entry.uid = 10
        self._good_entry.gid = 10
        self._good_entry.gecos = "How Now Brown Cow"
        self._good_entry.dir = "/home/foo"
        self._good_entry.shell = "/bin/bash"

    def testInit(self):
        """Construct an empty or seeded PasswdMap."""
        self.assertEqual(
            passwd.PasswdMap,
            type(passwd.PasswdMap()),
            msg="failed to create emtpy PasswdMap",
        )
        pmap = passwd.PasswdMap([self._good_entry])
        self.assertEqual(
            self._good_entry, pmap.PopItem(), msg="failed to seed PasswdMap with list"
        )
        self.assertRaises(TypeError, passwd.PasswdMap, ["string"])

    def testAdd(self):
        """Add raises exceptions for objects it can't add or verify."""
        pmap = passwd.PasswdMap()
        entry = self._good_entry
        self.assertTrue(pmap.Add(entry), msg="failed to add new entry.")

        self.assertEqual(1, len(pmap), msg="unexpected size for Map.")

        ret_entry = pmap.PopItem()
        self.assertEqual(ret_entry, entry, msg="failed to pop existing entry.")

        gentry = group.GroupMapEntry()
        gentry.name = "foo"
        gentry.gid = 10
        self.assertRaises(TypeError, pmap.Add, gentry)

    def testContains(self):
        """Verify __contains__ works, and does a deep compare."""
        pentry_good = self._good_entry
        pentry_like_good = passwd.PasswdMapEntry()
        pentry_like_good.name = "foo"  # same Key(), but rest of attributes differ
        pentry_bad = passwd.PasswdMapEntry()
        pentry_bad.name = "bar"

        pmap = passwd.PasswdMap([pentry_good])

        self.assertTrue(pentry_good in pmap, msg="expected entry to be in map")
        self.assertFalse(pentry_bad in pmap, msg="did not expect entry to be in map")
        self.assertFalse(
            pentry_like_good in pmap, msg="__contains__ not doing a deep compare"
        )

    def testIterate(self):
        """Check that we can iterate over PasswdMap."""
        pmap = passwd.PasswdMap()
        pmap.Add(self._good_entry)
        ret_entries = []
        for entry in pmap:
            ret_entries.append(entry)
        self.assertEqual(len(ret_entries), 1, msg="iterated over wrong count")
        self.assertEqual(
            ret_entries[0], self._good_entry, msg="got the wrong entry back"
        )

    def testLen(self):
        """Verify we have correctly overridden __len__ in MapEntry."""
        pmap = passwd.PasswdMap()
        self.assertEqual(len(pmap), 0, msg="expected len(pmap) to be 0")
        pmap.Add(self._good_entry)
        self.assertEqual(len(pmap), 1, msg="expected len(pmap) to be 1")

    def testExists(self):
        """Verify Exists() checks for presence of MapEntry objects."""
        pmap = passwd.PasswdMap()
        entry = self._good_entry
        self.assertFalse(pmap.Exists(entry))
        pmap.Add(entry)
        self.assertTrue(pmap.Exists(entry))

    def testMerge(self):
        """Verify Merge() throws the right exceptions and correctly merges."""

        # Setup some MapEntry objects with distinct Key()s
        pentry1 = self._good_entry
        pentry2 = passwd.PasswdMapEntry()
        pentry2.name = "john"
        pentry3 = passwd.PasswdMapEntry()
        pentry3.name = "jane"

        # Setup some Map objects
        pmap_big = passwd.PasswdMap([pentry1, pentry2])
        pmap_small = passwd.PasswdMap([pentry3])

        # Merge small into big
        self.assertTrue(
            pmap_big.Merge(pmap_small), msg="Merging small into big failed!"
        )
        self.assertTrue(pmap_big.Exists(pentry1), msg="pentry1 not found in Map")
        self.assertTrue(pmap_big.Exists(pentry2), msg="pentry1 not found in Map")
        self.assertTrue(pmap_big.Exists(pentry3), msg="pentry1 not found in Map")

        # A second merge should do nothing
        self.assertFalse(
            pmap_big.Merge(pmap_small), msg="Re-merging small into big succeeded."
        )

        # An empty merge should do nothing
        self.assertFalse(
            pmap_big.Merge(passwd.PasswdMap()),
            msg="Empty Merge should have done nothing.",
        )

        # Merge a GroupMap should throw TypeError
        gmap = group.GroupMap()
        self.assertRaises(TypeError, pmap_big.Merge, gmap)

        # Merge an older map should throw an UnsupportedMap
        old_map = passwd.PasswdMap(modify_time=1)
        new_map = passwd.PasswdMap(modify_time=2)
        self.assertRaises(error.InvalidMerge, new_map.Merge, old_map)
        old_map = passwd.PasswdMap(update_time=1)
        new_map = passwd.PasswdMap(update_time=2)
        self.assertRaises(error.InvalidMerge, new_map.Merge, old_map)

    def testPopItem(self):
        """Verify you can retrieve MapEntry with PopItem."""
        pmap = passwd.PasswdMap([self._good_entry])
        self.assertEqual(pmap.PopItem(), self._good_entry)

    def testLastModificationTimestamp(self):
        """Test setting/getting of timestamps on maps."""
        m = passwd.PasswdMap()
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
        entry = passwd.PasswdMapEntry()
        self.assertEqual(
            type(entry),
            passwd.PasswdMapEntry,
            msg="Could not create empty PasswdMapEntry",
        )
        seed = {
            "name": "foo",
            "passwd": "x",
            "uid": 10,
            "gid": 10,
            "gecos": "",
            "dir": "",
            "shell": "",
        }
        entry = passwd.PasswdMapEntry(seed)
        self.assertTrue(entry.Verify(), msg="Could not verify seeded PasswdMapEntry")
        self.assertEqual(entry.name, "foo", msg="Entry returned wrong value for name")
        self.assertEqual(entry.passwd, "x", msg="Entry returned wrong value for passwd")
        self.assertEqual(entry.uid, 10, msg="Entry returned wrong value for uid")
        self.assertEqual(entry.gid, 10, msg="Entry returned wrong value for gid")
        self.assertEqual(entry.gecos, "", msg="Entry returned wrong value for gecos")
        self.assertEqual(entry.dir, "", msg="Entry returned wrong value for dir")
        self.assertEqual(entry.shell, "", msg="Entry returned wrong value for shell")

    def testAttributes(self):
        """Test that we can get and set all expected attributes."""
        entry = passwd.PasswdMapEntry()
        entry.name = "foo"
        self.assertEqual(entry.name, "foo", msg="Could not set attribute: name")
        entry.passwd = "x"
        self.assertEqual(entry.passwd, "x", msg="Could not set attribute: passwd")
        entry.uid = 10
        self.assertEqual(entry.uid, 10, msg="Could not set attribute: uid")
        entry.gid = 10
        self.assertEqual(entry.gid, 10, msg="Could not set attribute: gid")
        entry.gecos = "How Now Brown Cow"
        self.assertEqual(
            entry.gecos, "How Now Brown Cow", msg="Could not set attribute: gecos"
        )
        entry.dir = "/home/foo"
        self.assertEqual(entry.dir, "/home/foo", msg="Could not set attribute: dir")
        entry.shell = "/bin/bash"
        self.assertEqual(entry.shell, "/bin/bash", msg="Could not set attribute: shell")

    def testEq(self):
        """Verify we are doing a deep compare in __eq__."""

        # Setup some things to compare
        entry_good = passwd.PasswdMapEntry({"name": "foo", "uid": 10, "gid": 10})
        entry_same_as_good = passwd.PasswdMapEntry(
            {"name": "foo", "uid": 10, "gid": 10}
        )
        entry_like_good = passwd.PasswdMapEntry()
        entry_like_good.name = "foo"  # same Key(), but rest of attributes differ
        entry_bad = passwd.PasswdMapEntry()
        entry_bad.name = "bar"

        self.assertEqual(entry_good, entry_good, msg="entry_good not equal to itself")
        self.assertEqual(
            entry_good, entry_same_as_good, msg="__eq__ not doing deep compare"
        )
        self.assertNotEqual(
            entry_good, entry_like_good, msg="__eq__ not doing deep compare"
        )
        self.assertNotEqual(entry_good, entry_bad, msg="unexpected equality")

    def testVerify(self):
        """Test that the object can verify it's attributes and itself."""
        entry = passwd.PasswdMapEntry()

        # by leaving _KEY unset, we should bomb.
        self.assertFalse(entry.Verify())

    def testKey(self):
        """Key() should return the value of the 'name' attribute."""
        entry = passwd.PasswdMapEntry()
        entry.name = "foo"
        self.assertEqual(entry.Key(), entry.name)


if __name__ == "__main__":
    unittest.main()
