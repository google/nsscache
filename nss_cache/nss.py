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

"""NSS utility library."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import pwd
import grp
import spwd
import logging
import subprocess

from nss_cache import config
from nss_cache import error
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow

# TODO(v): this should be a config option someday, but it's as standard
# as libc so at the moment we'll leave it be for simplicity.
GETENT = '/usr/bin/getent'


def GetMap(map_name):
  """Retrieves a Map of type map_name via nss calls."""

  if map_name == config.MAP_PASSWORD:
    return GetPasswdMap()
  elif map_name == config.MAP_GROUP:
    return GetGroupMap()
  elif map_name == config.MAP_SHADOW:
    return GetShadowMap()

  raise error.UnsupportedMap


def GetPasswdMap():
  """Returns a PasswdMap built from nss calls."""
  passwd_map = passwd.PasswdMap()

  for nss_entry in pwd.getpwall():
    map_entry = passwd.PasswdMapEntry()
    map_entry.name = nss_entry[0]
    map_entry.passwd = nss_entry[1]
    map_entry.uid = nss_entry[2]
    map_entry.gid = nss_entry[3]
    map_entry.gecos = nss_entry[4]
    map_entry.dir = nss_entry[5]
    map_entry.shell = nss_entry[6]
    passwd_map.Add(map_entry)

  return passwd_map


def GetGroupMap():
  """Returns a GroupMap built from nss calls."""
  group_map = group.GroupMap()

  for nss_entry in grp.getgrall():
    map_entry = group.GroupMapEntry()
    map_entry.name = nss_entry[0]
    map_entry.passwd = nss_entry[1]
    map_entry.gid = nss_entry[2]
    map_entry.members = nss_entry[3]
    if not map_entry.members:
      map_entry.members = ['']
    group_map.Add(map_entry)

  return group_map


def GetShadowMap():
  """Returns a ShadowMap built from nss calls."""
  shadow_map = shadow.ShadowMap()

  for nss_entry in spwd.getspall():
    map_entry = shadow.ShadowMapEntry()
    map_entry.name = nss_entry[0]
    map_entry.passwd = nss_entry[1]
    map_entry.lstchg = nss_entry[2]
    map_entry.min = nss_entry[3]
    map_entry.max = nss_entry[4]
    map_entry.warn = nss_entry[5]
    map_entry.inact = nss_entry[6]
    map_entry.expire = nss_entry[7]
    map_entry.flag = nss_entry[8]
    shadow_map.Add(map_entry)

  return shadow_map
