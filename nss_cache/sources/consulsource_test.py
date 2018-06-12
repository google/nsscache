"""An implementation of a mock consul data source for nsscache."""

__author__ = 'hexedpackets@gmail.com (William Huba)'

import io
import unittest

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import consulsource


class TestConsulSource(unittest.TestCase):

  def setUp(self):
    """Initialize a basic config dict."""
    super(TestConsulSource, self).setUp()
    self.config = {
      'passwd_url': 'PASSWD_URL',
      'group_url': 'GROUP_URL',
      'datacenter': 'TEST_DATACENTER',
      'token': 'TEST_TOKEN',
    }

  def testDefaultConfiguration(self):
    source = consulsource.ConsulFilesSource({})
    self.assertEqual(source.conf['datacenter'],
                      consulsource.ConsulFilesSource.DATACENTER)
    self.assertEqual(source.conf['token'],
                      consulsource.ConsulFilesSource.TOKEN)

  def testOverrideDefaultConfiguration(self):
    source = consulsource.ConsulFilesSource(self.config)
    self.assertEqual(source.conf['datacenter'], 'TEST_DATACENTER')
    self.assertEqual(source.conf['token'], 'TEST_TOKEN')
    self.assertEqual(source.conf['passwd_url'], 'PASSWD_URL?recurse&token=TEST_TOKEN&dc=TEST_DATACENTER')
    self.assertEqual(source.conf['group_url'], 'GROUP_URL?recurse&token=TEST_TOKEN&dc=TEST_DATACENTER')


class TestPasswdMapParser(unittest.TestCase):
  def setUp(self):
    """Set some default avalible data for testing."""
    self.good_entry = passwd.PasswdMapEntry()
    self.good_entry.name = 'foo'
    self.good_entry.passwd = 'x'
    self.good_entry.uid = 10
    self.good_entry.gid = 10
    self.good_entry.gecos = 'How Now Brown Cow'
    self.good_entry.dir = '/home/foo'
    self.good_entry.shell = '/bin/bash'
    self.parser = consulsource.ConsulPasswdMapParser()

  def testGetMap(self):
    passwd_map = passwd.PasswdMap()
    cache_info = io.StringIO('''[
                                   {"Key": "org/users/foo/uid", "Value": "MTA="},
                                   {"Key": "org/users/foo/gid", "Value": "MTA="},
                                   {"Key": "org/users/foo/home", "Value": "L2hvbWUvZm9v"},
                                   {"Key": "org/users/foo/shell", "Value": "L2Jpbi9iYXNo"},
                                   {"Key": "org/users/foo/comment", "Value": "SG93IE5vdyBCcm93biBDb3c="},
                                   {"Key": "org/users/foo/subkey/irrelevant_key", "Value": "YmFjb24="}
                                   ]''')
    self.parser.GetMap(cache_info, passwd_map)
    self.assertEqual(self.good_entry, passwd_map.PopItem())

  def testReadEntry(self):
    data = {'uid': '10', 'gid': '10', 'comment': 'How Now Brown Cow', 'shell': '/bin/bash', 'home': '/home/foo', 'passwd': 'x'}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(self.good_entry, entry)

  def testDefaultEntryValues(self):
    data = {'uid': '10', 'gid': '10'}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(entry.shell, '/bin/bash')
    self.assertEqual(entry.dir, '/home/foo')
    self.assertEqual(entry.gecos, '')
    self.assertEqual(entry.passwd, 'x')

  def testInvalidEntry(self):
    data = {'irrelevant_key': 'bacon'}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(entry, None)


class TestConsulGroupMapParser(unittest.TestCase):

  def setUp(self):
    self.good_entry = group.GroupMapEntry()
    self.good_entry.name = 'foo'
    self.good_entry.passwd = 'x'
    self.good_entry.gid = 10
    self.good_entry.members = ['foo', 'bar']
    self.parser = consulsource.ConsulGroupMapParser()

  def testGetMap(self):
    group_map = group.GroupMap()
    cache_info = io.StringIO('''[
                                   {"Key": "org/groups/foo/gid", "Value": "MTA="},
                                   {"Key": "org/groups/foo/members", "Value": "Zm9vCmJhcg=="},
                                   {"Key": "org/groups/foo/subkey/irrelevant_key", "Value": "YmFjb24="}
                                   ]''')
    self.parser.GetMap(cache_info, group_map)
    self.assertEqual(self.good_entry, group_map.PopItem())

  def testReadEntry(self):
    data = {'passwd': 'x', 'gid': '10', 'members': 'foo\nbar'}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(self.good_entry, entry)

  def testDefaultPasswd(self):
    data = {'gid': '10', 'members': 'foo\nbar'}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(self.good_entry, entry)

  def testNoMembers(self):
    data = {'gid': '10', 'members': ''}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(entry.members, [''])

  def testInvalidEntry(self):
    data = {'irrelevant_key': 'bacon'}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(entry, None)


class TestConsulShadowMapParser(unittest.TestCase):

  def setUp(self):
    self.good_entry = shadow.ShadowMapEntry()
    self.good_entry.name = 'foo'
    self.good_entry.passwd = '*'
    self.good_entry.lstchg = 17246
    self.good_entry.min = 0
    self.good_entry.max = 99999
    self.good_entry.warn = 7
    self.parser = consulsource.ConsulShadowMapParser()

  def testGetMap(self):
    shadow_map = shadow.ShadowMap()
    cache_info = io.StringIO('''[
                                   {"Key": "org/groups/foo/passwd", "Value": "Kg=="},
                                   {"Key": "org/groups/foo/lstchg", "Value": "MTcyNDY="},
                                   {"Key": "org/groups/foo/min", "Value": "MA=="},
                                   {"Key": "org/groups/foo/max", "Value": "OTk5OTk="},
                                   {"Key": "org/groups/foo/warn", "Value": "Nw=="}
                                   ]''')
    self.parser.GetMap(cache_info, shadow_map)
    self.assertEqual(self.good_entry, shadow_map.PopItem())

  def testReadEntry(self):
    data = {'passwd': '*', 'lstchg': 17246, 'min': 0, 'max': 99999, 'warn': 7}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(self.good_entry, entry)

  def testDefaultPasswd(self):
    data = {'lstchg': 17246, 'min': 0, 'max': 99999, 'warn': 7}
    entry = self.parser._ReadEntry('foo', data)
    self.assertEqual(self.good_entry, entry)


if __name__ == '__main__':
  unittest.main()
