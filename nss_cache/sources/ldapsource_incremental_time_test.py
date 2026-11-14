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
"""Calendar-aware LDAP incremental search-filter regressions."""

import calendar
import unittest

from nss_cache.sources import ldapsource


class SearchSource(list):
    def Search(self, **kwargs):
        self.search_filter = kwargs["search_filter"]


class IncrementalTimeTest(unittest.TestCase):
    def assertSinceFilter(self, before, after):
        since = calendar.timegm(before + (0, 0, 0))
        for ad in (False, True):
            with self.subTest(ad=ad):
                source = SearchSource()
                getter = ldapsource.ShadowUpdateGetter({"ad": ad})
                getter.GetUpdates(source, "dc=example", "(objectClass=*)", "sub", since)
                attribute = "whenChanged" if ad else "modifyTimestamp"
                suffix = ".0Z" if ad else "Z"
                self.assertEqual(
                    "(&(objectClass=*)(%s>=%s%s))" % (attribute, after, suffix),
                    source.search_filter,
                )

    def testMinuteRollover(self):
        self.assertSinceFilter((2024, 1, 1, 12, 34, 59), "20240101123500")

    def testYearRollover(self):
        self.assertSinceFilter((2023, 12, 31, 23, 59, 59), "20240101000000")

    def testLeapDayRollover(self):
        self.assertSinceFilter((2024, 2, 28, 23, 59, 59), "20240229000000")

    def testZeroSeconds(self):
        self.assertSinceFilter((2024, 1, 1, 12, 34, 0), "20240101123401")

    def testFullUpdateFilterUnchanged(self):
        source = SearchSource()
        getter = ldapsource.ShadowUpdateGetter({})
        getter.GetUpdates(source, "dc=example", "(objectClass=*)", "sub", None)
        self.assertEqual("(objectClass=*)", source.search_filter)


if __name__ == "__main__":
    unittest.main()
