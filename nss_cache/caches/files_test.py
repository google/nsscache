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
"""Unit tests for nss_cache/caches/files.py."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import os
import shutil
import tempfile
import unittest
import sys
from mox3 import mox

from nss_cache import config
from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import netgroup
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.caches import files


class TestFilesCache(mox.MoxTestBase):

    def setUp(self):
        super(TestFilesCache, self).setUp()
        self.workdir = tempfile.mkdtemp()
        self.config = {'dir': self.workdir}

    def tearDown(self):
        super(TestFilesCache, self).tearDown()
        shutil.rmtree(self.workdir)

    def testInstantiation(self):
        cache = files.FilesCache(self.config, config.MAP_PASSWORD)
        self.assertNotEqual(None, cache)

    def testWrite(self):
        cache = files.FilesPasswdMapHandler(self.config)
        entry = passwd.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
        pmap = passwd.PasswdMap([entry])
        written = cache.Write(pmap)
        self.assertTrue('foo' in written)
        self.assertFalse(entry in pmap)  # we emptied pmap to avoid mem leaks
        self.assertFalse(cache.temp_cache_file.closed)

    def testCacheFilenameSuffixOption(self):
        new_config = {'cache_filename_suffix': 'blarg'}
        new_config.update(self.config)
        cache = files.FilesCache(new_config, config.MAP_PASSWORD)

        cache.CACHE_FILENAME = 'test'
        self.assertEqual(os.path.join(self.workdir, 'test.blarg'),
                         cache.GetCacheFilename())

        cache.temp_cache_file = open(os.path.join(self.workdir, 'pre-commit'),
                                     'w')
        cache.temp_cache_file.write('\n')
        cache.temp_cache_filename = os.path.join(self.workdir, 'pre-commit')
        cache._Commit()
        expected_cache_filename = os.path.join(self.workdir, 'test.blarg')
        self.assertTrue(os.path.exists(expected_cache_filename))

    def testWritePasswdEntry(self):
        """We correctly write a typical entry in /etc/passwd format."""
        cache = files.FilesPasswdMapHandler(self.config)
        file_mock = self.mox.CreateMock(sys.stdout)
        file_mock.write(b'root:x:0:0:Rootsy:/root:/bin/bash\n')

        map_entry = passwd.PasswdMapEntry()
        map_entry.name = 'root'
        map_entry.passwd = 'x'
        map_entry.uid = 0
        map_entry.gid = 0
        map_entry.gecos = 'Rootsy'
        map_entry.dir = '/root'
        map_entry.shell = '/bin/bash'

        self.mox.ReplayAll()

        cache._WriteData(file_mock, map_entry)

    def testWriteGroupEntry(self):
        """We correctly write a typical entry in /etc/group format."""
        cache = files.FilesGroupMapHandler(self.config)
        file_mock = self.mox.CreateMock(sys.stdout)
        file_mock.write(b'root:x:0:zero_cool,acid_burn\n')

        map_entry = group.GroupMapEntry()
        map_entry.name = 'root'
        map_entry.passwd = 'x'
        map_entry.gid = 0
        map_entry.members = ['zero_cool', 'acid_burn']

        self.mox.ReplayAll()

        cache._WriteData(file_mock, map_entry)

    def testWriteShadowEntry(self):
        """We correctly write a typical entry in /etc/shadow format."""
        cache = files.FilesShadowMapHandler(self.config)
        file_mock = self.mox.CreateMock(sys.stdout)
        file_mock.write(b'root:$1$zomgmd5support:::::::\n')

        map_entry = shadow.ShadowMapEntry()
        map_entry.name = 'root'
        map_entry.passwd = '$1$zomgmd5support'

        self.mox.ReplayAll()

        cache._WriteData(file_mock, map_entry)

    def testWriteNetgroupEntry(self):
        """We correctly write a typical entry in /etc/netgroup format."""
        cache = files.FilesNetgroupMapHandler(self.config)
        file_mock = self.mox.CreateMock(sys.stdout)
        file_mock.write(
            b'administrators unix_admins noc_monkeys (-,zero_cool,)\n')

        map_entry = netgroup.NetgroupMapEntry()
        map_entry.name = 'administrators'
        map_entry.entries = 'unix_admins noc_monkeys (-,zero_cool,)'

        self.mox.ReplayAll()

        cache._WriteData(file_mock, map_entry)

    def testWriteAutomountEntry(self):
        """We correctly write a typical entry in /etc/auto.* format."""
        cache = files.FilesAutomountMapHandler(self.config)
        file_mock = self.mox.CreateMock(sys.stdout)
        file_mock.write(b'scratch -tcp,rw,intr,bg fileserver:/scratch\n')

        map_entry = automount.AutomountMapEntry()
        map_entry.key = 'scratch'
        map_entry.options = '-tcp,rw,intr,bg'
        map_entry.location = 'fileserver:/scratch'

        self.mox.ReplayAll()
        cache._WriteData(file_mock, map_entry)
        self.mox.VerifyAll()

        file_mock = self.mox.CreateMock(sys.stdout)
        file_mock.write('scratch fileserver:/scratch\n')

        map_entry = automount.AutomountMapEntry()
        map_entry.key = 'scratch'
        map_entry.options = None
        map_entry.location = 'fileserver:/scratch'

        self.mox.ReplayAll()

        cache._WriteData(file_mock, map_entry)

    def testAutomountSetsFilename(self):
        """We set the correct filename based on mountpoint information."""
        # also tests GetMapLocation() because it uses it :)
        conf = {'dir': self.workdir, 'cache_filename_suffix': ''}
        cache = files.FilesAutomountMapHandler(conf)
        self.assertEqual(cache.GetMapLocation(),
                         '%s/auto.master' % self.workdir)

        cache = files.FilesAutomountMapHandler(conf,
                                               automount_mountpoint='/home')
        self.assertEqual(cache.GetMapLocation(), '%s/auto.home' % self.workdir)

        cache = files.FilesAutomountMapHandler(conf,
                                               automount_mountpoint='/usr/meh')
        self.assertEqual(cache.GetMapLocation(),
                         '%s/auto.usr_meh' % self.workdir)

    def testCacheFileDoesNotExist(self):
        """Make sure we just get an empty map rather than exception."""
        conf = {'dir': self.workdir, 'cache_filename_suffix': ''}
        cache = files.FilesAutomountMapHandler(conf)
        self.assertFalse(
            os.path.exists(os.path.join(self.workdir, 'auto.master')))
        data = cache.GetMap()
        self.assertFalse(data)

    def testIndexCreation(self):
        cache = files.FilesPasswdMapHandler(self.config)
        entries = [
            passwd.PasswdMapEntry(dict(name='foo', uid=10, gid=10)),
            passwd.PasswdMapEntry(dict(name='bar', uid=11, gid=11)),
            passwd.PasswdMapEntry(dict(name='quux', uid=12, gid=11)),
        ]
        pmap = passwd.PasswdMap(entries)
        cache.Write(pmap)
        cache.WriteIndex()

        index_filename = cache.GetCacheFilename() + '.ixname'
        self.assertTrue(os.path.exists(index_filename),
                        'Index not created %s' % index_filename)
        with open(index_filename) as f:
            self.assertEqual('bar\x0015\x00\x00\n', f.readline())
            self.assertEqual('foo\x000\x00\x00\x00\n', f.readline())
            self.assertEqual('quux\x0030\x00\n', f.readline())

        index_filename = cache.GetCacheFilename() + '.ixuid'
        self.assertTrue(os.path.exists(index_filename),
                        'Index not created %s' % index_filename)
        with open(index_filename) as f:
            self.assertEqual('10\x000\x00\x00\n', f.readline())
            self.assertEqual('11\x0015\x00\n', f.readline())
            self.assertEqual('12\x0030\x00\n', f.readline())

    def testWriteCacheAndIndex(self):
        cache = files.FilesPasswdMapHandler(self.config)
        entries = [
            passwd.PasswdMapEntry(dict(name='foo', uid=10, gid=10)),
            passwd.PasswdMapEntry(dict(name='bar', uid=11, gid=11)),
        ]
        pmap = passwd.PasswdMap(entries)
        written = cache.Write(pmap)
        cache.WriteIndex()

        self.assertTrue('foo' in written)
        self.assertTrue('bar' in written)
        index_filename = cache.GetCacheFilename() + '.ixname'
        self.assertTrue(os.path.exists(index_filename),
                        'Index not created %s' % index_filename)
        index_filename = cache.GetCacheFilename() + '.ixuid'
        self.assertTrue(os.path.exists(index_filename),
                        'Index not created %s' % index_filename)

        entries = [
            passwd.PasswdMapEntry(dict(name='foo', uid=10, gid=10)),
            passwd.PasswdMapEntry(dict(name='bar', uid=11, gid=11)),
            passwd.PasswdMapEntry(dict(name='quux', uid=12, gid=11)),
        ]
        pmap = passwd.PasswdMap(entries)
        written = cache.Write(pmap)
        self.assertTrue('foo' in written)
        self.assertTrue('bar' in written)
        self.assertTrue('quux' in written)

        index_filename = cache.GetCacheFilename() + '.ixname'
        with open(index_filename) as f:
            self.assertEqual('bar\x0015\x00\n', f.readline())
            self.assertEqual('foo\x000\x00\x00\n', f.readline())

        index_filename = cache.GetCacheFilename() + '.ixuid'
        with open(index_filename) as f:
            self.assertEqual('10\x000\x00\x00\n', f.readline())
            self.assertEqual('11\x0015\x00\n', f.readline())

        cache.WriteIndex()
        index_filename = cache.GetCacheFilename() + '.ixname'
        with open(index_filename) as f:
            self.assertEqual('bar\x0015\x00\x00\n', f.readline())
            self.assertEqual('foo\x000\x00\x00\x00\n', f.readline())
            self.assertEqual('quux\x0030\x00\n', f.readline())

        index_filename = cache.GetCacheFilename() + '.ixuid'
        with open(index_filename) as f:
            self.assertEqual('10\x000\x00\x00\n', f.readline())
            self.assertEqual('11\x0015\x00\n', f.readline())
            self.assertEqual('12\x0030\x00\n', f.readline())


if __name__ == '__main__':
    unittest.main()
