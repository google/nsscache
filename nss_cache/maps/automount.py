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

"""An implementation of an automount map for nsscache.

AutomountMap:  An implementation of NSS automount maps based on the Map
class.

AutomountMapEntry:  A automount map entry based on the MapEntry class.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

from nss_cache.maps import base


class AutomountMap(base.Map):
  """This class represents an NSS automount map.
  
  Map data is stored as a list of MapEntry objects, see the abstract
  class Map.
  """

  def __init__(self, iterable=None):
    """Construct a AutomountMap object using optional iterable."""
    super(AutomountMap, self).__init__(iterable)
    
  def Add(self, entry):
    """Add a new object, verify it is a AutomountMapEntry object."""
    if not isinstance(entry, AutomountMapEntry):
      raise TypeError
    return super(AutomountMap, self).Add(entry)


class AutomountMapEntry(base.MapEntry):
  """This class represents NSS automount map entries."""
  __slots__ = ('key', 'location', 'options')
  _KEY = 'key'
  _ATTRS = ('key', 'location', 'options')
  
  def __init__(self, data=None):
    """Construct a AutomountMapEntry."""
    self.key = None
    self.location = None
    self.options = None
    
    super(AutomountMapEntry, self).__init__(data)
    

