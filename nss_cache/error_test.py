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
"""Unit tests for nss_cache/error.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import unittest

from nss_cache import error


class TestError(unittest.TestCase):
  """Unit tests for error.py"""

  def testError(self):
    """We can throw an error.Error"""

    class Ooops(object):
      """Raises error.Error"""

      def __init__(self):
        raise error.Error

    self.assertRaises(error.Error, Ooops)

  def testCacheNotFound(self):
    """We can throw an error.CacheNotFound"""

    class Ooops(object):
      """Raises error.CacheNotFound"""

      def __init__(self):
        raise error.CacheNotFound

    self.assertRaises(error.CacheNotFound, Ooops)

  def testCommandParseError(self):
    """We can throw an error.CommandParseError"""

    class Ooops(object):
      """Raises error.CommandParseError"""

      def __init__(self):
        raise error.CommandParseError

    self.assertRaises(error.CommandParseError, Ooops)

  def testConfigurationError(self):
    """We can throw an error.ConfigurationError"""

    class Ooops(object):
      """Raises error.ConfigurationError"""

      def __init__(self):
        raise error.ConfigurationError

    self.assertRaises(error.ConfigurationError, Ooops)

  def testEmptyMap(self):
    """error.EmptyMap is raisable"""

    def Kaboom():
      raise error.EmptyMap

    self.assertRaises(error.EmptyMap, Kaboom)

  def testNoConfigFound(self):
    """We can throw an error.NoConfigFound"""

    class Ooops(object):
      """Raises error.NoConfigFound"""

      def __init__(self):
        raise error.NoConfigFound

    self.assertRaises(error.NoConfigFound, Ooops)

  def testPermissionDenied(self):
    """error.PermissionDenied is raisable"""

    def Kaboom():
      raise error.PermissionDenied

    self.assertRaises(error.PermissionDenied, Kaboom)

  def testUnsupportedMap(self):
    """We can throw an error.UnsupportedMap"""

    class Ooops(object):
      """Raises error.UnsupportedMap"""

      def __init__(self):
        raise error.UnsupportedMap

    self.assertRaises(error.UnsupportedMap, Ooops)

  def testSourceUnavailable(self):
    """We can throw an error.SourceUnavailable"""

    class Ooops(object):
      """Raises error.SourceUnavailable"""

      def __init__(self):
        raise error.SourceUnavailable

    self.assertRaises(error.SourceUnavailable, Ooops)


if __name__ == '__main__':
  unittest.main()
