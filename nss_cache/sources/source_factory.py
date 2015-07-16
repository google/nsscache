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

"""Factory for data source implementations."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')


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
  global _source_implementations
  if 'name' not in source.__dict__:
    raise RuntimeError("'name' not defined in Source %r" % (source,))

  _source_implementations[source.name] = source


# Discover all the known implementations of sources.
from nss_cache.sources import httpsource
from nss_cache.sources import ldapsource
from nss_cache.sources import consulsource

httpsource.RegisterImplementation(RegisterImplementation)
ldapsource.RegisterImplementation(RegisterImplementation)
consulsource.RegisterImplementation(RegisterImplementation)

# Don't load the zsync source if zsync python module isn't there.
try:
  from nss_cache.sources import zsyncsource
  zsyncsource.RegisterImplementation(RegisterImplementation)
except ImportError:
  pass


def Create(conf):
  """Source creation factory method.

  Args:
   conf: a dictionary of configuration key/value pairs, including one
           required attribute 'name'.

  Returns:
    A Source instance.

  Raises:
    RuntimeError: no sources are registered with RegisterImplementation
  """
  global _source_implementations
  if not _source_implementations:
    raise RuntimeError('no source implementations exist')

  source_name = conf['name']

  if source_name not in _source_implementations.keys():
    raise RuntimeError('source not implemented: %r' % (source_name,))

  return _source_implementations[source_name](conf)
