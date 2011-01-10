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
from nss_cache import maps

_cache_implementations = {}


def RegisterImplementation(cache_name, map_name, cache):
  """Register a Cache implementation with the CacheFactory.

  Child modules are expected to call this method in the file-level scope
  so that the CacheFactory is aware of them.

  Args:
    cache_name: (string) The name of the NSS backend.
    map_name: (string) The name of the map handled by this Cache.
    cache: A class type that is a subclass of Cache.

  Returns: Nothing
  """
  if cache_name not in _cache_implementations:
    _cache_implementations[cache_name] = {}
  _cache_implementations[cache_name][map_name] = cache


def Create(conf, map_name, automount_info=None):
  """Cache creation factory method.

  Args:
   conf: a dictionary of configuration key/value pairs, including one
   required attribute 'name'
   map_name: a string identifying the map name to handle
   automount_info: A string containing the automount mountpoint, used only
     by automount maps.

  Returns:
    an instance of a Cache

  Raises:
    RuntimeError: problem instantiating the requested cache
  """
  if not _cache_implementations:
    raise RuntimeError('no cache implementations exist')
  cache_name = conf['name']

  if cache_name not in _cache_implementations:
    raise RuntimeError('cache not implemented: %r' % (cache_name,))
  if map_name not in _cache_implementations[cache_name]:
    raise RuntimeError('map %r not supported by cache %r' % (map_name,
                                                             cache_name))

  return _cache_implementations[cache_name][map_name](
    conf, map_name, automount_info=automount_info)


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

  def __init__(self, conf, map_name, automount_info=None):
    """Initialise the Cache object.

    Args:
      conf: A dictionary of key/value pairs
      map_name: A string representation of the map type
      automount_info: A string containing the automount mountpoint, used only
        by automount maps.

    Raises:
      UnsupportedMap: for map types we don't know about
    """
    super(Cache, self).__init__()
    # Set up a logger for our children
    self.log = logging.getLogger(self.__class__.__name__)
    # Store config info
    self.conf = conf
    self.output_dir = conf.get('dir', '.')
    self.automount_info = automount_info
    self.map_name = map_name

    # Setup the map we may be asked to load our cache into.
    if map_name == config.MAP_PASSWORD:
      self.data = maps.PasswdMap()
    elif map_name == config.MAP_GROUP:
      self.data = maps.GroupMap()
    elif map_name == config.MAP_SHADOW:
      self.data = maps.ShadowMap()
    elif map_name == config.MAP_NETGROUP:
      self.data = maps.NetgroupMap()
    elif map_name == config.MAP_AUTOMOUNT:
      self.data = maps.AutomountMap()
    else:
      raise error.UnsupportedMap('Cache does not support %s' % map_name)

  def _Begin(self):
    """Start a write transaction."""
    try:
      (fd, self.cache_filename) = tempfile.mkstemp(prefix='nsscache',
                                                   dir=self.output_dir)
      self.cache_file = os.fdopen(fd, 'w+b')
      self.log.debug('opened temporary cache filename %r', self.cache_filename)
    except OSError, e:
      if e.errno == 13:
        self.log.info('Got OSError (%s) when trying to create temporary file',
                      e)
        raise error.PermissionDenied('OSError: ' + str(e))
      raise

  def _Rollback(self):
    """Rollback a write transaction."""
    self.log.debug('rolling back, deleting cache file %r', self.cache_filename)
    self.cache_file.close()
    os.unlink(self.cache_filename)

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
    if not self.cache_file.closed:
      self.cache_file.flush()
      os.fsync(self.cache_file.fileno())
      self.cache_file.close()
    else:
      self.log.debug('cache file was already closed before Commit')
    # We emulate the permissions of our source map to avoid bugs where
    # permissions may differ (usually w/shadow map)
    # Catch the case where the source file may not exist for some reason and
    # chose a sensible default.
    try:
      shutil.copymode(self.GetCompatFilename(), self.cache_filename)
    except OSError, e:
      if e.errno == errno.ENOENT:
        os.chmod(self.cache_filename,
                 stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
    self.log.debug('committing temporary cache file %r to %r',
                   self.cache_filename, self.GetCacheFilename())
    os.rename(self.cache_filename, self.GetCacheFilename())
    return True

  def GetCacheFilename(self):
    """Return the final destination pathname of the cache file."""
    return os.path.join(self.output_dir, self.CACHE_FILENAME)

  def GetMap(self, cache_info=None):
    """Returns the map from the cache.

    Must be implemented by the child class!

    Args:
      cache_info:  optional extra info used by the child class
    Raises:
      NotImplementedError:  We should have been implemented by child.
    """
    raise NotImplementedError('%s must implement this method!' %
                              self.__class__.__name__)

  def GetCompatFilename(self):
    """Return the filename where the normal (not-cache) map would be."""
    return os.path.join(self.output_dir, self.map_name)

  def GetMapLocation(self):
    """Return the location of the Map in this cache.

    This is used by automount maps so far, and must be implemented in the
    child class only if it is to support automount maps.

    Raises:
      NotImplementedError:  We should have been implemented by child.
    """
    raise NotImplementedError('%s must implement this method!' %
                              self.__class__.__name__)

  def WriteMap(self, map_data=None):
    """Write a map to disk.

    Args:
      map_data: optional Map object to overwrite our current data with.

    Returns:
      0 if succesful, 1 if not
    """
    if map_data is None:
      writable_map = self.data
    else:
      writable_map = map_data

    entries_written = self.Write(writable_map)
    # N.B. Write is destructive, len(writable_map) == 0 now.

    if entries_written is None:
      self.log.warn('cache write failed, exiting')
      return 1

    if self.Verify(entries_written):
      # TODO(jaq): in the future we should handle return codes from
      # Commit()
      self._Commit()
      return 0

    self.log.warn('verification failed, exiting')
    return 1
