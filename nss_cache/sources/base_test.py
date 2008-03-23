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

"""Unit tests for sources/base.py."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import unittest

from nss_cache.sources import base


class TestSourceFactory(unittest.TestCase):
  """Unit tests for the source factory."""

  def testRegister(self):

    class DummySource(base.Source):
      name = 'dummy'

    base.RegisterImplementation(DummySource)

    self.failUnlessEqual(1, len(base._source_implementations))
    self.failUnlessEqual(DummySource, base._source_implementations['dummy'])

  def testRegisterWithoutName(self):

    class DummySource(base.Source):
      pass

    self.assertRaises(RuntimeError, base.RegisterImplementation, DummySource)

  def testCreateWithNoImplementations(self):
    base._source_implementations = {}
    self.assertRaises(RuntimeError, base.Create, {})

  def testCreate(self):

    class DummySource(base.Source):
      name = 'dummy'

    base.RegisterImplementation(DummySource)

    dummy_config = {'name': 'dummy'}

    source = base.Create(dummy_config)

    self.assertEqual(DummySource, type(source))


class TestSource(unittest.TestCase):
  """Unit tests for the Source class."""

  def testCreateNoConfig(self):

    config = []

    self.assertRaises(RuntimeError, base.Source, config)

    self.assertRaises(RuntimeError, base.Source, None)

    config = 'foo'

    self.assertRaises(RuntimeError, base.Source, config)

  def testVerify(self):
    s = base.Source({})
    self.assertRaises(NotImplementedError, s.Verify)


if __name__ == '__main__':
  unittest.main()
