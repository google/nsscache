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

"""An implementation of a nss_files format local cache, with indexing.

libnss-cache is a NSS module that reads NSS data from files in /etc,
that look similar to the standard ones used by nss_files, but with
".cache" extension. It also uses an index file if one exists, in a
format created here.
"""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import errno
import os.path
import re
import shutil
import stat
import sys
from configparser import ConfigParser

from nss_cache import config
from nss_cache import error
from nss_cache.caches import caches
from nss_cache.util import file_formats

if sys.version_info[0:2] >= (2, 5):
  def LongestLength(l): return len(max(l, key=len))
else: # Python < 2.4, 50% slower
  def LongestLength(l): return max([len(x) for x in l])

# Load suffix config variables
parser = ConfigParser()
for i in sys.argv:
  if ('nsscache.conf') in i:
    # Remove '--config-file=' from the string
    if ('--config-file') in i:
      i = i[14:] 
    parser.read(i)
  elif os.path.isfile('/etc/nsscache.conf'):
    parser.read('/etc/nsscache.conf')
  else:
    # Config in nsscache folder
    parser.read('nsscache.conf')
prefix = parser.get('suffix', 'prefix')
suffix = parser.get('suffix', 'suffix')

def RegisterAllImplementations(register_callback):
  """Register our cache classes independently from the import scheme."""
  register_callback('files', 'passwd', FilesPasswdMapHandler)
  register_callback('files', 'sshkey', FilesSshkeyMapHandler)
  register_callback('files', 'group', FilesGroupMapHandler)
  register_callback('files', 'shadow', FilesShadowMapHandler)
  register_callback('files', 'netgroup', FilesNetgroupMapHandler)
  register_callback('files', 'automount', FilesAutomountMapHandler)


class FilesCache(caches.Cache):
  """An implementation of a Cache specific to nss_files module.

  This implementation creates, updates, and verifies map caches used by
  nss_files module.

  Child classes can define the class attribute _INDEX_ATTRIBUTES, a
  sequence-type of strings containing attributes of their associated
  Map type that will be built into an index for use by libnss-cache.
  """

  def __init__(self, conf, map_name, automount_mountpoint=None):
    """Create a handler for the given map type.

    Args:
     conf: a configuration object
     map_name: a string representing the type of map we are
     automount_mountpoint: A string containing the automount mountpoint, used
       only by automount maps.
    """
    super(FilesCache, self).__init__(conf, map_name,
                                     automount_mountpoint=automount_mountpoint)

    # Documented in nsscache.conf example.
    self.cache_filename_suffix = conf.get('cache_filename_suffix', 'cache')
    # Store a dict of indexes, each containing a dict of keys to line, position
    # tuples.
    self._indices = {}
    if hasattr(self, '_INDEX_ATTRIBUTES'):
      for index in self._INDEX_ATTRIBUTES:
        self._indices[index] = {}
  def GetMap(self, cache_filename=None):
    """Returns the map from the cache.

    Args:
      cache_filename: alternative file to read, optional.

    Returns:
      A child of Map containing the cache data.

    Raises:
      CacheNotFound: The cache file we expected to read from does not exist.
    """
    data = self.data
    if cache_filename is None:
      cache_filename = self.GetCacheFilename()

    self.log.debug('Opening %r for reading existing cache', cache_filename)
    if not os.path.exists(cache_filename):
      self.log.warning('Cache file does not exist, using an empty map instead')
    else:
      cache_file = open(cache_filename)
      data = self.map_parser.GetMap(cache_file, data)

    return data

  def Verify(self, written_keys):
    """Verify that the cache is correct.

    Perform some unit tests on the written data, such as reading it
    back and verifying that it parses and has the entries we expect.

    Args:
      written_keys: a set of keys that should have been written to disk.

    Returns:
      a boolean indicating success.

    Raises:
      EmptyMap: The cache being verified is empty.
    """
    self.log.debug('verification starting on %r', self.temp_cache_filename)

    cache_data = self.GetMap(self.temp_cache_filename)
    map_entry_count = len(cache_data)
    self.log.debug('entry count: %d', map_entry_count)

    if map_entry_count <= 0:
      # We have read in an empty map, yet we expect that earlier we
      # should have written more. Uncaught disk full or other error?
      self.log.error('The files cache being verified "%r" is empty.',
                     self.temp_cache_filename)
      raise error.EmptyMap(self.temp_cache_filename + ' is empty')

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
      if len(missing_from_cache) < 1000:
        self.log.debug('keys missing from the on-disk cache: %r',
                       missing_from_cache)
      else:
        self.log.debug('More than 1000 keys missing from cache. '
                       'Not printing.')
      self._Rollback()
      return False

    missing_from_map = cache_keys - written_keys
    if missing_from_map:
      self.log.warn('verify failed: %d keys found, unexpected in the on-disk '
                    'cache', len(missing_from_map))
      if len(missing_from_map) < 1000:
        self.log.debug('keys missing from map: %r', missing_from_map)
      else:
        self.log.debug('More than 1000 keys missing from map.  Not printing.')
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
      a set of keys written or None on failure.
    """
    self._Begin()
    written_keys = set()
    write_offset = 0

    try:
      while 1:
        entry = map_data.PopItem()
        for index in self._indices:
          self._indices[index][str(getattr(entry, index))] = str(write_offset)
        write_offset += self._WriteData(self.temp_cache_file, entry)
        written_keys.update(self._ExpectedKeysForEntry(entry))
    except KeyError:
      # expected when PopItem() is done, and breaks our loop for us.
      self.temp_cache_file.flush()
    except:
      self._Rollback()
      raise
    
    return written_keys

  def GetCacheFilename(self):
    """Return the final destination pathname of the cache file."""
    cache_filename_target = self.CACHE_FILENAME
    if self.cache_filename_suffix:
      cache_filename_target += '.' + self.cache_filename_suffix
    return os.path.join(self.output_dir, cache_filename_target)

  def WriteIndex(self):
    """Generate an index for libnss-cache from this map."""
    for index_name in self._indices:
      # index file write to tmp file first, magic string ".ix"
      tmp_index_filename = '%s.ix%s.tmp' % (self.GetCacheFilename(), index_name)
      self.log.debug('Writing index %s', tmp_index_filename)

      index = self._indices[index_name]
      key_length = LongestLength(list(index.keys()))
      pos_length = LongestLength(list(index.values()))
      max_length = key_length + pos_length
      # Open for write/truncate
      index_file = open(tmp_index_filename, 'w')
      # setup permissions
      try:
        shutil.copymode(self.GetCompatFilename(), tmp_index_filename)
        stat_info = os.stat(self.GetCompatFilename())
        uid = stat_info.st_uid
        gid = stat_info.st_gid
        os.chown(tmp_index_filename, uid, gid)
      except OSError as e:
        if e.errno == errno.ENOENT:
          os.chmod(tmp_index_filename,
                   stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
      for key in sorted(index):
        pos = index[key]
        index_line = ('%s\0%s\0%s\n' %
                      (key, pos,
                       '\0' * (max_length - len(key) - len(pos))))
        index_file.write(index_line)
      index_file.close()
    for index_name in self._indices:
      # rename tmp index file to target index file in order to
      # prevent getting user info fail during update index.
      tmp_index_filename = '%s.ix%s.tmp' % (self.GetCacheFilename(), index_name)
      index_filename = '%s.ix%s' % (self.GetCacheFilename(), index_name)
      os.rename(tmp_index_filename, index_filename)


class FilesSshkeyMapHandler(FilesCache):
  """Concrete class for updating a nss_files module sshkey cache."""
  CACHE_FILENAME = 'sshkey'
  _INDEX_ATTRIBUTES = ('name',)

  def __init__(self, conf, map_name=None, automount_mountpoint=None):
    if map_name is None: map_name = config.MAP_SSHKEY
    super(FilesSshkeyMapHandler, self).__init__(
        conf, map_name, automount_mountpoint=automount_mountpoint)
    self.map_parser = file_formats.FilesSshkeyMapParser()
  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.

    Args:
      entry: A SshkeyMapEntry

    Returns:
      A list of strings
    """
    return [entry.name]

  def _WriteData(self, target, entry):
    """Write a SshekeyMapEntry to the target cache.

    Args:
      target: A file-like object.
      entry: A SshkeyMapEntry.

    Returns:
      Number of bytes written to the target.
    """
    sshkey_entry = '%s:%s' % (entry.name, entry.sshkey)
    target.write(sshkey_entry + '\n')
    return len(sshkey_entry) + 1


class FilesPasswdMapHandler(FilesCache):
  """Concrete class for updating a nss_files module passwd cache."""
  CACHE_FILENAME = 'passwd'
  _INDEX_ATTRIBUTES = ('name', 'uid')

  def __init__(self, conf, map_name=None, automount_mountpoint=None):
    if map_name is None: map_name = config.MAP_PASSWORD
    super(FilesPasswdMapHandler, self).__init__(
        conf, map_name, automount_mountpoint=automount_mountpoint)
    self.map_parser = file_formats.FilesPasswdMapParser()

  def _ExpectedKeysForEntry(self, entry):
    """Generate a list of expected cache keys for this type of map.

    Args:
      entry: A PasswdMapEntry

    Returns:
      A list of strings
    """
    return [entry.name]

  def _WriteData(self, target, entry):
    """Write a PasswdMapEntry to the target cache.

    Args:
      target: A file-like object.
      entry: A PasswdMapEntry.

    Returns:
      Number of bytes written to the target.
    """
    password_entry = '%s:%s:%d:%d:%s:%s:%s' % (entry.name, entry.passwd,
                                               entry.uid, entry.gid,
                                               entry.gecos, entry.dir,
                                               entry.shell)
    target.write(password_entry.encode() + b'\n')
    return len(password_entry) + 1


class FilesGroupMapHandler(FilesCache):
  """Concrete class for updating a nss_files module group cache."""
  CACHE_FILENAME = 'group'
  _INDEX_ATTRIBUTES = ('name', 'gid')

  def __init__(self, conf, map_name=None, automount_mountpoint=None):
    if map_name is None: map_name = config.MAP_GROUP
    super(FilesGroupMapHandler, self).__init__(
        conf, map_name, automount_mountpoint=automount_mountpoint)
    self.map_parser = file_formats.FilesGroupMapParser()

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
    target.write(group_entry.encode() + b'\n')
    return len(group_entry) + 1


class FilesShadowMapHandler(FilesCache):
  """Concrete class for updating a nss_files module shadow cache."""
  CACHE_FILENAME = 'shadow'
  _INDEX_ATTRIBUTES = ('name',)

  def __init__(self, conf, map_name=None, automount_mountpoint=None):
    if map_name is None: map_name = config.MAP_SHADOW
    super(FilesShadowMapHandler, self).__init__(
        conf, map_name, automount_mountpoint=automount_mountpoint)
    self.map_parser = file_formats.FilesShadowMapParser()

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
    target.write(shadow_entry.encode() + b'\n')
    return len(shadow_entry) + 1


class FilesNetgroupMapHandler(FilesCache):
  """Concrete class for updating a nss_files module netgroup cache."""
  CACHE_FILENAME = 'netgroup'
  _TUPLE_RE = re.compile('^\((.*?),(.*?),(.*?)\)$')  # Do this only once.

  def __init__(self, conf, map_name=None, automount_mountpoint=None):
    if map_name is None: map_name = config.MAP_NETGROUP
    super(FilesNetgroupMapHandler, self).__init__(
        conf, map_name, automount_mountpoint=automount_mountpoint)
    self.map_parser = file_formats.FilesNetgroupMapParser()

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
    if entry.entries:
      netgroup_entry = '%s %s' % (entry.name, entry.entries)
    else:
      netgroup_entry = entry.name
    target.write(netgroup_entry + '\n')
    return len(netgroup_entry) + 1


class FilesAutomountMapHandler(FilesCache):
  """Concrete class for updating a nss_files module automount cache."""
  CACHE_FILENAME = None  # we have multiple files, set as we update.

  def __init__(self, conf, map_name=None, automount_mountpoint=None):
    if map_name is None: map_name = config.MAP_AUTOMOUNT
    super(FilesAutomountMapHandler, self).__init__(
        conf, map_name, automount_mountpoint=automount_mountpoint)
    self.map_parser = file_formats.FilesAutomountMapParser()

    if automount_mountpoint is None:
      # we are dealing with the master map
      self.CACHE_FILENAME = 'auto.master'
    else:
      # turn /auto into auto.auto, and /usr/local into /auto.usr_local
      automount_mountpoint = automount_mountpoint.lstrip('/')
      self.CACHE_FILENAME = 'auto.%s' % automount_mountpoint.replace('/', '_')

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
    # Modify suffix after mountpoint for autofs
    pattern = re.compile(prefix)
    if entry.options is not None:
      if prefix != '':
        if (pattern.match(entry.location)): # Found string with regex
          entry.location = re.sub(r'({0})'.format(prefix), r'{0}'.format(suffix), entry.location)
      automount_entry = '%s %s %s' % (entry.key, entry.options, entry.location)
    else:
      automount_entry = '%s %s' % (entry.key, entry.location)
    target.write(automount_entry + '\n')
    return len(automount_entry) + 1

  def GetMapLocation(self):
    """Get the location of this map for the automount master map."""
    return self.GetCacheFilename()
