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
"""Base class of data source object for nss_cache."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import logging

from nss_cache import config
from nss_cache import error


class Source(object):
  """Abstract base class for map data sources."""

  def __init__(self, conf):
    """Initialise the Source object.

    Args:
      conf: A dictionary of key/value pairs.

    Raises:
      RuntimeError: object wasn't initialised with a dict
    """
    if not isinstance(conf, dict):
      raise RuntimeError('Source constructor not passed a dictionary')

    self.conf = conf

    # create a logger for our children
    self.log = logging.getLogger(self.__class__.__name__)

  def GetMap(self, map_name, since=None, location=None):
    """Get a specific map from this source.

    Args:
      map_name: A string representation of the map you want
      since: optional timestamp for incremental query
      location: optional field used by automounts to indicate a specific map

    Returns:
      A Map child class for the map requested.

    Raises:
      UnsupportedMap: for unknown source maps
    """
    if map_name == config.MAP_PASSWORD:
      return self.GetPasswdMap(since)
    elif map_name == config.MAP_SSHKEY:
      return self.GetSshkeyMap(since)
    elif map_name == config.MAP_GROUP:
      return self.GetGroupMap(since)
    elif map_name == config.MAP_SHADOW:
      return self.GetShadowMap(since)
    elif map_name == config.MAP_NETGROUP:
      return self.GetNetgroupMap(since)
    elif map_name == config.MAP_AUTOMOUNT:
      return self.GetAutomountMap(since, location=location)

    raise error.UnsupportedMap('Source can not fetch %s' % map_name)

  def GetAutomountMap(self, since=None, location=None):
    """Get an automount map from this source."""
    raise NotImplementedError

  def GetAutomountMasterMap(self):
    """Get an automount map from this source."""
    raise NotImplementedError

  def Verify(self):
    """Perform verification of the source availability.

    Attempt to open/connect or otherwise use the data source, and report if
    there are any problems.
    """
    raise NotImplementedError


class FileSource(object):
  """Abstract base class for file data sources."""

  def __init__(self, conf):
    """Initialise the Source object.

    Args:
      conf: A dictionary of key/value pairs.

    Raises:
      RuntimeError: object wasn't initialised with a dict
    """
    if not isinstance(conf, dict):
      raise RuntimeError('Source constructor not passed a dictionary')

    self.conf = conf

    # create a logger for our children
    self.log = logging.getLogger(self.__class__.__name__)

  def GetFile(self, map_name, dst_file, current_file, location=None):
    """Retrieve a file from this source.

    Args:
      map_name: A string representation of the map whose file you want
      dst_file: Temporary filename to write to.
      current_file: Path to the current cache.
      location: optional field used by automounts to indicate a specific map

    Returns:
      path to new file

    Raises:
      UnsupportedMap: for unknown source maps
    """
    if map_name == config.MAP_PASSWORD:
      return self.GetPasswdFile(dst_file, current_file)
    elif map_name == config.MAP_GROUP:
      return self.GetGroupFile(dst_file, current_file)
    elif map_name == config.MAP_SHADOW:
      return self.GetShadowFile(dst_file, current_file)
    elif map_name == config.MAP_NETGROUP:
      return self.GetNetgroupFile(dst_file, current_file)
    elif map_name == config.MAP_AUTOMOUNT:
      return self.GetAutomountFile(dst_file, current_file, location=location)

    raise error.UnsupportedMap('Source can not fetch %s' % map_name)
