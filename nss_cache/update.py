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

"""Update class, used for manipulating source and cache data."""

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)')

import calendar
import logging
import os
import stat
import tempfile
import time

from nss_cache import caches
from nss_cache import error


class Updater(object):
  """Base class used for all the update logic.

  It holds all the timestamp manipulation, as well as forcing the child
  classes to implement the public methods.
  """
  MODIFY_SUFFIX = '-modify'
  UPDATE_SUFFIX = '-update'

  def __init__(self, map_name, timestamp_dir, cache_options,
               automount_info=None):
    super(Updater, self).__init__()
    
    # Set up a logger
    self.log = logging.getLogger(self.__class__.__name__)
    # Used to fetch the right maps later on
    self.map_name = map_name
    # Used for tempfile writing
    self.timestamp_dir = timestamp_dir
    # Used to create cache(s)
    self.cache_options = cache_options
    
    # Calculate our timestamp files
    if automount_info is None:
      timestamp_prefix = '%s/timestamp-%s' % (timestamp_dir, map_name)
    else:
      # turn /auto into auto.auto, and /usr/local into /auto.usr_local
      automount_info = automount_info.lstrip('/')
      automount_info = automount_info.replace('/','_')
      timestamp_prefix = '%s/timestamp-%s-%s' % (timestamp_dir, map_name,
                                                 automount_info)
    self.modify_file = '%s-modify' % timestamp_prefix
    self.update_file = '%s-update' % timestamp_prefix

  def _ReadTimestamp(self, filename):
    """Return the named timestamp for this map.

    The timestamp file format is a single line, containing a string in the
    ISO-8601 format YYYY-MM-DDThh:mm:ssZ (i.e. UTC time).  We do not support
    all ISO-8601 formats for reasons of convenience in the code.

    Timestamps internal to nss_cache deliberately do not carry milliseconds.
     
    Args:
      filename:  the name of the file to read a timestamp from

    Returns:
      number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    if not os.path.exists(filename):
      return None

    try:
      timestamp_file = open(filename, 'r')
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
                       filename, e)
        timestamp = None
    else:
      timestamp = None

    if timestamp > time.time():
      self.log.warn('timestamp %r from %r is in the future.',
                    timestamp_string, filename)

    self.log.debug('read timestamp %s from file %r',
                   timestamp_string, filename)
    return timestamp

  def _WriteTimestamp(self, timestamp, filename):
    """Write the current time as the time of last update.

    Args:
      timestamp: nss_cache internal timestamp format, aka time_t
      filename: name of the file to write to.

    Returns:
       Boolean indicating success of write
    """
    (filedesc, temp_filename) = tempfile.mkstemp(prefix='nsscache',
                                                 dir=self.timestamp_dir)

    time_string = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                time.gmtime(timestamp))
    try:
      os.write(filedesc, '%s\n' % time_string)
      os.close(filedesc)
    except OSError:
      os.unlink(temp_filename)
      self.log.warn('writing timestamp failed!')
      return False

    os.chmod(temp_filename, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
    os.rename(temp_filename, filename)
    self.log.debug('wrote timestamp %s to file %r',
                   time_string, filename)
    return True

  def GetUpdateTimestamp(self):
    """Return the timestamp of the last cache update.
    
    Args: None

    Returns:
      number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    return self._ReadTimestamp(self.update_file)

  def GetModifyTimestamp(self):
    """Return the timestamp of the last cache modification.

    Args: None

    Returns:
      number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    return self._ReadTimestamp(self.modify_file)

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
    return self._WriteTimestamp(update_timestamp, self.update_file)

  def WriteModifyTimestamp(self, timestamp):
    """Convenience method for writing the last modify timestamp."""
    return self._WriteTimestamp(timestamp, self.modify_file)

  def UpdateFromSource(self, source, incremental=True, force_write=False):
    """Raise an exception if the child class fails to implement."""
    raise NotImplementedError


class SingleMapUpdater(Updater):
  """Updates simple maps like passwd, group, shadow, and netgroup."""

  def UpdateFromSource(self, source, incremental=True, force_write=False):
    """Update this map's cache from the source provided.

    The SingleMapUpdater expects to fetch as single map from the source
    and write/merge it to disk.  We create a cache to write to, and then call
    UpdateCacheFromSource() with that cache.

    Note that AutomountUpdater also calls UpdateCacheFromSource() for each
    cache it is writing.

    Args:
      source: a nss_cache.sources.Source
      incremental: a boolean flag indicating that an incremental update
        should be performed
      force_write: a boolean flag forcing empty map updates

    Returns:
      Integer indicating success of update (0 == good, fail otherwise)
    """
    # Create the single cache we write to:
    cache = caches.base.Create(self.cache_options, self.map_name)

    return self.UpdateCacheFromSource(cache, source, incremental,
                                      force_write, location=None)

  def UpdateCacheFromSource(self, cache, source, incremental, force_write,
                            location):
    """Update a single cache, from a source.

    Args:
      source: a nss_cache.sources.Source
      incremental: a boolean flag indicating that an incremental update
        should be performed
      force_write: a boolean flag forcing empty map updates
      location: the optional location in the source of this map, used by
        automount to specify which automount map to get

    Returns:
      Integer indicating success of update (0 == good, fail otherwise)
    """
    return_val = 0
    
    timestamp = self.GetModifyTimestamp()
    if timestamp is None and incremental is True:
      self.log.info('Missing previous timestamp, defaulting to a full sync.')
      incremental = False

    if incremental:
      source_map = source.GetMap(self.map_name,
                                 since=timestamp,
                                 location=location)
      try:
        return_val += self.IncrementalUpdateFromMap(cache, source_map)
      except (error.CacheNotFound, error.EmptyMap):
        self.log.warning('Local cache is invalid, faulting to a full sync.')
        incremental = False

    # We don't use an if/else, because we give the incremental a chance to
    # fail through to a full sync.
    if not incremental:
      source_map = source.GetMap(self.map_name,
                                 location=location)
      return_val += self.FullUpdateFromMap(cache, source_map, force_write)

    return return_val

  def IncrementalUpdateFromMap(self, cache, new_map):
    """Merge a new map into the provided cache.

    Args:
      cache: a nss_cache.caches.Cache
      new_map: a nss_cache.maps.Map class

    Returns:
      Integer indicating success of update (0 == good, fail otherwise)

    Raises:
      EmptyMap: if no cache map to merge with
    """
    return_val = 0
    
    if len(new_map) is 0:
      self.log.info('Empty map on incremental update, skipping')
      return 0

    self.log.debug('loading cache map, may be slow for large maps.')
    cache_map = cache.GetMap()
    
    if len(cache_map) is 0:
      raise error.EmptyMap

    if cache_map.Merge(new_map):
      return_val += cache.WriteMap(map_data=cache_map)
      if return_val is 0:
        self.WriteModifyTimestamp(new_map.GetModifyTimestamp())
    else:
      self.WriteModifyTimestamp(new_map.GetModifyTimestamp())
      self.log.info('Nothing new merged, returning')

    # We did an update, even if nothing was written, so write our
    # update timestamp unless there is an error.
    if return_val is 0:
      self.WriteUpdateTimestamp()
      
    return return_val

  def FullUpdateFromMap(self, cache, new_map, force_write=False):
    """Write a new map into the provided cache (overwrites)."""
    return_val = 0
    
    if len(new_map) is 0 and not force_write:
      raise error.EmptyMap('Source map empty during full update, aborting. '
                           'Use --force-write to override.')
    
    return_val = cache.WriteMap(map_data=new_map)
    
    # We did an update, write our timestamps unless there is an error.
    if return_val is 0:
      self.WriteModifyTimestamp(new_map.GetModifyTimestamp())
      self.WriteUpdateTimestamp()

    return return_val


class AutomountUpdater(Updater):
  """Update an automount map.

  Automount maps are a unique case.  They are not a single set of map entries,
  they are a set of sets.  Updating automount maps require fetching the list
  of maps and updating each map as well as the list of maps.

  This class is written to re-use the individual update code in the
  SingleMapUpdater class."""

  def UpdateFromSource(self, source, incremental=True, force_write=False):
    """Update the automount master map, and every map it points to.

    We fetch a full copy of the master map everytime, and then uses the
    SingleMapUpdater to write each map the master map points to, as well
    as the master map itself.

    During this process, the master map will be modified.  It starts
    out pointing to other maps in the source, but when written it needs
    to point to other maps in the cache instead.  For example, using ldap we
    store this data in ldap:

    map_entry.key = /auto
    map_entry.location = ou=auto.auto,ou=automounts,dc=example,dc=com

    We need to go back to ldap get the map in ou=auto.auto, but when it comes
    time to write the master map to (for example) a file, we need to write
    out the /etc/auto.master file with:

    map_entry.key = /auto
    map_entry.location = /etc/auto.auto

    This is annoying :)  Since the keys are fixed, namely /auto is a mountpoint
    that isn't going to change format, we expect each Cache implementation that
    supports automount maps to support a GetMapLocation() method which returns
    the correct cache location from the key.
        
    Args:
      source: a nss_cache.sources.Source
      incremental: a boolean flag indicating that an incremental update
      should be performed
      force_write: a boolean flag forcing empty map updates

    Returns:
      Integer indicating success of update (0 == good, fail otherwise)
    """
    return_val = 0
    
    self.log.info('Retrieving automount master map.')
    master_map = source.GetAutomountMasterMap()

    # update specific maps, e.g. auto.home and auto.auto
    for map_entry in master_map:
      
      source_location = map_entry.location  # e.g. ou=auto.auto in ldap
      automount_info = map_entry.key  # e.g. /auto mountpoint
      self.log.info('Updating %s mount.', automount_info)
      
      # create the cache to update
      cache = caches.base.Create(self.cache_options,
                                 self.map_name,
                                 automount_info=automount_info)
      
      # update the master map with the location of the map in the cache
      # e.g. /etc/auto.auto replaces ou=auto.auto
      map_entry.location = cache.GetMapLocation()

      # update this map (e.g. /etc/auto.auto)
      updater = SingleMapUpdater(self.map_name,
                                 self.timestamp_dir,
                                 self.cache_options,
                                 automount_info=automount_info)
      return_val += updater.UpdateCacheFromSource(cache, source, incremental,
                                                  force_write, source_location)
    # with sub-maps updated, write modified master map to disk
    cache = caches.base.Create(self.cache_options,
                               self.map_name,
                               automount_info=None)  # None defaults to master
    updater = SingleMapUpdater(self.map_name,
                               self.timestamp_dir,
                               self.cache_options)
    return_val += updater.FullUpdateFromMap(cache, master_map)

    return return_val
