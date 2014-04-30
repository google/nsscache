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

"""An implementation of a netgroup map for nsscache.

NetgroupMap:  An implementation of NSS netgroup maps based on the Map
class.

NetgroupMapEntry:  A netgroup map entry based on the MapEntry class.

Netgroup maps are somewhat different than the "typical"
passwd/group/shadow maps.  Instead of each entry having a fixed set of
fields, each entry has an arbitrarily long list containing a arbitrary
mix of other netgroup names or (host, user, domain) triples.

Given the choice between more complex design, or just sticking a list
of strings into each MapEntry class... the latter was chosen due to
it's combination of simplicity and effectiveness.

No provisioning is done in these classes to prevent infinite reference
loops, e.g. a NetgroupMapEntry naming itself as a member, or
unresolvable references.  No dereferencing is ever done in these
classes and datastores such as /etc/netgroup actually allow for those
and similar cases.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

from nss_cache.maps import maps


class NetgroupMap(maps.Map):
  """This class represents an NSS netgroup map.
  
  Map data is stored as a list of MapEntry objects, see the abstract
  class Map.
  """

  def __init__(self, iterable=None):
    """Construct a NetgroupMap object using optional iterable."""
    super(NetgroupMap, self).__init__(iterable)
    
  def Add(self, entry):
    """Add a new object, verify it is a NetgroupMapEntry object."""
    if not isinstance(entry, NetgroupMapEntry):
      raise TypeError
    return super(NetgroupMap, self).Add(entry)


class NetgroupMapEntry(maps.MapEntry):
  """This class represents NSS netgroup map entries.

  The entries attribute is a list containing an arbitray mix of either
  strings which are netgroup names, or tuples mapping to (host, user,
  domain) as per the definition of netgroups.  A None item in the
  tuple is the equivalent of a null pointer from getnetgrent(),
  specifically a wildcard.
  """
  __slots__ = ('name', 'entries')
  _KEY = 'name'
  _ATTRS = ('name', 'entries')

  def __init__(self, data=None):
    """Construct a NetgroupMapEntry."""
    self.name = None
    self.entries = None
    
    super(NetgroupMapEntry, self).__init__(data)

    # Seed data with defaults if needed
    if self.entries is None: self.entries = ''
