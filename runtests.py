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

"""Run all the nss_cache tests."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import unittest

from nss_cache.app_test import *
from nss_cache.caches.base_test import *
from nss_cache.caches.files_test import *
from nss_cache.caches.nssdb_test import *
from nss_cache.command_test import *
from nss_cache.config_test import *
from nss_cache.error_test import *
from nss_cache.maps.base_test import *
from nss_cache.maps.group_test import *
from nss_cache.maps.passwd_test import *
from nss_cache.maps.shadow_test import *
from nss_cache.nss_test import *
from nss_cache.sources.base_test import *
from nss_cache.sources.ldapsource_test import *

if __name__ == '__main__':
  unittest.main()
