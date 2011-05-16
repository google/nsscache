#!/usr/bin/python -B
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

"""Run ALL the nss_cache tests."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import logging
import os
import sys
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
from nss_cache.sources.httpsource_test import *
from nss_cache.sources.ldapsource_test import *
from nss_cache.sources.zsyncsource_test import *
from nss_cache.update.base_test import *
from nss_cache.update.files_test import *
# buggy.
#from nss_cache.update.maps_test import *
from nss_cache.util.files_test import *


class NsscacheTestProgram(unittest.TestProgram):
  def __init__(self, *args, **kwargs):
    super(NsscacheTestProgram, self).__init__(*args, **kwargs)
    if self.verbosity >= 2:
      format_str = ('\n%(pathname)s:%(lineno)d:\n'
                    '  %(levelname)-8s %(module)s.%(funcName)s: '
                    '%(message)s')
      logging.basicConfig(stream=sys.stderr,
                          format=format_str)
      logging.getLogger().setLevel(logging.DEBUG)
    else:
      logging.disable(logging.CRITICAL)
    self.runAllTests()

  def runTests(self):
    """Don't run the tests yet, so our own constructor can do work."""

  def runAllTests(self):
    super(NsscacheTestProgram, self).runTests()


if __name__ == '__main__':
  os.chdir(os.path.dirname(sys.argv[0]))
  NsscacheTestProgram()
