# Copyright 2026 Google Inc.
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
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
"""Regression tests for LDAP group-member regex transformations."""

import unittest

from nss_cache.sources import ldapsource


class GroupRegexTest(unittest.TestCase):
    def testMemberUidRegexPreservesWholeMembers(self):
        members = ["bob@example.com", "alice@example.com"]
        getter = ldapsource.GroupUpdateGetter({"groupregex": r"(.*)@example\.com"})
        entry = getter.Transform(
            {"cn": ["staff"], "gidNumber": ["1000"], "memberUid": members}
        )
        self.assertEqual(["alice", "bob"], entry.members)
        self.assertEqual("staff", entry.name)
        self.assertEqual(1000, entry.gid)
        self.assertEqual(["bob@example.com", "alice@example.com"], members)

    def testEmptyMemberUidRegex(self):
        getter = ldapsource.GroupUpdateGetter({"groupregex": r"(.*)@example\.com"})
        entry = getter.Transform(
            {"cn": ["staff"], "gidNumber": ["1000"], "memberUid": []}
        )
        self.assertEqual([], entry.members)

    def testNoRegexPreservesMemberNames(self):
        entry = ldapsource.GroupUpdateGetter({}).Transform(
            {
                "cn": ["staff"],
                "gidNumber": ["1000"],
                "memberUid": ["bob@example.com", "alice@example.com"],
            }
        )
        self.assertEqual(["alice@example.com", "bob@example.com"], entry.members)

    def testMemberDnRegexStillWorks(self):
        getter = ldapsource.GroupUpdateGetter(
            {"groupregex": r"(.*)@example\.com", "rfc2307bis": True}
        )
        entry = getter.Transform(
            {
                "cn": ["staff"],
                "gidNumber": ["1000"],
                "member": ["uid=alice@example.com,dc=example,dc=com"],
            }
        )
        self.assertEqual(["alice"], entry.members)


if __name__ == "__main__":
    unittest.main()
