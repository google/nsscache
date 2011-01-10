#!/usr/bin/python
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

"""Unit test for base.py.

Since these are abstract classes, the bulk of the functionality in base.py is
specifically tested in passwd_test.py instead.
"""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import unittest


from nss_cache.maps import base


class TestMap(unittest.TestCase):
  """Tests for the Map class."""
  
  def testIsAbstract(self):
    """Creating a Map should raise a TypeError."""
    self.assertRaises(TypeError, base.Map)


class TestMapEntry(unittest.TestCase):
  """Tests for the MapEntry class."""
  
  def testIsAbstract(self):
    """Creating a MapEntry should raise a TypeError."""
    self.assertRaises(TypeError, base.MapEntry)


if __name__ == '__main__':
  unittest.main()
