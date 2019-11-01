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
"""Unit tests for sources/source.py."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import unittest

from nss_cache.sources import source
from nss_cache.sources import source_factory


class TestSourceFactory(unittest.TestCase):
  """Unit tests for the source factory."""

  def testRegister(self):

    number_of_sources = len(source_factory._source_implementations)

    class DummySource(source.Source):
      name = 'dummy'

    source_factory.RegisterImplementation(DummySource)

    self.assertEqual(number_of_sources + 1,
                     len(source_factory._source_implementations))
    self.assertEqual(DummySource,
                     source_factory._source_implementations['dummy'])

  def testRegisterWithoutName(self):

    class DummySource(source.Source):
      pass

    self.assertRaises(RuntimeError, source_factory.RegisterImplementation,
                      DummySource)

  def testCreateWithNoImplementations(self):
    source_factory._source_implementations = {}
    self.assertRaises(RuntimeError, source_factory.Create, {})

  def testCreate(self):

    class DummySource(source.Source):
      name = 'dummy'

    source_factory.RegisterImplementation(DummySource)

    dummy_config = {'name': 'dummy'}
    dummy_source = source_factory.Create(dummy_config)

    self.assertEqual(DummySource, type(dummy_source))


if __name__ == '__main__':
  unittest.main()
