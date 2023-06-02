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
"""An implementation of a mock ldap data source for nsscache."""

__author__ = (
    "jaq@google.com (Jamie Wilkinson)",
    "vasilios@google.com (Vasilios Hoffman)",
)

import time
import unittest
import ldap
from unittest import mock

from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import ldapsource

TEST_RETRY_MAX = 1
TEST_RETRY_DELAY = 0
TEST_URI = "TEST_URI"


class TestLdapSource(unittest.TestCase):
    def setUp(self):
        """Initialize a basic config dict."""
        super(TestLdapSource, self).setUp()
        self.config = {
            "uri": "TEST_URI",
            "base": "TEST_BASE",
            "filter": "TEST_FILTER",
            "bind_dn": "TEST_BIND_DN",
            "bind_password": "TEST_BIND_PASSWORD",
            "retry_delay": TEST_RETRY_DELAY,
            "retry_max": TEST_RETRY_MAX,
            "timelimit": "TEST_TIMELIMIT",
            "tls_require_cert": 0,
            "tls_cacertdir": "TEST_TLS_CACERTDIR",
            "tls_cacertfile": "TEST_TLS_CACERTFILE",
        }
        ldap_patcher = mock.patch.object(ldap, "ldapobject", autospec=True)
        self.addCleanup(ldap_patcher.stop)
        self.ldap_mock = ldap_patcher.start()

    class compareSPRC:
        def __init__(self, expected_value=""):
            self.expected_value = expected_value

        def __eq__(self, other):
            if not isinstance(other, list):
                return False

            sprc = other[0]
            if not isinstance(sprc, ldap.controls.SimplePagedResultsControl):
                return False

            cookie = ldapsource.getCookieFromControl(sprc)
            return cookie == self.expected_value

    def testDefaultConfiguration(self):
        config = {"uri": "ldap://foo"}

        source = ldapsource.LdapSource(config)

        self.assertEqual(source.conf["bind_dn"], ldapsource.LdapSource.BIND_DN)
        self.assertEqual(
            source.conf["bind_password"], ldapsource.LdapSource.BIND_PASSWORD
        )
        self.assertEqual(source.conf["retry_max"], ldapsource.LdapSource.RETRY_MAX)
        self.assertEqual(source.conf["retry_delay"], ldapsource.LdapSource.RETRY_DELAY)
        self.assertEqual(source.conf["scope"], ldapsource.LdapSource.SCOPE)
        self.assertEqual(source.conf["timelimit"], ldapsource.LdapSource.TIMELIMIT)
        self.assertEqual(source.conf["tls_require_cert"], ldap.OPT_X_TLS_DEMAND)

    def testOverrideDefaultConfiguration(self):
        config = dict(self.config)
        config["scope"] = ldap.SCOPE_BASE

        source = ldapsource.LdapSource(config)

        self.assertEqual(source.conf["scope"], ldap.SCOPE_BASE)
        self.assertEqual(source.conf["bind_dn"], "TEST_BIND_DN")
        self.assertEqual(source.conf["bind_password"], "TEST_BIND_PASSWORD")
        self.assertEqual(source.conf["retry_delay"], TEST_RETRY_DELAY)
        self.assertEqual(source.conf["retry_max"], TEST_RETRY_MAX)
        self.assertEqual(source.conf["timelimit"], "TEST_TIMELIMIT")
        self.assertEqual(source.conf["tls_require_cert"], 0)
        self.assertEqual(source.conf["tls_cacertdir"], "TEST_TLS_CACERTDIR")
        self.assertEqual(source.conf["tls_cacertfile"], "TEST_TLS_CACERTFILE")

    def testDebugLevelSet(self):
        config = dict(self.config)
        config["ldap_debug"] = 3

        ldapsource.LdapSource(config)

        self.ldap_mock.ReconnectLDAPObject.return_value.set_option.assert_called_with(
            ldap.OPT_DEBUG_LEVEL, 3
        )

    def testTrapServerDownAndRetry(self):
        config = dict(self.config)
        config["bind_dn"] = ""
        config["bind_password"] = ""
        config["retry_delay"] = 5
        config["retry_max"] = 3
        self.ldap_mock.ReconnectLDAPObject.return_value.simple_bind_s.side_effect = (
            ldap.SERVER_DOWN
        )

        with mock.patch("time.sleep"):
            self.assertRaises(error.SourceUnavailable, ldapsource.LdapSource, config)

        self.ldap_mock.ReconnectLDAPObject.assert_called_with(
            mock.ANY, retry_max=3, retry_delay=5
        )

    def testIterationOverLdapDataSource(self):
        config = dict(self.config)
        dataset = [("dn", {"uid": [0]})]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, dataset, None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        source.Search(
            search_base=config["base"],
            search_filter="TEST_FILTER",
            search_scope="TEST_SCOPE",
            attrs="TEST_ATTRLIST",
        )

        count = 0
        for r in source:
            self.assertEqual(dataset[0][1], r)
            count += 1
        self.assertEqual(1, count)

    @mock.patch("time.sleep")
    def testIterationTimeout(self, unused_time_mock):
        config = dict(self.config)
        config["retry_delay"] = 5
        config["retry_max"] = 3
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = (
            ldap.TIMELIMIT_EXCEEDED
        )

        source = ldapsource.LdapSource(config)
        source.Search(
            search_base=config["base"],
            search_filter="TEST_FILTER",
            search_scope="TEST_SCOPE",
            attrs="TEST_ATTRLIST",
        )

        count = 0
        for r in source:
            count += 1
        self.assertEqual(0, count)

    def testGetPasswdMap(self):
        test_posix_account = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "uidNumber": ["1000"],
                "gidNumber": ["1000"],
                "uid": ["test"],
                "cn": ["Testguy McTest"],
                "homeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "userPassword": ["p4ssw0rd"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        attrlist = [
            "uid",
            "uidNumber",
            "gidNumber",
            "gecos",
            "cn",
            "homeDirectory",
            "fullName",
            "loginShell",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetPasswdMap()

        self.assertEqual(1, len(data))
        first = data.PopItem()
        self.assertEqual("test", first.name)

    def testGetPasswdMapWithUidAttr(self):
        test_posix_account = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "uidNumber": [1000],
                "gidNumber": [1000],
                "uid": ["test"],
                "name": ["test"],
                "cn": ["Testguy McTest"],
                "homeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "userPassword": ["p4ssw0rd"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["uidattr"] = "name"
        attrlist = [
            "uid",
            "uidNumber",
            "gidNumber",
            "gecos",
            "cn",
            "homeDirectory",
            "loginShell",
            "fullName",
            "name",
            "modifyTimestamp",
        ]

        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]
        source = ldapsource.LdapSource(config)
        data = source.GetPasswdMap()

        self.assertEqual(1, len(data))
        first = data.PopItem()
        self.assertEqual("test", first.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetPasswdMapWithShellOverride(self):
        test_posix_account = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "uidNumber": [1000],
                "gidNumber": [1000],
                "uid": ["test"],
                "cn": ["Testguy McTest"],
                "homeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "userPassword": ["p4ssw0rd"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["override_shell"] = "/bin/false"
        attrlist = [
            "uid",
            "uidNumber",
            "gidNumber",
            "gecos",
            "cn",
            "homeDirectory",
            "loginShell",
            "fullName",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetPasswdMap()

        self.assertEqual(1, len(data))
        first = data.PopItem()
        self.assertEqual("/bin/false", first.shell)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetPasswdMapWithUseRid(self):
        test_posix_account = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "uidNumber": [1000],
                "gidNumber": [1000],
                "uid": ["test"],
                "cn": ["Testguy McTest"],
                "homeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "userPassword": ["p4ssw0rd"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["use_rid"] = "1"
        attrlist = [
            "uid",
            "uidNumber",
            "gidNumber",
            "gecos",
            "cn",
            "homeDirectory",
            "loginShell",
            "fullName",
            "sambaSID",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetPasswdMap()

        self.assertEqual(1, len(data))
        first = data.PopItem()
        self.assertEqual("test", first.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetPasswdMapAD(self):
        test_posix_account = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "objectSid": [
                    b"\x01\x05\x00\x00\x00\x00\x00\x05\x15\x00\x00\x00\xa0e\xcf~xK\x9b_\xe7|\x87p\t\x1c\x01\x00"
                ],
                "sAMAccountName": ["test"],
                "displayName": ["Testguy McTest"],
                "unixHomeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "pwdLastSet": ["132161071270000000"],
                "whenChanged": ["20070227012807.0Z"],
            },
        )
        config = dict(self.config)
        config["ad"] = "1"
        attrlist = [
            "sAMAccountName",
            "objectSid",
            "displayName",
            "unixHomeDirectory",
            "pwdLastSet",
            "loginShell",
            "whenChanged",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetPasswdMap()

        self.assertEqual(1, len(data))
        first = data.PopItem()
        self.assertEqual("test", first.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetPasswdMapADWithOffset(self):
        test_posix_account = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "objectSid": [
                    b"\x01\x05\x00\x00\x00\x00\x00\x05\x15\x00\x00\x00\xa0e\xcf~xK\x9b_\xe7|\x87p\t\x1c\x01\x00"
                ],
                "sAMAccountName": ["test"],
                "displayName": ["Testguy McTest"],
                "unixHomeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "pwdLastSet": ["132161071270000000"],
                "whenChanged": ["20070227012807.0Z"],
            },
        )

        config = dict(self.config)
        config["ad"] = "1"
        config["offset"] = 10000
        attrlist = [
            "sAMAccountName",
            "objectSid",
            "displayName",
            "unixHomeDirectory",
            "pwdLastSet",
            "loginShell",
            "whenChanged",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetPasswdMap()

        self.assertEqual(1, len(data))
        first = data.PopItem()
        self.assertEqual("test", first.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupMap(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "memberUid": ["testguy", "fooguy", "barguy"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        attrlist = ["cn", "gidNumber", "memberUid", "uid", "modifyTimestamp"]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("testgroup", ent.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupMapWithUseRid(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "memberUid": ["testguy", "fooguy", "barguy"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["use_rid"] = "1"
        attrlist = [
            "cn",
            "gidNumber",
            "memberUid",
            "uid",
            "sambaSID",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("testgroup", ent.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupMapAsUser(self):
        test_posix_group = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "uidNumber": [1000],
                "gidNumber": [1000],
                "uid": ["test"],
                "cn": ["Testguy McTest"],
                "homeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "userPassword": ["p4ssw0rd"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["use_rid"] = "1"
        attrlist = [
            "cn",
            "gidNumber",
            "memberUid",
            "uid",
            "sambaSID",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("test", ent.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupMapAD(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "objectSid": [
                    b"\x01\x05\x00\x00\x00\x00\x00\x05\x15\x00\x00\x00\xa0e\xcf~xK\x9b_\xe7|\x87p\t\x1c\x01\x00"
                ],
                "sAMAccountName": ["testgroup"],
                "cn": ["testgroup"],
                "member": [
                    "cn=testguy,ou=People,dc=example,dc=com",
                    "cn=fooguy,ou=People,dc=example,dc=com",
                    "cn=barguy,ou=People,dc=example,dc=com",
                ],
                "whenChanged": ["20070227012807.0Z"],
            },
        )
        config = dict(self.config)
        config["ad"] = "1"
        attrlist = [
            "sAMAccountName",
            "member",
            "objectSid",
            "whenChanged",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("testgroup", ent.name)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupMapBis(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "member": [
                    "cn=testguy,ou=People,dc=example,dc=com",
                    "cn=fooguy,ou=People,dc=example,dc=com",
                    "cn=barguy,ou=People,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["rfc2307bis"] = 1
        attrlist = [
            "cn",
            "gidNumber",
            "member",
            "uid",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("testgroup", ent.name)
        self.assertEqual(3, len(ent.members))
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupNestedNotConfigured(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "member": [
                    "cn=testguy,ou=People,dc=example,dc=com",
                    "cn=fooguy,ou=People,dc=example,dc=com",
                    "cn=barguy,ou=People,dc=example,dc=com",
                    "cn=child,ou=Group,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        test_child_group = (
            "cn=child,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72714"],
                "gidNumber": [1001],
                "cn": ["child"],
                "member": [
                    "cn=newperson,ou=People,dc=example,dc=com",
                    "cn=fooperson,ou=People,dc=example,dc=com",
                    "cn=barperson,ou=People,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["rfc2307bis"] = 1
        attrlist = [
            "cn",
            "gidNumber",
            "member",
            "uid",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group, test_child_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(2, len(data))
        datadict = {i.name: i for i in data}
        self.assertIn("child", datadict)
        self.assertIn("testgroup", datadict)
        self.assertEqual(len(datadict["testgroup"].members), 4)
        self.assertEqual(len(datadict["child"].members), 3)
        self.assertNotIn("newperson", datadict["testgroup"].members)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupNested(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "member": [
                    "cn=testguy,ou=People,dc=example,dc=com",
                    "cn=fooguy,ou=People,dc=example,dc=com",
                    "cn=barguy,ou=People,dc=example,dc=com",
                    "cn=child,ou=Group,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        test_child_group = (
            "cn=child,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72714"],
                "gidNumber": [1001],
                "cn": ["child"],
                "member": [
                    "cn=newperson,ou=People,dc=example,dc=com",
                    "cn=fooperson,ou=People,dc=example,dc=com",
                    "cn=barperson,ou=People,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["rfc2307bis"] = 1
        config["nested_groups"] = 1
        config["use_rid"] = 1
        attrlist = [
            "cn",
            "gidNumber",
            "member",
            "uid",
            "sambaSID",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group, test_child_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(2, len(data))
        datadict = {i.name: i for i in data}
        self.assertIn("child", datadict)
        self.assertIn("testgroup", datadict)
        self.assertEqual(len(datadict["testgroup"].members), 7)
        self.assertEqual(len(datadict["child"].members), 3)
        self.assertIn("newperson", datadict["testgroup"].members)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupLoop(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "member": [
                    "cn=testguy,ou=People,dc=example,dc=com",
                    "cn=fooguy,ou=People,dc=example,dc=com",
                    "cn=barguy,ou=People,dc=example,dc=com",
                    "cn=child,ou=Group,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        test_child_group = (
            "cn=child,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72714"],
                "gidNumber": [1001],
                "cn": ["child"],
                "member": [
                    "cn=newperson,ou=People,dc=example,dc=com",
                    "cn=fooperson,ou=People,dc=example,dc=com",
                    "cn=barperson,ou=People,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        test_loop_group = (
            "cn=loop,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72715"],
                "gidNumber": [1002],
                "cn": ["loop"],
                "member": [
                    "cn=loopperson,ou=People,dc=example,dc=com",
                    "cn=testgroup,ou=Group,dc=example,dc=com",
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        config["rfc2307bis"] = 1
        config["nested_groups"] = 1
        config["use_rid"] = 1
        attrlist = [
            "cn",
            "gidNumber",
            "member",
            "uid",
            "sambaSID",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (
                ldap.RES_SEARCH_ENTRY,
                [
                    test_posix_group,
                    test_child_group,
                    test_loop_group,
                ],
                None,
                [],
            ),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(3, len(data))
        datadict = {i.name: i for i in data}
        self.assertIn("child", datadict)
        self.assertIn("testgroup", datadict)
        self.assertEqual(len(datadict["testgroup"].members), 7)
        self.assertEqual(len(datadict["child"].members), 3)
        self.assertIn("newperson", datadict["testgroup"].members)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetGroupMapBisAlt(self):
        test_posix_group = (
            "cn=test,ou=Group,dc=example,dc=com",
            {
                "sambaSID": ["S-1-5-21-2127521184-1604012920-1887927527-72713"],
                "gidNumber": [1000],
                "cn": ["testgroup"],
                "uniqueMember": ["cn=testguy,ou=People,dc=example,dc=com"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        dn_user = "cn=testguy,ou=People,dc=example,dc=com"
        test_posix_account = (
            dn_user,
            {
                "sambaSID": ["S-1-5-21-2562418665-3218585558-1813906818-1576"],
                "uidNumber": [1000],
                "gidNumber": [1000],
                "uid": ["test"],
                "cn": ["testguy"],
                "homeDirectory": ["/home/test"],
                "loginShell": ["/bin/sh"],
                "userPassword": ["p4ssw0rd"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )

        config = dict(self.config)
        config["rfc2307bis_alt"] = 1
        config["use_rid"] = 1
        attrlist = [
            "cn",
            "gidNumber",
            "uniqueMember",
            "uid",
            "sambaSID",
            "modifyTimestamp",
        ]
        uidattr = ["uid"]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_group], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
            (ldap.RES_SEARCH_ENTRY, [test_posix_account], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetGroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("testgroup", ent.name)
        self.assertEqual(1, len(ent.members))
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_has_calls(
            [
                mock.call(
                    base=mock.ANY,
                    filterstr=mock.ANY,
                    scope=mock.ANY,
                    attrlist=attrlist,
                    serverctrls=self.compareSPRC(),
                ),
                mock.call(
                    base=dn_user,
                    filterstr="(objectClass=*)",
                    scope=mock.ANY,
                    attrlist=uidattr,
                    serverctrls=self.compareSPRC(),
                ),
            ]
        )

    def testGetShadowMap(self):
        test_shadow = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "uid": ["test"],
                "shadowLastChange": ["11296"],
                "shadowMax": ["99999"],
                "shadowWarning": ["7"],
                "shadowInactive": ["-1"],
                "shadowExpire": ["-1"],
                "shadowFlag": ["134537556"],
                "modifyTimestamp": ["20070227012807Z"],
                "userPassword": ["{CRYPT}p4ssw0rd"],
            },
        )
        config = dict(self.config)
        attrlist = [
            "uid",
            "shadowLastChange",
            "shadowMin",
            "shadowMax",
            "shadowWarning",
            "shadowInactive",
            "shadowExpire",
            "shadowFlag",
            "userPassword",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_shadow], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetShadowMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("test", ent.name)
        self.assertEqual("p4ssw0rd", ent.passwd)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetShadowMapWithUidAttr(self):
        test_shadow = (
            "cn=test,ou=People,dc=example,dc=com",
            {
                "uid": ["test"],
                "name": ["test"],
                "shadowLastChange": ["11296"],
                "shadowMax": ["99999"],
                "shadowWarning": ["7"],
                "shadowInactive": ["-1"],
                "shadowExpire": ["-1"],
                "shadowFlag": ["134537556"],
                "modifyTimestamp": ["20070227012807Z"],
                "userPassword": ["{CRYPT}p4ssw0rd"],
            },
        )
        config = dict(self.config)
        config["uidattr"] = "name"
        attrlist = [
            "uid",
            "shadowLastChange",
            "shadowMin",
            "shadowMax",
            "shadowWarning",
            "shadowInactive",
            "shadowExpire",
            "shadowFlag",
            "userPassword",
            "name",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_shadow], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetShadowMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("test", ent.name)
        self.assertEqual("p4ssw0rd", ent.passwd)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetNetgroupMap(self):
        test_posix_netgroup = (
            "cn=test,ou=netgroup,dc=example,dc=com",
            {
                "cn": ["test"],
                "memberNisNetgroup": ["admins"],
                "nisNetgroupTriple": ["(-,hax0r,)"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        attrlist = [
            "cn",
            "memberNisNetgroup",
            "nisNetgroupTriple",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_netgroup], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetNetgroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("test", ent.name)
        self.assertEqual("(-,hax0r,) admins", ent.entries)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetNetgroupMapWithDupes(self):
        test_posix_netgroup = (
            "cn=test,ou=netgroup,dc=example,dc=com",
            {
                "cn": ["test"],
                "memberNisNetgroup": ["(-,hax0r,)"],
                "nisNetgroupTriple": ["(-,hax0r,)"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        attrlist = [
            "cn",
            "memberNisNetgroup",
            "nisNetgroupTriple",
            "modifyTimestamp",
        ]
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_posix_netgroup], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetNetgroupMap()

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("test", ent.name)
        self.assertEqual("(-,hax0r,)", ent.entries)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=mock.ANY,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetAutomountMap(self):
        test_automount = (
            "cn=user,ou=auto.home,ou=automounts,dc=example,dc=com",
            {
                "cn": ["user"],
                "automountInformation": ["-tcp,rw home:/home/user"],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        attrlist = ["cn", "automountInformation", "modifyTimestamp"]
        filterstr = "(objectclass=automount)"
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_automount], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetAutomountMap(location="TEST_BASE")

        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("user", ent.key)
        self.assertEqual("-tcp,rw", ent.options)
        self.assertEqual("home:/home/user", ent.location)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=filterstr,
            scope=mock.ANY,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testGetAutomountMasterMap(self):
        test_master_ou = (
            "ou=auto.master,ou=automounts,dc=example,dc=com",
            {"ou": ["auto.master"]},
        )
        test_automount = (
            "cn=/home,ou=auto.master,ou=automounts,dc=example,dc=com",
            {
                "cn": ["/home"],
                "automountInformation": [
                    "ldap:ldap:ou=auto.home," "ou=automounts,dc=example," "dc=com"
                ],
                "modifyTimestamp": ["20070227012807Z"],
            },
        )
        config = dict(self.config)
        scope = ldap.SCOPE_SUBTREE
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.side_effect = [
            (ldap.RES_SEARCH_ENTRY, [test_master_ou], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
            (ldap.RES_SEARCH_ENTRY, [test_automount], None, []),
            (ldap.RES_SEARCH_RESULT, None, None, []),
        ]

        source = ldapsource.LdapSource(config)
        data = source.GetAutomountMasterMap()
        self.assertEqual(1, len(data))
        ent = data.PopItem()
        self.assertEqual("/home", ent.key)
        self.assertEqual("ou=auto.home,ou=automounts,dc=example,dc=com", ent.location)
        self.assertEqual(None, ent.options)
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_has_calls(
            [
                # first search for the dn of ou=auto.master
                mock.call(
                    base=mock.ANY,
                    filterstr="(&(objectclass=automountMap)(ou=auto.master))",
                    scope=ldap.SCOPE_SUBTREE,
                    attrlist=["dn"],
                    serverctrls=self.compareSPRC(),
                ),
                # then search for the entries under ou=auto.master
                mock.call(
                    base="ou=auto.master,ou=automounts,dc=example,dc=com",
                    filterstr="(objectclass=automount)",
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=[
                        "cn",
                        "automountInformation",
                        "modifyTimestamp",
                    ],
                    serverctrls=self.compareSPRC(),
                ),
            ]
        )

    def testVerify(self):
        attrlist = [
            "uid",
            "uidNumber",
            "gidNumber",
            "gecos",
            "cn",
            "homeDirectory",
            "loginShell",
            "fullName",
            "modifyTimestamp",
        ]
        filterstr = "(&TEST_FILTER(modifyTimestamp>=19700101000001Z))"
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.return_value = (
            ldap.RES_SEARCH_RESULT,
            None,
            None,
            [],
        )

        source = ldapsource.LdapSource(self.config)

        self.assertEqual(0, source.Verify(0))
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=filterstr,
            scope=ldap.SCOPE_ONELEVEL,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )

    def testVerifyRID(self):
        attrlist = [
            "uid",
            "uidNumber",
            "gidNumber",
            "gecos",
            "cn",
            "homeDirectory",
            "loginShell",
            "fullName",
            "sambaSID",
            "modifyTimestamp",
        ]
        filterstr = "(&TEST_FILTER(modifyTimestamp>=19700101000001Z))"
        self.ldap_mock.ReconnectLDAPObject.return_value.result3.return_value = (
            ldap.RES_SEARCH_RESULT,
            None,
            None,
            [],
        )
        config = dict(self.config)
        config["use_rid"] = 1

        source = ldapsource.LdapSource(config)

        self.assertEqual(0, source.Verify(0))
        self.ldap_mock.ReconnectLDAPObject.return_value.search_ext.assert_called_with(
            base=mock.ANY,
            filterstr=filterstr,
            scope=ldap.SCOPE_ONELEVEL,
            attrlist=attrlist,
            serverctrls=self.compareSPRC(),
        )


class TestUpdateGetter(unittest.TestCase):
    def setUp(self):
        """Create a dummy source object."""
        super(TestUpdateGetter, self).setUp()

        class DummySource(list):
            """Dummy Source class for this test.

            Inherits from list as Sources are iterables.
            """

            def Search(self, search_base, search_filter, search_scope, attrs):
                pass

        self.source = DummySource()

    def testFromTimestampToLdap(self):
        ts = 1259641025
        expected_ldap_ts = "20091201041705Z"
        self.assertEqual(
            expected_ldap_ts, ldapsource.UpdateGetter({}).FromTimestampToLdap(ts)
        )

    def testFromLdapToTimestamp(self):
        expected_ts = 1259641025
        ldap_ts = "20091201041705Z"
        self.assertEqual(
            expected_ts, ldapsource.UpdateGetter({}).FromLdapToTimestamp(ldap_ts)
        )

    def testPasswdEmptySourceGetUpdates(self):
        """Test that getUpdates on the PasswdUpdateGetter works."""
        getter = ldapsource.PasswdUpdateGetter({})

        data = getter.GetUpdates(self.source, "TEST_BASE", "TEST_FILTER", "base", None)

        self.assertEqual(passwd.PasswdMap, type(data))

    def testGroupEmptySourceGetUpdates(self):
        """Test that getUpdates on the GroupUpdateGetter works."""
        getter = ldapsource.GroupUpdateGetter({})

        data = getter.GetUpdates(self.source, "TEST_BASE", "TEST_FILTER", "base", None)

        self.assertEqual(group.GroupMap, type(data))

    def testShadowEmptySourceGetUpdates(self):
        """Test that getUpdates on the ShadowUpdateGetter works."""
        getter = ldapsource.ShadowUpdateGetter({})

        data = getter.GetUpdates(self.source, "TEST_BASE", "TEST_FILTER", "base", None)

        self.assertEqual(shadow.ShadowMap, type(data))

    def testAutomountEmptySourceGetsUpdates(self):
        """Test that getUpdates on the AutomountUpdateGetter works."""
        getter = ldapsource.AutomountUpdateGetter({})

        data = getter.GetUpdates(self.source, "TEST_BASE", "TEST_FILTER", "base", None)

        self.assertEqual(automount.AutomountMap, type(data))

    def testBadScopeException(self):
        """Test that a bad scope raises a config.ConfigurationError."""
        # One of the getters is sufficient, they all inherit the
        # exception-raising code.
        getter = ldapsource.PasswdUpdateGetter({})

        self.assertRaises(
            error.ConfigurationError,
            getter.GetUpdates,
            self.source,
            "TEST_BASE",
            "TEST_FILTER",
            "BAD_SCOPE",
            None,
        )


if __name__ == "__main__":
    unittest.main()
