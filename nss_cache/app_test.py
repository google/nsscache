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
import io
import os
import sys
import unittest

from nss_cache import app


class TestNssCacheApp(unittest.TestCase):
    """Unit tests for NssCacheApp class."""

    def setUp(self):
        dev_null = io.StringIO()
        self.stdout = sys.stdout
        sys.stdout = dev_null

    def tearDown(self):
        sys.stdout = self.stdout

    def testRun(self):
        return_code = app.NssCacheApp().Run([], {})
        self.assertEqual(os.EX_USAGE, return_code)

    def testParseGlobalOptions(self):
        a = app.NssCacheApp()
        (options, args) = a.parser.parse_args(['-d', '-v', 'command'])
        self.assertNotEqual(None, options.debug)
        self.assertNotEqual(None, options.verbose)
        self.assertEqual(['command'], args)

    def testParseCommandLineDebug(self):
        a = app.NssCacheApp()
        (options, args) = a.parser.parse_args(['-d'])
        self.assertNotEqual(None, options.debug)
        (options, args) = a.parser.parse_args(['--debug'])
        self.assertNotEqual(None, options.debug)
        a.Run(['-d'], {})
        self.assertEqual(logging.DEBUG, a.log.getEffectiveLevel())

    def testParseCommandLineVerbose(self):
        a = app.NssCacheApp()
        (options, args) = a.parser.parse_args(['-v'])
        self.assertNotEqual(None, options.verbose)
        self.assertEqual([], args)
        (options, args) = a.parser.parse_args(['--verbose'])
        self.assertNotEqual(None, options.verbose)
        self.assertEqual([], args)
        a.Run(['-v'], {})
        self.assertEqual(logging.INFO, a.log.getEffectiveLevel())

    def testParseCommandLineVerboseDebug(self):
        a = app.NssCacheApp()
        a.Run(['-v', '-d'], {})
        self.assertEqual(logging.DEBUG, a.log.getEffectiveLevel())

    def testParseCommandLineConfigFile(self):
        a = app.NssCacheApp()
        (options, args) = a.parser.parse_args(['-c', 'file'])
        self.assertNotEqual(None, options.config_file)
        self.assertEqual([], args)
        (options, args) = a.parser.parse_args(['--config-file', 'file'])
        self.assertNotEqual(None, options.config_file)
        self.assertEqual([], args)

    def testBadOptionsCauseNoExit(self):
        a = app.NssCacheApp()
        stderr_buffer = io.StringIO()
        old_stderr = sys.stderr
        sys.stderr = stderr_buffer
        self.assertEqual(2, a.Run(['--invalid'], {}))
        sys.stderr = old_stderr

    def testHelpOptionPrintsGlobalHelp(self):
        stdout_buffer = io.StringIO()
        a = app.NssCacheApp()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        self.assertEqual(0, a.Run(['--help'], {}))
        sys.stdout = old_stdout
        self.assertNotEqual(0, stdout_buffer.tell())
        (prelude, usage, commands,
         options) = stdout_buffer.getvalue().split('\n\n')
        self.assertTrue(prelude.startswith('nsscache synchronises'))
        expected_str = 'Usage: nsscache [global options] command [command options]'
        self.assertEqual(expected_str, usage)
        self.assertTrue(commands.startswith('commands:'))
        self.assertTrue(options.startswith('Options:'))
        self.assertTrue(options.find('show this help message and exit') >= 0)

    def testHelpCommandOutput(self):
        # trap stdout into a StringIO
        stdout_buffer = io.StringIO()
        a = app.NssCacheApp()
        old_stdout = sys.stdout
        sys.stdout = stdout_buffer
        self.assertEqual(0, a.Run(['help'], {}))
        sys.stdout = old_stdout
        self.assertNotEqual(0, stdout_buffer.tell())
        self.assertTrue(
            stdout_buffer.getvalue().find('nsscache synchronises') >= 0)


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


if __name__ == '__main__':
    unittest.main()
