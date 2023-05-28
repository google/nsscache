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
"""Package level factory implementation for cache implementations.

We use a factory instead of relying on the __init__.py module to
register cache implementations at import time.  This is much more
reliable.
"""

__author__ = "springer@google.com (Matthew Springer)"

import logging

from nss_cache.caches import files

_cache_implementations = {}


def RegisterImplementation(cache_name, map_name, cache):
    """Register a Cache implementation with the CacheFactory.

    Child modules are expected to call this method in the file-level scope
    so that the CacheFactory is aware of them.

    Args:
      cache_name: (string) The name of the NSS backend.
      map_name: (string) The name of the map handled by this Cache.
      cache: A class type that is a subclass of Cache.

    Returns: Nothing
    """
    global _cache_implementations
    if cache_name not in _cache_implementations:
        logging.info("Registering [%s] cache for [%s].", cache_name, map_name)
        _cache_implementations[cache_name] = {}
    _cache_implementations[cache_name][map_name] = cache


def Create(conf, map_name, automount_mountpoint=None):
    """Cache creation factory method.

    Args:
     conf: a dictionary of configuration key/value pairs, including one
       required attribute 'name'
     map_name: a string identifying the map name to handle
     automount_mountpoint: A string containing the automount mountpoint, used only
       by automount maps.

    Returns:
      an instance of a Cache

    Raises:
      RuntimeError: problem instantiating the requested cache
    """
    global _cache_implementations
    if not _cache_implementations:
        raise RuntimeError("no cache implementations exist")
    cache_name = conf["name"]

    if cache_name not in _cache_implementations:
        raise RuntimeError("cache not implemented: %r" % (cache_name,))
    if map_name not in _cache_implementations[cache_name]:
        raise RuntimeError("map %r not supported by cache %r" % (map_name, cache_name))

    return _cache_implementations[cache_name][map_name](
        conf, map_name, automount_mountpoint=automount_mountpoint
    )


files.RegisterAllImplementations(RegisterImplementation)
