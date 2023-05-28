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
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
"""Unit tests for nss_cache/util/file_formats.py."""

__author__ = (
    "jaq@google.com (Jamie Wilkinson)",
    "vasilios@google.com (Vasilios Hoffman)",
)

import unittest

from nss_cache.util import file_formats


class TestFilesUtils(unittest.TestCase):
    def testReadPasswdEntry(self):
        """We correctly parse a typical entry in /etc/passwd format."""
        parser = file_formats.FilesPasswdMapParser()
        file_entry = "root:x:0:0:Rootsy:/root:/bin/bash"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.name, "root")
        self.assertEqual(map_entry.passwd, "x")
        self.assertEqual(map_entry.uid, 0)
        self.assertEqual(map_entry.gid, 0)
        self.assertEqual(map_entry.gecos, "Rootsy")
        self.assertEqual(map_entry.dir, "/root")
        self.assertEqual(map_entry.shell, "/bin/bash")

    def testReadGroupEntry(self):
        """We correctly parse a typical entry in /etc/group format."""
        parser = file_formats.FilesGroupMapParser()
        file_entry = "root:x:0:zero_cool,acid_burn"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.name, "root")
        self.assertEqual(map_entry.passwd, "x")
        self.assertEqual(map_entry.gid, 0)
        self.assertEqual(map_entry.members, ["zero_cool", "acid_burn"])

    def testReadShadowEntry(self):
        """We correctly parse a typical entry in /etc/shadow format."""
        parser = file_formats.FilesShadowMapParser()
        file_entry = "root:$1$zomgmd5support:::::::"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.name, "root")
        self.assertEqual(map_entry.passwd, "$1$zomgmd5support")
        self.assertEqual(map_entry.lstchg, None)
        self.assertEqual(map_entry.min, None)
        self.assertEqual(map_entry.max, None)
        self.assertEqual(map_entry.warn, None)
        self.assertEqual(map_entry.inact, None)
        self.assertEqual(map_entry.expire, None)
        self.assertEqual(map_entry.flag, None)

    def testReadNetgroupEntry(self):
        """We correctly parse a typical entry in /etc/netgroup format."""
        parser = file_formats.FilesNetgroupMapParser()
        file_entry = "administrators unix_admins noc_monkeys (-,zero_cool,)"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.name, "administrators")
        self.assertEqual(map_entry.entries, "unix_admins noc_monkeys (-,zero_cool,)")

    def testReadEmptyNetgroupEntry(self):
        """We correctly parse a memberless netgroup entry."""
        parser = file_formats.FilesNetgroupMapParser()
        file_entry = "administrators"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.name, "administrators")
        self.assertEqual(map_entry.entries, "")

    def testReadAutomountEntry(self):
        """We correctly parse a typical entry in /etc/auto.* format."""
        parser = file_formats.FilesAutomountMapParser()
        file_entry = "scratch -tcp,rw,intr,bg fileserver:/scratch"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.key, "scratch")
        self.assertEqual(map_entry.options, "-tcp,rw,intr,bg")
        self.assertEqual(map_entry.location, "fileserver:/scratch")

    def testReadAutmountEntryWithExtraWhitespace(self):
        """Extra whitespace doesn't break the parsing."""
        parser = file_formats.FilesAutomountMapParser()
        file_entry = "scratch  fileserver:/scratch"
        map_entry = parser._ReadEntry(file_entry)

        self.assertEqual(map_entry.key, "scratch")
        self.assertEqual(map_entry.options, None)
        self.assertEqual(map_entry.location, "fileserver:/scratch")

    def testReadBadAutomountEntry(self):
        """Cope with empty data."""
        parser = file_formats.FilesAutomountMapParser()
        file_entry = ""
        map_entry = parser._ReadEntry(file_entry)
        self.assertEqual(None, map_entry)


if __name__ == "__main__":
    unittest.main()
