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

"""Base class of cache for nsscache."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import calendar
import logging
import os
import stat
import tempfile
import time

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


def Create(config, map_name):
  """Cache creation factory method.

  Args:
   config: a dictionary of configuration key/value pairs, including one
           required attribute 'name'
   map_name: a string identifying the map name to handle

  Returns:
    an instance of a Cache

  Raises:
    RuntimeError: problem instantiating the requested cache
  """
  if not _cache_implementations:
    raise RuntimeError('no cache implementations exist')

  cache_name = config['name']

  if cache_name not in _cache_implementations:
    raise RuntimeError('cache not implemented: %r' % (cache_name,))
  if map_name not in _cache_implementations[cache_name]:
    raise RuntimeError('map %r not supported by cache %r' % (map_name,
                                                             cache_name))

  return _cache_implementations[cache_name][map_name](config)


class Cache(object):
  """Abstract base class for Caches.

  The Cache object represents the cache used by NSS, that we plan on
  writing the NSS data to -- it is the cache that we up date so that
  the NSS module has a place to retrieve data from.  Typically an
  on-disk local storage, the Cache has has two important properties:
   * The map data stored in the cache
   * The timestamps associated with the cache

  It is important to note that Cache objects are not shared between
  Maps, even when more than one Map is defined to have the same Cache
  storage in the configuration.  A new Cache is instantiated for each
  'map' defined in the configuration -- allowing different Cache
  storages for different NSS maps.
  """

  def __init__(self, config):
    """Initialise the Cache object.

    Args:
      config: A dictionary of key/value pairs
    """
    super(Cache, self).__init__()
    # Set up a logger for our children
    self.log = logging.getLogger(self.__class__.__name__)
    self.config = config
    self.output_dir = config.get('dir', '.')
    self.timestamp_dir = config.get('timestamp_dir', self.output_dir)

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

  def GetUpdateTimestamp(self):
    """Return the timestamp of the last cache update.

    Args: None

    Returns:
      number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    return self._ReadTimestamp(self.UPDATE_TIMESTAMP_SUFFIX)

  def GetModifyTimestamp(self):
    """Return the timestamp of the last cache modification.

    Args: None

    Returns:
      number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    return self._ReadTimestamp(self.MODIFY_TIMESTAMP_SUFFIX)

  def _ReadTimestamp(self, timestamp_name):
    """Return the named timestamp for this map.

    The timestamp file format is a single line, containing a string in the
    ISO-8601 format YYYY-MM-DDThh:mm:ssZ (i.e. UTC time).  We do not support
    all ISO-8601 formats for reasons of convenience in the code.

    Timestamps internal to nss_cache deliberately do not carry milliseconds.

    Args:
      timestamp_name: the identifying name of this timestamp

    Returns:
      number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    timestamp_filename = os.path.join(self.timestamp_dir,
                                      self.CACHE_FILENAME + \
                                      '.' + timestamp_name)

    if not os.path.exists(timestamp_filename):
      return None

    try:
      timestamp_file = open(timestamp_filename, 'r')
      timestamp_string = timestamp_file.read().strip()
    except IOError, e:
      self.log.warn('error opening timestamp file: %s', e)
      timestamp_string = None
    else:
      timestamp_file.close()

    if timestamp_string is not None:
      try:
        timestamp = calendar.timegm(time.strptime(timestamp_string,
                                                  '%Y-%m-%dT%H:%M:%SZ'))
      except ValueError, e:
        self.log.error('cannot parse timestamp file %r: %s',
                       timestamp_filename, e)
        timestamp = None
    else:
      timestamp = None

    if timestamp > time.time():
      self.log.warn('timestamp %r from %r is in the future.',
                    timestamp_string, timestamp_filename)

    self.log.debug('read timestamp %s from file %r',
                   timestamp_string, timestamp_filename)
    return timestamp

  def _WriteTimestamp(self, timestamp, timestamp_name):
    """Write the current time as the time of last update.

    Args:
     timestamp: nss_cache internal timestamp format, aka time_t
     timestamp_name: suffix of filename for identifying timestamp

    Returns:
      Boolean indicating success of write
    """
    (timestamp_filedesc, temp_timestamp_filename) =\
                         tempfile.mkstemp(prefix='nsscache',
                                          dir=self.timestamp_dir)

    timestamp_string = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                     time.gmtime(timestamp))
    try:
      os.write(timestamp_filedesc, '%s\n' % timestamp_string)
      os.close(timestamp_filedesc)
    except OSError:
      os.unlink(temp_timestamp_filename)
      self.log.warn('writing timestamp failed!')
      return False

    os.chmod(temp_timestamp_filename,
             stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
    timestamp_filename = os.path.join(self.timestamp_dir,
                                      self.CACHE_FILENAME +\
                                      '.' + timestamp_name)
    os.rename(temp_timestamp_filename, timestamp_filename)
    self.log.debug('wrote timestamp %s to file %r',
                   timestamp_string, timestamp_filename)
    return True

  def WriteUpdateTimestamp(self, update_timestamp=None):
    """Convenience method for writing the last update timestamp.

    Args:
      update_timestamp: nss_cache internal timestamp format, aka time_t
                        defaulting to the current time if not specified

    Returns:
      boolean indicating success of write.
    """
    if update_timestamp is None:
      update_timestamp = int(time.time())
    return self._WriteTimestamp(update_timestamp, self.UPDATE_TIMESTAMP_SUFFIX)

  def WriteModifyTimestamp(self, timestamp):
    """Convenience method for writing the last modify timestamp."""
    return self._WriteTimestamp(timestamp, self.MODIFY_TIMESTAMP_SUFFIX)

  def Update(self, source, incremental=True, force_write=False):
    """Update this map's cache from the source provided.

    Args:
     source: a nss_cache.sources.Source
     incremental: a boolean flag indicating that an incremental update
      should be performed
     force_write: a boolean flag indicating that safety checks should be ignored

    Returns:
      Integer indicating success of update (0 == good, fail otherwise)

    Raises:
      EmptyMap: An empty map was unexpectedly returned from the source.
    """
    return_val = 0

    if incremental:
      timestamp = self.GetModifyTimestamp()
    else:
      timestamp = None

    # Query our source right away, if we have no new data we can quickly exit.
    source_map = self.GetSourceMap(source, since=timestamp)
    if incremental:
      if len(source_map) == 0:
        self.log.info('Fetched empty map during incremental update, '
                      'doing nothing.')
        return return_val
      try:
        self.log.debug('loading cache map, may be slow for large maps.')
        cache_map = self.GetCacheMap()

        if len(cache_map) == 0:
          raise error.EmptyMap

      except (error.CacheNotFound, error.EmptyMap):
        self.log.warning('Local cache is invalid, faulting to a full sync.')
        incremental = False
        timestamp = None

    if len(source_map) == 0 and not force_write:
      # We should not get here during incremental updates, thus
      # we refuse to do full update on an empty source map.
      raise error.EmptyMap('Source map empty during full update, aborting. '
                           'Use --force-write to override this behaviour.')

    # Here we write out to disk.  Note that for purposes of saving memory on
    # large maps, the Write() call in _WriteMap() empties the cache_map object
    # as it writes, so len(source_map) == 0.
    if incremental:
      if cache_map.Merge(source_map):
        return_val = self._WriteMap(cache_map, source_map.GetModifyTimestamp())
      else:
        self.log.info('Nothing new merged, returning')
    else:
      # TODO(jaq): think about a way to remove the timestamp from source_map
      return_val = self._WriteMap(source_map, source_map.GetModifyTimestamp())

    # TODO(jaq): rename return_val into something like 'status_ok' and make
    # it a boolean
    if return_val == 0:
      self.WriteUpdateTimestamp()

    return return_val

  def _WriteMap(self, writable_map, new_modify_timestamp):
    """Write a map to disk."""

    entries_written = self.Write(writable_map)
    # N.B. Write is destructive, len(writable_map) == 0 now.
    
    if entries_written is None:
      self.log.warn('cache write failed, exiting')
      return 1
    
    if self.Verify(entries_written):
      # TODO(jaq): in the future we should handle return codes from
      # Commit()
      self._Commit(new_modify_timestamp)
      return 0

    self.log.warn('verification failed, exiting')
    return 1

  def _Commit(self, modify_timestamp):
    """Ensure the cache is now the active data source for NSS.

    Perform an atomic rename on the cache file to the location
    expected by the NSS module.  No verification of database validity
    or consistency is performed here.

    Args:
      modify_timestamp: nss_cache internal timestamp format, aka UNIX
      time_t.

    Returns:
      Always returns True
    """
    # TODO(jaq): if self WriteModifyTimestamp() fails below, we still have a
    # new cache, but we might instead want to reserve the space on
    # disk for a timestamp first -- thus needing a write/commit pair
    # of functions for a timestamp.  Edge case, so not bothering for now.
    self.cache_file.close()
    os.chmod(self.cache_filename,
             stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
    self.log.debug('committing temporary cache file %r to %r',
                   self.cache_filename, self._GetCacheFilename())
    os.rename(self.cache_filename, self._GetCacheFilename())
    self.WriteModifyTimestamp(modify_timestamp)
    return True

  def _GetCacheFilename(self):
    """Return the final destination pathname of the cache file."""
    return os.path.join(self.output_dir, self.CACHE_FILENAME)


class PasswdMapMixin(object):
  """Mixin class for PasswdMap handler objects.

  This mixin class provides the common method GetMap for derivatives
  of CacheMapHandler, specifically for PasswdMap handlers.
  """

  def GetMap(self):
    """Return an empty PasswdMap."""
    return maps.PasswdMap()

  def GetSourceMap(self, source, since):
    """Return the PasswdMap from this source.

    Args:
     source: a subclass of Source
     since: timestamp of the last update

    Returns:
      a PasswdMap
    """
    return source.GetPasswdMap(since)


class GroupMapMixin(object):
  """Mixin class for GroupMap handler objects.

  This mixin class provides the common method GetMap for derivatives
  of CacheMapHandler, specifically for GroupMap handlers.
  """

  def GetMap(self):
    """Return an empty GroupMap."""
    return maps.GroupMap()

  def GetSourceMap(self, source, since):
    """Return the GroupMap from this source.

    Args:
     source: An instance of a Source
     since: Timestamp of the last update

    Returns:
      a GroupMap
    """
    return source.GetGroupMap(since)


class ShadowMapMixin(object):
  """Mixin class for ShadowMap handler objects.

  This mixin class provides the common method GetMap for derivatives
  of CacheMapHandler, specifically for ShadowMap handlers.
  """

  def GetMap(self):
    """Return an empty ShadowMap."""
    return maps.ShadowMap()

  def GetSourceMap(self, source, since):
    """Return the ShadowMap from this source.

    Args:
     source: An instance of a Source
     since: Timestamp of the last update

    Returns:
      a ShadowMap
    """
    return source.GetShadowMap(since)


class NetgroupMapMixin(object):
  """Mixin class for NetgroupMap handler objects.

  This mixin class provides the common method GetMap for derivatives
  of CacheMapHandler, specifically for NetgroupMap handlers.
  """

  def GetMap(self):
    """Return an empty NetgroupMap."""
    return maps.NetgroupMap()

  def GetSourceMap(self, source, since):
    """Return the NetgroupMap from this source.

    Args:
     source: An instance of a Source
     since: Timestamp of the last update

    Returns:
      a NetgroupMap
    """
    return source.GetNetgroupMap(since)


class AutomountMapMixin(object):
  """Mixin class for AutomountMap handler objects.

  This mixin class provides the common method GetMap for derivatives
  of CacheMapHandler, specifically for AutomountMap handlers.
  """

  def GetMap(self):
    """Return an empty AutomountMap."""
    return maps.AutomountMap()
