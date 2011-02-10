#!/usr/bin/python
#
# Copyright 2010 Google Inc.
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

These update classes are based around file synchronization rather than
map synchronization.

These classes contains all the business logic for updating cache objects.
They also contain the code for reading, writing, and updating timestamps.
"""

__author__ = ('blaedd@google.com (David MacKinnon)',)

import logging
import os
import shutil
import stat
import tempfile
import time

from nss_cache import caches
from nss_cache import error
from nss_cache.update import base


class SingleMapUpdater(base.Updater):
  """Updates simple map files like passwd, group, shadow, and netgroup."""

  def UpdateFromSource(self, source, incremental=False, force_write=False):
    """Update this map's cache file from the source provided.

    The SingleMapUpdater expects to fetch as single file from the source
    and write it to disk.

    The source will return a temporary file that we then write to the
    final location.

    Note that AutomountUpdater also calls UpdateCacheFromSource() for each
    cache it is writing, hence the distinct seperation.

    Args:
      source: A nss_cache.sources.Source object.
      incremental: A boolean where True is an incremental update, defaults to
        True.
      force_write: A boolean causing emtpy maps to be written on update when
        True, defaults to False.

    Returns:
      An int indicating success of update (0 == good, fail otherwise).
    """
    # Create the single cache we write to
    cache = caches.base.Create(self.cache_options, self.map_name)

    return self.UpdateCacheFromSource(cache, source, location=None,
                                      force_write=force_write)

  def UpdateCacheFromSource(self, cache, source, force_write=False,
                            location=None):
    """Update a single cache file, from a given source.

    Args:
      cache: A nss_cache.caches.Cache object.
      source: A nss_cache.sources.Source object.
      force_write: A boolean flag forcing empty map updates when False,
        defaults to False.
      location: The optional location in the source of this map used by
        automount to specify which automount map to get, defaults to None.

    Returns:
      An int indicating the success of an update (0 == good, fail otherwise).
    """
    return_val = 0

    tmpdir = tempfile.mkdtemp(prefix=self.__class__.__name__)
    try:
      new_file = os.path.join(tmpdir,
                              os.path.basename(cache.GetCacheFilename()))
      source.GetFile(self.map_name, new_file, cache.GetCacheFilename(),
                     location=location)
      return_val += self.FullUpdateFromMap(cache, new_file, force_write)
    finally:
      shutil.rmtree(tmpdir)

    return return_val

  def FullUpdateFromMap(self, cache, source_file, force_write=False):
    """Write a new map into the provided cache (overwrites).

    Args:
      cache: A nss_cache.caches.Cache object.
      source_file: The file that we're replacing the cache with.
      force_write: A boolean flag forcing empty map updates when False,
        defaults to False.

    Returns:
      0 if succesful, non-zero indicating number of failures otherwise.

    Raises:
      EmptyMap: Update is an empty map, not raised if force_write=True.
      InvalidMap:
    """
    self.log.debug('Source file: %s', source_file)
    self.log.debug('Cache location: %s', cache.GetCacheFilename())
    self.log.debug('Automount Info: %s', cache.automount_info)
    return_val = 0
    tmpdir = os.path.dirname(source_file)
    cache_options = self.cache_options.copy()
    cache_options['dir'] = tmpdir
    verify_cache = caches.base.Create(cache_options, self.map_name,
                                      automount_info=cache.automount_info)

    new_map = verify_cache.GetMap()

    if not new_map:
      raise error.InvalidMap('Map is not valid. Aborting')

    for entry in new_map:
      if not entry.Verify():
        raise error.InvalidMap('Map is not valid. Aborting')

    if len(new_map) is 0 and not force_write:
      raise error.EmptyMap('Source map empty during full update, aborting. '
                           'Use --force-write to override.')

    try:
      os.chmod(source_file, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
      os.rename(source_file, cache.GetCacheFilename())
    except OSError:
      logging.warning('Unable to copy new cache across')
      return_val += 1

    # We did an update, write our timestamps unless there is an error.
    if return_val is 0:
      mtime = os.stat(cache.GetCacheFilename()).st_mtime
      gmtime = time.gmtime(mtime)
      self.log.debug('Cache filename %s has mtime %d, gmtime %r',
                     cache.GetCacheFilename(), mtime, gmtime)
      self.WriteModifyTimestamp(gmtime)
      self.WriteUpdateTimestamp()

    return return_val


class AutomountUpdater(base.Updater):
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

  def UpdateFromSource(self, source, incremental=False, force_write=False):
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
      incremental: Not used by this class
      force_write: A boolean flag forcing empty map updates when False,
        defaults to False.

    Returns:
      An int indicating success of update (0 == good, fail otherwise).
    """
    return_val = 0

    tmpdir = tempfile.mkdtemp(prefix=self.__class__.__name__)
    try:
      try:
        self.log.info('Retrieving automount master map.')
        master_file = source.GetAutomountMasterFile(
            os.path.join(tmpdir, 'auto.master'))
        cache_options = self.cache_options.copy()
        cache_options['dir'] = tmpdir
        master_cache = caches.base.Create(cache_options, self.map_name,
                                          None)
        master_map = master_cache.GetMap()
      except error.CacheNotFound:
        return 1
    finally:
      shutil.rmtree(tmpdir)

    if self.local_master:
      self.log.info('Using local master map to determine maps to update.')
      # we need the local map to determine which of the other maps to update
      cache = caches.base.Create(self.cache_options, self.map_name,
                                 automount_info=None)
      try:
        local_master = cache.GetMap()
      except error.CacheNotFound:
        self.log.warning('Local master map specified but no map found! '
                         'No maps will update.')
        return return_val + 1

    # update specific maps, e.g. auto.home and auto.auto
    for map_entry in master_map:
      source_location = os.path.basename(map_entry.location)
      automount_info = map_entry.key        # e.g. /auto mountpoint
      self.log.debug('looking at %s mount.', automount_info)

      # create the cache to update
      cache = caches.base.Create(self.cache_options,
                                 self.map_name,
                                 automount_info=automount_info)

      # update the master map with the location of the map in the cache
      # e.g. /etc/auto.auto replaces ou=auto.auto
      map_entry.location = cache.GetMapLocation()
      self.log.debug('Map location: %s', map_entry.location)

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
      return_val += updater.UpdateCacheFromSource(
          cache, source, force_write, source_location)
    # with sub-maps updated, write modified master map to disk if
    # configured to
    if not self.local_master:
      cache = caches.base.Create(cache_options,
                                 self.map_name,
                                 automount_info=None)  # None defaults to master
      updater = SingleMapUpdater(self.map_name,
                                 self.timestamp_dir,
                                 self.cache_options)
      return_val += updater.FullUpdateFromMap(cache, master_map)

    return return_val
