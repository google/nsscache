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

"""Unit tests for nss_cache/app.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import logging
import os
import StringIO
import sys
import unittest

from nss_cache import app

logging.disable(logging.CRITICAL)


class TestNssCacheApp(unittest.TestCase):
  """Unit tests for NssCacheApp class."""

  def testRun(self):
    return_code = app.NssCacheApp().Run([], {})
    self.assertEquals(os.EX_USAGE, return_code)

  def testParseGlobalOptions(self):
    a = app.NssCacheApp()
    (options, args) = a.parser.parse_args(['-d', '-v', 'command'])
    self.failIfEqual(None, options.debug)
    self.failIfEqual(None, options.verbose)
    self.assertEqual(['command'], args)

  def testParseCommandLineDebug(self):
    a = app.NssCacheApp()
    (options, args) = a.parser.parse_args(['-d'])
    self.failIfEqual(None, options.debug)
    (options, args) = a.parser.parse_args(['--debug'])
    self.failIfEqual(None, options.debug)
    a.Run(['-d'], {})
    self.assertEquals(logging.DEBUG, a.log.getEffectiveLevel())

  def testParseCommandLineVerbose(self):
    a = app.NssCacheApp()
    (options, args) = a.parser.parse_args(['-v'])
    self.failIfEqual(None, options.verbose)
    self.assertEqual([], args)
    (options, args) = a.parser.parse_args(['--verbose'])
    self.failIfEqual(None, options.verbose)
    self.assertEqual([], args)
    a.Run(['-v'], {})
    self.assertEquals(logging.INFO, a.log.getEffectiveLevel())

  def testParseCommandLineVerboseDebug(self):
    a = app.NssCacheApp()
    a.Run(['-v', '-d'], {})
    self.assertEquals(logging.DEBUG, a.log.getEffectiveLevel())

  def testParseCommandLineConfigFile(self):
    a = app.NssCacheApp()
    (options, args) = a.parser.parse_args(['-c', 'file'])
    self.failIfEqual(None, options.config_file)
    self.assertEqual([], args)
    (options, args) = a.parser.parse_args(['--config-file', 'file'])
    self.failIfEqual(None, options.config_file)
    self.assertEqual([], args)

  def testBadOptionsCauseNoExit(self):
    a = app.NssCacheApp()
    stderr_buffer = StringIO.StringIO()
    old_stderr = sys.stderr
    sys.stderr = stderr_buffer
    self.assertEquals(2, a.Run(['--invalid'], {}))
    sys.stderr = old_stderr

  def testHelpOptionPrintsGlobalHelp(self):
    stdout_buffer = StringIO.StringIO()
    a = app.NssCacheApp()
    old_stdout = sys.stdout
    sys.stdout = stdout_buffer
    self.assertEquals(0, a.Run(['--help'], {}))
    sys.stdout = old_stdout
    self.failIfEqual(0, stdout_buffer.tell())
    (prelude, usage, commands, options) = stdout_buffer.getvalue().split('\n\n')
    self.failUnless(prelude.startswith('nsscache synchronises'))
    expected_str = 'Usage: nsscache [global options] command [command options]'
    self.failUnlessEqual(expected_str, usage)
    self.failUnless(commands.startswith('commands:'))
    self.failUnless(options.startswith('Options:'))
    self.failUnless(options.find('show this help message and exit') >= 0)

  def testHelpCommandOutput(self):
    # trap stdout into a StringIO
    stdout_buffer = StringIO.StringIO()
    a = app.NssCacheApp()
    old_stdout = sys.stdout
    sys.stdout = stdout_buffer
    self.assertEquals(0, a.Run(['help'], {}))
    sys.stdout = old_stdout
    self.failIfEqual(0, stdout_buffer.tell())
    self.failUnless(stdout_buffer.getvalue().find('nsscache synchronises') >= 0)

# TODO(jaq): app.Run() invocation of command_callable is tested by inspection
# only.

# TODO(jaq): increase betteriness of this test
#   def testRunBadArgsPrintsGlobalHelp(self):
#     # verify bad arguments calls help
#     # This will fail when run under 'nosetests -s' because nose will
#     # also intercept sys.stdout :(  (Recommend refactoring NssCacheApp
#     # to take in an output stream for help and usage?
#     output = cStringIO.StringIO()
#     stdout = sys.stdout
#     sys.stdout = output

#     return_code = app.NssCacheApp().Run(['blarg'])
#     sys.stdout = stdout

#     self.assertEquals(return_code, 1, msg='invalid return code')
#     self.assertTrue(output.getvalue().find('enable debugging') >= 0,
#                     msg='Bad argument failed to output expected help text')

  # TODO(jaq):  test terminal logging (syslog versus stdout)

  # TODO(jaq): these two tests fail because logging is being imported at the
  # top of this file before nss_cache.app and thus the logger class is not
  # set correctly
  # def testDebug2LoggingLevel(self):
  #   class test_handler(logging.Handler):
  #     def __init__(self):
  #       logging.Handler.__init__(self)
  #       #self.setLevel(logging.DEBUG)
  #       self.levels = []

  #     def emit(self, record):
  #       print record
  #       self.levels.append(record.levelno)
  #       print self.levels

  #   handler = test_handler()
  #   a = app.NssCacheApp()
  #   print "log:", a.log
  #   a.log.addHandler(handler)
  #   a.log.debug2('logged at level debug2')
  #   print handler.levels
  #   self.failUnless(5 in handler.levels)

  # def testVerboseLoggingLevel(self):
  #   a = app.NssCacheApp()
  #   a.log.verbose('logged at level verbose')


if __name__ == '__main__':
  unittest.main()
