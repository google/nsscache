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

  def __init__(self, iterable=None):
    """Construct a PasswdMap object from optional iterable."""
    super(PasswdMap, self).__init__(iterable)

  def Add(self, entry):
    """Add a new object, verify it is a PasswdMapEntry object."""
    if not isinstance(entry, PasswdMapEntry):
      raise TypeError
    return super(PasswdMap, self).Add(entry)


class PasswdMapEntry(base.MapEntry):
  """This class represents NSS passwd map entries.
  
  Entries are internally a dict, see the abstract class MapEntry.
  """
  
  def __init__(self, data=None):
    """Construct a PasswdMapEntry, setting reasonable defaults."""
    
    # Primary key for this MapEntry is name
    pkey = 'name'
    # Required keys, e.g. no reasonable defaults.
    req_keys = ('name', 'uid', 'gid')
    # All keys and their expected types.
    types = {'name': str, 'passwd': str, 'uid': int, 'gid': int, 'gecos': str,
             'dir': str, 'shell': str}
    
    # Seed data with defaults if needed
    if data is None: data = {}
    if 'passwd' not in data: data['passwd'] = 'x'
    if 'gecos' not in data: data['gecos'] = ''
    if 'dir' not in data: data['dir'] = ''
    if 'shell' not in data: data['shell'] = ''

    # Initialize!
    super(PasswdMapEntry, self).__init__(pkey, req_keys, types, data)

  def _VerifyAttr(self, attr):
    """Verify a single attribute, and return True or raise an exception."""
    super(PasswdMapEntry, self)._VerifyAttr(attr)
    value = self._data[attr]
    # Strings can not have ':' in them.
    if isinstance(value, str) and value.count(':') > 0:
      raise AttributeError('Colon in strings not allowed.', attr, value)

    return True
