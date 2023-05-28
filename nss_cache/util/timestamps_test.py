# Copyright 2011 Google Inc.
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
"""Unit tests for nss_cache/util/timestamps.py."""

__author__ = "jaq@google.com (Jamie Wilkinson)"

import datetime
from datetime import timezone
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

from nss_cache.util import timestamps


class TestTimestamps(unittest.TestCase):
    def setUp(self):
        super(TestTimestamps, self).setUp()
        self.workdir = tempfile.mkdtemp()

    def tearDown(self):
        super(TestTimestamps, self).tearDown()
        shutil.rmtree(self.workdir)

    def testReadTimestamp(self):
        ts_filename = os.path.join(self.workdir, "tsr")
        ts_file = open(ts_filename, "w")
        ts_file.write("1970-01-01T00:00:01Z\n")
        ts_file.close()

        ts = timestamps.ReadTimestamp(ts_filename)
        self.assertEqual(time.gmtime(1), ts)

    def testReadTimestamp(self):
        # TZ=UTC date -d @1306428781
        # Thu May 26 16:53:01 UTC 2011
        ts_filename = os.path.join(self.workdir, "tsr")
        ts_file = open(ts_filename, "w")
        ts_file.write("2011-05-26T16:53:01Z\n")
        ts_file.close()

        ts = timestamps.ReadTimestamp(ts_filename)
        self.assertEqual(time.gmtime(1306428781), ts)

    def testReadTimestampInFuture(self):
        ts_filename = os.path.join(self.workdir, "tsr")
        ts_file = open(ts_filename, "w")
        ts_file.write("2011-05-26T16:02:00Z")
        ts_file.close()

        now = time.gmtime(1)
        with mock.patch("time.gmtime") as gmtime:
            gmtime.return_value = now
            ts = timestamps.ReadTimestamp(ts_filename)
            self.assertEqual(now, ts)

    def testWriteTimestamp(self):
        ts_filename = os.path.join(self.workdir, "tsw")

        good_ts = time.gmtime(1)
        timestamps.WriteTimestamp(good_ts, ts_filename)

        self.assertEqual(good_ts, timestamps.ReadTimestamp(ts_filename))

        ts_file = open(ts_filename, "r")
        self.assertEqual("1970-01-01T00:00:01Z\n", ts_file.read())
        ts_file.close()

    def testTimestampToDateTime(self):
        now = datetime.datetime.now(timezone.utc)
        self.assertEqual(
            timestamps.FromTimestampToDateTime(now.timestamp()),
            now.replace(tzinfo=None),
        )

    def testDateTimeToTimestamp(self):
        now = datetime.datetime.now(timezone.utc)
        self.assertEqual(
            now.replace(microsecond=0).timestamp(),
            timestamps.FromDateTimeToTimestamp(now),
        )


if __name__ == "__main__":
    unittest.main()
