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


# pylint: disable-msg=W0401
from nss_cache.app_test import *
from nss_cache.command_test import *
from nss_cache.config_test import *
from nss_cache.error_test import *
from nss_cache.nss_test import *
from nss_cache.lock_test import *

from nss_cache.caches.caches_test import *
from nss_cache.caches.cache_factory_test import *
from nss_cache.caches.files_test import *
from nss_cache.caches.nssdb_test import *

from nss_cache.maps.maps_test import *
from nss_cache.maps.automount_test import *
from nss_cache.maps.group_test import *
from nss_cache.maps.netgroup_test import *
from nss_cache.maps.passwd_test import *
from nss_cache.maps.shadow_test import *


from nss_cache.sources.source_test import *
from nss_cache.sources.source_factory_test import *
from nss_cache.sources.consulsource_test import *
from nss_cache.sources.httpsource_test import *
from nss_cache.sources.ldapsource_test import *

from nss_cache.update.updater_test import *
from nss_cache.update.map_updater_test import *
# This test conflicts with the previous.
#from nss_cache.update.files_updater_test import *

from nss_cache.util.file_formats_test import *
from nss_cache.util.timestamps_test import *


class NsscacheTestProgram(unittest.TestProgram):
  """Run nsscache tests.

  Wraps the TestProgram class to set the logging output based on the
  test verbosity.
  """
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

  # pylint: disable-msg=C6409
  def runTests(self):
    """Don't run the tests yet, so our own constructor can do work."""

  # pylint: disable-msg=C6409
  def runAllTests(self):
    super(NsscacheTestProgram, self).runTests()


if __name__ == '__main__':
  os.chdir(os.path.dirname(sys.argv[0]))
  NsscacheTestProgram()
