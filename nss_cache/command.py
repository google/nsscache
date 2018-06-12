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



"""Command objects."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')


import inspect
import logging
import optparse
import os
import shutil
try:
    import io
except ImportError:
    from io import StringIO

import tempfile
import time

from nss_cache import config
from nss_cache import error
from nss_cache import lock
from nss_cache import nss

from nss_cache.caches import cache_factory
from nss_cache.sources import source_factory
from nss_cache.update import map_updater
from nss_cache.update import files_updater


class Command(object):
  """Base class for commands.

  The Command object mostly handles the mapping of commandline
  parameters into one or more nss_cache operations, and the results
  back into output.

  Commands normally don't have any state.  All their arguments are
  passed into the run() method.

  The docstring for an actual command should give a one-line
  summary, then a complete description of the command.  This is used
  as part of the help system.
  """
  # Well known exit codes.  We reserve anything 30 and under for the
  # number of failed NSS maps (~15 defined under modern linux/glibc
  # implementations of named services.  add fudge facter of 2 until I
  # check out a sun box and some other unices).
  #
  # This should all be uplifted into error.py and
  # coordinated there for the entire module.
  ERR_LOCK = 200

  def __init__(self):
    # Setup logging.
    self.log = logging.getLogger(self.__class__.__name__)
    if self.__doc__ == Command.__doc__:
      self.log.warn('No help message set for %r', self)
    # Setup command parser.
    self.parser = self._GetParser()
    # Attribute used to hold optional lock object.
    self.lock = None

  def __del__(self):
    """Release any locks before we exit."""
    self._Unlock()

  def _GetParser(self):
    """Initialize the argument parser for this command object.

    A default parser is initialized which supports common flags.  It
    is expected that Command subclasses extend this and add specific
    flags as needed.

    Returns:
      an optparse.OptionParser instance
    """
    parser = optparse.OptionParser()

    # We do not mix arguments and flags!
    parser.disable_interspersed_args()

    # commonly used options
    parser.add_option('-m', '--map', action='append',
                      type='string', dest='maps',
                      help='map to operate on, can be'
                      ' supplied multiple times')

    return parser

  def Run(self, conf, args):
    """Run this command.

    Commands are invoked with a global configuration object and a list
    of arguments.

    Args:
      conf: A Config object defining global configuration of
            nss_cache.
      args: A list of strings of commandline arguments.
    Returns:
      0 if the command was successful
      non-zero shell error code if not.
    """
    raise NotImplementedError('command %r not implemented'
                              % self.__class__.__name__)

  def _Lock(self, path=None, force=False):
    """Grab a system-wide lock for this command.

    Commands wishing to prevent concurrent operation can invoke this
    method to acquire a system-wide lock.  The lock will be
    automatically released on object destruction, however an optional
    Unlock() method is provided for commands wishing a smaller scope
    of locking.

    Args:
     path: optional path to lock file.
     force: optional boolean to override existing locks.
    Returns:
     True if the lock was acquired.
     False if the lock was not.
    """
    # Create the lock if it doesn't exist.
    if self.lock is None:
      self.lock = lock.PidFile(filename=path)

    # Acquire the lock.
    return self.lock.Lock(force=force)

  def _Unlock(self):
    """Release the system-wide lock if present."""
    if self.lock is not None:
      if self.lock.Locked():
        self.lock.Unlock()

  def Help(self, short=False):
    """Return the help message for this command."""
    if self.__doc__ is Command.__doc__:
      return None
    help_text = inspect.getdoc(self) + '\n'
    if short:
      # only use the short summary first line
      help_text = help_text.split('\n')[0]
    else:
      # lose the short summary first line
      help_text = '\n'.join(help_text.split('\n')[2:])
      help_buffer = io.StringIO()
      self.parser.print_help(file=help_buffer)
      # lose the first line, which is the usage line
      help_text += '\n'.join(help_buffer.getvalue().split('\n')[1:])
    return help_text


class Update(Command):
  """Update the cache.

  Performs an update of the configured caches from the configured sources.
  """

  def __init__(self):
    """Initialize the argument parser for this command object."""
    super(Update, self).__init__()
    self.parser.add_option('-f', '--full',
                           action='store_false',
                           help='force a full update from the data source',
                           dest='incremental', default=True)
    self.parser.add_option('-s', '--sleep',
                           action='store', type='int',
                           default=False, dest='delay',
                           help='number of seconds to sleep before'
                           ' executing command')
    self.parser.add_option('--force-write',
                           action='store_true',
                           default=False,
                           dest='force_write',
                           help='force the update to write new maps, overriding'
                           ' safety checks, such as refusing to write empty'
                           'maps.')
    self.parser.add_option('--force-lock',
                           action='store_true',
                           default=False,
                           dest='force_lock',
                           help='forcibly acquire the lock, and issue a SIGTERM'
                           'to any nsscache process holding the lock.')

  def Run(self, conf, args):
    """Run the Update command.

    See Command.Run() for full documentation on the Run() method.

    Args:
      conf: a nss_cache.config.Config object
      args: a list of arguments to be parsed by this command

    Returns:
      0 on success, nonzero on error
    """
    try:
      (options, args) = self.parser.parse_args(args)
    except SystemExit as e:
      return e.code

    if options.maps:
      self.log.info('Setting configured maps to %s', options.maps)
      conf.maps = options.maps

    if not options.incremental:
      self.log.debug('performing FULL update of caches')
    else:
      self.log.debug('performing INCREMENTAL update of caches')

    if options.delay:
      self.log.info('Delaying %d seconds before executing', options.delay)
      time.sleep(options.delay)

    return self.UpdateMaps(conf,
                           incremental=options.incremental,
                           force_write=options.force_write,
                           force_lock=options.force_lock)

  def UpdateMaps(self, conf, incremental, force_write=False, force_lock=False):
    """Update each configured map.

    For each configured map, create a source and cache object and
    update the cache from the source.

    Args:
      conf: configuration object
      incremental: flag indicating incremental update should occur
      force_write: optional flag indicating safety checks should be ignored
      force_lock: optional flag indicating we override existing locks

    Returns:
      integer, zero indicating success, non-zero failure
    """
    # Grab a lock before we continue!
    if not self._Lock(path=conf.lockfile, force=force_lock):
      self.log.error('Failed to acquire lock, aborting!')
      return self.ERR_LOCK

    retval = 0
    for map_name in conf.maps:
      if map_name not in conf.options:
        self.log.error('No such map name defined in config: %s', map_name)
        return 1

      if incremental:
        self.log.info('Updating and verifying %s cache.', map_name)
      else:
        self.log.info('Rebuilding and verifying %s cache.', map_name)

      cache_options = conf.options[map_name].cache
      source_options = conf.options[map_name].source

      # Change into the target directory.
      # Sources such as zsync handle their temporary files badly, so we
      # want to be in the same location that the destination file will
      # exist in, so that the atomic rename occurs in the same
      # filesystem.
      # In addition, we create a tempdir below this dir to work in, because
      # zsync's librcksum sometimes leaves temp files around, and we don't
      # want to leave file turds around /etc.
      # We save and restore the directory here as each cache can define its own
      # output directory.
      # Finally, relative paths in the config are treated as relative to the
      # startup directory, but we convewrt them to absolute paths so that future
      # temp dirs do not mess with our output routines.
      old_cwd = os.getcwd()
      tempdir = tempfile.mkdtemp(dir=cache_options['dir'],
                                 prefix='nsscache-%s-' % map_name)
      if not os.path.isabs(cache_options['dir']):
        cache_options['dir'] = os.path.abspath(cache_options['dir'])
      if not os.path.isabs(conf.timestamp_dir):
        conf.timestamp_dir = os.path.abspath(conf.timestamp_dir)
      if not os.path.isabs(tempdir):
        tempdir = os.path.abspath(tempdir)
      os.chdir(tempdir)
      # End chdir dirty hack.

      try:
        try:
          source = source_factory.Create(source_options)

          updater = self._Updater(map_name, source, cache_options, conf)

          if incremental:
            self.log.info('Updating and verifying %s cache.', map_name)
          else:
            self.log.info('Rebuilding and verifying %s cache.', map_name)

          retval = updater.UpdateFromSource(source, incremental=incremental,
                                          force_write=force_write)
        except error.PermissionDenied:
          self.log.error('Permission denied: could not update map %r.  Aborting',
                       map_name)
          retval += 1
        except (error.EmptyMap, error.InvalidMap) as e:
          self.log.error(e)
          retval += 1
        except error.InvalidMerge as e:
          self.log.warn('Could not merge map %r: %s.  Skipping.',
                         map_name, e)
      finally:
        # Start chdir cleanup
        os.chdir(old_cwd)
        shutil.rmtree(tempdir)
        # End chdir cleanup

    return retval

  def _Updater(self, map_name, source, cache_options, conf):
    # Bit ugly. This just checks the class attribute UPDATER
    # to determine which type of updater the source uses. At the moment
    # there's only two, so not a huge deal. If we add another we should
    # refactor though.
    if hasattr(source, 'UPDATER') and source.UPDATER == config.UPDATER_FILE:
      if map_name == config.MAP_AUTOMOUNT:
        return files_updater.FileAutomountUpdater(map_name, conf.timestamp_dir,
                                                     cache_options)
      else:
        return files_updater.FileMapUpdater(map_name, conf.timestamp_dir,
                                            cache_options,
                                            can_do_incremental=True)
    else:
      if map_name == config.MAP_AUTOMOUNT:
        return map_updater.AutomountUpdater(map_name, conf.timestamp_dir,
                                               cache_options)
      else:
        return map_updater.MapUpdater(map_name, conf.timestamp_dir,
                                      cache_options,
                                      can_do_incremental=True)


class Verify(Command):
  """Verify the cache and configuration.

  Perform verification of the built caches and validation of the
  system NSS configuration.
  """

  def Run(self, conf, args):
    """Run the Verify command.

    See Command.Run() for full documentation on the Run() method.

    Args:
      conf: nss_cache.config.Config object
      args: list of arguments to be parsed

    Returns:
      count of warnings and errors detected when verifying
    """
    try:
      (options, args) = self.parser.parse_args(args)
    except SystemExit as e:
      return e.code

    if options.maps:
      self.log.info('Setting configured maps to %s', options.maps)
      conf.maps = options.maps

    (warnings, errors) = (0, 0)
    self.log.info('Verifying program and system configuration.')
    (config_warnings, config_errors) = config.VerifyConfiguration(conf)
    warnings += config_warnings
    errors += config_errors

    self.log.info('Verifying data sources.')
    errors += self.VerifySources(conf)

    self.log.info('Verifying data caches.')
    errors += self.VerifyMaps(conf)

    self.log.info('Verification result: %d warnings, %d errors',
                  warnings, errors)
    if warnings + errors:
      self.log.info('Verification failed!')
    else:
      self.log.info('Verification passed!')

    return warnings + errors

  def VerifyMaps(self, conf):
    """Compare each configured map against data retrieved from NSS.

    For each configured map, build a Map object from NSS and compare
    it against a Map object retrieved directly from the cache.  We
    expect the cache Map to be a subset of the nss Map due to possible
    inclusion of other NSS map types (e.g. files, nis, ldap, etc).

    This could be done via series of get*nam calls, however at this
    time it appears to be more efficient to grab them in bulk and use
    the Map.__contains__() membership test.

    Args:
      conf: nss_cache.config.Config object

    Returns:
      count of failures when verifying
    """
    retval = 0

    for map_name in conf.maps:
      self.log.info('Verifying map: %s.', map_name)

      # The netgroup map does not have an enumerator,
      # to test this we'd have to loop over the loaded cache map
      # and verify each entry is retrievable via getent directly.
      # TODO(blaed): apply fix from comment to allow for netgroup checking
      if map_name == config.MAP_NETGROUP:
        self.log.info(('The netgroup map does not support enumeration, '
                       'skipping.'))
        continue

      # Automount maps do not support getent, we'll have to come up with
      # a good way to verify these.
      if map_name == config.MAP_AUTOMOUNT:
        self.log.info(('The automount map does not support enumeration, '
                       'skipping.'))
        continue

      try:
        nss_map = nss.GetMap(map_name)
      except error.UnsupportedMap:
        self.log.warning('Verification of %s map is unsupported!', map_name)
        continue

      self.log.debug('built NSS map of %d entries', len(nss_map))

      cache_options = conf.options[map_name].cache
      cache = cache_factory.Create(cache_options, map_name)

      try:
        cache_map = cache.GetMap()
      except error.CacheNotFound:
        self.log.error('Cache missing!')
        retval +=1
        continue

      self.log.debug('built cache map of %d entries', len(cache_map))

      # cache_map is a subset of nss_map due to possible other maps,
      # e.g. files, nis, ldap, etc.
      missing_entries = 0
      for map_entry in cache_map:
        if map_entry not in nss_map:
          self.log.info('The following entry is present in the cache '
                        'but not availible via NSS! %s', map_entry.name)
          self.log.debug('missing entry data: %s', map_entry)
          missing_entries += 1

      if missing_entries > 0:
        self.log.warning('Missing %d entries in %s map',
                         missing_entries, map_name)
        retval +=1

    return retval

  def VerifySources(self, conf):
    """Verify each possible source and return the appropriate retval."""
    possible_sources = set()
    retval = 0

    for map_name in conf.maps:
      possible_sources.add(map_name)

    if possible_sources:
      for map_name in possible_sources:
        source_options = conf.options[map_name].source
        try:
          source = source_factory.Create(source_options)
        except error.SourceUnavailable as e:
          self.log.debug('map %s dumps source error %s', map_name, e)
          self.log.error('Map %s is unvavailable!', map_name)
          retval +=1
          continue
        retval += source.Verify()
    else:
      self.log.error('No sources configured for any maps!')
      retval += 1

    return retval


class Help(Command):
  """Show per-command help.

  usage: help [command]

  Shows online help for each command.
  e.g. 'help help' shows this help.
  """

  def Run(self, conf, args):
    """Run the Help command.

    See Command.Run() for full documentation on the Run() method.

    Args:
      conf: nss_cache.config.Config object
      args: list of arguments to be parsed by this command.

    Returns:
      zero, and prints the help text as a side effectg
    """
    if not args:
      help_text = self.Help()
    else:
      help_command = args.pop()
      print('Usage: nsscache [global options] %s [options]' % help_command)
      print()
      try:
        callable_action = getattr(inspect.getmodule(self),
                                  help_command.capitalize())
        help_text = callable_action().Help()
      except AttributeError:
        print('command %r is not implemented' % help_command)
        return 1

    print(help_text)
    return 0


class Repair(Command):
  """Repair the cache.

  Verify that the configuration is correct, that the source is
  reachable, then perform a full synchronisation of the cache.
  """

  def Run(self, conf, args):
    """Run the Repair command.

    See Command.Run() for full documentation on the Run() method.

    Args:
      conf: nss_cache.config.Config object
      args: list of arguments to be parsed by this command

    Returns:
      0 on success, nonzero on error
    """
    try:
      (options, args) = self.parser.parse_args(args)
    except SystemExit as e:
      return e.code

    if options.maps:
      self.log.info('Setting configured maps to %s', options.maps)
      conf.maps = options.maps

    (warnings, errors) = (0, 0)

    self.log.info('Verifying program and system configuration.')
    (config_warnings, config_errors) = config.VerifyConfiguration(conf)
    warnings += config_warnings
    errors += config_errors

    self.log.info('Verifying data sources.')
    errors += Verify().VerifySources(conf)

    self.log.info('verification: %d warnings, %d errors', warnings, errors)

    # Exit and report if config or source failed verification, because
    # we cannot reliably build a cache if either of these are faulty.
    if errors > 0:
      self.log.error('Too many errors in verification tests failed;'
                     ' repair aborted!')
      return 1

    # Rebuild local cache in full, which also verifies each cache.
    self.log.info('Rebuilding and verifying caches: %s.', conf.maps)
    return Update().UpdateMaps(conf=conf, incremental=False)


class Status(Command):
  """Show current cache status.

  Show the last update time of each configured cache, and other
  metrics, optionally in a machine-readable format.
  """

  def __init__(self):
    super(Status, self).__init__()
    self.parser.add_option('--epoch',
                           action='store_true',
                           help='show timestamps in UNIX epoch time',
                           dest='epoch', default=False)
    self.parser.add_option('--template',
                           action='store',
                           help='Set format for output',
                           metavar='FORMAT', dest='template',
                           default='NSS map: %(map)s\n%(key)s: %(value)s')
    self.parser.add_option('--automount-template',
                           action='store',
                           help='Set format for automount output',
                           metavar='FORMAT', dest='automount_template',
                           default=('NSS map: %(map)s\nAutomount map: '
                                    '%(automount)s\n%(key)s: %(value)s'))

  def Run(self, conf, args):
    """Run the Status command.

    See Command.Run() for full documentation on the Run() method.

    Args:
      conf: nss_cache.config.Config object
      args: list of arguments to be parsed by this command

    Returns:
      zero on success, nonzero on error
    """
    try:
      (options, args) = self.parser.parse_args(args)
    except SystemExit as e:
      # See app.NssCacheApp.Run()
      return e.code

    if options.maps:
      self.log.info('Setting configured maps to %s', options.maps)
      conf.maps = options.maps

    for map_name in conf.maps:
      # Hardcoded to support the two-tier structure of automount maps
      if map_name == config.MAP_AUTOMOUNT:
        value_list = self.GetAutomountMapMetadata(conf, epoch=options.epoch)
        self.log.debug('Value list: %r', value_list)
        for value_dict in value_list:
          self.log.debug('Value dict: %r', value_dict)
          output = options.automount_template % value_dict
          print(output)
      else:
        for value_dict in self.GetSingleMapMetadata(map_name, conf,
                                                    epoch=options.epoch):
          self.log.debug('Value dict: %r', value_dict)
          output = options.template % value_dict
          print(output)

    return os.EX_OK

  def GetSingleMapMetadata(self, map_name, conf, automount_mountpoint=None,
                           epoch=False):
    """Return metadata from map specified.

    Args:
      map_name: name of map to extract data from
      conf: a config.Config object
      automount_mountpoint: information necessary for automount maps
      epoch: return times as an integer epoch (time_t) instead of a
        human readable name

    Returns:
      a list of dicts of metadata key/value pairs
    """
    cache_options = conf.options[map_name].cache

    updater = map_updater.MapUpdater(map_name, conf.timestamp_dir,
                                     cache_options, automount_mountpoint)

    modify_dict = {'key': 'last-modify-timestamp',
                   'map': map_name}
    update_dict = {'key': 'last-update-timestamp',
                   'map': map_name}
    if map_name == config.MAP_AUTOMOUNT:
      # have to find out *which* automount map from a cache object!
      cache = cache_factory.Create(cache_options, config.MAP_AUTOMOUNT,
                                   automount_mountpoint=automount_mountpoint)
      automount = cache.GetMapLocation()
      modify_dict['automount'] = automount
      update_dict['automount'] = automount

    last_modify_timestamp = updater.GetModifyTimestamp() or 0
    last_update_timestamp = updater.GetUpdateTimestamp() or 0

    if not epoch:
      # If we are displaying the time as a string, do so in localtime.  This is
      # the only place such a conversion is appropriate.
      if last_modify_timestamp:
        last_modify_timestamp = time.asctime(time.localtime(last_modify_timestamp))
      else:
        last_modify_timestamp = 'Unknown'
      if last_update_timestamp:
        last_update_timestamp = time.asctime(time.localtime(last_update_timestamp))
      else:
        last_update_timestamp = 'Unknown'

    modify_dict['value'] = last_modify_timestamp
    update_dict['value'] = last_update_timestamp

    return [modify_dict, update_dict]

  def GetAutomountMapMetadata(self, conf, epoch=False):
    """Return status of automount master map and all listed automount maps.

    We retrieve the automount master map, and build a list of dicts which
    are used by the caller to print the status output.

    Args:
      conf: a config.Config object
      epoch: return times as an integer epoch (time_t) instead of a
        human readable name

    Returns:
      a list of dicts of metadata key/value pairs
    """
    map_name = config.MAP_AUTOMOUNT
    cache_options = conf.options[map_name].cache
    value_list = []

    # get the value_dict for the master map, note that automount_mountpoint=None
    # defaults to the master map!
    values = self.GetSingleMapMetadata(
        map_name, conf, automount_mountpoint=None, epoch=epoch)
    value_list.extend(values)

    # now get the contents of the master map, and get the status for each map
    # we find
    cache = cache_factory.Create(cache_options, config.MAP_AUTOMOUNT,
                                 automount_mountpoint=None)
    master_map = cache.GetMap()

    for map_entry in master_map:
      values = self.GetSingleMapMetadata(map_name, conf,
                                         automount_mountpoint=map_entry.key,
                                         epoch=epoch)
      value_list.extend(values)
    return value_list
