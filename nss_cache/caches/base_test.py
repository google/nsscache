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

import unittest
import pmock

from nss_cache.caches import base


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
      def _Commit(self):
        pass

    cache_map = DummyCache()
    cache_map\
                       .expects(pmock.once())\
                       .Write(pmock.eq('writable_map'))\
                       .will(pmock.return_value('entries_written'))
    cache_map\
                       .expects(pmock.once())\
                       .Verify(pmock.eq('entries_written'))\
                       .will(pmock.return_value(True))

    self.assertEqual(0, cache_map.WriteMap('writable_map'))


if __name__ == '__main__':
  unittest.main()
