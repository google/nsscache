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

"""Module __init__ for nss_cache.sources."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

from nss_cache.sources import base
from nss_cache.sources import httpsource
from nss_cache.sources import ldapsource
# Don't load the zsync source if zsync python module isn't there.
try:
  from nss_cache.sources import zsyncsource
except ImportError:
  pass
