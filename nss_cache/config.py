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

"""Configuration classes for nss_cache module.

These classes perform command line and file-based configuration
loading and parsing for the nss_cache module.
"""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import ConfigParser
import logging
import re

from nss_cache import error

# known nss map types.
MAP_PASSWORD = 'passwd'
MAP_GROUP = 'group'
MAP_SHADOW = 'shadow'
MAP_NETGROUP = 'netgroup'
MAP_AUTOMOUNT = 'automount'

# accepted commands.
CMD_HELP = 'help'
CMD_REPAIR = 'repair'
CMD_STATUS = 'status'
CMD_UPDATE = 'update'
CMD_VERIFY = 'verify'

# default file locations
FILE_NSSWITCH = '/etc/nsswitch.conf'


class Config(object):
  """Data container for runtime configuration information.

  Global information such as the command, configured maps, etc, are
  loaded into this object.  Source and cache configuration
  information is also stored here.

  However since each map can be configured against a different
  source and cache implementation we have to store per-map
  configuration information.  This is done via a Config().options
  dictionary with the map name as the key and a MapOptions object as
  the value.
  """

  # default config file.
  NSSCACHE_CONFIG = '/etc/nsscache.conf'

  # known config file option names
  OPT_SOURCE = 'source'
  OPT_CACHE = 'cache'
  OPT_MAPS = 'maps'
  OPT_LOCKFILE = 'lockfile'

  def __init__(self, env):
    """Initialize defaults for data we hold.

    Args:
      env: dictionary of environment variables (typically os.environ)
    """
    # override constants based on ENV vars
    if env.has_key('NSSCACHE_CONFIG'):
      self.config_file = env['NSSCACHE_CONFIG']
    else:
      self.config_file = self.NSSCACHE_CONFIG

    # default values
    self.command = None
    self.help_command = None
    self.maps = []
    self.options = {}
    self.lockfile = None
    self.log = logging.getLogger('config')

  def __repr__(self):
    """String representation of this object."""
    # self.options is of variable length so we are forced to do
    # some fugly concatenation here to print our config in a
    # readable fashion.
    string = '<Config:\n\tcommand=%r\n\thelp_command=%r\n\tmaps=%r' \
             '\n\tlockfile=%r' % (self.command, self.help_command,
                                  self.maps, self.lockfile)
    for key in self.options:
      string = '%s\n\t%s=%r' % (string, key, self.options[key])
    return '%s\n>' % string


class MapOptions(object):
  """Data container for individual maps.

  Each map is configured against a source and cache.  The
  dictionaries used by the source and cache implementations are
  stored here.
  """

  def __init__(self):
    """Initialize default values."""
    self.cache = {}
    self.source = {}

  def __repr__(self):
    """String representation of this object."""
    return '<MapOptions cache=%r source=%r>' % (self.cache, self.source)


#
# Configuration itself is done through module-level methods.  These
# methods are below.
#
def LoadConfig(configuration):
  """Load the on-disk configuration file and merge it into config.

  Args:
    configuration: a config.Config object

  Raises:
    error.NoConfigFound: no configuration file was found
  """
  parser = ConfigParser.ConfigParser()

  # load config file
  configuration.log.debug('Attempting to parse configuration file: %s',
                          configuration.config_file)
  loaded = parser.read(configuration.config_file)
  if loaded:
    configuration.log.debug('Succesfully parsed configuration file: %s',
                            configuration.config_file)
  else:
    raise error.NoConfigFound

  # source, cache, and maps are required defaults
  default = 'DEFAULT'
  default_source = FixValue(parser.get(default, Config.OPT_SOURCE))
  default_cache = FixValue(parser.get(default, Config.OPT_CACHE))

  # optional defaults
  if parser.has_option(default, Config.OPT_LOCKFILE):
    configuration.lockfile = FixValue(parser.get(default, Config.OPT_LOCKFILE))

  if not configuration.maps:
    # command line did not override
    maplist = FixValue(parser.get(default, Config.OPT_MAPS))
    # special case for empty string, or split(',') will return a
    # non-empty list
    if maplist:
      configuration.maps = [m.strip() for m in maplist.split(',')]
    else:
      configuration.maps = []

  # build per-map source and cache dictionaries and store
  # them in MapOptions() objects.
  for map_name in configuration.maps:
    map_options = MapOptions()

    source = default_source
    cache = default_cache

    # override source and cache if necessary
    if parser.has_section(map_name):
      if parser.has_option(map_name, Config.OPT_SOURCE):
        source = FixValue(parser.get(map_name, Config.OPT_SOURCE))
      if parser.has_option(map_name, Config.OPT_CACHE):
        cache = FixValue(parser.get(map_name, Config.OPT_CACHE))

    # load source and cache default options
    map_options.source = Options(parser.items(default), source)
    map_options.cache = Options(parser.items(default), cache)

    # overide with any section-specific options
    if parser.has_section(map_name):
      options = Options(parser.items(map_name), source)
      map_options.source.update(options)
      options = Options(parser.items(map_name), cache)
      map_options.cache.update(options)

    # used to instantiate the specific cache/source
    map_options.source['name'] = source
    map_options.cache['name'] = cache

    # save final MapOptions() in the parent config object
    configuration.options[map_name] = map_options

  configuration.log.info('Configured maps are: %s',
                         ', '.join(configuration.maps))

  configuration.log.debug('loaded configuration: %r', configuration)


def Options(items, name):
  """Returns a dict of options specific to an implementation.

  This is used to retrieve a dict of options for a given
  implementation.  We look for configuration options in the form of
  name_option and ignore the rest.

  Args:
    items: [('key1', 'value1'), ('key2, 'value2'), ...]
    name: 'foo'
  Returns:
    dictionary of option:value pairs
  """
  options = {}
  option_re = re.compile('^%s_(.+)' % name)
  for item in items:
    match = option_re.match(item[0])
    if match:
      options[match.group(1)] = FixValue(item[1])

  return options


def FixValue(value):
  """Helper function to fix values loaded from a config file.

  Currently we strip bracketed quotes as well as convert numbers to
  floats for configuration parameters expecting numerical data types.

  Args:
    value: value to be converted

  Returns:
    fixed value
  """
  # Strip quotes if necessary.
  if (value.startswith('"') and value.endswith('"')) or \
     (value.startswith('\'') and value.endswith('\'')):
    value = value[1:-1]

  # Convert to float if necessary.  Python converts between floats and ints
  # on demand, but won't attempt string conversion automagically.
  #
  # Caveat:  '1' becomes 1.0, however python treats it reliably as 1
  # for native comparisons to int types, and if an int type is needed
  # explicitly the caller will have to cast.  This is simplist.
  try:
    try:
      value = int(value)
    except ValueError:
      value = float(value)
  except ValueError:
    pass

  return value


def ParseNSSwitchConf(nsswitch_filename):
  """Parse /etc/nsswitch.conf and return the sources for each map.

  Args:
    nsswitch_filename: Full path to an nsswitch.conf to parse.  See manpage
      nsswitch.conf(5) for full details on the format expected.

  Returns:
    a dictionary keyed by map names and containing a list of sources
    for each map.
  """
  nsswitch_file = open(nsswitch_filename, 'r')

  nsswitch = {}

  map_re = re.compile('^([a-z]+): *(.*)$')
  for line in nsswitch_file:
    match = map_re.match(line)
    if match:
      sources = match.group(2).split()
      nsswitch[match.group(1)] = sources

  return nsswitch


def VerifyConfiguration(conf, nsswitch_filename=FILE_NSSWITCH):
  """Verify that the system configuration matches the nsscache configuration.

  Checks that NSS configuration has the cache listed for each map that
  is configured in the nsscache configuration, i.e. that the system is
  configured to use the maps we are building.

  Args:
    conf: a Configuration
    nsswitch_filename: optionally the name of the file to parse
  Returns:
    (warnings, errors) a tuple counting the number of warnings and
    errors detected
  """
  (warnings, errors) = (0, 0)
  if not conf.maps:
    logging.error('No maps are configured.')
    errors += 1

  nsswitch = ParseNSSwitchConf(nsswitch_filename)
  for configured_map in conf.maps:
    # Determine what the name of the nss module should be
    if conf.options[configured_map].cache['name'] == 'nssdb':
      module_name = 'db'
    if conf.options[configured_map].cache['name'] == 'files':
      module_name = 'cache'
    else:
      # TODO(jaq): default due to hysterical raisins
      module_name = 'db'

    if module_name not in nsswitch[configured_map]:
      logging.warn('nsscache is configured to build maps for %r, ' \
                   'but NSS is not configured (in %r) to use it',
                   configured_map, nsswitch_filename)
      warnings += 1
  return (warnings, errors)
