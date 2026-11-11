"""An implementation of a mock consul data source for nsscache."""

__author__ = "hexedpackets@gmail.com (William Huba)"

import base64
from io import StringIO
import json
import tempfile
import unittest

from nss_cache.caches import files
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import consulsource


def _EncodeValue(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


class TestConsulSource(unittest.TestCase):
    def setUp(self):
        """Initialize a basic config dict."""
        super(TestConsulSource, self).setUp()
        self.config = {
            "passwd_url": "PASSWD_URL",
            "group_url": "GROUP_URL",
            "datacenter": "TEST_DATACENTER",
            "token": "TEST_TOKEN",
        }

    def testDefaultConfiguration(self):
        source = consulsource.ConsulFilesSource({})
        self.assertEqual(
            source.conf["datacenter"], consulsource.ConsulFilesSource.DATACENTER
        )
        self.assertEqual(source.conf["token"], consulsource.ConsulFilesSource.TOKEN)

    def testOverrideDefaultConfiguration(self):
        source = consulsource.ConsulFilesSource(self.config)
        self.assertEqual(source.conf["datacenter"], "TEST_DATACENTER")
        self.assertEqual(source.conf["token"], "TEST_TOKEN")
        self.assertEqual(
            source.conf["passwd_url"],
            "PASSWD_URL?recurse&token=TEST_TOKEN&dc=TEST_DATACENTER",
        )
        self.assertEqual(
            source.conf["group_url"],
            "GROUP_URL?recurse&token=TEST_TOKEN&dc=TEST_DATACENTER",
        )


class TestPasswdMapParser(unittest.TestCase):
    def setUp(self):
        """Set some default avalible data for testing."""
        self.good_entry = passwd.PasswdMapEntry()
        self.good_entry.name = "foo"
        self.good_entry.passwd = "x"
        self.good_entry.uid = 10
        self.good_entry.gid = 10
        self.good_entry.gecos = "How Now Brown Cow"
        self.good_entry.dir = "/home/foo"
        self.good_entry.shell = "/bin/bash"
        self.parser = consulsource.ConsulPasswdMapParser()

    def testGetMap(self):
        passwd_map = passwd.PasswdMap()
        cache_info = StringIO(
            """[
                          {"Key": "org/users/foo/uid", "Value": "MTA="},
                          {"Key": "org/users/foo/gid", "Value": "MTA="},
                          {"Key": "org/users/foo/home", "Value": "L2hvbWUvZm9v"},
                          {"Key": "org/users/foo/shell", "Value": "L2Jpbi9iYXNo"},
                          {"Key": "org/users/foo/comment", "Value": "SG93IE5vdyBCcm93biBDb3c="},
                          {"Key": "org/users/foo/subkey/irrelevant_key", "Value": "YmFjb24="}
                          ]"""
        )
        self.parser.GetMap(cache_info, passwd_map)
        self.assertEqual(self.good_entry, passwd_map.PopItem())

    def testGetMapAndWriteMapUtf8(self):
        passwd_map = passwd.PasswdMap()
        records = [
            {"Key": "org/users/foo/passwd", "Value": _EncodeValue("!")},
            {"Key": "org/users/foo/uid", "Value": _EncodeValue("10")},
            {"Key": "org/users/foo/gid", "Value": _EncodeValue("10")},
            {"Key": "org/users/foo/comment", "Value": _EncodeValue("José Cow")},
            {"Key": "org/users/foo/home", "Value": _EncodeValue("/home/josé")},
            {"Key": "org/users/foo/shell", "Value": _EncodeValue("/bin/zsh")},
        ]
        self.parser.GetMap(StringIO(json.dumps(records)), passwd_map)
        with tempfile.TemporaryDirectory() as workdir:
            handler = files.FilesPasswdMapHandler({"dir": workdir})
            self.assertEqual(0, handler.WriteMap(passwd_map))
            with open(handler.GetCacheFilename(), encoding="utf-8") as cache_file:
                written = cache_file.read()
        self.assertEqual("foo:!:10:10:José Cow:/home/josé:/bin/zsh\n", written)
        self.assertNotIn("b'", written)

    def testGetMapSkipsMalformedValues(self):
        passwd_map = passwd.PasswdMap()
        bad_utf8 = base64.b64encode(b"\xff\xfe").decode("ascii")
        records = [
            {"Key": "org/users/bad1/uid", "Value": "!!!"},
            {"Key": "org/users/bad2/uid", "Value": bad_utf8},
            {"Key": "org/users/foo/uid", "Value": _EncodeValue("10")},
            {"Key": "org/users/foo/gid", "Value": _EncodeValue("10")},
        ]
        self.parser.GetMap(StringIO(json.dumps(records)), passwd_map)
        entry = passwd_map.PopItem()
        self.assertEqual("foo", entry.name)
        self.assertEqual(0, len(passwd_map))

    def testReadEntry(self):
        data = {
            "uid": b"10",
            "gid": b"10",
            "comment": b"How Now Brown Cow",
            "shell": b"/bin/bash",
            "home": b"/home/foo",
            "passwd": b"x",
        }
        entry = self.parser._ReadEntry(b"foo", data)
        self.assertEqual(self.good_entry, entry)
        self.assertIsInstance(entry.name, str)
        self.assertIsInstance(entry.passwd, str)
        self.assertIsInstance(entry.gecos, str)
        self.assertIsInstance(entry.dir, str)
        self.assertIsInstance(entry.shell, str)

    def testDefaultEntryValues(self):
        data = {"uid": "10", "gid": "10"}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(entry.shell, "/bin/bash")
        self.assertEqual(entry.dir, "/home/foo")
        self.assertEqual(entry.gecos, "")
        self.assertEqual(entry.passwd, "x")

    def testInvalidEntry(self):
        data = {"irrelevant_key": "bacon"}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(entry, None)


class TestConsulGroupMapParser(unittest.TestCase):
    def setUp(self):
        self.good_entry = group.GroupMapEntry()
        self.good_entry.name = "foo"
        self.good_entry.passwd = "x"
        self.good_entry.gid = 10
        self.good_entry.members = ["foo", "bar"]
        self.parser = consulsource.ConsulGroupMapParser()

    def testGetMap(self):
        group_map = group.GroupMap()
        cache_info = StringIO(
            """[
                          {"Key": "org/groups/foo/gid", "Value": "MTA="},
                          {"Key": "org/groups/foo/members", "Value": "Zm9vCmJhcg=="},
                          {"Key": "org/groups/foo/subkey/irrelevant_key", "Value": "YmFjb24="}
                          ]"""
        )
        self.parser.GetMap(cache_info, group_map)
        self.assertEqual(self.good_entry, group_map.PopItem())

    def testGetMapWithExplicitPasswdAndWriteMap(self):
        group_map = group.GroupMap()
        records = [
            {"Key": "org/groups/foo/passwd", "Value": _EncodeValue("!")},
            {"Key": "org/groups/foo/gid", "Value": _EncodeValue("10")},
            {"Key": "org/groups/foo/members", "Value": _EncodeValue("josé\nbar")},
        ]
        self.parser.GetMap(StringIO(json.dumps(records)), group_map)
        with tempfile.TemporaryDirectory() as workdir:
            handler = files.FilesGroupMapHandler({"dir": workdir})
            self.assertEqual(0, handler.WriteMap(group_map))
            with open(handler.GetCacheFilename(), encoding="utf-8") as cache_file:
                written = cache_file.read()
        self.assertEqual("foo:!:10:josé,bar\n", written)
        self.assertNotIn("b'", written)

    def testReadEntry(self):
        data = {"passwd": "x", "gid": "10", "members": "foo\nbar"}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(self.good_entry, entry)

    def testReadEntryBytes(self):
        data = {"passwd": b"!", "gid": b"10", "members": b"foo\nbar"}
        entry = self.parser._ReadEntry(b"foo", data)
        self.assertEqual("foo", entry.name)
        self.assertEqual("!", entry.passwd)
        self.assertEqual(10, entry.gid)
        self.assertEqual(["foo", "bar"], entry.members)
        self.assertIsInstance(entry.name, str)
        self.assertIsInstance(entry.passwd, str)

    def testDefaultPasswd(self):
        data = {"gid": "10", "members": "foo\nbar"}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(self.good_entry, entry)

    def testNoMembers(self):
        data = {"gid": "10", "members": ""}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(entry.members, [""])

    def testInvalidEntry(self):
        data = {"irrelevant_key": "bacon"}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(entry, None)


class TestConsulShadowMapParser(unittest.TestCase):
    def setUp(self):
        self.good_entry = shadow.ShadowMapEntry()
        self.good_entry.name = "foo"
        self.good_entry.passwd = "*"
        self.good_entry.lstchg = 17246
        self.good_entry.min = 0
        self.good_entry.max = 99999
        self.good_entry.warn = 7
        self.parser = consulsource.ConsulShadowMapParser()

    def testGetMap(self):
        shadow_map = shadow.ShadowMap()
        cache_info = StringIO(
            """[
                          {"Key": "org/groups/foo/passwd", "Value": "Kg=="},
                          {"Key": "org/groups/foo/lstchg", "Value": "MTcyNDY="},
                          {"Key": "org/groups/foo/min", "Value": "MA=="},
                          {"Key": "org/groups/foo/max", "Value": "OTk5OTk="},
                          {"Key": "org/groups/foo/warn", "Value": "Nw=="}
                          ]"""
        )
        self.parser.GetMap(cache_info, shadow_map)
        self.assertEqual(self.good_entry, shadow_map.PopItem())

    def testReadEntry(self):
        data = {"passwd": "*", "lstchg": 17246, "min": 0, "max": 99999, "warn": 7}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(self.good_entry, entry)

    def testReadEntryBytes(self):
        data = {
            "passwd": b"$6$salt$hash",
            "lstchg": b"17246",
            "min": b"0",
            "max": b"99999",
            "warn": b"7",
        }
        entry = self.parser._ReadEntry(b"foo", data)
        self.assertEqual("foo", entry.name)
        self.assertEqual("$6$salt$hash", entry.passwd)
        self.assertEqual(17246, entry.lstchg)
        self.assertIsInstance(entry.name, str)
        self.assertIsInstance(entry.passwd, str)

    def testDefaultPasswd(self):
        data = {"lstchg": 17246, "min": 0, "max": 99999, "warn": 7}
        entry = self.parser._ReadEntry("foo", data)
        self.assertEqual(self.good_entry, entry)


if __name__ == "__main__":
    unittest.main()
