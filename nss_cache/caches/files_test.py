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
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

"""Unit tests for nss_cache/caches/files.py."""

__author__ =  ('jaq@google.com (Jamie Wilkinson)',
               'vasilios@google.com (Vasilios Hoffman)')

import os
import pmock
import tempfile
import unittest

from nss_cache.caches import files
from nss_cache import maps


class TestFilesCache(pmock.MockTestCase):

  def setUp(self):
    self.workdir = tempfile.mkdtemp()
    self.config = {'dir': self.workdir}

  def tearDown(self):
    os.rmdir(self.workdir)

  def testInstantiation(self):
    cache = files.FilesCache(self.config)
    self.failIfEqual(None, cache)

  def testWrite(self):
    cache = files.FilesCache(self.config)
    self.assertEqual(True, cache.Write([]))
    os.unlink(cache.cache_filename)

  def testCacheFilenameSuffixOption(self):
    new_config = {'cache_filename_suffix': 'blarg'}
    new_config.update(self.config)
    cache = files.FilesCache(new_config)

    cache.CACHE_FILENAME = 'test'
    self.assertEqual(os.path.join(self.workdir, 'test.blarg'),
                     cache._GetCacheFilename())

    cache.cache_file = open(os.path.join(self.workdir, 'pre-commit'), 'w')
    cache.cache_file.write('\n')
    cache.cache_filename = os.path.join(self.workdir,
                                        'pre-commit')
    cache._Commit(0)
    expected_cache_filename = os.path.join(self.workdir,
                                           'test.blarg')
    self.failUnless(os.path.exists(expected_cache_filename))
    os.unlink(expected_cache_filename)
    os.unlink(os.path.join(self.workdir,
                           'test.nsscache-files-modify-timestamp'))

  def testReadPasswdEntry(self):
    """We correctly parse a typical entry in /etc/passwd format."""
    cache = files.FilesPasswdMapHandler(self.config)
    file_entry = 'root:x:0:0:Rootsy:/root:/bin/bash'
    map_entry = cache._ReadEntry(file_entry)
    
    self.assertEqual(map_entry.name, 'root')
    self.assertEqual(map_entry.passwd, 'x')
    self.assertEqual(map_entry.uid, 0)
    self.assertEqual(map_entry.gid, 0)
    self.assertEqual(map_entry.gecos, 'Rootsy')
    self.assertEqual(map_entry.dir, '/root')
    self.assertEqual(map_entry.shell, '/bin/bash')

  def testWritePasswdEntry(self):
    """We correctly write a typical entry in /etc/passwd format."""
    cache = files.FilesPasswdMapHandler(self.config)
    file_mock = self.mock()
    file_mock\
               .expects(pmock.once())\
               .write(pmock.eq('root:x:0:0:Rootsy:/root:/bin/bash\n'))
    map_entry = maps.PasswdMapEntry()
    map_entry.name = 'root'
    map_entry.passwd = 'x'
    map_entry.uid = 0
    map_entry.gid = 0
    map_entry.gecos = 'Rootsy'
    map_entry.dir = '/root'
    map_entry.shell = '/bin/bash'
    cache._WriteData(file_mock, map_entry)

  def testReadGroupEntry(self):
    """We correctly parse a typical entry in /etc/group format."""
    cache = files.FilesGroupMapHandler(self.config)
    file_entry = 'root:x:0:zero_cool,acid_burn'
    map_entry = cache._ReadEntry(file_entry)
    
    self.assertEqual(map_entry.name, 'root')
    self.assertEqual(map_entry.passwd, 'x')
    self.assertEqual(map_entry.gid, 0)
    self.assertEqual(map_entry.members, ['zero_cool', 'acid_burn'])

  def testWriteGroupEntry(self):
    """We correctly write a typical entry in /etc/group format."""
    cache = files.FilesGroupMapHandler(self.config)
    file_mock = self.mock()
    file_mock\
               .expects(pmock.once())\
               .write(pmock.eq('root:x:0:zero_cool,acid_burn\n'))
    map_entry = maps.GroupMapEntry()
    map_entry.name = 'root'
    map_entry.passwd = 'x'
    map_entry.gid = 0
    map_entry.members = ['zero_cool', 'acid_burn']
    cache._WriteData(file_mock, map_entry)

  def testReadShadowEntry(self):
    """We correctly parse a typical entry in /etc/shadow format."""
    cache = files.FilesShadowMapHandler(self.config)
    file_entry = 'root:$1$zomgmd5support:::::::'
    map_entry = cache._ReadEntry(file_entry)
    
    self.assertEqual(map_entry.name, 'root')
    self.assertEqual(map_entry.passwd, '$1$zomgmd5support')
    self.assertEqual(map_entry.lstchg, None)
    self.assertEqual(map_entry.min, None)
    self.assertEqual(map_entry.max, None)
    self.assertEqual(map_entry.warn, None)
    self.assertEqual(map_entry.inact, None)
    self.assertEqual(map_entry.expire, None)
    self.assertEqual(map_entry.flag, None)

  def testWriteShadowEntry(self):
    """We correctly write a typical entry in /etc/shadow format."""
    cache = files.FilesShadowMapHandler(self.config)
    file_mock = self.mock()
    file_mock\
               .expects(pmock.once())\
               .write(pmock.eq('root:$1$zomgmd5support:::::::\n'))
    map_entry = maps.ShadowMapEntry()
    map_entry.name = 'root'
    map_entry.passwd = '$1$zomgmd5support'
    cache._WriteData(file_mock, map_entry)

  def testReadNetgroupEntry(self):
    """We correctly parse a typical entry in /etc/netgroup format."""
    cache = files.FilesNetgroupMapHandler(self.config)
    file_entry = 'administrators unix_admins noc_monkeys (-,zero_cool,)'
    map_entry = cache._ReadEntry(file_entry)

    self.assertEqual(map_entry.name, 'administrators')
    self.assertEqual(map_entry.entries, ['unix_admins', 'noc_monkeys',
                                         '(-,zero_cool,)'])
    
  def testWriteNetgroupEntry(self):
    """We correctly write a typical entry in /etc/netgroup format."""
    cache = files.FilesNetgroupMapHandler(self.config)
    file_mock = self.mock()
    file_mock\
               .expects(pmock.once())\
               .write(pmock.eq(
                   'administrators unix_admins noc_monkeys (-,zero_cool,)\n'))
    map_entry = maps.NetgroupMapEntry()
    map_entry.name = 'administrators'
    map_entry.entries.append('unix_admins')
    map_entry.entries.append('noc_monkeys')
    map_entry.entries.append('(-,zero_cool,)')
    cache._WriteData(file_mock, map_entry)


if __name__ == '__main__':
  unittest.main()
