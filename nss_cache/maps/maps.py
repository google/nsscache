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

"""Base class of maps for nsscache.

Map:  Abstract class representing a basic NSS map.
MapEntry:  Abstract class representing an entry in a NSS map.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import logging

from nss_cache import error


class Map(object):
  """Abstract class representing a basic NSS map.

  Map data is stored internally as a dict of MapEntry objects, with
  the key being the unique value provided by MapEntry.Key().

  MapEntry.Key() is implemented by returning the attribute value for
  some attribute which is expected to be unique, e.g. the name of a
  user or the name of a group.

  This allows for a fast implementation of __contains__() although
  it restricts Map objects from holding two MapEntry objects with
  the same keys (e.g. no two entries for root allowed).  This is
  considered an acceptable restriction as posix semantics imply that
  entries are unique in each map with respect to certain attributes.

  A Map also stores two timestamps; a "last update timestamp" which
  is set every time an update/merge operation occurs on a map, and a
  "last modification timestamp", which stores the last time that
  fresh data was merged into the map.

  N.B.  Changing the MapEntry().Key() after adding to a Map() will
  corrupt the index...so don't do it.

  Attributes:
    log: A logging.Logger instance used for output.
  """

  def __init__(self, iterable=None, modify_time=None, update_time=None):
    """Construct a Map object.

    Args:
      iterable: A tuple or list that can be iterated over and added to the Map,
        defaults to None.
      modify_time: An optional modify time for this Map, defaults to None.
        defaults to None.
      update_time: An optional update time for this Map, defaults to None.
         defaults to None.

    Raises:
      TypeError: If the objects in the iterable are of the wrong type.
    """
    if self.__class__ is Map:
      raise TypeError('Map is an abstract class.')
    self._data = {}
    self._last_modification_timestamp = modify_time
    self._last_update_timestamp = update_time

    self.log = logging.getLogger(self.__class__.__name__)

    # Seed with iterable, should raise TypeError for bad items.
    if iterable is not None:
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
    """Add a MapEntry object to the Map and verify it (overwrites).

    Args:
      entry: A maps.MapEntry instance.

    Returns:
      A boolean indicating the add is successfull when True.

    Raises:
      TypeError: The object passed is not the right type.
    """

    # Correct type?
    if not isinstance(entry, MapEntry):
      raise TypeError('Not instance of MapEntry')

    # Entry okay?
    if not entry.Verify():
      self.log.info('refusing to add entry, verify failed')
      return False

    self._data[entry.Key()] = entry
    return True

  def Exists(self, entry):
    """Deep comparison of a MapEntry to the MapEntry instances in the Map.

    Args:
      entry: A maps.MapEntry instance.

    Returns:
      A boolean indicating the object is present when True.
    """
    if entry in self:
      return True
    return False

  def Merge(self, other):
    """Update this Map based on another Map.

    Walk over other and for each entry, Add() it if it doesn't
    exist -- this will update changed entries as well as adding
    new ones.

    Args:
      other: A maps.Map instance.

    Returns:
      True if anything was added or modified, False if
      nothing changed.

    Raises:
      TypeError: Merging differently typed Maps.
      InvalidMerge: Attempt to Merge an older map into a newer one.
    """
    if type(self) != type(other):
      raise TypeError(
          'Attempt to Merge() differently typed Maps: %r != %r' %
          (type(self), type(other)))

    if other.GetModifyTimestamp() < self.GetModifyTimestamp():
      raise error.InvalidMerge(
          'Attempt to Merge a map with an older modify time into a newer one: '
          'other: %s, self: %s' %
          (other.GetModifyTimestamp(), self.GetModifyTimestamp()))

    if other.GetUpdateTimestamp() < self.GetUpdateTimestamp():
      raise error.InvalidMerge(
          'Attempt to Merge a map with an older update time into a newer one: '
          'other: %s, self: %s' %
          (other.GetUpdateTimestamp(), self.GetUpdateTimestamp()))

    self.log.info('merging from a map of %d entries', len(other))

    merge_count = 0
    for their_entry in other:
      if their_entry not in self:
        # Add() will overwrite similar entries if they exist.
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
    """Return a MapEntry object, throw KeyError if none exist.

    Returns:
      A maps.MapEntry from within maps.Map internal dict.

    Raises:
      KeyError if there is nothing to return
    """
    (unused_key, value) = self._data.popitem()  #Throws KeyError if empty.
    return value

  def SetModifyTimestamp(self, value):
    """Set the last modify timestamp of this map.

    Args:
      value: An integer containing the number of seconds since epoch, or None.

    Raises:
      TypeError: The argument is not an int or None.
    """
    if value is None or isinstance(value, int):
      self._last_modification_timestamp = value
    else:
      raise TypeError('timestamp can only be int or None, not %r'
                      % value)

  def GetModifyTimestamp(self):
    """Return last modification timestamp of this map.

    Returns:
      Either an int containing seconds since epoch, or None.
    """
    return self._last_modification_timestamp

  def SetUpdateTimestamp(self, value):
    """Set the last update timestamp of this map.

    Args:
      value:  An int containing seconds since epoch, or None.

    Raises:
      TypeError: The argument is not an int or None.
    """
    if value is None or isinstance(value, int):
      self._last_update_timestamp = value
    else:
      raise TypeError('timestamp can only be int or None, not %r',
                      value)

  def GetUpdateTimestamp(self):
    """Return last update timestamp of this map.

    Returns:
      An int containing seconds since epoch, or None.
    """
    return self._last_update_timestamp


class MapEntry(object):
  """Abstract class for representing an entry in an NSS map.

  We expect to be contained in MapEntry objects and provide a unique identifier
  via Key() so that Map objects can properly index us.  See the Map class for
  more details.

  Attributes:
    log: A logging.Logger instance used for output.
  """
  # Using slots saves us over 2x memory on large maps.
  __slots__ = ('_KEY', '_ATTRS', 'log')
  # Overridden in the derived classes
  _KEY = None
  _ATTRS = None

  def __init__(self, data=None):
    """This is an abstract class.

    Args:
      data:  An optional dict of attribute, value pairs to populate with.

    Raises:
      TypeError:  Bad argument, or attempt to instantiate abstract class.
    """
    if self.__class__ is MapEntry:
      raise TypeError('MapEntry is an abstract class.')

    # Initialize from dict, if passed.
    if data is None:
      return
    else:
      for key in data:
        setattr(self, key, data[key])

    self.log = logging.getLogger(self.__class__.__name__)

  def __eq__(self, other):
    """Deep comparison of two MapEntry objects."""
    if type(self) != type(other):
      return False
    for key in self._ATTRS:
      if getattr(self, key) != getattr(other, key, None):
        return False
    return True

  def __repr__(self):
    """String representation."""
    rep = ''
    for key in self._ATTRS:
      rep = '%r:%r %s' % (key, getattr(self, key), rep)
    return '<%s : %r>' % (self.__class__.__name__, rep.rstrip())

  def Key(self):
    """Return unique identifier for this MapEntry object.

    Returns:
      A str which contains the name of the attribute to be used as an index
      value for a maps.MapEntry instance in a maps.Map.
    """
    return getattr(self, self._KEY)

  def Verify(self):
    """We can properly index this instance into a Map.

    Returns:
      True if the value in the attribute named by self._KEY for this class
      is not None.  False otherwise.
    """
    return getattr(self, self._KEY) is not None
