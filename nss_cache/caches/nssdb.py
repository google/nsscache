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

"""An implementation of nss_db local cache for nsscache."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import bsddb
import os
import subprocess

from nss_cache import config
from nss_cache import error
from nss_cache import maps
from nss_cache.caches import base


class NssDbCache(base.Cache):
  """An implementation of a Cache specific to nss_db.

  nss_db uses one Berkeley DB database per map for the cache.  This class
  abstracts the update and write strategies for nss_db caches.

  This class also provides timestamp read/write routines that are
  independent of the cache storage, as nss_db provides no support for
  these.
  """
  UPDATE_TIMESTAMP_SUFFIX = 'nsscache-update-timestamp'
  MODIFY_TIMESTAMP_SUFFIX = 'nsscache-timestamp'

  def __init__(self, conf, map_name, automount_info=None):
    """Create a handler for the given map type.

    Args:
     conf: a configuration object
     map_name: a string representing the type of map we are
     automount_info: A string containing the automount mountpoint, used only
       by automount maps.

    Returns: A CacheMapHandler instance.
    """
    super(NssDbCache, self).__init__(conf, map_name,
                                     automount_info=automount_info)
    self.makedb = conf.get('makedb', '/usr/bin/makedb')

  def GetMap(self, cache_info=None):
    """Returns the map from the cache.

    Args:
      cache_info: unused by this implementation of base.Cache
    Returns:
      a Map containing the map cache
    """
    data = self.data
    self._LoadBdbCacheFile(data)
    return data

  def _LoadBdbCacheFile(self, data):
    """Load data from bdb caches into a map.

    Args:
      data: a map.Map subclass

    Returns:
      Nothing.  Cache data is loaded into the 'data' parameter.

    Raises:
      CacheNotFound: if the database file does not exist
    """
    db_file = os.path.join(self.output_dir, self.CACHE_FILENAME)
    if not os.path.exists(db_file):
      self.log.debug('cache file does not exist: %r', db_file)
      raise error.CacheNotFound('cache file does not exist: %r' % db_file)

    db = bsddb.btopen(db_file, 'r')
    for k in db:
      if self.IsMapPrimaryKey(k):
        password_entry = self.ConvertValueToMapEntry(db[k])
        if not data.Add(password_entry):
          self.log.warn('could not add entry built from %r', db[k])

    db.close()

  def _SpawnMakeDb(self):
    """Run 'makedb' in a subprocess and return it to use for streaming.

    Returns:
      makedb: a subprocess object
    """
    self.log.debug('executing makedb: %s - %s',
                   self.makedb, self.cache_filename)
    makedb = subprocess.Popen([self.makedb, '-', self.cache_filename],
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT,
                              close_fds=True)
    return makedb

  def Write(self, map_data):
    """Write the map to the cache file.

    Warning -- this destroys map_data as it is written.  This is done to save
    memory and keep our peak footprint smaller.  We consume memory again
    on Verify() as we read a new copy of the entries back in.

    Args:
      map_data: A Map subclass

    Returns:
      a set() of keys written or None on failure.
    """
    self._Begin()
    written_keys = set()

    try:
      makedb = self._SpawnMakeDb()
      enumeration_index = 0

      try:
        while 1:
          entry = map_data.PopItem()
          if makedb.poll() is not None:
            self.log.error('early exit from makedb! child output: %s',
                           makedb.stdout.read())
            # in this case, no matter how the child exited, we complain
            return None
          self.WriteData(makedb.stdin, entry, enumeration_index)
          written_keys.update(self.ExpectedKeysForEntry(entry))
          enumeration_index += 1
      except KeyError:
        # expected when PopItem() is done, and breaks our loop for us.
        pass

      self.log.debug('%d entries written, %d keys', enumeration_index,
                     len(written_keys))
      makedb.stdin.close()

      map_data = makedb.stdout.read()
      if map_data:
        self.log.debug('makedb output: %r', map_data)

      if self._DecodeExitCode(makedb.wait()):
        return written_keys
      
      return None
      
    except:
      self._Rollback()
      raise

  def _DecodeExitCode(self, code):
    """Helper function to compute if a child exited with code 0 or not."""
    return os.WIFEXITED(code) and (os.WEXITSTATUS(code) is 0)

  def Verify(self, written_keys):
    """Verify that the written cache is correct.

    Perform some unit tests on the written data, such as reading it
    back and verifying that it loads and has the entries we expect.

    Args:
      written_keys: a set() of keys that should have been written to disk.

    Returns:
      boolean indicating success.

    Raises:
      EmptyMap: The map to be verified against is empty.
    """
    self.log.debug('verification started')
    db = bsddb.btopen(self.cache_filename, 'r')
    # cast keys to a set for fast __contains__ lookup in the loop
    # following
    cache_keys = set(db)
    db.close()

    written_key_count = len(written_keys)
    cache_key_count = len(cache_keys)
    self.log.debug('%d written keys, %d cache keys', written_key_count,
                   cache_key_count)

    if cache_key_count <= 0 and written_key_count > 0:
      # We have an empty map yet we should have written more.
      # Uncaught disk full or other error?
      raise error.EmptyMap

    # makedb creates new keys internally.  we only care that all the keys
    # we tried to write out are still there.  so written_keys must be a subset
    # of cache_keys!
    if not written_keys.issubset(cache_keys):
      self.log.warn('verify failed: written keys missing from the on-disk'
                    ' cache!')
      intersection = written_keys.intersection(cache_keys)
      missing_keys = written_keys - intersection
      self.log.debug('missing: %r', missing_keys)
      self._Rollback()
      return False

    self.log.info('verify passed: %s', self.CACHE_FILENAME)
    return True


class NssDbPasswdHandler(NssDbCache):
  """Concrete class for updating a nss_db passwd cache."""
  CACHE_FILENAME = 'passwd.db'

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_PASSWORD
    super(NssDbPasswdHandler, self).__init__(conf, map_name,
                                             automount_info=automount_info)

  def WriteData(self, target, entry, enumeration_index):
    """Generate three entries as expected by nss_db passwd map.

    nss_db keys each pwent on three keys: username, uid number, and an
    enumeration index.  This method writes the pwent out three times
    to the target file-like object with each of these keys, each marked
    specially as documented in the nss_db source db-Makefile.

    Args:
      target: File-like object of the makedb subprocess stdin
      entry: A PasswdMapEntry
      enumeration_index: The number of records processed so far.

    Returns:
      Nothing
    """
    password_entry = '%s:%s:%d:%d:%s:%s:%s' % (entry.name, entry.passwd,
                                               entry.uid, entry.gid,
                                               entry.gecos, entry.dir,
                                               entry.shell)
    # Write to makedb with each key
    target.write('.%s %s\n' % (entry.name, password_entry))
    target.write('=%d %s\n' % (entry.uid, password_entry))
    target.write('0%d %s\n' % (enumeration_index, password_entry))

  def IsMapPrimaryKey(self, key):
    """Defines the 'primary' key for this map.

    nss_db maps typically have the same entry many times in their cache
    files.  In order to build our representation of the cache, we need to
    ignore all but one of them.  This method chooses one key as the primary.

    Args:
     key: the database key returned from the Berkeley DB key/value pairs

    Returns:
      a boolean indicating truth
    """
    # only take values keyed with username, known in nss_db land as the
    # one starting with a dot
    return key.startswith('.')

  def ConvertValueToMapEntry(self, entry):
    """Convert a pwent-like string into a PasswdMapEntry.

    Args:
     entry: A string containing a pwent entry ala /etc/passwd

    Returns:
      a PasswdMapEntry instance
    """
    if entry.endswith('\x00'):
      entry = entry[:-1]

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

  def ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this entry.

    Args:
     entry:  A PasswdMapEntry

    Returns:
      a list of strings
    """
    return ['.%s' % entry.name,
            '=%d' % entry.uid]


base.RegisterImplementation('nssdb', 'passwd', NssDbPasswdHandler)


class NssDbGroupHandler(NssDbCache):
  """Concrete class for updating nss_db group maps."""
  CACHE_FILENAME = 'group.db'

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_GROUP
    super(NssDbGroupHandler, self).__init__(conf, map_name,
                                            automount_info=automount_info)

  def WriteData(self, target, entry, enumeration_index):
    """Generate three entries as expected by nss_db group map.

    nss_db keys each grent on three keys: group name, gid number, and an
    enumeration index.  This method writes the grent out three times
    to the target file-like object with each of these keys, each marked
    specially as documented in the nss_db source db-Makefile.

    Args:
      target: File-like object of the makedb subprocess stdin
      entry: A GroupMapEntry
      enumeration_index: The number of records processed so far.

    Returns:
      Nothing
    """
    grent = '%s:%s:%d:%s' % (entry.name, entry.passwd, entry.gid,
                             ','.join(entry.members))
    # Write to makedb with each key
    target.write('.%s %s\n' % (entry.name, grent))
    target.write('=%d %s\n' % (entry.gid, grent))
    target.write('0%d %s\n' % (enumeration_index, grent))

  def IsMapPrimaryKey(self, key):
    """Defines the 'primary' key for a nss_db group.db map.

    See the docstring for NssDbPasswdCache.IsMapPrimaryKey()

    Args:
      key: they database key returned from bsddb.

    Returns:
      a boolean indicating truth
    """
    # use the key designated as a 'group name' key
    return key.startswith('.')

  def ConvertValueToMapEntry(self, entry):
    """Convert a grent-like string into a GroupMapEntry.

    Args:
      entry: A string containing a grent entry ala /etc/group

    Returns:
      A GroupMapEntry instance
    """
    if entry.endswith('\x00'):
      entry = entry[:-1]

    entry = entry.split(':')
    map_entry = maps.GroupMapEntry()
    # map entries expect strict typing, so convert as appropriate
    map_entry.name = entry[0]
    map_entry.passwd = entry[1]
    map_entry.gid = int(entry[2])
    map_entry.members = entry[3].split(',')

    return map_entry

  def ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this entry.

    Args:
      entry:  A GroupMapEntry

    Returns:
      a list of strings
    """
    return ['.%s' % entry.name,
            '=%d' % entry.gid]


base.RegisterImplementation('nssdb', 'group', NssDbGroupHandler)


class NssDbShadowHandler(NssDbCache):
  """Concrete class for updating nss_db shadow maps."""
  CACHE_FILENAME = 'shadow.db'

  def __init__(self, conf, map_name=None, automount_info=None):
    if map_name is None: map_name = config.MAP_SHADOW
    super(NssDbShadowHandler, self).__init__(conf, map_name,
                                             automount_info=automount_info)

  def WriteData(self, target, entry, enumeration_index):
    """Generate three entries as expected by nss_db shadow map.

    nss_db keys each shadow entry on two keys, username and enumeration
    index.

    This method writes out the shadow entry twice, once with each key,
    each marked specially as documented in the nss_db source db-Makefile.

    Args:
      target: File-like object of the makedb subprocess stdin
      entry: A ShadowMapEntry
      enumeration_index: The number of records processed so far.

    Returns:
      Nothing
    """
    # If the field is None, then set to empty string
    shadow_entry = '%s:%s:%s:%s:%s:%s:%s:%s:%s' % (entry.name,
                                                   entry.passwd,
                                                   entry.lstchg or '',
                                                   entry.min or '',
                                                   entry.max or '',
                                                   entry.warn or '',
                                                   entry.inact or '',
                                                   entry.expire or '',
                                                   entry.flag or 0)
    # Write to makedb with each key
    target.write('.%s %s\n' % (entry.name, shadow_entry))
    target.write('0%d %s\n' % (enumeration_index, shadow_entry))

  def IsMapPrimaryKey(self, key):
    """Defines the 'primary' key for a nss_db shadow.db map.

    See the docstring for NssDbPasswdCache.IsMapPrimaryKey()

    Args:
      key: they database key returned from bsddb.

    Returns:
      a boolean indicating truth
    """
    # use the key designated as a "shadow name" key
    return key.startswith('.')

  def ConvertValueToMapEntry(self, entry):
    """Convert a grent-like string into a ShadowMapEntry.

    Args:
      entry: A string containing a grent entry ala /etc/shadow

    Returns:
      A ShadowMapEntry instance
    """
    if entry.endswith('\x00'):
      entry = entry[:-1]

    entry = entry.split(':')
    map_entry = maps.ShadowMapEntry()
    # map entries expect strict typing, so convert as appropriate
    map_entry.name = entry[0]
    map_entry.passwd = entry[1]
    if entry[2]:
      map_entry.lstchg = int(entry[2])
    if entry[3]:
      map_entry.min = int(entry[3])
    if entry[4]:
      map_entry.max = int(entry[4])
    if entry[5]:
      map_entry.warn = int(entry[5])
    if entry[6]:
      map_entry.inact = int(entry[6])
    if entry[7]:
      map_entry.expire = int(entry[7])
    if entry[8]:
      map_entry.flag = int(entry[8])
    return map_entry

  def ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this entry.

    Args:
      entry:  A ShadowMapEntry

    Returns:
      a list of strings
    """
    return ['.%s' % entry.name]


base.RegisterImplementation('nssdb', 'shadow', NssDbShadowHandler)
