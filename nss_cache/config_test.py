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

"""Unit tests for nss_cache/config.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import os
import shutil
import tempfile
import unittest

from nss_cache import config


class TestConfig(unittest.TestCase):
  """Unit tests for config.Config()."""

  def testConfigInit(self):
    env = {'NSSCACHE_CONFIG': 'test.conf'}
    conf = config.Config(env)

    self.assertEqual(conf.config_file, env['NSSCACHE_CONFIG'],
                      msg='Failed to override NSSCACHE_CONFIG.')


class TestMapOptions(unittest.TestCase):
  """Unit tests for config.MapOptions()."""

  def testMapOptionsInit(self):
    mapconfig = config.MapOptions()
    self.assertTrue(isinstance(mapconfig.cache, dict))
    self.assertTrue(isinstance(mapconfig.source, dict))


class TestClassMethods(unittest.TestCase):
  """Unit tests for class-level methods in config.py."""

  def setUp(self):
    # create a directory with a writeable copy of nsscache.conf in it
    self.workdir = tempfile.mkdtemp()
    conf_filename = 'nsscache.conf'
    self.conf_filename = os.path.join(self.workdir, conf_filename)
    shutil.copy(conf_filename, self.conf_filename)
    os.chmod(self.conf_filename, 0o640)

    # prepare a config object with this config
    self.conf = config.Config({})
    self.conf.config_file = self.conf_filename

  def tearDown(self):
    shutil.rmtree(self.workdir)

  def testLoadConfigSingleMap(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = foo\n'
                    'timestamp_dir = foo\n')
    conf_file.close()

    config.LoadConfig(self.conf)

    self.assertEqual(['foo'], self.conf.maps)

  def testLoadConfigTwoMaps(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = foo, bar\n'
                    'timestamp_dir = foo\n')
    conf_file.close()

    config.LoadConfig(self.conf)

    self.assertEqual(['foo', 'bar'], self.conf.maps)

  def testLoadConfigMapsWhitespace(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = foo,  bar  , baz\n'
                    'timestamp_dir = foo\n')
    conf_file.close()

    config.LoadConfig(self.conf)

    self.assertEqual(['foo', 'bar', 'baz'], self.conf.maps)

  def testLoadConfigExample(self):
    """Test that we parse and load the example config.

    Note that this also tests MapOptions() creation and our overriding
    of defaults in LoadConfig.

    This requires that nsscache.conf exists in the top of the source tree.
    Changes to the configuration options may break this test.
    """
    conf = self.conf
    config.LoadConfig(conf)
    passwd = conf.options['passwd']
    group = conf.options['group']
    shadow = conf.options['shadow']
    automount = conf.options['automount']

    self.assertTrue(isinstance(passwd, config.MapOptions))
    self.assertTrue(isinstance(group, config.MapOptions))
    self.assertTrue(isinstance(shadow, config.MapOptions))
    self.assertTrue(isinstance(automount, config.MapOptions))

    self.assertEqual(passwd.source['name'], 'ldap')
    self.assertEqual(group.source['name'], 'ldap')
    self.assertEqual(shadow.source['name'], 'ldap')
    self.assertEqual(automount.source['name'], 'ldap')

    self.assertEqual(passwd.cache['name'], 'files')
    self.assertEqual(group.cache['name'], 'files')
    self.assertEqual(shadow.cache['name'], 'files')
    self.assertEqual(automount.cache['name'], 'files')

    self.assertEqual(passwd.source['base'],
                      'ou=people,dc=example,dc=com')
    self.assertEqual(passwd.source['filter'],
                      '(objectclass=posixAccount)')

    self.assertEqual(group.source['base'],
                      'ou=group,dc=example,dc=com')
    self.assertEqual(group.source['filter'],
                      '(objectclass=posixGroup)')

  def testLoadConfigOptionalDefaults(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = foo,  bar  , baz\n'
                    'lockfile = foo\n'
                    'timestamp_dir = foo\n')
    conf_file.close()

    config.LoadConfig(self.conf)

    self.assertEqual(self.conf.lockfile, 'foo')

  def testLoadConfigStripQuotesFromStrings(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = "ldap"\n'  # needs to be ldap due to magic
                    'cache = \'b\'ar\'\n'
                    'maps = quux\n'
                    'timestamp_dir = foo\n'
                    'ldap_tls_require_cert = \'blah\'\n'
                    '[quux]\n'
                    'ldap_klingon = "qep\'a\' wa\'maH loS\'DIch"\n')
    conf_file.close()
    config.LoadConfig(self.conf)
    self.assertEqual('ldap', self.conf.options['quux'].source['name'])
    self.assertEqual('b\'ar', self.conf.options['quux'].cache['name'])
    self.assertEqual('blah',
                      self.conf.options['quux'].source['tls_require_cert'])
    self.assertEqual('qep\'a\' wa\'maH loS\'DIch',
                      self.conf.options['quux'].source['klingon'])

  def testLoadConfigConvertsNumbers(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = foo\n'
                    'timestamp_dir = foo\n'
                    'foo_string = test\n'
                    'foo_float = 1.23\n'
                    'foo_int = 1\n')
    conf_file.close()

    config.LoadConfig(self.conf)

    foo_dict = self.conf.options['foo'].source
    self.assertTrue(isinstance(foo_dict['string'], str))
    self.assertTrue(isinstance(foo_dict['float'], float))
    self.assertTrue(isinstance(foo_dict['int'], int))
    self.assertEqual(foo_dict['string'], 'test')
    self.assertEqual(foo_dict['float'], 1.23)
    self.assertEqual(foo_dict['int'], 1)

  def testOptions(self):
    # check the empty case.
    options = config.Options([], 'foo')
    self.assertEqual(options, {})

    # create a list like from ConfigParser.items()
    items = [('maps', 'foo, bar, foobar'),
             ('nssdb_dir', '/path/to/dir'),
             ('ldap_uri', 'TEST_URI'),
             ('source', 'foo'),
             ('cache', 'bar'),
             ('ldap_base', 'TEST_BASE'),
             ('ldap_filter', 'TEST_FILTER')]

    options = config.Options(items, 'ldap')

    self.assertTrue('uri' in options)
    self.assertTrue('base' in options)
    self.assertTrue('filter' in options)

    self.assertEqual(options['uri'], 'TEST_URI')
    self.assertEqual(options['base'], 'TEST_BASE')
    self.assertEqual(options['filter'], 'TEST_FILTER')

  def testParseNSSwitchConf(self):
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: files db\n')
    nsswitch_file.write('group: files db\n')
    nsswitch_file.write('shadow: files db\n')
    nsswitch_file.close()
    expected_switch = {'passwd': ['files', 'db'],
                       'group': ['files', 'db'],
                       'shadow': ['files', 'db']}
    self.assertEqual(expected_switch,
                      config.ParseNSSwitchConf(nsswitch_filename))
    os.unlink(nsswitch_filename)

  def testVerifyConfiguration(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = passwd, group, shadow\n'
                    'timestamp_dir = foo\n')
    conf_file.close()
    config.LoadConfig(self.conf)
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: files db\n')
    nsswitch_file.write('group: files db\n')
    nsswitch_file.write('shadow: files db\n')
    nsswitch_file.close()
    self.assertEqual((0, 0),
                      config.VerifyConfiguration(self.conf,
                                                 nsswitch_filename))
    os.unlink(nsswitch_filename)

  def testVerifyConfigurationWithCache(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = files\n'
                    'maps = passwd, group, shadow\n'
                    'timestamp_dir = foo\n'
                    'files_cache_filename_suffix = cache')
    conf_file.close()
    config.LoadConfig(self.conf)
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: cache\n')
    nsswitch_file.write('group: cache\n')
    nsswitch_file.write('shadow: cache\n')
    nsswitch_file.close()
    self.assertEqual((0, 0),
                      config.VerifyConfiguration(self.conf,
                                                 nsswitch_filename))
    os.unlink(nsswitch_filename)

  def testVerifyConfigurationWithFiles(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = files\n'
                    'maps = passwd, group, shadow\n'
                    'timestamp_dir = foo\n')
    conf_file.close()
    config.LoadConfig(self.conf)
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: files\n')
    nsswitch_file.write('group: files\n')
    nsswitch_file.write('shadow: files\n')
    nsswitch_file.close()
    self.assertEqual((0, 0),
                      config.VerifyConfiguration(self.conf,
                                                 nsswitch_filename))
    os.unlink(nsswitch_filename)

  def testVerifyBadConfigurationWithCache(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = files\n'
                    'maps = passwd, group, shadow\n'
                    'timestamp_dir = foo\n'
                    'files_cache_filename_suffix = cache')
    conf_file.close()
    config.LoadConfig(self.conf)
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: files\n')
    nsswitch_file.write('group: files\n')
    nsswitch_file.write('shadow: files\n')
    nsswitch_file.close()
    self.assertEqual((3, 0),
                      config.VerifyConfiguration(self.conf,
                                                 nsswitch_filename))
    os.unlink(nsswitch_filename)

  def testVerifyBadConfigurationIncrementsWarningCount(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = passwd, group, shadow\n'
                    'timestamp_dir = foo\n')
    conf_file.close()
    config.LoadConfig(self.conf)
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: files ldap\n')
    nsswitch_file.write('group: files db\n')
    nsswitch_file.write('shadow: files db\n')
    nsswitch_file.close()
    self.assertEqual((1, 0),
                      config.VerifyConfiguration(self.conf,
                                                 nsswitch_filename))
    os.unlink(nsswitch_filename)

  def testVerifyNoMapConfigurationIsError(self):
    conf_file = open(self.conf_filename, 'w')
    conf_file.write('[DEFAULT]\n'
                    'source = foo\n'
                    'cache = foo\n'
                    'maps = \n'
                    'timestamp_dir = foo\n')
    conf_file.close()
    config.LoadConfig(self.conf)
    nsswitch_filename = os.path.join(self.workdir, 'nsswitch.conf')
    nsswitch_file = open(nsswitch_filename, 'w')
    nsswitch_file.write('passwd: files ldap\n')
    nsswitch_file.close()
    self.assertEqual((0, 1),
                      config.VerifyConfiguration(self.conf,
                                                 nsswitch_filename))
    os.unlink(nsswitch_filename)


if __name__ == '__main__':
  unittest.main()
