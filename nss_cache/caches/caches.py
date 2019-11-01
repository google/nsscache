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
"""Base class of cache for nsscache."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import errno
import logging
import os
import shutil
import stat
import tempfile

from nss_cache import config
from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import netgroup
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.maps import sshkey


class Cache(object):
  """Abstract base class for Caches.

  The Cache object represents the cache used by NSS, that we plan on
  writing the NSS data to -- it is the cache that we up date so that
  the NSS module has a place to retrieve data from.  Typically a cache
  is some form of on-disk local storage.

  You can manipulate a cache directly, like asking for a Map object from
  it, or giving it a Map to write out to disk.  There is an Updater class
  which holds the logic for taking data from Source objects and merging them
  with Cache objects.

  It is important to note that a new Cache is instantiated for each
  'map' defined in the configuration -- allowing different Cache
  storages for different NSS maps, instead of one Cache to hold them all
  (and in the darkness bind them).
  """

  def __init__(self, conf, map_name, automount_mountpoint=None):
    """Initialise the Cache object.

    Args:
      conf: A dictionary of key/value pairs
      map_name: A string representation of the map type
      automount_mountpoint: A string containing the automount mountpoint,
        used only by automount maps.

    Raises:
      UnsupportedMap: for map types we don't know about
    """
    super(Cache, self).__init__()
    # Set up a logger for our children
    self.log = logging.getLogger(self.__class__.__name__)
    # Store config info
    self.conf = conf
    self.output_dir = conf.get('dir', '.')
    self.automount_mountpoint = automount_mountpoint
    self.map_name = map_name

    # Setup the map we may be asked to load our cache into.
    if map_name == config.MAP_PASSWORD:
      self.data = passwd.PasswdMap()
    elif map_name == config.MAP_SSHKEY:
      self.data = sshkey.SshkeyMap()
    elif map_name == config.MAP_GROUP:
      self.data = group.GroupMap()
    elif map_name == config.MAP_SHADOW:
      self.data = shadow.ShadowMap()
    elif map_name == config.MAP_NETGROUP:
      self.data = netgroup.NetgroupMap()
    elif map_name == config.MAP_AUTOMOUNT:
      self.data = automount.AutomountMap()
    else:
      raise error.UnsupportedMap('Cache does not support %s' % map_name)

  def _Begin(self):
    """Start a write transaction."""
    self.log.debug('Output dir: %s', self.output_dir)
    self.log.debug('CWD: %s', os.getcwd())
    try:
      self.temp_cache_file = tempfile.NamedTemporaryFile(
        delete=False,
          prefix='nsscache-cache-file-',
          dir=os.path.join(os.getcwd(), self.output_dir))
      self.temp_cache_filename = self.temp_cache_file.name
      self.log.debug('opened temporary cache filename %r',
                     self.temp_cache_filename)
    except OSError as e:
      if e.errno == errno.EACCES:
        self.log.info('Got OSError (%s) when trying to create temporary file',
                      e)
        raise error.PermissionDenied('OSError: ' + str(e))
      raise

  def _Rollback(self):
    """Rollback a write transaction."""
    self.log.debug('rolling back, deleting temp cache file %r',
                   self.temp_cache_filename)
    self.temp_cache_file.close()
    # Safe file remove (ignore "no such file or directory" errors):
    try:
      os.remove(self.temp_cache_filename)
    except OSError as e:
      if e.errno != errno.ENOENT:  # errno.ENOENT = no such file or directory
        raise  # re-raise exception if a different error occured

  def _Commit(self):
    """Ensure the cache is now the active data source for NSS.

    Perform an atomic rename on the cache file to the location
    expected by the NSS module.  No verification of database validity
    or consistency is performed here.

    Returns:
      Always returns True
    """
    # TODO(jaq): if self WriteModifyTimestamp() fails below, we still have a
    # new cache, but we might instead want to reserve the space on
    # disk for a timestamp first -- thus needing a write/commit pair
    # of functions for a timestamp.  Edge case, so not bothering for now.
    if not self.temp_cache_file.closed:
      self.temp_cache_file.flush()
      os.fsync(self.temp_cache_file.fileno())
      self.temp_cache_file.close()
    else:
      self.log.debug('temp cache file was already closed before Commit')
    # We emulate the permissions of our source map to avoid bugs where
    # permissions may differ (usually w/shadow map)
    # Catch the case where the source file may not exist for some reason and
    # chose a sensible default.
    try:
      shutil.copymode(self.GetCompatFilename(), self.temp_cache_filename)
      stat_info = os.stat(self.GetCompatFilename())
      uid = stat_info.st_uid
      gid = stat_info.st_gid
      os.chown(self.temp_cache_filename, uid, gid)
    except OSError as e:
      if e.errno == errno.ENOENT:
        if self.map_name == 'sshkey':
          os.chmod(self.temp_cache_filename,
                   stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        else:
          os.chmod(self.temp_cache_filename,
                   stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    self.log.debug('committing temporary cache file %r to %r',
                   self.temp_cache_filename, self.GetCacheFilename())
    os.rename(self.temp_cache_filename, self.GetCacheFilename())
    return True

  def GetCacheFilename(self):
    """Return the final destination pathname of the cache file."""
    return os.path.join(self.output_dir, self.CACHE_FILENAME)

  def GetCompatFilename(self):
    """Return the filename where the normal (not-cache) map would be."""
    # TODO(jaq): Probably shouldn't hard code '/etc' here.
    return os.path.join('/etc', self.map_name)

  def GetMap(self, cache_filename=None):
    """Returns the map from the cache.

    Must be implemented by the child class!

    Args:
      cache_filename:  optional extra info used by the child class

    Raises:
      NotImplementedError:  We should have been implemented by child.
    """
    raise NotImplementedError(
        '%s must implement this method!' % self.__class__.__name__)

  def GetMapLocation(self):
    """Return the location of the Map in this cache.

    This is used by automount maps so far, and must be implemented in the
    child class only if it is to support automount maps.

    Raises:
      NotImplementedError:  We should have been implemented by child.
    """
    raise NotImplementedError(
        '%s must implement this method!' % self.__class__.__name__)

  def WriteMap(self, map_data=None, force_write=False):
    """Write a map to disk.

    Args:
      map_data: optional Map object to overwrite our current data with.
      force_write: optional flag to indicate verification checks can be
        ignored.

    Returns:
      0 if succesful, 1 if not
    """
    if map_data is None:
      writable_map = self.data
    else:
      writable_map = map_data

    entries_written = self.Write(writable_map)

    # N.B. Write is destructive, len(writable_map) == 0 now.
    # Asserting this isn't good for the unit tests, though.
    #assert 0 == len(writable_map), "self.Write should be destructive."

    if entries_written is None:
      self.log.warning('cache write failed, exiting')
      return 1

    if force_write or self.Verify(entries_written):
      # TODO(jaq): in the future we should handle return codes from
      # Commit()
      self._Commit()
      # Create an index for this map.
      self.WriteIndex()
      return 0

    self.log.warning('verification failed, exiting')
    return 1

  def WriteIndex(self):
    """Build an index for this cache.

    No-op, but child classes may override this.
    """
    pass

  def Write(self, writable_map):
    raise NotImplementedError

  def Verify(self, entries_written):
    raise NotImplementedError
