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

"""Unit tests for nss_cache/caches/nssdb.py."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import logging
import os.path
import select
import shutil
import sys
import tempfile
import time
import unittest

try:
  import bsddb3
except ImportError:
  raise unittest.SkipTest('bsddb3 import failed')
  
try:
  from mox3 import mox
except ImportError:
  import mox

from nss_cache import error

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow

try:
  from nss_cache.caches import nssdb
except ImportError:
  raise unittest.SkipTest('nssdb import failed')
  

def NoMakeDB():
  return not os.path.exists('/usr/bin/makedb')


class MakeDbDummy(object):
  allout = ""
      
  def wait(self):
    return 0

  def poll(self):
    return None


class TestNssDbPasswdHandler(mox.MoxTestBase):

  def setUp(self):
    super(TestNssDbPasswdHandler, self).setUp()
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    super(TestNssDbPasswdHandler, self).tearDown()
    # remove the test working directory
    shutil.rmtree(self.workdir)

  def testConvertValueToMapEntry(self):
    ent = 'foo:x:1000:1001:bar:/:/bin/sh'

    updater = nssdb.NssDbPasswdHandler({})

    pme = updater.ConvertValueToMapEntry(ent)

    self.assertEqual('foo', pme.name)
    self.assertEqual(1000, pme.uid)
    self.assertEqual(1001, pme.gid)
    self.assertEqual('bar', pme.gecos)
    self.assertEqual('/bin/sh', pme.shell)
    self.assertEqual('/', pme.dir)

  def testIsMapPrimaryKey(self):
    updater = nssdb.NssDbPasswdHandler({})

    self.assertTrue(updater.IsMapPrimaryKey('.foo'))
    self.assertFalse(updater.IsMapPrimaryKey('=1000'))
    self.assertFalse(updater.IsMapPrimaryKey('00'))

  def testNssDbPasswdHandlerWriteData(self):
    entry_string = 'foo:x:1000:1000:foo:/:/bin/sh'

    makedb_stdin = self.mox.CreateMock(sys.stdin)
    makedb_stdin.write('.foo %s\n' % entry_string)
    makedb_stdin.write('=1000 %s\n' % entry_string)
    makedb_stdin.write('00 %s\n' % entry_string)

    passwd_map = passwd.PasswdMap()
    passwd_map_entry = passwd.PasswdMapEntry()
    passwd_map_entry.name = 'foo'
    passwd_map_entry.uid = 1000
    passwd_map_entry.gid = 1000
    passwd_map_entry.gecos = 'foo'
    passwd_map_entry.dir = '/'
    passwd_map_entry.shell = '/bin/sh'
    passwd_map_entry.passwd = 'x'
    self.assertTrue(passwd_map.Add(passwd_map_entry))

    writer = nssdb.NssDbPasswdHandler({'makedb': '/bin/false',
                                       'dir': '/tmp'})

    self.mox.ReplayAll()

    writer.WriteData(makedb_stdin, passwd_map_entry, 0)

  def testNssDbPasswdHandlerWrite(self):
    ent = 'foo:x:1000:1000:foo:/:/bin/sh'

    makedb_stdin = self.mox.CreateMock(sys.stdin)
    makedb_stdin.write('.foo %s\n' % ent)
    makedb_stdin.write('=1000 %s\n' % ent)
    makedb_stdin.write('00 %s\n' % ent)
    makedb_stdin.close()

    makedb_stdout = self.mox.CreateMock(sys.stdout)
    makedb_stdout.read().AndReturn('')
    makedb_stdout.close()

    m = passwd.PasswdMap()
    pw = passwd.PasswdMapEntry()
    pw.name = 'foo'
    pw.uid = 1000
    pw.gid = 1000
    pw.gecos = 'foo'
    pw.dir = '/'
    pw.shell = '/bin/sh'
    pw.passwd = 'x'
    pw.Verify()
    self.assertTrue(m.Add(pw))

    self.mox.StubOutWithMock(select, 'select')
    select.select([makedb_stdout], (), (), 0).AndReturn(([37], [], []))
    select.select([makedb_stdout], (), (), 0).AndReturn(([], [], []))

    def SpawnMakeDb():
      makedb = MakeDbDummy()
      makedb.stdin = makedb_stdin
      makedb.stdout = makedb_stdout
      return makedb

    writer = nssdb.NssDbPasswdHandler({'makedb': '/usr/bin/makedb',
                                       'dir': self.workdir})

    writer._SpawnMakeDb = SpawnMakeDb

    self.mox.ReplayAll()

    writer.Write(m)

    tmppasswd = os.path.join(self.workdir, 'passwd.db')
    self.assertFalse(os.path.exists(tmppasswd))
    # just clean it up, Write() doesn't Commit()
    writer._Rollback()

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testVerify(self):
    # create a map
    m = passwd.PasswdMap()
    e = passwd.PasswdMapEntry()
    e.name = 'foo'
    e.uid = 1000
    e.gid = 2000
    self.assertTrue(m.Add(e))

    updater = nssdb.NssDbPasswdHandler({'dir': self.workdir,
                                        'makedb': '/usr/bin/makedb'})
    written = updater.Write(m)

    self.assertTrue(os.path.exists(updater.temp_cache_filename),
                    'updater.Write() did not create a file')

    retval = updater.Verify(written)

    self.assertEqual(True, retval)

    os.unlink(updater.temp_cache_filename)

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testVerifyFailure(self):
    # Hide the warning that we expect to get

    class TestFilter(logging.Filter):

      def filter(self, record):
        return not record.msg.startswith('verify failed: %d keys missing')

    fltr = TestFilter()
    logging.getLogger('NssDbPasswdHandler').addFilter(fltr)
    # create a map
    m = passwd.PasswdMap()
    e = passwd.PasswdMapEntry()
    e.name = 'foo'
    e.uid = 1000
    e.gid = 2000
    self.assertTrue(m.Add(e))

    updater = nssdb.NssDbPasswdHandler({'dir': self.workdir,
                                        'makedb': '/usr/bin/makedb'})
    written = updater.Write(m)

    self.assertTrue(os.path.exists(updater.temp_cache_filename),
                    'updater.Write() did not create a file')

    # change the cache
    db = bsddb.btopen(updater.temp_cache_filename)
    del db[db.first()[0]]
    db.sync()
    db.close()

    retval = updater.Verify(written)

    self.assertEqual(False, retval)
    self.assertFalse(os.path.exists(os.path.join(updater.temp_cache_filename)))
    # no longer hide this message
    logging.getLogger('NssDbPasswdHandler').removeFilter(fltr)

  def testVerifyEmptyMap(self):
    updater = nssdb.NssDbPasswdHandler({'dir': self.workdir})
    # create a temp file, clag it into the updater object
    (_, temp_filename) = tempfile.mkstemp(prefix='nsscache-nssdb_test',
                                          dir=self.workdir)
    updater.temp_cache_filename = temp_filename
    # make it empty
    db = bsddb.btopen(temp_filename, 'w')
    self.assertEqual(0, len(db))
    db.close()
    # TODO(jaq): raising an exception is probably the wrong behaviour
    self.assertRaises(error.EmptyMap, updater.Verify, set('foo'))
    os.unlink(temp_filename)


class TestNssDbGroupHandler(mox.MoxTestBase):

  def setUp(self):
    super(TestNssDbGroupHandler, self).setUp()
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    super(TestNssDbGroupHandler, self).tearDown()
    # remove the test working directory
    shutil.rmtree(self.workdir)

  def testConvertValueToMapEntry(self):
    ent = 'foo:x:1000:bar'
    updater = nssdb.NssDbGroupHandler({})

    gme = updater.ConvertValueToMapEntry(ent)

    self.assertEqual('foo', gme.name)
    self.assertEqual(1000, gme.gid)
    self.assertEqual('x', gme.passwd)
    self.assertEqual(['bar'], gme.members)

  def testIsMapPrimaryKey(self):
    updater = nssdb.NssDbGroupHandler({})

    self.assertTrue(updater.IsMapPrimaryKey('.foo'))
    self.assertFalse(updater.IsMapPrimaryKey('=1000'))
    self.assertFalse(updater.IsMapPrimaryKey('00'))

  def testNssDbGroupHandlerWriteData(self):
    ent = 'foo:x:1000:bar'

    makedb_stdin = self.mox.CreateMock(sys.stdin)
    makedb_stdin.write('.foo %s\n' % ent)
    makedb_stdin.write('=1000 %s\n' % ent)
    makedb_stdin.write('00 %s\n' % ent)

    m = group.GroupMap()
    g = group.GroupMapEntry()
    g.name = 'foo'
    g.gid = 1000
    g.passwd = 'x'
    g.members = ['bar']

    self.assertTrue(m.Add(g))

    writer = nssdb.NssDbGroupHandler({'makedb': '/bin/false',
                                      'dir': '/tmp'})

    self.mox.ReplayAll()

    writer.WriteData(makedb_stdin, g, 0)

  def testNssDbGroupHandlerWrite(self):
    ent = 'foo:x:1000:bar'

    makedb_stdin = self.mox.CreateMock(sys.stdin)
    makedb_stdin.write('.foo %s\n' % ent)
    makedb_stdin.write('=1000 %s\n' % ent)
    makedb_stdin.write('00 %s\n' % ent)
    makedb_stdin.close()

    makedb_stdout = self.mox.CreateMock(sys.stdout)
    makedb_stdout.read().AndReturn('')
    makedb_stdout.close()

    m = group.GroupMap()
    g = group.GroupMapEntry()
    g.name = 'foo'
    g.gid = 1000
    g.passwd = 'x'
    g.members = ['bar']
    g.Verify()
    self.assertTrue(m.Add(g))

    self.mox.StubOutWithMock(select, 'select')
    select.select([makedb_stdout], (), (), 0).AndReturn(([37], [], []))
    select.select([makedb_stdout], (), (), 0).AndReturn(([], [], []))
    
    def SpawnMakeDb():
      makedb = MakeDbDummy()
      makedb.stdin = makedb_stdin
      makedb.stdout = makedb_stdout
      return makedb

    writer = nssdb.NssDbGroupHandler({'makedb': '/usr/bin/makedb',
                                      'dir': self.workdir})
    writer._SpawnMakeDb = SpawnMakeDb
    self.mox.ReplayAll()

    writer.Write(m)

    tmpgroup = os.path.join(self.workdir, 'group.db')
    self.assertFalse(os.path.exists(tmpgroup))
    # just clean it up, Write() doesn't Commit()
    writer._Rollback()

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testVerify(self):
    # create a map
    m = group.GroupMap()
    e = group.GroupMapEntry()
    e.name = 'foo'
    e.gid = 2000
    self.assertTrue(m.Add(e))

    updater = nssdb.NssDbGroupHandler({'dir': self.workdir,
                                       'makedb': '/usr/bin/makedb'})
    written = updater.Write(m)

    self.assertTrue(os.path.exists(updater.temp_cache_filename),
                    'updater.Write() did not create a file')

    retval = updater.Verify(written)

    self.assertEqual(True, retval)
    os.unlink(updater.temp_cache_filename)

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testVerifyFailure(self):
    # Hide the warning that we expect to get

    class TestFilter(logging.Filter):
      def filter(self, record):
        return not record.msg.startswith('verify failed: %d keys missing')

    fltr = TestFilter()
    logging.getLogger('NssDbGroupHandler').addFilter(fltr)

    # create a map
    m = group.GroupMap()
    e = group.GroupMapEntry()
    e.name = 'foo'
    e.gid = 2000
    self.assertTrue(m.Add(e))

    updater = nssdb.NssDbGroupHandler({'dir': self.workdir,
                                       'makedb': '/usr/bin/makedb'})
    written = updater.Write(m)

    self.assertTrue(os.path.exists(updater.temp_cache_filename),
                    'updater.Write() did not create a file')

    # change the cache
    db = bsddb.btopen(updater.temp_cache_filename)
    del db[db.first()[0]]
    db.sync()
    db.close()

    retval = updater.Verify(written)

    self.assertEqual(False, retval)
    self.assertFalse(os.path.exists(os.path.join(updater.temp_cache_filename)))
    # no longer hide this message
    logging.getLogger('NssDbGroupHandler').removeFilter(fltr)


class TestNssDbShadowHandler(mox.MoxTestBase):

  def setUp(self):
    super(TestNssDbShadowHandler, self).setUp()
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    super(TestNssDbShadowHandler, self).tearDown()
    # remove the test working directory
    shutil.rmtree(self.workdir)

  def testConvertValueToMapEntry(self):
    ent = 'foo:*:::::::0'

    updater = nssdb.NssDbShadowHandler({})

    sme = updater.ConvertValueToMapEntry(ent)

    self.assertEqual('foo', sme.name)
    self.assertEqual('*', sme.passwd)
    self.assertEqual(0, sme.flag)

  def testIsMapPrimaryKey(self):
    updater = nssdb.NssDbShadowHandler({})

    self.assertTrue(updater.IsMapPrimaryKey('.foo'))
    self.assertFalse(updater.IsMapPrimaryKey('00'))

  def testNssDbShadowHandlerWriteData(self):
    ent = 'foo:!!:::::::0'

    makedb_stdin = self.mox.CreateMock(sys.stdin)
    makedb_stdin.write('.foo %s\n' % ent)
    makedb_stdin.write('00 %s\n' % ent)

    m = shadow.ShadowMap()
    s = shadow.ShadowMapEntry()
    s.name = 'foo'

    self.assertTrue(m.Add(s))

    writer = nssdb.NssDbShadowHandler({'makedb': '/bin/false',
                                       'dir': '/tmp'})

    self.mox.ReplayAll()

    writer.WriteData(makedb_stdin, s, 0)

  def testNssDbShadowHandlerWrite(self):
    ent = 'foo:*:::::::0'

    makedb_stdin = self.mox.CreateMock(sys.stdin)
    makedb_stdin.write('.foo %s\n' % ent)
    makedb_stdin.write('00 %s\n' % ent)
    makedb_stdin.close()

    makedb_stdout = self.mox.CreateMock(sys.stdout)
    makedb_stdout.read().AndReturn('')
    makedb_stdout.close()

    m = shadow.ShadowMap()
    s = shadow.ShadowMapEntry()
    s.name = 'foo'
    s.passwd = '*'
    s.Verify()
    self.assertTrue(m.Add(s))

    self.mox.StubOutWithMock(select, 'select')
    select.select([makedb_stdout], (), (), 0).AndReturn(([37], [], []))
    select.select([makedb_stdout], (), (), 0).AndReturn(([], [], []))

    def SpawnMakeDb():
      makedb = MakeDbDummy()
      makedb.stdin = makedb_stdin
      makedb.stdout = makedb_stdout
      return makedb

    writer = nssdb.NssDbShadowHandler({'makedb': '/usr/bin/makedb',
                                       'dir': self.workdir})
    writer._SpawnMakeDb = SpawnMakeDb
    self.mox.ReplayAll()

    writer.Write(m)

    tmpshadow = os.path.join(self.workdir, 'shadow.db')
    self.assertFalse(os.path.exists(tmpshadow))
    # just clean it up, Write() doesn't Commit()
    writer._Rollback()

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testVerify(self):
    m = shadow.ShadowMap()
    s = shadow.ShadowMapEntry()
    s.name = 'foo'
    self.assertTrue(m.Add(s))

    updater = nssdb.NssDbShadowHandler({'dir': self.workdir,
                                        'makedb': '/usr/bin/makedb'})
    written = updater.Write(m)

    self.assertTrue(os.path.exists(updater.temp_cache_filename),
                    'updater.Write() did not create a file')

    retval = updater.Verify(written)

    self.assertEqual(True, retval)
    os.unlink(updater.temp_cache_filename)

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testVerifyFailure(self):
    # Hide the warning that we expect to get
    class TestFilter(logging.Filter):
      def filter(self, record):
        return not record.msg.startswith('verify failed: %d keys missing')

    fltr = TestFilter()
    logging.getLogger('NssDbShadowHandler').addFilter(fltr)

    # create a map
    m = shadow.ShadowMap()
    s = shadow.ShadowMapEntry()
    s.name = 'foo'
    self.assertTrue(m.Add(s))

    updater = nssdb.NssDbShadowHandler({'dir': self.workdir,
                                        'makedb': '/usr/bin/makedb'})
    written = updater.Write(m)

    self.assertTrue(os.path.exists(updater.temp_cache_filename),
                    'updater.Write() did not create a file')

    # change the cache
    db = bsddb.btopen(updater.temp_cache_filename)
    del db[db.first()[0]]
    db.sync()
    db.close()

    retval = updater.Verify(written)

    self.assertEqual(False, retval)
    self.assertFalse(os.path.exists(os.path.join(updater.temp_cache_filename)))
    # no longer hide this message
    logging.getLogger('NssDbShadowHandler').removeFilter(fltr)


class TestNssDbCache(unittest.TestCase):

  def setUp(self):
    super(TestNssDbCache, self).setUp()
    self.workdir = tempfile.mkdtemp()

  def tearDown(self):
    super(TestNssDbCache, self).tearDown()
    shutil.rmtree(self.workdir)

  @unittest.skipIf(NoMakeDB(), 'no /usr/bin/makedb')
  def testWriteTestBdb(self):
    data = passwd.PasswdMap()
    pw = passwd.PasswdMapEntry()
    pw.name = 'foo'
    pw.passwd = 'x'
    pw.uid = 1000
    pw.gid = 1000
    pw.gecos = 'doody'
    pw.dir = '/'
    pw.shell = '/bin/sh'
    self.assertTrue(data.Add(pw))

    # instantiate object under test
    dummy_config = {'dir': self.workdir}
    cache = nssdb.NssDbPasswdHandler(dummy_config)

    written = cache.Write(data)
    self.assertTrue('.foo' in written)
    self.assertTrue('=1000' in written)

    # perform test
    db = bsddb.btopen(cache.temp_cache_filename, 'r')

    self.assertEqual(3, len(list(db.keys())))
    self.assertTrue('.foo' in list(db.keys()))
    self.assertTrue('=1000' in list(db.keys()))
    self.assertTrue('00' in list(db.keys()))

    # convert data to pwent
    d = '%s:x:%s:%s:%s:%s:%s\x00' % (pw.name, pw.uid, pw.gid, pw.gecos,
                                     pw.dir, pw.shell)
    self.assertEqual(db['00'], d)
    self.assertEqual(db['.foo'], d)
    self.assertEqual(db['=1000'], d)

    # tear down
    os.unlink(cache.temp_cache_filename)

  def testLoadBdbCacheFile(self):
    pass_file = os.path.join(self.workdir, 'passwd.db')
    db = bsddb.btopen(pass_file, 'c')
    ent = 'foo:x:1000:500:bar:/:/bin/sh'
    db['00'] = ent
    db['=1000'] = ent
    db['.foo'] = ent
    db.sync()
    self.assertTrue(os.path.exists(pass_file))

    config = {'dir': self.workdir}
    cache = nssdb.NssDbPasswdHandler(config)
    data_map = cache.GetMap()
    cache._LoadBdbCacheFile(data_map)
    self.assertEqual(1, len(data_map))

    # convert data to pwent
    x = data_map.PopItem()
    d = '%s:x:%s:%s:%s:%s:%s' % (x.name, x.uid, x.gid, x.gecos, x.dir, x.shell)
    self.assertEqual(ent, d)

    os.unlink(pass_file)

  def testGetMapRaisesCacheNotFound(self):
    bad_file = os.path.join(self.workdir, 'really_not_going_to_exist_okay')
    self.assertFalse(os.path.exists(bad_file), 'what the hell, it exists!')

    config = {}
    cache = nssdb.NssDbPasswdHandler(config)
    cache.CACHE_FILENAME = bad_file
    self.assertRaises(error.CacheNotFound, cache.GetMap)

  def testGetMapIsSizedObject(self):
    timestamp = int(time.time())
    update_ts_filename = os.path.join(self.workdir,
                                      'passwd.db.nsscache-update-timestamp')
    update_ts_file = open(update_ts_filename, 'w')
    update_ts_file.write('%s\n' % time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                time.gmtime(timestamp)))
    update_ts_file.close()
    db_filename = os.path.join(self.workdir, 'passwd.db')
    db = bsddb.btopen(db_filename)
    db.close()
    cache = nssdb.NssDbPasswdHandler({'dir': self.workdir})
    cache_map = cache.GetMap()
    self.assertEqual(0, len(cache_map))
    os.unlink(update_ts_filename)
    os.unlink(db_filename)

  def testGetMapHasMerge(self):
    timestamp = int(time.time())
    update_ts_filename = os.path.join(self.workdir,
                                      'passwd.db.nsscache-update-timestamp')
    update_ts_file = open(update_ts_filename, 'w')
    update_ts_file.write('%s\n' % time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                time.gmtime(timestamp)))
    update_ts_file.close()
    db_filename = os.path.join(self.workdir, 'passwd.db')
    db = bsddb.btopen(db_filename)
    db.close()
    cache = nssdb.NssDbPasswdHandler({'dir': self.workdir})
    cache_map = cache.GetMap()
    self.assertEqual(False, cache_map.Merge(passwd.PasswdMap()))
    os.unlink(update_ts_filename)
    os.unlink(db_filename)

  def testGetMapIsIterable(self):
    timestamp = int(time.time())
    update_ts_filename = os.path.join(self.workdir,
                                      'passwd.db.nsscache-update-timestamp')
    update_ts_file = open(update_ts_filename, 'w')
    update_ts_file.write('%s\n' % time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                                time.gmtime(timestamp)))
    update_ts_file.close()
    db_filename = os.path.join(self.workdir, 'passwd.db')
    db = bsddb.btopen(db_filename)
    db.close()
    cache = nssdb.NssDbPasswdHandler({'dir': self.workdir})
    cache_map = cache.GetMap()
    self.assertEqual([], list(cache_map))
    os.unlink(update_ts_filename)
    os.unlink(db_filename)


if __name__ == '__main__':
  unittest.main()
