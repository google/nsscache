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
"""Exception classes for nss_cache module."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'


class Error(Exception):
    """Base exception class for nss_cache."""
    pass


class CacheNotFound(Error):
    """Raised when a local cache is missing."""
    pass


class CacheInvalid(Error):
    """Raised when a cache is invalid."""
    pass


class CommandParseError(Error):
    """Raised when the command line fails to parse correctly."""
    pass


class ConfigurationError(Error):
    """Raised when there is a problem with configuration values."""
    pass


class EmptyMap(Error):
    """Raised when an empty map is discovered and one is not expected."""
    pass


class NoConfigFound(Error):
    """Raised when no configuration file is loaded."""
    pass


class PermissionDenied(Error):
    """Raised when nss_cache cannot access a resource."""
    pass


class UnsupportedMap(Error):
    """Raised when trying to use an unsupported map type."""
    pass


class InvalidMap(Error):
    """Raised when an invalid map is encountered."""
    pass


class SourceUnavailable(Error):
    """Raised when a source is unavailable."""
    pass


class InvalidMerge(Error):
    """An invalid merge was attempted."""
