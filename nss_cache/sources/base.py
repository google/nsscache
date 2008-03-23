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

"""Base class of data source object for nss_cache."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import logging

_source_implementations = {}


def RegisterImplementation(source):
  """Register a Source implementation with the factory method.

  Sources being registered are expected to have a name attribute,
  unique to themselves.

  Child modules are expected to call this method in the file-level
  scope.

  Args:
    source: A class type that is a subclass of Source

  Returns:
    Nothing

  Raises:
    RuntimeError: no 'name' entry in this source.
  """
  if 'name' not in source.__dict__:
    raise RuntimeError("'name' not defined in Source %r" % (source,))

  _source_implementations[source.name] = source


def Create(config):
  """Source creation factory method.

  Args:
   config: a dictionary of configuration key/value pairs, including one
           required attribute 'name'.

  Returns:
    A Source instance.

  Raises:
    RuntimeError: no sources are registered with RegisterImplementation
  """
  if not _source_implementations:
    raise RuntimeError('no source implementations exist')

  source_name = config['name']

  if source_name not in _source_implementations.keys():
    raise RuntimeError('source not implemented: %r' % (source_name,))

  return _source_implementations[source_name](config)


class Source(object):
  """Abstract base class for map data sources."""

  def __init__(self, config):
    """Initialise the Source object.

    Args:
      config: A dictionary of key/value pairs.

    Raises:
      RuntimeError: object wasn't initialised with a dict
    """
    if not isinstance(config, dict):
      raise RuntimeError('Source constructor not passed a dictionary')

    self.config = config

    # create a logger for our children
    self.log = logging.getLogger(self.__class__.__name__)

  def Verify(self):
    """Perform verification of the source availability.

    Attempt to open/connect or otherwise use the data source, and report if
    there are any problems.
    """
    raise NotImplementedError
