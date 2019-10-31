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
"""Main program body for nsscache.

The nsscache program is the user interface to the nss_cache package,
responsible for updating or building local persistent cache, e.g. nss_db.
"""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import logging
import logging.handlers
import optparse
import os
import socket
import sys

import nss_cache
from nss_cache import command
from nss_cache import config
from nss_cache import error

# Hack to support python 2.3's logging module
try:
  BaseLoggingClass = logging.getLoggerClass()
except AttributeError:
  BaseLoggingClass = logging.Logger


class NssCacheLogger(BaseLoggingClass):
  """Custom logger class for nss_cache.

  This class defines two extra logging levels, VERBOSE which is for
  messages that can be hidden unless asked for with -v, and DEBUG2
  for really chatty implementation details.
  """

  def __init__(self, name):
    logging.Logger.__init__(self, name)
    logging.VERBOSE = logging.INFO - 1
    logging.addLevelName(logging.VERBOSE, 'VERBOSE')
    logging.DEBUG2 = logging.DEBUG - 1
    logging.addLevelName(logging.DEBUG2, 'DEBUG2')

  def verbose(self, msg, *args, **kwargs):
    self.log(logging.VERBOSE, msg, args, kwargs)

  def debug2(self, msg, *args, **kwargs):
    self.log(logging.DEBUG2, msg, args, kwargs)


logging.setLoggerClass(NssCacheLogger)


class NssCacheApp(object):
  """Main application for building/updating NSS caches."""

  def __init__(self):
    """Set up the application.

    See the file README.style for logging policy set up here.
    """
    # default to syslog unless on a tty
    try:
      is_tty = os.isatty(sys.stdin.fileno())
    except ValueError:
      is_tty = False
    if is_tty:
      format_str = ('%(levelname)-8s %(asctime)-15s '
                    '%(filename)s:%(lineno)d: '
                    '%(funcName)s: '
                    '%(message)s')
      logging.basicConfig(format=format_str)
      # python2.3's basicConfig doesn't let you set the default level
      logger = logging.getLogger()
      logger.setLevel(logging.WARN)
    else:
      facility = logging.handlers.SysLogHandler.LOG_DAEMON
      try:
        handler = logging.handlers.SysLogHandler(
            address='/dev/log', facility=facility)
      except socket.error:
        print('/dev/log could not be opened; falling back on stderr.')
        # Omitting an argument to StreamHandler results in sys.stderr being
        # used.
        handler = logging.StreamHandler()
      format_str = (
          os.path.basename(sys.argv[0]) +
          '[%(process)d]: %(levelname)s %(message)s')
      fmt = logging.Formatter(format_str)
      handler.setFormatter(fmt)
      handler.setLevel(level=logging.INFO)
      logging.getLogger('').addHandler(handler)

    self.log = logging.getLogger('NSSCacheApp')
    self.parser = self._GetParser()

  def _GetParser(self):
    """Sets up our parser for global options.

    Args:  None
    Returns:
    # OptionParser is from standard python module optparse
    OptionParser
    """
    usage = ('nsscache synchronises a local NSS cache against a '
             'remote data source.\n'
             '\n'
             'Usage: nsscache [global options] command [command options]\n'
             '\n'
             'commands:\n')
    command_descriptions = []
    for (name, cls) in list(command.__dict__.items()):
      # skip the command base object
      if name == 'Command':
        continue
      if hasattr(cls, 'Help'):
        short_help = cls().Help(short=True)
        command_descriptions.append(
            '  %-21s %.40s' % (name.lower(), short_help.lower()))

    usage += '\n'.join(command_descriptions)
    version_string = ('nsscache ' + nss_cache.__version__ + '\n'
                      '\n'
                      'Copyright (c) 2007 Google, Inc.\n'
                      'This is free software; see the source for copying '
                      'conditions.  There is NO\n'
                      'warranty; not even for MERCHANTABILITY or FITNESS '
                      'FOR A PARTICULAR PURPOSE.\n'
                      '\n'
                      'Written by Jamie Wilkinson and Vasilios Hoffman.')

    parser = optparse.OptionParser(usage, version=version_string)

    # We do not mix arguments and flags!
    parser.disable_interspersed_args()

    # Add options.
    parser.set_defaults(verbose=False, debug=False)
    parser.add_option(
        '-v', '--verbose', action='store_true', help='enable verbose output')
    parser.add_option(
        '-d', '--debug', action='store_true', help='enable debugging output')
    parser.add_option(
        '-c',
        '--config-file',
        type='string',
        help='read configuration from FILE',
        metavar='FILE')

    # filthy monkeypatch hack to remove the prepended 'usage: '
    # TODO(jaq): we really ought to subclass OptionParser instead...
    old_get_usage = parser.get_usage

    def get_usage():
      return old_get_usage()[7:]

    parser.get_usage = get_usage

    return parser

  def Run(self, args, env):
    """Begin execution of nsscache.

    This method loads our runtime configuration, instantiates the
    appropriate Source and Cache objects, and invokes the
    appropriate method based on the command given.

    NOTE:  We avoid calling sys.exit() and instead return an int
    to our caller, who will exit with that status.

    Args:
      args: list of command line arguments
      env: dictionary of environment variables

    Returns:
      POSIX exit status
    """
    # Parse the commandline.
    try:
      (options, args) = self.parser.parse_args(args)
    except SystemExit as e:
      # OptionParser objects raise SystemExit (error() calls exit()
      # calls sys.exit()) upon a parser error.
      # This can be handled better by overriding error or monkeypatching
      # our parser.
      return e.code
    # Initialize a configuration object.
    conf = config.Config(env)

    # Process the global flags.
    if options.verbose:
      logger = logging.getLogger()
      logger.setLevel(logging.INFO)
    if options.debug:
      logger = logging.getLogger()
      logger.setLevel(logging.DEBUG)
    if options.config_file:
      conf.config_file = options.config_file

    self.log.info('using nss_cache library, version %s', nss_cache.__version__)
    self.log.debug('library path is %r', nss_cache.__file__)

    # Identify the command to dispatch.
    if not args:
      print('No command given')
      self.parser.print_help()
      return os.EX_USAGE
    # print global help if command is 'help' with no argument
    if len(args) == 1 and args[0] == 'help':
      self.parser.print_help()
      return os.EX_OK
    self.log.debug('args: %r' % args)
    command_name = args.pop(0)
    self.log.debug('command: %r' % command_name)

    # Load the configuration from file.
    config.LoadConfig(conf)

    # Dispatch the command.
    try:
      command_callable = getattr(command, command_name.capitalize())
    except AttributeError:
      self.log.warn('%s is not implemented', command_name)
      print(('command %r is not implemented' % command_name))
      self.parser.print_help()
      return os.EX_SOFTWARE

    try:
      retval = command_callable().Run(conf=conf, args=args)
    except error.SourceUnavailable as e:
      self.log.error('Problem with configured data source: %s', e)
      return os.EX_TEMPFAIL

    return retval
