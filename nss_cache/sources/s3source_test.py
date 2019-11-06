"""An implementation of a mock S3 data source for nsscache."""

__author__ = 'alexey.pikin@gmail.com'

import unittest
from io import StringIO

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import s3source


class TestS3Source(unittest.TestCase):

    def setUp(self):
        """Initialize a basic config dict."""
        super(TestS3Source, self).setUp()
        self.config = {
            'passwd_object': 'PASSWD_OBJ',
            'group_object': 'GROUP_OBJ',
            'bucket': 'TEST_BUCKET'
        }

    def testDefaultConfiguration(self):
        source = s3source.S3FilesSource({})
        self.assertEqual(source.conf['bucket'], s3source.S3FilesSource.BUCKET)
        self.assertEqual(source.conf['passwd_object'],
                         s3source.S3FilesSource.PASSWD_OBJECT)

    def testOverrideDefaultConfiguration(self):
        source = s3source.S3FilesSource(self.config)
        self.assertEqual(source.conf['bucket'], 'TEST_BUCKET')
        self.assertEqual(source.conf['passwd_object'], 'PASSWD_OBJ')
        self.assertEqual(source.conf['group_object'], 'GROUP_OBJ')


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
        self.parser = s3source.S3PasswdMapParser()

    def testGetMap(self):
        passwd_map = passwd.PasswdMap()
        cache_info = StringIO('''[
                            { "Key": "foo",
                              "Value": {
                               "uid": 10, "gid": 10, "home": "/home/foo",
                               "shell": "/bin/bash", "comment": "How Now Brown Cow",
                               "irrelevant_key":"bacon"
                              }
                            }
                          ]''')
        self.parser.GetMap(cache_info, passwd_map)
        self.assertEqual(self.good_entry, passwd_map.PopItem())

    def testReadEntry(self):
        data = {
            'uid': '10',
            'gid': '10',
            'comment': 'How Now Brown Cow',
            'shell': '/bin/bash',
            'home': '/home/foo',
            'passwd': 'x'
        }
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


class TestS3GroupMapParser(unittest.TestCase):

    def setUp(self):
        self.good_entry = group.GroupMapEntry()
        self.good_entry.name = 'foo'
        self.good_entry.passwd = 'x'
        self.good_entry.gid = 10
        self.good_entry.members = ['foo', 'bar']
        self.parser = s3source.S3GroupMapParser()

    def testGetMap(self):
        group_map = group.GroupMap()
        cache_info = StringIO('''[
                            { "Key": "foo",
                              "Value": {
                               "gid": 10,
                               "members": "foo\\nbar",
                               "irrelevant_key": "bacon"
                              }
                            }
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


class TestS3ShadowMapParser(unittest.TestCase):

    def setUp(self):
        self.good_entry = shadow.ShadowMapEntry()
        self.good_entry.name = 'foo'
        self.good_entry.passwd = '*'
        self.good_entry.lstchg = 17246
        self.good_entry.min = 0
        self.good_entry.max = 99999
        self.good_entry.warn = 7
        self.parser = s3source.S3ShadowMapParser()

    def testGetMap(self):
        shadow_map = shadow.ShadowMap()
        cache_info = StringIO('''[
                            { "Key": "foo",
                              "Value": {
                               "passwd": "*", "lstchg": 17246, "min": 0,
                               "max": 99999, "warn": 7
                              }
                            }
                          ]''')
        self.parser.GetMap(cache_info, shadow_map)
        self.assertEqual(self.good_entry, shadow_map.PopItem())

    def testReadEntry(self):
        data = {
            'passwd': '*',
            'lstchg': 17246,
            'min': 0,
            'max': 99999,
            'warn': 7
        }
        entry = self.parser._ReadEntry('foo', data)
        self.assertEqual(self.good_entry, entry)

    def testDefaultPasswd(self):
        data = {'lstchg': 17246, 'min': 0, 'max': 99999, 'warn': 7}
        entry = self.parser._ReadEntry('foo', data)
        self.assertEqual(self.good_entry, entry)


if __name__ == '__main__':
    unittest.main()
