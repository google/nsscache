# Copyright 2014 Google Inc.
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
"""An implementation of a sshkey map for nsscache.

SshkeyMap:  An implementation of NSS sshkey maps based on the Map
class.

SshkeyMapEntry:  A sshkey map entry based on the MapEntry class.
"""

__author__ = 'mimianddaniel@gmail.com'

from nss_cache.maps import maps


class SshkeyMap(maps.Map):
    """This class represents an NSS sshkey map.

    Map data is stored as a list of MapEntry objects, see the abstract
    class Map.
    """

    def Add(self, entry):
        """Add a new object, verify it is a SshkeyMapEntry instance.

        Args:
          entry: A SshkeyMapEntry instance.

        Returns:
          True if added successfully, False otherwise.

        Raises:
          TypeError: The argument is of the wrong type.
        """
        if not isinstance(entry, SshkeyMapEntry):
            raise TypeError
        return super(SshkeyMap, self).Add(entry)


class SshkeyMapEntry(maps.MapEntry):
    """This class represents NSS sshkey map entries."""
    # Using slots saves us over 2x memory on large maps.
    __slots__ = ('name', 'sshkey')
    _KEY = 'name'
    _ATTRS = ('name', 'sshkey')

    def __init__(self, data=None):
        """Construct a SshkeyMapEntry, setting reasonable defaults."""
        self.name = None
        self.sshkey = None

        super(SshkeyMapEntry, self).__init__(data)
        # Seed data with defaults if still empty
        if self.sshkey is None:
            self.sshkey = ''
