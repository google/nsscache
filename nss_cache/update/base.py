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

"""Update class, used for manipulating source and cache data.

These classes contains all the business logic for updating cache objects.
They also contain the code for reading, writing, and updating timestamps.

Updater:  Base class with setup and timestamp code.
SingleMapUpdater:  Class used for all single map caches.
AutomountMapUpdater:  Class used for updating automount map caches.
"""

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)')

import logging
import os
import stat
import tempfile
import time

from nss_cache import caches
from nss_cache import error


class Updater(object):
  """Base class which holds the setup and timestamp logic.

  This class holds all the timestamp manipulation used by child classes and
  callers.

  Attributes:
    log: logging.Logger instance used for output.
    map_name: A string representing the type of the map we are an Updater for.
    timestamp_dir: A string with the directory containing our timestamp files.
    cache_options: A dict containing the options for any caches we create.
    modify_file: A string with our last modified timestamp filename.
    update_file: A string with our last updated timestamp filename.
  """

  def __init__(self, map_name, timestamp_dir, cache_options,
               automount_info=None):
    """Construct an updater object.

    Args:
      map_name: A string representing the type of the map we are an Updater for.
      timestamp_dir: A string with the directory containing our timestamp files.
      cache_options: A dict containing the options for any caches we create.
      automount_info: An optional string containing automount path info.
    """
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
      automount_info = automount_info.replace('/', '_')
      timestamp_prefix = '%s/timestamp-%s-%s' % (timestamp_dir, map_name,
                                                 automount_info)
    self.modify_file = '%s-modify' % timestamp_prefix
    self.update_file = '%s-update' % timestamp_prefix

    # Timestamp info is cached here
    self.modify_time = None
    self.update_time = None

  def _ReadTimestamp(self, filename):
    """Return a timestamp from a file.

    The timestamp file format is a single line, containing a string in the
    ISO-8601 format YYYY-MM-DDThh:mm:ssZ (i.e. UTC time).  We do not support
    all ISO-8601 formats for reasons of convenience in the code.

    Timestamps internal to nss_cache deliberately do not carry milliseconds.

    Args:
      filename:  A String naming the file to read from.

    Returns:
      A time.struct_time, or None if the timestamp file doesn't
      exist or has errors.
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
        # Append UTC to force the timezone to parse the string in.
        timestamp = time.strptime(timestamp_string + ' UTC',
                                  '%Y-%m-%dT%H:%M:%SZ %Z')
      except ValueError, e:
        self.log.error('cannot parse timestamp file %r: %s',
                       filename, e)
        timestamp = None
    else:
      timestamp = None

    if timestamp > time.gmtime():
      self.log.warn('timestamp %r from %r is in the future.',
                    timestamp_string, filename)

    self.log.debug('read timestamp %s from file %r',
                   timestamp_string, filename)
    return timestamp

  def _WriteTimestamp(self, timestamp, filename):
    """Write a given timestamp out to a file, converting to the ISO-8601 format.

    We convert internal timestamp format (epoch) to ISO-8601 format, i.e.
    YYYY-MM-DDThh:mm:ssZ which is basically UTC time, then write it out to a
    file.

    Args:
      timestamp: A String in nss_cache internal timestamp format, aka time_t.
      filename: A String naming the file to write to.

    Returns:
       A boolean indicating success of write.
    """
    (filedesc, temp_filename) = tempfile.mkstemp(prefix='nsscache',
                                                 dir=self.timestamp_dir)

    time_string = time.strftime('%Y-%m-%dT%H:%M:%SZ', timestamp)

    try:
      os.write(filedesc, '%s\n' % time_string)
      os.fsync(filedesc)
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

    Returns:
      An int with the number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    if self.update_time is None:
      self.update_time = self._ReadTimestamp(self.update_file)
    return self.update_time

  def GetModifyTimestamp(self):
    """Return the timestamp of the last cache modification.

    Args: None

    Returns:
      An int with the number of seconds since epoch, or None if the timestamp
      file doesn't exist or has errors.
    """
    if self.modify_time is None:
      self.modify_time = self._ReadTimestamp(self.modify_file)
    return self.modify_time

  def WriteUpdateTimestamp(self, update_timestamp=None):
    """Convenience method for writing the last update timestamp.

    Args:
      update_timestamp: An int with the number of seconds since epoch,
        defaulting to the current time if None.

    Returns:
      A boolean indicating success of the write.
    """
    # blow away our cached value
    self.update_time = None

    # default to now
    if update_timestamp is None:
      update_timestamp = time.gmtime()
    return self._WriteTimestamp(update_timestamp, self.update_file)

  def WriteModifyTimestamp(self, timestamp):
    """Convenience method for writing the last modify timestamp.

    Args:
      timestamp:  An int with the number of seconds since epoch.

    Returns:
      A boolean indicating success of the write.
    """
    # blow away our cached value
    self.modify_time = None

    return self._WriteTimestamp(timestamp, self.modify_file)

  def UpdateFromSource(self, source, incremental=True, force_write=False):
    """Raise an exception if the child class fails to implement.

    The implementation should fetch the appropriate data for a given map (as
    specified self.map_name) from the source object and create or update the
    local cache copy of that data.

    Args:
      source: A sources.Source instance to update from.
      incremental: A boolean where True is an incremental update, defaults to
        True.
      force_write: A boolean causing emtpy maps to be written on update when
        True, defaults to False.

    Raises:
      NotImplementedError: A child class fails to define this method.
    """
    raise NotImplementedError


class SingleMapUpdater(Updater):
  """Updates simple maps like passwd, group, shadow, and netgroup."""

  def UpdateFromSource(self, source, incremental=True, force_write=False):
    """Update this map's cache from the source provided.

    The SingleMapUpdater expects to fetch as single map from the source
    and write/merge it to disk.  We create a cache to write to, and then call
    UpdateCacheFromSource() with that cache.

    Note that AutomountUpdater also calls UpdateCacheFromSource() for each
    cache it is writing, hence the distinct seperation.

    Args:
      source: A nss_cache.sources.Source object.
      incremental: A boolean flag indicating that an incremental update should
        be performed, defaults to True.
      force_write: A boolean flag forcing empty map updates, defaults to False.

    Returns:
      An int indicating success of update (0 == good, fail otherwise).
    """
    # Create the single cache we write to
    cache = caches.base.Create(self.cache_options, self.map_name)

    return self.UpdateCacheFromSource(cache, source, incremental,
                                      force_write, location=None)

  def UpdateCacheFromSource(self, cache, source, incremental, force_write,
                            location=None):
    """Update a single cache, from a given source.

    Args:
      cache: A nss_cache.caches.Cache object.
      source: A nss_cache.sources.Source object.
      incremental: A boolean flag indicating that an incremental update
        should be performed if True.
      force_write: A boolean flag forcing empty map updates if True.
      location: The optional location in the source of this map used by
        automount to specify which automount map to get, defaults to None.

    Returns:
      An int indicating the success of an update (0 == good, fail otherwise).
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
    """Merge a given map into the provided cache.

    Args:
      cache: A nss_cache.caches.Cache object.
      new_map: A nss_cache.maps.Map object.

    Returns:
      An int indicating the success of an update (0 == good, fail otherwise).

    Raises:
      EmptyMap: We're trying to merge into cache with an emtpy map.
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
    """Write a new map into the provided cache (overwrites).

    Args:
      cache: A nss_cache.caches.Cache object.
      new_map: A nss_cache.maps.Map object.
      force_write: A boolean indicating empty maps are okay to write, defaults
        to False which means do not write them.

    Returns:
      0 if succesful, non-zero indicating number of failures otherwise.

    Raises:
      EmptyMap: Update is an empty map, not raised if force_write=True.
    """
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
  SingleMapUpdater class.
  """

  # automount-specific options
  OPT_LOCAL_MASTER = 'local_automount_master'

  def __init__(self, map_name, timestamp_dir, cache_options,
               automount_info=None):
    """Initialize automount-specific updater options.

    Args:
      map_name: A string representing the type of the map we are an Updater for.
      timestamp_dir: A string with the directory containing our timestamp files.
      cache_options: A dict containing the options for any caches we create.
      automount_info: An optional string containing automount path info.
    """
    super(AutomountUpdater, self).__init__(map_name, timestamp_dir,
                                           cache_options, automount_info)
    self.local_master = False
    if self.OPT_LOCAL_MASTER in cache_options:
      if cache_options[self.OPT_LOCAL_MASTER] == 'yes':
        self.local_master = True

  def UpdateFromSource(self, source, incremental=True, force_write=False):
    """Update the automount master map, and every map it points to.

    We fetch a full copy of the master map everytime, and then use the
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
      source: An nss_cache.sources.Source object.
      incremental: A boolean flag indicating that an incremental update
        should be performed when True, defaults to True.
      force_write: A boolean flag forcing empty map updates when False,
        defaults to False.

    Returns:
      An int indicating success of update (0 == good, fail otherwise).
    """
    return_val = 0

    self.log.info('Retrieving automount master map.')
    master_map = source.GetAutomountMasterMap()

    if self.local_master:
      self.log.info('Using local master map to determine maps to update.')
      # we need the local map to determine which of the other maps to update
      cache = caches.base.Create(self.cache_options, self.map_name,
                                 automount_mountpoint=None)
      try:
        local_master = cache.GetMap()
      except error.CacheNotFound:
        self.log.warning('Local master map specified but no map found! '
                         'No maps will update.')
        return return_val + 1

    # update specific maps, e.g. auto.home and auto.auto
    for map_entry in master_map:

      source_location = map_entry.location  # e.g. ou=auto.auto in ldap
      automount_info = map_entry.key        # e.g. /auto mountpoint
      self.log.debug('looking at %s mount.', automount_info)

      # create the cache to update
      cache = caches.base.Create(self.cache_options,
                                 self.map_name,
                                 automount_mountpoint=automount_info)

      # update the master map with the location of the map in the cache
      # e.g. /etc/auto.auto replaces ou=auto.auto
      map_entry.location = cache.GetMapLocation()

      # if configured to use the local master map, skip any not defined there
      if self.local_master:
        if map_entry not in local_master:
          self.log.debug('skipping %s, not in %s', map_entry, local_master)
          continue

      self.log.info('Updating %s mount.', map_entry.key)
      # update this map (e.g. /etc/auto.auto)
      updater = SingleMapUpdater(self.map_name,
                                 self.timestamp_dir,
                                 self.cache_options,
                                 automount_info=automount_info)
      return_val += updater.UpdateCacheFromSource(cache, source, incremental,
                                                  force_write, source_location)
    # with sub-maps updated, write modified master map to disk if configured to
    if not self.local_master:
      # automount_mountpoint=None defaults to master
      cache = caches.base.Create(self.cache_options,
                                 self.map_name,
                                 automount_mountpoint=None)
      updater = SingleMapUpdater(self.map_name,
                                 self.timestamp_dir,
                                 self.cache_options)
      return_val += updater.FullUpdateFromMap(cache, master_map)

    return return_val
