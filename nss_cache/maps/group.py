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

"""An implementation of a group map for nsscache.

GroupMap:  An implementation of NSS group maps based on the Map
class.

GroupMapEntry:  A group map entry based on the MapEntry class.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

from nss_cache.maps import base


class GroupMap(base.Map):
  """This class represents an NSS group map.
  
  Map data is stored as a list of MapEntry objects, see the abstract
  class Map.
  """

  def __init__(self, iterable=None):
    """Construct a GroupMap object using optional iterable."""
    super(GroupMap, self).__init__(iterable)
    
  def Add(self, entry):
    """Add a new object, verify it is a GroupMapEntry object."""
    if not isinstance(entry, GroupMapEntry):
      raise TypeError
    return super(GroupMap, self).Add(entry)


class GroupMapEntry(base.MapEntry):
  """This class represents NSS group map entries.
  
  Entries are internally a dict, see the abstract class MapEntry.
  """

  def __init__(self, data=None):
    """Construct a GroupMapEntry."""

    # Primary key for this MapEntry is name
    pkey = 'name'
    # Required keys, e.g. no reasonble defaults.
    req_keys = ('name', 'gid')
    # All keys and their expected types.
    types = {'name': str, 'passwd': str, 'gid': int, 'members': list}

    # Seed data with defaults if needed
    if data is None: data = {}
    if 'passwd' not in data: data['passwd'] = 'x'
    if 'members' not in data: data['members'] = []
    
    super(GroupMapEntry, self).__init__(pkey, req_keys, types, data)

  def _VerifyAttr(self, attr):
    """Verify a single attribute, and return True or raise an exception."""
    super(GroupMapEntry, self)._VerifyAttr(attr)
    
    value = self._data[attr]
    # Strings can not have ':' in them.
    if isinstance(value, str) and value.count(':') > 0:
      raise AttributeError('Colon in strings not allowed.', attr, value)

    return True
