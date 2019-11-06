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

from nss_cache.maps import maps


class ShadowMap(maps.Map):
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


class ShadowMapEntry(maps.MapEntry):
    """This class represents NSS shadow map entries."""
    __slots__ = ('name', 'passwd', 'lstchg', 'min', 'max', 'warn', 'inact',
                 'expire', 'flag')
    _KEY = 'name'
    _ATTRS = ('name', 'passwd', 'lstchg', 'min', 'max', 'warn', 'inact',
              'expire', 'flag')

    def __init__(self, data=None):
        """Construct a ShadowMapEntry, setting reasonable defaults."""
        self.name = None
        self.passwd = None
        self.lstchg = None
        self.min = None
        self.max = None
        self.warn = None
        self.inact = None
        self.expire = None
        self.flag = None

        super(ShadowMapEntry, self).__init__(data)

        # Seed data with defaults if needed
        if self.passwd is None:
            self.passwd = '!!'
