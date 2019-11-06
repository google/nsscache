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
FileMapUpdater:  Class used for all single map caches.
AutomountMapUpdater:  Class used for updating automount map caches.
"""
import errno

__author__ = ('vasilios@google.com (V Hoffman)',
              'jaq@google.com (Jamie Wilkinson)')

import calendar
import logging
import os
import stat
import tempfile
import time

from nss_cache.caches import cache_factory
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

    def __init__(self,
                 map_name,
                 timestamp_dir,
                 cache_options,
                 automount_mountpoint=None,
                 can_do_incremental=False):
        """Construct an updater object.

        Args:
          map_name: A string representing the type of the map we are an Updater for.
          timestamp_dir: A string with the directory containing our timestamp files.
          cache_options: A dict containing the options for any caches we create.
          automount_mountpoint: An optional string containing automount path info.
          can_do_incremental: Indicates whether or not our source can provide
              incremental updates at all.
        """

        # Set up a logger
        self.log = logging.getLogger(__name__)
        # Used to fetch the right maps later on
        self.map_name = map_name
        # Used for tempfile writing
        self.timestamp_dir = timestamp_dir
        # Used to create cache(s)
        self.cache_options = cache_options
        self.can_do_incremental = can_do_incremental

        # Calculate our timestamp files
        if automount_mountpoint is None:
            timestamp_prefix = '%s/timestamp-%s' % (timestamp_dir, map_name)
        else:
            # turn /auto into auto.auto, and /usr/local into /auto.usr_local
            automount_mountpoint = automount_mountpoint.lstrip('/')
            automount_mountpoint = automount_mountpoint.replace('/', '_')
            timestamp_prefix = '%s/timestamp-%s-%s' % (timestamp_dir, map_name,
                                                       automount_mountpoint)
        self.modify_file = '%s-modify' % timestamp_prefix
        self.update_file = '%s-update' % timestamp_prefix

        # Timestamp info is cached here
        self.modify_time = None
        self.update_time = None

    def _GetCurrentTime(self):
        """Helper method to get the current time, to assist test mocks."""
        return int(time.time())

    def _ReadTimestamp(self, filename):
        """Return a timestamp from a file.

        The timestamp file format is a single line, containing a string in the
        ISO-8601 format YYYY-MM-DDThh:mm:ssZ (i.e. UTC time).  We do not support
        all ISO-8601 formats for reasons of convenience in the code.

        Timestamps internal to nss_cache deliberately do not carry milliseconds.

        Args:
          filename:  A String naming the file to read from.

        Returns:
          An int with the number of seconds since epoch, or None if the timestamp
          file doesn't exist or has errors.
        """
        if not os.path.exists(filename):
            return None

        try:
            timestamp_file = open(filename, 'r')
            timestamp_string = timestamp_file.read().strip()
        except IOError as e:
            self.log.warning('error opening timestamp file: %s', e)
            timestamp_string = None
        else:
            timestamp_file.close()

        self.log.debug('read timestamp %s from file %r', timestamp_string,
                       filename)

        if timestamp_string is not None:
            try:
                # Append UTC to force the timezone to parse the string in.
                timestamp = int(
                    calendar.timegm(
                        time.strptime(timestamp_string + ' UTC',
                                      '%Y-%m-%dT%H:%M:%SZ %Z')))
            except ValueError as e:
                self.log.error('cannot parse timestamp file %r: %s', filename,
                               e)
                timestamp = None
        else:
            timestamp = None

        now = self._GetCurrentTime()
        if timestamp and timestamp > now:
            self.log.warning('timestamp %r from %r is in the future, now is %r',
                             timestamp_string, filename, now)
            if timestamp - now >= 60 * 60:
                self.log.info('Resetting timestamp to now.')
                timestamp = now

        return timestamp

    def _WriteTimestamp(self, timestamp, filename):
        """Write a given timestamp out to a file, converting to the ISO-8601
        format.

        We convert internal timestamp format (epoch) to ISO-8601 format, i.e.
        YYYY-MM-DDThh:mm:ssZ which is basically UTC time, then write it out to a
        file.

        Args:
          timestamp: A String in nss_cache internal timestamp format, aka time_t.
          filename: A String naming the file to write to.

        Returns:
           A boolean indicating success of write.
        """
        # Make sure self.timestamp_dir exists before calling tempfile.mkstemp
        try:
            os.makedirs(self.timestamp_dir)
        except OSError as e:
            if e.errno == errno.EEXIST and os.path.isdir(self.timestamp_dir):
                pass  # Directory already exists; squelch error
            else:
                raise

        (filedesc, temp_filename) = tempfile.mkstemp(prefix='nsscache-update-',
                                                     dir=self.timestamp_dir)
        time_string = time.strftime('%Y-%m-%dT%H:%M:%SZ',
                                    time.gmtime(timestamp))

        try:
            os.write(filedesc, b'%s\n' % time_string.encode())
            os.fsync(filedesc)
            os.close(filedesc)
        except OSError:
            os.unlink(temp_filename)
            self.log.warning('writing timestamp failed!')
            return False

        os.chmod(temp_filename,
                 stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        os.rename(temp_filename, filename)
        self.log.debug('wrote timestamp %s to file %r', time_string, filename)
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
            update_timestamp = self._GetCurrentTime()
        return self._WriteTimestamp(update_timestamp, self.update_file)

    def WriteModifyTimestamp(self, timestamp):
        """Convenience method for writing the last modify timestamp.

        Args:
          timestamp:  An int with the number of seconds since epoch.
            If timestamp is None, performs no action.

        Returns:
          A boolean indicating success of the write.
        """
        if timestamp is None:
            return True
        # blow away our cached value
        self.modify_time = None
        return self._WriteTimestamp(timestamp, self.modify_file)

    def UpdateFromSource(self, source, incremental=True, force_write=False):
        """Update this map's cache from the source provided.

        The FileMapUpdater expects to fetch as single map from the source
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
        cache = cache_factory.Create(self.cache_options, self.map_name)

        return self.UpdateCacheFromSource(cache,
                                          source,
                                          incremental,
                                          force_write,
                                          location=None)
