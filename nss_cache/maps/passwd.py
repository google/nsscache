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

"""An implementation of a passwd map for nsscache.

PasswdMap:  An implementation of NSS passwd maps based on the Map
class.

PasswdMapEntry:  A passwd map entry based on the MapEntry class.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

from nss_cache.maps import base


class PasswdMap(base.Map):
  """This class represents an NSS passwd map.
  
  Map data is stored as a list of MapEntry objects, see the abstract
  class Map.
  """

  def Add(self, entry):
    """Add a new object, verify it is a PasswdMapEntry instance.

    Args:
      entry: A PasswdMapEntry instance.

    Returns:
      True if added successfully, False otherwise.

    Raises:
      TypeError: The argument is of the wrong type.
    """
    if not isinstance(entry, PasswdMapEntry):
      raise TypeError
    return super(PasswdMap, self).Add(entry)


class PasswdMapEntry(base.MapEntry):
  """This class represents NSS passwd map entries."""
  # Using slots saves us over 2x memory on large maps.
  __slots__ = ('name', 'uid', 'gid', 'passwd', 'gecos', 'dir', 'shell')
  _KEY = 'name'
  _ATTRS = ('name', 'uid', 'gid', 'passwd', 'gecos', 'dir', 'shell')
  
  def __init__(self, data=None):
    """Construct a PasswdMapEntry, setting reasonable defaults."""
    self.name = None
    self.uid = None
    self.gid = None
    self.passwd = None
    self.gecos = None
    self.dir = None
    self.shell = None

    super(PasswdMapEntry, self).__init__(data)

    # Seed data with defaults if still empty
    if self.passwd is None: self.passwd = 'x'
    if self.gecos is None: self.gecos = ''
    if self.dir is None: self.dir = ''
    if self.shell is None: self.shell = ''
