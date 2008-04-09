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

"""Unit tests for caches/base.py."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import os
import tempfile
import unittest

from nss_cache import error
from nss_cache import maps
from nss_cache.caches import base

import pmock


class StubOut:
  """Testing class for stubbing."""

  def __init__(self):
    self._stubs = {}

  def __del__(self):
    for method in self._stubs:
      self.UnSet(method)

  def Set(self, cls, method, callable_object):
    """Stub out a method on a class, with a callable.

    At object destruction, the stubbed-over method is restored.

    Args:
      cls: An object to have methods stubbed.
      method: A string naming the method to stub out.
      callable_object: A callable object to replace the named method.
    """
    try:
      stubbed = getattr(cls, method)
    except AttributeError:
      stubbed = None
    self._stubs[method] = (cls, method, stubbed)
    setattr(cls, method, callable_object)

  def UnSet(self, method):
    """Restore the class's method to its original."""
    if method in self._stubs:
      cls, method, stubbed = self._stubs[method]
      setattr(cls, method, stubbed)


class TestCacheFactory(unittest.TestCase):

  def testRegister(self):

    class DummyCache(base.Cache):
      pass

    old_cache_implementations = base._cache_implementations
    base._cache_implementations = {}
    base.RegisterImplementation('dummy', 'dummy', DummyCache)
    self.failUnlessEqual(1, len(base._cache_implementations))
    self.failUnlessEqual(1, len(base._cache_implementations['dummy']))
    self.failUnlessEqual(DummyCache,
                         base._cache_implementations['dummy']['dummy'])
    base._cache_implementations = old_cache_implementations

  def testCreateWithNoImplementations(self):
    old_cache_implementations = base._cache_implementations
    base._cache_implementations = {}
    self.assertRaises(RuntimeError, base.Create, {}, 'map_name')
    base._cache_implementations = old_cache_implementations


class TestCache(pmock.MockTestCase):

  def setUp(self):
    class DummyLogger(object):
      def debug(self, message):
        pass
      
      def info(self, message):
        pass
      
      def warning(self, message):
        pass

    self.dummy_logger = DummyLogger()

  def testWriteMap(self):

    class DummyCache(pmock.Mock, base.Cache):
      def _Commit(self, ts):
        return ts == 'modify'

    cache_map = DummyCache()
    cache_map\
                       .expects(pmock.once())\
                       .Write(pmock.eq('writable_map'))\
                       .will(pmock.return_value('entries_written'))
    cache_map\
                       .expects(pmock.once())\
                       .Verify(pmock.eq('entries_written'))\
                       .will(pmock.return_value(True))

    self.assertEqual(0, cache_map._WriteMap('writable_map', 'modify'))

  def testUpdateIncrementalTrue(self):

    class DummyMap(pmock.Mock, list):
      pass

    cache_map = DummyMap()
    # make the sequence some len
    cache_map.append(1)
    cache_map\
               .expects(pmock.once())\
               .Merge(pmock.eq(['foo']))\
               .will(pmock.return_value(True))

    source_map = DummyMap()
    source_map.append('foo')
    source_map\
                .expects(pmock.once())\
                .GetModifyTimestamp()\
                .will(pmock.return_value('source-modify-timestamp'))

    class DummyHandler(pmock.Mock, base.Cache):
      def _ReadTimestamp(self, suffix):
        return 'cache-modify-timestamp'

      def _WriteTimestamp(self, timestamp, suffix):
        return

      def _Commit(self, ts):
        return ts == 'cache-modify-timestamp'

    handler = DummyHandler()
    handler.log = self.dummy_logger
    handler\
             .expects(pmock.once())\
             .GetSourceMap(pmock.eq('source'),
                           since=pmock.eq('cache-modify-timestamp'))\
             .will(pmock.return_value(source_map))
    handler\
             .expects(pmock.once())\
             .GetCacheMap()\
             .will(pmock.return_value(cache_map))
    handler\
             .expects(pmock.once())\
             .Write(pmock.eq(cache_map))\
             .will(pmock.return_value('entries_written'))
    handler\
               .expects(pmock.once())\
               .Verify(pmock.eq('entries_written'))\
               .will(pmock.return_value(True))

    self.assertEqual(0, handler.Update('source', incremental=True))

  def testUpdateIncrementalFalse(self):

    class DummyMap(pmock.Mock, list):
      """mock object that is also some sequence object (and has __len__)."""
      pass

    source_map = DummyMap()
    # make the sequence some len > 0
    source_map.append(1)
    source_map\
                .expects(pmock.once())\
                .GetModifyTimestamp()\
                .will(pmock.return_value('foo'))

    class DummyMapHandler(pmock.Mock, base.Cache):
      def _WriteTimestamp(self, timestamp, suffix):
        return

      def _Commit(self, ts):
        return ts == 'foo'

    cache_map_handler = DummyMapHandler()
    cache_map_handler.log = self.dummy_logger
    cache_map_handler\
                       .expects(pmock.once())\
                       .GetSourceMap(pmock.eq('source'),
                                     since=pmock.eq(None))\
                       .will(pmock.return_value(source_map))
    cache_map_handler\
                       .expects(pmock.once())\
                       .Write(pmock.eq(source_map))\
                       .will(pmock.return_value('entries_written'))
    cache_map_handler\
                       .expects(pmock.once())\
                       .Verify(pmock.eq('entries_written'))\
                       .will(pmock.return_value(True))
    cache_map_handler\
                       .expects(pmock.once())\
                       .WriteUpdateTimestamp()

    self.assertEqual(0, cache_map_handler.Update('source', incremental=False))

  def testFullUpdateDiscardsCacheMap(self):
    # when we do a full update, we should discard the cache map
    # so that deletions from the upstream source actually propagate.

    # create a cache map with some data in it
    cache_map_entry = maps.PasswdMapEntry()
    cache_map_entry.name = 'foo'
    cache_map_entry.passwd = 'x'
    cache_map_entry.uid = 10
    cache_map_entry.gid = 11
    cache_map_entry.gecos = 'Foo Bar Baz'
    cache_map_entry.dir = '/home/foo'
    cache_map_entry.shell = '/bin/sh'
    cache_map = maps.PasswdMap([cache_map_entry])
    # create a source with different data in it
    source_map_entry = maps.PasswdMapEntry()
    source_map_entry.name = 'bar'
    source_map_entry.passwd = 'x'
    source_map_entry.uid = 10
    source_map_entry.gid = 11
    source_map_entry.gecos = 'Bar Baz Foo'
    source_map_entry.dir = '/home/bar'
    source_map_entry.shell = '/bin/sh'
    source_map = maps.PasswdMap([source_map_entry])
    # call update with incremental false

    class DummyMapHandler(pmock.Mock, base.Cache):
      def _WriteTimestamp(self, timestamp, suffix):
        return

      def _Commit(self, ts):
        assert ts is None
        return True

    handler = DummyMapHandler()
    handler.log = self.dummy_logger
    handler\
             .expects(pmock.once())\
             .GetCacheMap()\
             .will(pmock.return_value(cache_map))
    handler\
             .expects(pmock.once())\
             .GetSourceMap(pmock.eq('source'),
                           since=pmock.eq(None))\
             .will(pmock.return_value(source_map))
    handler\
             .expects(pmock.once())\
             .Write(pmock.eq(source_map))\
             .will(pmock.return_value('entries_written'))
    handler\
             .expects(pmock.once())\
             .Verify(pmock.eq('entries_written'))\
             .will(pmock.return_value(True))
    handler\
             .expects(pmock.once())\
             .WriteUpdateTimestamp()

    self.assertEqual(0, handler.Update('source', incremental=False))

  def testUpdateTrapsCacheNotFound(self):

    class DummyHandler(pmock.Mock, base.Cache):
      def _WriteMap(self, writable_map, timestamp):
        return 0

      def _WriteTimestamp(self, timestamp, suffix):
        return

    class DummySource(pmock.Mock, list):
      pass
    source_mock = DummySource()
    source_mock.append(1)
    source_mock\
                 .expects(pmock.once())\
                 .method('GetModifyTimestamp')
    handler = DummyHandler()
    handler.log = self.dummy_logger
    handler\
             .expects(pmock.once())\
             .GetCacheMap()\
             .will(pmock.raise_exception(error.CacheNotFound))
    handler\
             .expects(pmock.once())\
             .GetSourceMap(pmock.eq(None), since=pmock.eq(None))\
             .will(pmock.return_value(source_mock))
    handler\
             .expects(pmock.once())\
             .WriteUpdateTimestamp()

    # pass None to handler.Update as source, as we already override
    # GetSourceMap in the DummyHandler
    self.assertEqual(0, handler.Update(None, incremental=False))

  def testFullEmptySourceMapDoesntUpdate(self):
    # During 'update --full', we should not replace the local database if
    # the source map retrieved is empty -- i.e. this looks like an error
    # so we should abort before doing something potentially bad.

    class DummyMapHandler(pmock.Mock, base.Cache):
      """Dummy cache map handler mock."""
      pass

    handler = DummyMapHandler()
    handler.log = self.dummy_logger
    # only implement the method we expect to have called,
    # returning an empty list
    handler\
             .expects(pmock.once())\
             .GetSourceMap(pmock.eq(None), since=pmock.eq(None))\
             .will(pmock.return_value([]))
    # if write gets called, Update is doing the wrong thing
    handler\
             .expects(pmock.never())\
             .Write(pmock.eq([]))
    # TODO(jaq): do we want to check that WriteUpdateTimestamp occurred?
    # even though we flagged a failure?

    self.assertRaises(error.EmptyMap, handler.Update, None, incremental=False)

  def testFullEmptySourceMapDoesUpdateWhenForced(self):
    # same as above, but we ignore the check when force_write=True

    # mock object that is also some sequence object (and has __len__)
    class DummyMap(pmock.Mock, list):
      pass

    source_map = DummyMap()
    source_map\
                .expects(pmock.once())\
                .GetModifyTimestamp()\
                .will(pmock.return_value('foo'))

    class DummyMapHandler(pmock.Mock, base.Cache):
      """Dummy cache map handler mock."""

      def _WriteTimestamp(self, timestamp, suffix):
        return

      def _Commit(self, ts):
        assert 'foo' == ts
        return True

    handler = DummyMapHandler()
    handler.log = self.dummy_logger
    # only implement the method we expect to have called
    handler\
             .expects(pmock.once())\
             .GetSourceMap(pmock.eq(None), since=pmock.eq(None))\
             .will(pmock.return_value(source_map))
    handler\
             .expects(pmock.once())\
             .Write(pmock.eq(source_map))\
             .will(pmock.return_value('entries_written'))
    handler\
             .expects(pmock.once())\
             .Verify(pmock.eq('entries_written'),)\
             .will(pmock.return_value(True))
    handler\
             .expects(pmock.once())\
             .WriteUpdateTimestamp()\
             .will(pmock.return_value(True))

    self.assertEquals(0, handler.Update(None, incremental=False,
                                        force_write=True))

  def testIncrementalUpdateEmptyMapDoesUpdate(self):

    class DummyMap(pmock.Mock, list):
      pass

    source_map = DummyMap()
    source_map\
                .expects(pmock.once())\
                .GetModifyTimestamp()\
                .will(pmock.return_value('source-modify-timestamp'))

    cache_map = DummyMap()
    cache_map.append('cache-map-entry')
    cache_map\
               .expects(pmock.once())\
               .Merge(pmock.eq(source_map))\
               .will(pmock.return_value(True))

    class DummyHandler(pmock.Mock, base.Cache):
      """Dummy cache map handler mock."""

      def _ReadTimestamp(self, suffix):
        return 'cache-modify-timestamp'

      def _WriteTimestamp(self, timestamp, suffix):
        return

      def _Commit(self, ts):
        assert 'source-modify-timestamp' == ts
        return True

    handler = DummyHandler()
    handler.log = self.dummy_logger
    handler\
             .expects(pmock.once())\
             .GetSourceMap(pmock.eq('source'),
                           since=pmock.eq('cache-modify-timestamp'))\
             .will(pmock.return_value(source_map))
    handler\
             .expects(pmock.once())\
             .GetCacheMap()\
             .will(pmock.return_value(cache_map))
    handler\
             .expects(pmock.once())\
             .Write(pmock.eq(cache_map))\
             .will(pmock.return_value('entries_written'))
    handler\
             .expects(pmock.once())\
             .Verify(pmock.eq('entries_written'))\
             .will(pmock.return_value(True))
    handler\
             .expects(pmock.once())\
             .WriteUpdateTimestamp()\
             .will(pmock.return_value(True))

    self.assertEquals(0, handler.Update('source', incremental=True))

  def testTimestampDir(self):
    workdir = tempfile.mkdtemp()
    timestamp_dir = os.path.join(workdir, 'timestamps')
    os.mkdir(timestamp_dir)
    config = {'timestamp_dir': timestamp_dir,
              'dir': workdir}
    cache = base.Cache(config)
    cache.UPDATE_TIMESTAMP_SUFFIX = 'update'
    cache.MODIFY_TIMESTAMP_SUFFIX = 'modify'
    cache.CACHE_FILENAME = 'test'

    self.assertEquals(True, cache.WriteUpdateTimestamp(1))
    update_timestamp_filename = os.path.join(timestamp_dir, 'test.update')
    self.failUnless(os.path.exists(update_timestamp_filename))
    self.assertEqual(1, cache.GetUpdateTimestamp())

    self.assertEquals(True, cache.WriteModifyTimestamp(2))
    modify_timestamp_filename = os.path.join(timestamp_dir, 'test.modify')
    self.failUnless(os.path.exists(modify_timestamp_filename))
    self.assertEqual(2, cache.GetModifyTimestamp())

    os.unlink(update_timestamp_filename)
    os.unlink(modify_timestamp_filename)
    os.rmdir(timestamp_dir)
    os.rmdir(workdir)

  def testIncrementalUpdateWhenCacheNotFound(self):

    def StubGetModifyTimestamp():
      return 'timestamp'

    def StubGetSourceMap(source, since):
      class Foo:
        def GetModifyTimestamp(self):
          return 'foo'

        def __len__(self):
          return 37

      return Foo()

    def StubGetCacheMap():
      raise error.CacheNotFound

    def StubWriteMap(writable_map, timestamp):
      # this function returns what Update eventually returns
      return 12

    config = {}
    cache = base.Cache(config)
    # stub out things
    stubs = StubOut()
    stubs.Set(cache, 'GetModifyTimestamp', StubGetModifyTimestamp)
    stubs.Set(cache, 'GetSourceMap', StubGetSourceMap)
    stubs.Set(cache, 'GetCacheMap', StubGetCacheMap)
    stubs.Set(cache, '_WriteMap', StubWriteMap)

    return_val = cache.Update('source', incremental=True)
    self.assertEqual(12, return_val)


if __name__ == '__main__':
  unittest.main()
