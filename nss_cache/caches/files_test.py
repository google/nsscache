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

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import os
import tempfile
import pmock
import unittest

from nss_cache import config
from nss_cache import maps
from nss_cache.caches import files


class TestFilesCache(pmock.MockTestCase):

  def setUp(self):
    self.workdir = tempfile.mkdtemp()
    self.config = {'dir': self.workdir}

  def tearDown(self):
    os.rmdir(self.workdir)

  def testInstantiation(self):
    cache = files.FilesCache(self.config, config.MAP_PASSWORD)
    self.failIfEqual(None, cache)

  def testWrite(self):
    cache = files.FilesPasswdMapHandler(self.config)
    entry = maps.PasswdMapEntry({'name': 'foo', 'uid': 10, 'gid': 10})
    pmap = maps.PasswdMap([entry])
    written = cache.Write(pmap)
    self.assertTrue('foo' in written)
    self.assertFalse(entry in pmap)  # we emptied pmap to avoid mem leaks
    os.unlink(cache.cache_filename)

  def testCacheFilenameSuffixOption(self):
    new_config = {'cache_filename_suffix': 'blarg'}
    new_config.update(self.config)
    cache = files.FilesCache(new_config, config.MAP_PASSWORD)

    cache.CACHE_FILENAME = 'test'
    self.assertEqual(os.path.join(self.workdir, 'test.blarg'),
                     cache._GetCacheFilename())

    cache.cache_file = open(os.path.join(self.workdir, 'pre-commit'), 'w')
    cache.cache_file.write('\n')
    cache.cache_filename = os.path.join(self.workdir,
                                        'pre-commit')
    cache._Commit()
    expected_cache_filename = os.path.join(self.workdir,
                                           'test.blarg')
    self.failUnless(os.path.exists(expected_cache_filename))
    os.unlink(expected_cache_filename)

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
    invocation = file_mock.expects(pmock.once())
    invocation.write(pmock.eq('root:x:0:0:Rootsy:/root:/bin/bash\n'))
    
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
    invocation = file_mock.expects(pmock.once())
    invocation.write(pmock.eq('root:x:0:zero_cool,acid_burn\n'))
    
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
    invocation = file_mock.expects(pmock.once())
    invocation.write(pmock.eq('root:$1$zomgmd5support:::::::\n'))
    
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
    self.assertEqual(map_entry.entries,
                     'unix_admins noc_monkeys (-,zero_cool,)')

  def testReadEmptyNetgroupEntry(self):
    """We correctly parse a memberless netgroup entry."""
    cache = files.FilesNetgroupMapHandler(self.config)
    file_entry = 'administrators'
    map_entry = cache._ReadEntry(file_entry)

    self.assertEqual(map_entry.name, 'administrators')
    self.assertEqual(map_entry.entries, '')
    
  def testWriteNetgroupEntry(self):
    """We correctly write a typical entry in /etc/netgroup format."""
    cache = files.FilesNetgroupMapHandler(self.config)
    file_mock = self.mock()
    invocation = file_mock.expects(pmock.once())
    invocation.write(
        pmock.eq('administrators unix_admins noc_monkeys (-,zero_cool,)\n'))
    
    map_entry = maps.NetgroupMapEntry()
    map_entry.name = 'administrators'
    map_entry.entries = 'unix_admins noc_monkeys (-,zero_cool,)'
    cache._WriteData(file_mock, map_entry)

  def testReadAutomountEntry(self):
    """We correctly parse a typical entry in /etc/auto.* format."""
    cache = files.FilesAutomountMapHandler(self.config)
    file_entry = 'scratch -tcp,rw,intr,bg fileserver:/scratch'
    map_entry = cache._ReadEntry(file_entry)

    self.assertEqual(map_entry.key, 'scratch')
    self.assertEqual(map_entry.options, '-tcp,rw,intr,bg')
    self.assertEqual(map_entry.location, 'fileserver:/scratch')

  def testReadAutmountEntryWithExtraWhitespace(self):
    """Extra whitespace doesn't break the parsing."""
    cache = files.FilesAutomountMapHandler(self.config)
    file_entry = 'scratch  fileserver:/scratch'
    map_entry = cache._ReadEntry(file_entry)

    self.assertEqual(map_entry.key, 'scratch')
    self.assertEqual(map_entry.options, None)
    self.assertEqual(map_entry.location, 'fileserver:/scratch')

  def testWriteAutomountEntry(self):
    """We correctly write a typical entry in /etc/auto.* format."""
    cache = files.FilesAutomountMapHandler(self.config)
    file_mock = self.mock()
    invocation = file_mock.expects(pmock.once())
    invocation.write(pmock.eq('scratch -tcp,rw,intr,bg fileserver:/scratch\n'))
    
    map_entry = maps.AutomountMapEntry()
    map_entry.key = 'scratch'
    map_entry.options = '-tcp,rw,intr,bg'
    map_entry.location = 'fileserver:/scratch'
    cache._WriteData(file_mock, map_entry)

    file_mock = self.mock()
    invocation = file_mock.expects(pmock.once())
    invocation.write(pmock.eq('scratch fileserver:/scratch\n'))
    
    map_entry = maps.AutomountMapEntry()
    map_entry.key = 'scratch'
    map_entry.options = None
    map_entry.location = 'fileserver:/scratch'
    cache._WriteData(file_mock, map_entry)

  def testAutomountSetsFilename(self):
    """We set the correct filename based on mountpoint information."""
    # also tests GetMapLocation() because it uses it :)
    conf = {'dir': self.workdir, 'cache_filename_suffix': ''}
    cache = files.FilesAutomountMapHandler(conf)
    self.assertEquals(cache.GetMapLocation(), '%s/auto.master' % self.workdir)

    cache = files.FilesAutomountMapHandler(conf, automount_info='/home')
    self.assertEquals(cache.GetMapLocation(), '%s/auto.home' % self.workdir)

    cache = files.FilesAutomountMapHandler(conf, automount_info='/usr/meh')
    self.assertEquals(cache.GetMapLocation(), '%s/auto.usr_meh' % self.workdir)

if __name__ == '__main__':
  unittest.main()
