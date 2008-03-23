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

"""An implementation of a shadow map for nsscache.

ShadowMap:  An implementation of NSS shadow maps based on the Map
class.

ShadowMapEntry:  A shadow map entry based on the MapEntry class.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

from nss_cache.maps import base


class ShadowMap(base.Map):
  """This class represents an NSS shadow map.
  
  Map data is stored as a list of MapEntry objects, see the abstract
  class Map.
  """

  def __init__(self, iterable=None):
    """Construct a ShadowMap object using optional iterable."""
    super(ShadowMap, self).__init__(iterable)
    
  def Add(self, entry):
    """Add a new object, verify it is a ShadowMapEntry object."""
    if not isinstance(entry, ShadowMapEntry):
      raise TypeError
    return super(ShadowMap, self).Add(entry)


class ShadowMapEntry(base.MapEntry):
  """This class represents NSS shadow map entries.
  
  Entries are internally a dict, see the abstract class MapEntry.
  """
    
  def __init__(self, data=None):
    """Construct a ShadowMapEntry, setting reasonable defaults."""

    # Primary key for this MapEntry is name
    pkey = 'name'
    # Required keys, e.g. no reasonable defaults.
    req_keys = ('name',)
    # All keys and their expected types.
    types = {'name': str, 'passwd': str, 'lstchg': (int, None),
             'min': (int, None), 'max': (int, None),
             'warn': (int, None), 'inact': (int, None),
             'expire': (int, None), 'flag': (int, None)}
    
    # Seed data with defaults if needed
    if data is None: data = {}
    if 'passwd' not in data: data['passwd'] = '!!'
    if 'lstchg' not in data: data['lstchg'] = None
    if 'min' not in data: data['min'] = None
    if 'max' not in data: data['max'] = None
    if 'warn' not in data: data['warn'] = None
    if 'inact' not in data: data['inact'] = None
    if 'expire' not in data: data['expire'] = None
    if 'flag' not in data: data['flag'] = None

    # Initialize!
    super(ShadowMapEntry, self).__init__(pkey, req_keys, types, data)

  def _VerifyAttr(self, attr):
    """Verify a single attribute, and return True or raise an exception."""
    super(ShadowMapEntry, self)._VerifyAttr(attr)
    value = self._data[attr]
    # Strings can not have ':' in them.
    if isinstance(value, str) and value.count(':') > 0:
      raise AttributeError('Colon in strings not allowed.', attr, value)

    return True
