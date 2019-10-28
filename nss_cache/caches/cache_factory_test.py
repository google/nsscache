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

"""Unit tests for out cache factory"""

__author__ = 'springer@google.com (Matthew Springer)'

import unittest

from nss_cache.caches import caches
from nss_cache.caches import cache_factory

class TestCacheFactory(unittest.TestCase):

  def testRegister(self):

    class DummyCache(caches.Cache):
      pass

    old_cache_implementations = cache_factory._cache_implementations
    cache_factory._cache_implementations = {}
    cache_factory.RegisterImplementation('dummy', 'dummy', DummyCache)
    self.assertEqual(1, len(cache_factory._cache_implementations))
    self.assertEqual(1, len(cache_factory._cache_implementations['dummy']))
    self.assertEqual(DummyCache,
                         cache_factory._cache_implementations['dummy']['dummy'])
    cache_factory._cache_implementations = old_cache_implementations

  def testCreateWithNoImplementations(self):
    old_cache_implementations = cache_factory._cache_implementations
    cache_factory._cache_implementations = {}
    self.assertRaises(RuntimeError, cache_factory.Create, {}, 'map_name')
    cache_factory._cache_implementations = old_cache_implementations


  def testThatRegularImplementationsArePresent(self):
    self.assertEqual(len(cache_factory._cache_implementations), 2)


if __name__ == '__main__':
  unittest.main()
