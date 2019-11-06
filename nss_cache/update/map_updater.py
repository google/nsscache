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

FileMapUpdater:  Class used for all single map caches.
AutomountMapUpdater:  Class used for updating automount map caches.
"""

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)')

from nss_cache import error
from nss_cache.caches import cache_factory
from nss_cache.update import updater


class MapUpdater(updater.Updater):
    """Updates simple maps like passwd, group, shadow, and netgroup."""

    def UpdateCacheFromSource(self,
                              cache,
                              source,
                              incremental=False,
                              force_write=False,
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
        incremental = incremental and self.can_do_incremental

        timestamp = self.GetModifyTimestamp()
        if timestamp is None and incremental is True:
            self.log.info(
                'Missing previous timestamp, defaulting to a full sync.')
            incremental = False

        if incremental:
            source_map = source.GetMap(self.map_name,
                                       since=timestamp,
                                       location=location)
            try:
                return_val += self._IncrementalUpdateFromMap(cache, source_map)
            except (error.CacheNotFound, error.EmptyMap):
                self.log.warning(
                    'Local cache is invalid, faulting to a full sync.')
                incremental = False

        # We don't use an if/else, because we give the incremental a chance to
        # fail through to a full sync.
        if not incremental:
            source_map = source.GetMap(self.map_name, location=location)
            return_val += self.FullUpdateFromMap(cache, source_map, force_write)

        return return_val

    def _IncrementalUpdateFromMap(self, cache, new_map):
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
            raise error.EmptyMap(
                'Source map empty during full update, aborting. '
                'Use --force-write to override.')

        return_val = cache.WriteMap(map_data=new_map)

        # We did an update, write our timestamps unless there is an error.
        if return_val == 0:
            self.WriteModifyTimestamp(new_map.GetModifyTimestamp())
            self.WriteUpdateTimestamp()

        return return_val


class AutomountUpdater(updater.Updater):
    """Update an automount map.

    Automount maps are a unique case.  They are not a single set of map entries,
    they are a set of sets.  Updating automount maps require fetching the list
    of maps and updating each map as well as the list of maps.

    This class is written to re-use the individual update code in the
    FileMapUpdater class.
    """

    # automount-specific options
    OPT_LOCAL_MASTER = 'local_automount_master'

    def __init__(self,
                 map_name,
                 timestamp_dir,
                 cache_options,
                 automount_mountpoint=None):
        """Initialize automount-specific updater options.

        Args:
          map_name: A string representing the type of the map we are an Updater for.
          timestamp_dir: A string with the directory containing our timestamp files.
          cache_options: A dict containing the options for any caches we create.
          automount_mountpoint: An optional string containing automount path info.
        """
        super(AutomountUpdater,
              self).__init__(map_name, timestamp_dir, cache_options,
                             automount_mountpoint)
        self.local_master = False
        if self.OPT_LOCAL_MASTER in cache_options:
            if cache_options[self.OPT_LOCAL_MASTER] == 'yes':
                self.local_master = True

    def UpdateFromSource(self, source, incremental=True, force_write=False):
        """Update the automount master map, and every map it points to.

        We fetch a full copy of the master map everytime, and then use the
        FileMapUpdater to write each map the master map points to, as well
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
            cache = cache_factory.Create(self.cache_options,
                                         self.map_name,
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
            automount_mountpoint = map_entry.key  # e.g. /auto mountpoint
            self.log.debug('looking at %s mount.', automount_mountpoint)

            # create the cache to update
            cache = cache_factory.Create(
                self.cache_options,
                self.map_name,
                automount_mountpoint=automount_mountpoint)

            # update the master map with the location of the map in the cache
            # e.g. /etc/auto.auto replaces ou=auto.auto
            map_entry.location = cache.GetMapLocation()

            # if configured to use the local master map, skip any not defined there
            if self.local_master:
                if map_entry not in local_master:
                    self.log.debug('skipping %s, not in %s', map_entry,
                                   local_master)
                    continue

            self.log.info('Updating %s mount.', map_entry.key)
            # update this map (e.g. /etc/auto.auto)
            update_obj = MapUpdater(self.map_name,
                                    self.timestamp_dir,
                                    self.cache_options,
                                    automount_mountpoint=automount_mountpoint)
            return_val += update_obj.UpdateCacheFromSource(
                cache, source, incremental, force_write, source_location)
        # with sub-maps updated, write modified master map to disk if configured to
        if not self.local_master:
            # automount_mountpoint=None defaults to master
            cache = cache_factory.Create(self.cache_options,
                                         self.map_name,
                                         automount_mountpoint=None)
            update_obj = MapUpdater(self.map_name, self.timestamp_dir,
                                    self.cache_options)
            return_val += update_obj.FullUpdateFromMap(cache, master_map)

        return return_val
