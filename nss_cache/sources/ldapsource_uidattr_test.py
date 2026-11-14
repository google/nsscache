# Copyright 2026 Google Inc.
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
# Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301, USA.
"""Custom LDAP UID validation through the public update path."""

import unittest

from nss_cache.sources import ldapsource


class SearchSource(list):
    def Search(self, **kwargs):
        pass


class CustomUidTest(unittest.TestCase):
    GETTERS = (
        ldapsource.PasswdUpdateGetter,
        ldapsource.ShadowUpdateGetter,
        ldapsource.SshkeyUpdateGetter,
    )

    def entry(self):
        return {
            "loginName": ["alice"],
            "cn": ["Alice"],
            "uidNumber": ["1000"],
            "gidNumber": ["1000"],
            "homeDirectory": ["/home/alice"],
            "modifyTimestamp": ["20260101000000Z"],
            "sshPublicKey": ["ssh-ed25519 AAAATEST alice"],
        }

    def assertCustomUidAccepted(self, getter_type):
        getter = getter_type({"uidattr": "loginName"})
        result = getter.GetUpdates(
            SearchSource([self.entry()]), "dc=example", "(objectClass=*)", "sub", None
        )
        self.assertEqual(["alice"], [entry.name for entry in result])

    def testPasswdCustomUidWithoutDefaultUid(self):
        self.assertCustomUidAccepted(ldapsource.PasswdUpdateGetter)

    def testShadowCustomUidWithoutDefaultUid(self):
        self.assertCustomUidAccepted(ldapsource.ShadowUpdateGetter)

    def testSshkeyCustomUidWithoutDefaultUid(self):
        self.assertCustomUidAccepted(ldapsource.SshkeyUpdateGetter)

    def testDefaultUidStillRequiredWithoutOverride(self):
        for getter_type in self.GETTERS:
            with self.subTest(getter=getter_type.__name__):
                getter = getter_type({})
                with self.assertRaises(ValueError):
                    getter.GetUpdates(
                        SearchSource([self.entry()]),
                        "dc=example",
                        "(objectClass=*)",
                        "sub",
                        None,
                    )

    def testConfiguredUidRequiredEvenIfDefaultUidPresent(self):
        for getter_type in self.GETTERS:
            with self.subTest(getter=getter_type.__name__):
                obj = self.entry()
                obj["uid"] = obj.pop("loginName")
                getter = getter_type({"uidattr": "loginName"})
                with self.assertRaises(ValueError):
                    getter.GetUpdates(
                        SearchSource([obj]),
                        "dc=example",
                        "(objectClass=*)",
                        "sub",
                        None,
                    )


if __name__ == "__main__":
    unittest.main()
