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

  In addition, each set of mapentries has a mountpoint such as /home
  or /auto, and a location the filesystems are listed such as /etc/auto.home
  or ldap:ldap.example.com:ou=auto.home,ou=automounts,dc=example,dc=com
  so the Map itself has attributes to store these.

  Specifically, Map.GetMountpoint() for the mountpoint (e.g. /home) and
  Map.GetFilesystemLocation() for the filesystem list location.
  """

  def __init__(self, iterable=None):
    """Construct a AutomountMap object using optional iterable."""
    super(AutomountMap, self).__init__(iterable)
    self._mountpoint = None
    self._filesystem_location = None
    
  def Add(self, entry):
    """Add a new object, verify it is a AutomountMapEntry object."""
    if not isinstance(entry, AutomountMapEntry):
      raise TypeError
    return super(AutomountMap, self).Add(entry)

  def GetMountpoint(self):
    """Return the parent mountpoint for the automount MapEntry objects."""
    return self._mountpoint

  def SetMountpoint(self, value):
    """Set the mountpoint for the automount MapEntry objects."""
    if value is None or isinstance(value, str):
      self._mountpoint = value
    else:
      raise TypeError('mountpoint can only be str or None, not %r', value)

  def GetFilesystemLocation(self):
    """Return the location of the filesystem list."""
    return self._filesystem_location

  def SetFilesystemLocation(self, value):
    """Set the location of the filesystem list."""
    if value is None or isinstance(value, str):
      self._filesystem_location = value
    else:
      raise TypeError('filesystem location can only be str or None, not %r',
                      value)


class AutomountMapEntry(base.MapEntry):
  """This class represents NSS automount map entries.
  
  Entries are internally a dict, see the abstract class MapEntry.
  """

  def __init__(self, data=None):
    """Construct a AutomountMapEntry."""

    # Primary key for this MapEntry is name
    pkey = 'key'
    # Required keys, e.g. no reasonble defaults.
    req_keys = ('key', 'location')
    # All keys and their expected types.
    types = {'key': str, 'options': (str, None), 'location': str}

    # Seed data with defaults if needed
    if data is None: data = {}
    if 'options' not in data: data['options'] = None
    
    super(AutomountMapEntry, self).__init__(pkey, req_keys, types, data)
