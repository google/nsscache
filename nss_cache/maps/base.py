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

"""Base class of maps for nsscache.

Map:  Abstract class representing a basic NSS map.
MapEntry:  Abstract class representing an entry in a NSS map.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import logging


class Map(object):
  """Abstract class representing a basic NSS map.
  
  Map data is stored internally as a dict of MapEntry objects, with
  the key as the unique value provided by MapEntry.Key().
  
  MapEntry.Key() is implemented by returning the attribute value for
  some attribute which is expected to be unique, e.g. the name of a
  user or the name of a group.
  
  This allows for a fast implementation of __contains__() although
  it restricts Map objects from holding two MapEntry objects with
  the same keys (e.g. no two entries for root allowed).  This is
  considered an acceptable restriction as posix semantics imply that
  entries are unique in each map with respect to certain attributes.

  Each time a MapEntry is added to a Map, the Map is registered with
  the MapEntry so that a change to the MapEntry.Key() attribute is
  reflected in the MapEntry's containers.  The inverse is done on
  remove.

  A Map also stores two timestamps; a "last update timestamp" which
  is set every time an update/merge operation occurs on a map, and a
  "last modification timestamp", which stores the last time that
  fresh data was merged into the map.
  """
  
  def __init__(self, iterable):
    """Construct a Map object."""
    if self.__class__ is Map:
      raise TypeError('Map is an abstract class.')
    self._data = {}
    # Last mod timestamp should be either None or an integer number
    # of seconds since the epoch.  (aka unix time_t)
    self._last_modification_timestamp = None
    # Last update timestamp, same as previous
    self._last_update_timestamp = None
    
    self.log = logging.getLogger(self.__class__.__name__)

    # Seed with iterable, should raise TypeError for bad items.
    if type(iterable) in (tuple, list):
      for item in iterable:
        self.Add(item)

  def __contains__(self, other):
    """Deep compare on a MapEntry."""
    key = other.Key()
    if key in self._data:
      possibility = self._data[key]
      if other == possibility:
        return True
    return False

  def __iter__(self):
    """Iterate over the MapEntry objects in this map."""
    return iter(self._data.values())

  def __len__(self):
    """Returns the number of items in the map."""
    return len(self._data)

  def __repr__(self):
    return '<%s: %r>' % (self.__class__.__name__, self._data)

  def Add(self, entry):
    """Add a MapEntry object to the dict and verify.  Will overwrite.."""

    # Correct type?
    if not isinstance(entry, MapEntry):
      raise TypeError('Not instance of MapEntry')

    # Entry okay?
    if not entry.Verify():
      self.log.info('refusing to add entry, verify failed')
      return False

    # Register/Unregister, depending on if we are overwriting an
    # entry or just adding a new one.  Registering/UnRegistering
    # does no harm, so if entry == oldentry we don't care.
    key = entry.Key()
    if key in self._data:
      oldentry = self._data[key]
      oldentry.UnRegister(self)
    self._data[key] = entry
    entry.Register(self)

    return True

  def Exists(self, entry):
    """Return True if entry is in Map, False if not.  Does deep compare."""
    if entry in self:
      return True
    return False

  def Merge(self, other):
    """Update this Map based on another Map.

    Walk over other and for each entry, Add() it if it doesn't
    exist -- this will update changed entries as well as adding
    new ones.

    Args:
      other: Another Map object.
    
    Returns:
      True if anything was added or modified, False if
      nothing changed.

    Raises:
      TypeError: Merging differently typed Maps.
    """
    if type(self) != type(other):
      raise TypeError(
          'Attempt to Merge() differently typed Maps: %r != %r' %
          (type(self), type(other)))

    self.log.info('merging from a map of %d entries', len(other))

    merge_count = 0
    for their_entry in other:
      if their_entry not in self:
        # Add() will overwrite similar entries if they exist
        if self.Add(their_entry):
          merge_count += 1
    self.log.info('%d of %d entries were new or modified',
                  merge_count, len(other))

    if merge_count > 0:
      self.SetModifyTimestamp(other.GetModifyTimestamp())

    # set last update timestamp
    self.SetUpdateTimestamp(other.GetUpdateTimestamp())

    return merge_count > 0

  def PopItem(self):
    """Return a MapEntry object, throw KeyError if none exist."""
    (unused_key, value) = self._data.popitem()  #Throws KeyError if empty.
    value.UnRegister(self)
    return value

  def Remove(self, entry):
    """Removes and returns an entry from a Map, if present."""
    key = entry.Key()
    try:
      possible_entry = self._data.pop(key)
    except KeyError:
      return None
    if possible_entry == entry:
      possible_entry.UnRegister(self)
      return possible_entry
    else:
      self._data[key] = possible_entry  # put it back
      return None

  def UpdateKey(self, old_key, new_key):
    """Replace an old_key with a new_key."""
    try:
      value = self._data.pop(old_key)
    except KeyError:
      return False
    self._data[new_key] = value
    return True

  def SetModifyTimestamp(self, value):
    """Set the last modify timestamp of this map."""
    if value is None or isinstance(value, int):
      self._last_modification_timestamp = value
    else:
      raise TypeError('timestamp can only be int or None, not %r',
                      value)

  def GetModifyTimestamp(self):
    """Return last modification timestamp of this map."""
    return self._last_modification_timestamp

  def SetUpdateTimestamp(self, value):
    """Set the last update timestamp of this map."""
    if value is None or isinstance(value, int):
      self._last_update_timestamp = value
    else:
      raise TypeError('timestamp can only be int or None, not %r',
                      value)

  def GetUpdateTimestamp(self):
    """Return last update timestamp of this map."""
    return self._last_update_timestamp

  #TODO(v):  write Get() to do an imutable fetch of specific MapEntry.


class MapEntry(object):
  """Abstract class for representing an entry in an NSS map.
  
  Map data is stored internally as a dict, we expect to be contained
  in MapEntry objects and provide a unique identifier via Key() so
  that MapEntry objects can properly index us.  See the MapEntry
  class for more details.
  """

  # TODO(v):  clean up req_keys/types/pkey to be less confusing.
  def __init__(self, pkey, req_keys, types, data=None):
    """This is an abstract class.

    We intialize a few private attributes, then add any data to
    the MapEntry that was handed to us.  Expected private
    attributes are:

    Args:
      pkey:  Name of an attribute whose value is to be used as our
      unique identifier.
      req_keys:  tuple of keys which have no default value, ones that
      must be present in a MapEntry.
      types:  dict of attribute names and their expected types.
      The expected types can be either a single type, e.g. str or
      int, or it can be a tuple of types.
      data:  optional dict of attribute, value pairs.

    Raises:
      TypeError:  Bad argument, or attempt to instantiate abstract class.
    """

    if self.__class__ is MapEntry:
      raise TypeError('MapEntry is an abstract class.')

    # Sanity check arguments.
    if type(pkey) != str:
      raise TypeError('pkey is not a string.')
    else:
      self._pkey = pkey
    if type(req_keys) not in (list, tuple):
      raise TypeError('req_keys neither list nor tuple.')
    else:
      self._req_keys = req_keys
    if type(types) is not dict:
      raise TypeError('types expected to be dict.')
    else:
      self._types = types

    # Initialize internal data structures.
    self._data = {}
    self._registered = []

    # Initialize from dict, if passed.
    if data is None:
      return
    else:
      for key in data:
        self.Set(key, data[key])

    # Setup logging.  Note the __setattr__() override below is
    # necessary to avoid calling self.Set('log', logger) which
    # will correctly fail.
    logger = logging.getLogger(self.__class__.__name__)
    super(MapEntry, self).__setattr__('log', logger)

  def __eq__(self, other):
    """Deep comparison of two MapEntry objects."""
    if type(self) != type(other):
      return False
    for key in self._types:
      if self.Get(key) != other.Get(key):
        return False
    return True

  def __getattr__(self, name):
    """Force all attribute reads through self.Get()."""
    # skip override for private attributes like self._data by using the
    # parent's getattr method which is unmodified (unlike this one).
    if name.startswith('_'):
      return super(MapEntry, self).__getattr__(name)
    return self.Get(name)

  def __setattr__(self, name, value):
    """Force all attribute writes through self.Set()."""
    # skip override for private attributes like self._data by using the
    # parent's setattr method which is unmodified (unlike this one).
    if name.startswith('_'):
      return super(MapEntry, self).__setattr__(name, value)
    return self.Set(name, value)

  def __repr__(self):
    """String representation."""
    return '<%s : %r>' % (self.__class__.__name__, self._data)

  def Key(self):
    """Return unique identifier for this MapEntry object."""
    return self.Get(self._pkey)

  def Get(self, attr):
    """Get attribute, throw AttributeError if unknown attribute."""
    if attr in self._data: return self._data[attr]
    raise AttributeError('Can not get unknown attribute %s' % attr)

  def Register(self, map_object):
    """Register a map so we can update indexes on primary key changes."""
    self._registered.append(map_object)

  def Set(self, attr, value):
    """Set attribute, verify it."""

    # Check for unknown keys
    if attr not in self._types:
      raise AttributeError('Can not set unknown attribute %s' % attr)

    # Update any registered maps
    if attr == self._pkey:
      for registered in self._registered:
        if not registered.UpdateKey(self._data[attr], value):
          raise AttributeError('Unexpected failure updating Map')

    # Set and return!
    self._data[attr] = value
    return self.Verify(attr)

  def UnRegister(self, map_object):
    """Remove a map from a list of registered maps."""
    self._registered.remove(map_object)

  def Verify(self, attr=None):
    """Verify either the whole object, or a single attribute."""
    if attr is not None:
      return self._VerifyAttr(attr)

    return self._VerifyObj()

  def _VerifyAttr(self, attr):
    """Verify a single attribute and return True or raise an exception."""
    types = self._types[attr]
    value = self._data[attr]
    
    if not isinstance(types, tuple):
      types = (types,)  # set a tuple for below
      
    # Verify attribute is of the appropriate type.
    verified = False  # I hate flags like this
    for type_value in types:
      if type_value is None:
        if value is None: verified = True
      else:
        if isinstance(value, type_value):
          verified = True

    if verified:
      return True

    raise AttributeError('Bad attribute data for %r: %r', attr, value)

  def _VerifyObj(self):
    """Verify every attribute in the object."""

    # Verify each attribute.
    for attr in self._types:
      try:
        self.Verify(attr)
      except AttributeError, e:
        self.log.debug('attribute %s failed Verify() with error %s'
                       ' in %s', attr, e, self.__class__)
        return False

    # Check for required keys.
    required_keys = 0
    for key in self._req_keys:
      if key in self._data:
        required_keys += 1
      else:
        self.log.debug('key "%s" missing or bad in %s', key,
                       self.__class__)

    if required_keys == len(self._req_keys):
      return True

    return False
