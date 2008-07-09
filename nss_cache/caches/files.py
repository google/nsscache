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
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

"""An implementation of nss_files local cache for nsscache."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import os.path
import re

from nss_cache import config
from nss_cache import error
from nss_cache import maps
from nss_cache.caches import base


class FilesCache(base.Cache):
  """An implementation of a Cache specific to nss_files module.

  This implementation creates, updates, and verifies map caches used by
  nss_files module.
  """

  def __init__(self, conf, map_name, automount_info=None):
    """Create a handler for the given map type.

    Args:
     conf: a configuration object
     map_name: a string representing the type of map we are
     automount_info: A string containing the automount mountpoint, used only
       by automount maps.
    """
    super(FilesCache, self).__init__(conf, map_name,
                                     automount_info=automount_info)
    
    # TODO(jaq): this 'cache' constant default is not obvious, needs documenting
    self.cache_filename_suffix = conf.get('cache_filename_suffix', 'cache')

  def GetMap(self, cache_info=None):
    """Returns the map from the cache.

    Args:
      cache_info:  alternative file to read, optional.
    Returns:
      A child of Map containing the cache data.
    Raises:
      CacheNotFound: The cache file we expected to read from does not exist.
    """
    data = self.data
    if cache_info is not None:
      cache_file = cache_info
    else:
      cache_file = self._GetCacheFilename()
      
    if not os.path.exists(cache_file):
      self.log.debug('cache file %r does not exist', cache_file)
      raise error.CacheNotFound('cache file %r does not exist' %
                                cache_file)

    for line in open(cache_file):
      line = line.rstrip('\n')
      if not line:
        continue
      entry = self._ReadEntry(line)
      if not data.Add(entry):
        self.log.warn('could not add entry built from %r', line)

    return data

  def Verify(self, written_keys):
    """Verify that the cache is correct.

    Perform some unit tests on the written data, such as reading it
    back and verifying that it parses and has the entries we expect.

    Args:
      written_keys: a set() of keys that should have been written to disk.

    Returns:
      a boolean indicating success.

    Raises:
      error.EmptyMap: see nssdb.py:Verify
    """
    self.log.debug('verification starting on %r', self.cache_filename)

    cache_data = self.GetMap(cache_info=self.cache_filename)
    map_entry_count = len(cache_data)
    self.log.debug('entry count: %d', map_entry_count)
    
    if map_entry_count <= 0:
      # See nssdb.py Verify for a comment about this raise
      raise error.EmptyMap

    cache_keys = set()
    # Use PopItem() so we free our memory if multiple maps are Verify()ed.
    try:
      while 1:
        entry = cache_data.PopItem()
        cache_keys.update(self._ExpectedKeysForEntry(entry))
    except KeyError:
      # expected when PopItem() is done, and breaks our loop for us.
      pass

    missing_from_cache = written_keys - cache_keys
    if missing_from_cache:
      self.log.warn('verify failed: %d missing from the on-disk cache',
                    len(missing_from_cache))
      self.log.debug('keys missing from cache: %r', missing_from_cache)
      self._Rollback()
      return False

    missing_from_map = cache_keys - written_keys
    if missing_from_map:
      self.log.warn('verify failed: %d keys unexpected in the on-disk cache',
                    len(missing_from_map))
      self.log.warn('keys missing from map: %r', missing_from_map)
      self._Rollback()
      return False

    return True

  def Write(self, map_data):
    """Write the map to the cache.

    Warning -- this destroys map_data as it is written.  This is done to save
    memory and keep our peak footprint smaller.  We consume memory again
    on Verify() as we read a new copy of the entries back in.

    Args:
      map_data: A Map subclass containing the entire map to be written.

    Returns:
      a set() of keys written or None on failure.
    """
    self._Begin()
    written_keys = set()
    
    try:
      while 1:
        entry = map_data.PopItem()
        self._WriteData(self.cache_file, entry)
        written_keys.update(self._ExpectedKeysForEntry(entry))
    except KeyError:
      # expected when PopItem() is done, and breaks our loop for us.
      self.cache_file.flush()
      self.cache_file.close()
    except:
      self._Rollback()
      raise

    return written_keys

  def _GetCacheFilename(self):
    """Return the final destination pathname of the cache file."""
    cache_filename_target = self.CACHE_FILENAME
    if self.cache_filename_suffix:
      cache_filename_target += '.' + self.cache_filename_suffix
    return os.path.join(self.output_dir, cache_filename_target)


class FilesPasswdMapHandler(FilesCache):
  """Concrete class for updating a nss_files module passwd cache."""
  CACHE_FILENAME = 'passwd'

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_PASSWORD
    super(FilesPasswdMapHandler, self).__init__(conf, map_name,
                                                automount_info=automount_info)

  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.

    Args:
      entry: A PasswdMapEntry

    Returns:
      A list of strings
    """
    return [entry.name]

  def _WriteData(self, target, entry):
    """Write a PasswdMapEntry to the target cache."""
    password_entry = '%s:%s:%d:%d:%s:%s:%s' % (entry.name, entry.passwd,
                                               entry.uid, entry.gid,
                                               entry.gecos, entry.dir,
                                               entry.shell)
    target.write(password_entry + '\n')

  def _ReadEntry(self, entry):
    """Return a PasswdMapEntry from a record in the target cache."""
    entry = entry.split(':')
    map_entry = maps.PasswdMapEntry()
    # maps expect strict typing, so convert to int as appropriate.
    map_entry.name = entry[0]
    map_entry.passwd = entry[1]
    map_entry.uid = int(entry[2])
    map_entry.gid = int(entry[3])
    map_entry.gecos = entry[4]
    map_entry.dir = entry[5]
    map_entry.shell = entry[6]
    return map_entry


base.RegisterImplementation('files', 'passwd', FilesPasswdMapHandler)


class FilesGroupMapHandler(FilesCache):
  """Concrete class for updating a nss_files module group cache."""
  CACHE_FILENAME = 'group'

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_GROUP
    super(FilesGroupMapHandler, self).__init__(conf, map_name,
                                               automount_info=automount_info)

  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.

    Args:
      entry: A GroupMapEntry

    Returns:
      A list of strings
    """
    return [entry.name]

  def _WriteData(self, target, entry):
    """Write a GroupMapEntry to the target cache."""
    group_entry = '%s:%s:%d:%s' % (entry.name, entry.passwd, entry.gid,
                                   ','.join(entry.members))
    target.write(group_entry + '\n')

  def _ReadEntry(self, line):
    """Return a GroupMapEntry from a record in the target cache."""
    line = line.split(':')
    map_entry = maps.GroupMapEntry()
    # map entries expect strict typing, so convert as appropriate
    map_entry.name = line[0]
    map_entry.passwd = line[1]
    map_entry.gid = int(line[2])
    map_entry.members = line[3].split(',')
    return map_entry


base.RegisterImplementation('files', 'group', FilesGroupMapHandler)


class FilesShadowMapHandler(FilesCache):
  """Concrete class for updating a nss_files module shadow cache."""
  CACHE_FILENAME = 'shadow'

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_SHADOW
    super(FilesShadowMapHandler, self).__init__(conf, map_name,
                                                automount_info=automount_info)

  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.

    Args:
      entry: A ShadowMapEntry

    Returns:
      A list of strings
    """
    return [entry.name]

  def _WriteData(self, target, entry):
    """Write a ShadowMapEntry to the target cache."""
    shadow_entry = '%s:%s:%s:%s:%s:%s:%s:%s:%s' % (entry.name,
                                                   entry.passwd,
                                                   entry.lstchg or '',
                                                   entry.min or '',
                                                   entry.max or '',
                                                   entry.warn or '',
                                                   entry.inact or '',
                                                   entry.expire or '',
                                                   entry.flag or '')
    target.write(shadow_entry + '\n')

  def _ReadEntry(self, line):
    """Return a ShadowMapEntry from a record in the target cache."""
    line = line.split(':')
    map_entry = maps.ShadowMapEntry()
    # map entries expect strict typing, so convert as appropriate
    map_entry.name = line[0]
    map_entry.passwd = line[1]
    if line[2]:
      map_entry.lstchg = int(line[2])
    if line[3]:
      map_entry.min = int(line[3])
    if line[4]:
      map_entry.max = int(line[4])
    if line[5]:
      map_entry.warn = int(line[5])
    if line[6]:
      map_entry.inact = int(line[6])
    if line[7]:
      map_entry.expire = int(line[7])
    if line[8]:
      map_entry.flag = int(line[8])
    return map_entry


base.RegisterImplementation('files', 'shadow', FilesShadowMapHandler)


class FilesNetgroupMapHandler(FilesCache):
  """Concrete class for updating a nss_files module netgroup cache."""
  CACHE_FILENAME = 'netgroup'
  _TUPLE_RE = re.compile('^\((.*?),(.*?),(.*?)\)$')  # Do this only once.

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_NETGROUP
    super(FilesNetgroupMapHandler, self).__init__(conf, map_name,
                                                  automount_info=automount_info)

  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.

    Args:
      entry: A NetgroupMapEntry

    Returns:
      A list of strings
    """
    return [entry.name]

  def _WriteData(self, target, entry):
    """Write a NetgroupMapEntry to the target cache."""
    netgroup_entry = entry.name
    for item in entry.entries:
      if isinstance(item, tuple):
        (host, user, domain) = item
        if host is None: host = ''
        if user is None: user = ''
        if domain is None: domain = ''
        item = '(%s,%s,%s)' % (host, user, domain)
      netgroup_entry = '%s %s' % (netgroup_entry, item)

    target.write(netgroup_entry + '\n')

  def _ReadEntry(self, line):
    """Return a NetgroupMapEntry from a record in the target cache."""
    map_entry = maps.NetgroupMapEntry()

    # hax0red stream parsing...
    tokens = line.split()

    # first entry is our name
    try:
      name = tokens.pop(0)
    except IndexError:
      raise RuntimeError('Failed to parse entry: %s' % line)

    map_entry.name = name

    # now build the entries list.
    #
    # TODO(v):  handle parsing spaces out of tuples.  we are fortunate right
    # now to test against data sources that look like (-,foo,) instead of
    # (-, foo, ) but this should be fixed or we might end up with mismatches on
    # verify.
    while tokens:
      token = tokens.pop(0)
      map_entry.entries.append(token)
        
    return map_entry


base.RegisterImplementation('files', 'netgroup', FilesNetgroupMapHandler)


class FilesAutomountMapHandler(FilesCache):
  """Concrete class for updating a nss_files module automount cache."""
  CACHE_FILENAME = None  # we have multiple files, set as we update.

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_AUTOMOUNT
    super(FilesAutomountMapHandler, self).__init__(
      conf, map_name, automount_info=automount_info)
    
    if automount_info is None:
      # we are dealing with the master map
      self.CACHE_FILENAME = 'auto.master'
    else:
      # turn /auto into auto.auto, and /usr/local into /auto.usr_local
      automount_info = automount_info.lstrip('/')
      self.CACHE_FILENAME = 'auto.%s' % automount_info.replace('/','_')

  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.
    
    Args:
      entry: A AutomountMapEntry

    Returns:
      A list of strings
    """
    return [entry.key]

  def _WriteData(self, target, entry):
    """Write an AutomountMapEntry to the target cache."""
    automount_entry = '%s %s %s' % (entry.key,
                                    entry.options or '',
                                    entry.location)
    target.write(automount_entry + '\n')

  def _ReadEntry(self, line):
    """Return an AutomountMapEntry from a record in the target cache."""
    line = line.split(' ')
    map_entry = maps.AutomountMapEntry()
    map_entry.key = line[0]
    if len(line) > 2:
      map_entry.options = line[1]
      map_entry.location = line[2]
    else:
      map_entry.location = line[1]
    return map_entry

  def GetMapLocation(self):
    """Get the location of this map for the automount master map."""
    return self._GetCacheFilename()
    
base.RegisterImplementation('files', 'automount', FilesAutomountMapHandler)
