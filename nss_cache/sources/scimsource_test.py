"""Unit tests for SCIM data source for nsscache."""

import json
import os
import unittest
import pycurl
from unittest import mock

from nss_cache import error
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import sshkey

from nss_cache.sources import scimsource
from nss_cache.util import curl


class TestScimSource(unittest.TestCase):
    def setUp(self):
        """Initialize a basic config dict."""
        super(TestScimSource, self).setUp()
        self.config = {
            "base_url": "https://api.example.com/scim",
            "auth_token": "test_token",
            "users_endpoint": "Users",
            "groups_endpoint": "Groups",
            "timeout": 30,
            "verify_ssl": True,
            "retry_delay": 3,
            "retry_max": 2,
            "default_shell": "/bin/zsh",
        }

    def testDefaultConfiguration(self):
        """Test that default configuration values are set correctly."""
        config = {
            "base_url": "https://api.example.com/scim",
            "auth_token": "test_token"
        }
        source = scimsource.ScimSource(config)
        
        self.assertEqual(source.conf["users_endpoint"], scimsource.ScimSource.USERS_ENDPOINT)
        self.assertEqual(source.conf["groups_endpoint"], scimsource.ScimSource.GROUPS_ENDPOINT)
        self.assertEqual(source.conf["timeout"], scimsource.ScimSource.TIMEOUT)
        self.assertEqual(source.conf["verify_ssl"], scimsource.ScimSource.VERIFY_SSL)
        self.assertEqual(source.conf["retry_delay"], scimsource.ScimSource.RETRY_DELAY)
        self.assertEqual(source.conf["retry_max"], scimsource.ScimSource.RETRY_MAX)
        self.assertEqual(source.conf["default_shell"], scimsource.ScimSource.DEFAULT_SHELL)

    def testOverrideDefaultConfiguration(self):
        """Test that configuration values can be overridden."""
        source = scimsource.ScimSource(self.config)
        
        self.assertEqual(source.conf["base_url"], "https://api.example.com/scim")
        self.assertEqual(source.conf["auth_token"], "test_token")
        self.assertEqual(source.conf["users_endpoint"], "Users")
        self.assertEqual(source.conf["groups_endpoint"], "Groups")
        self.assertEqual(source.conf["timeout"], 30)
        self.assertEqual(source.conf["verify_ssl"], True)
        self.assertEqual(source.conf["retry_delay"], 3)
        self.assertEqual(source.conf["retry_max"], 2)
        self.assertEqual(source.conf["default_shell"], "/bin/zsh")

    def testMissingBaseUrlRaisesError(self):
        """Test that missing base_url raises ConfigurationError."""
        config = {"auth_token": "test_token"}
        
        with self.assertRaises(error.ConfigurationError) as cm:
            scimsource.ScimSource(config)
        
        self.assertIn("base_url and auth_token are required", str(cm.exception))

    def testMissingAuthTokenRaisesError(self):
        """Test that missing auth_token raises ConfigurationError."""
        config = {"base_url": "https://api.example.com/scim"}
        
        with self.assertRaises(error.ConfigurationError) as cm:
            scimsource.ScimSource(config)
        
        self.assertIn("base_url and auth_token are required", str(cm.exception))

    @mock.patch.dict(os.environ, {'NSSCACHE_SCIM_AUTH_TOKEN': 'env_token'})
    def testAuthTokenFromEnvironment(self):
        """Test that auth_token can be loaded from environment variable."""
        config = {"base_url": "https://api.example.com/scim"}
        source = scimsource.ScimSource(config)
        
        self.assertEqual(source.conf["auth_token"], "env_token")

    def testVerifySslDisabled(self):
        """Test that SSL verification can be disabled."""
        config = {
            "base_url": "https://api.example.com/scim",
            "auth_token": "test_token",
            "verify_ssl": False
        }
        
        with mock.patch('pycurl.Curl') as mock_curl:
            mock_conn = mock.Mock()
            mock_curl.return_value = mock_conn
            
            source = scimsource.ScimSource(config)
            
            mock_conn.setopt.assert_any_call(pycurl.SSL_VERIFYPEER, 0)
            mock_conn.setopt.assert_any_call(pycurl.SSL_VERIFYHOST, 0)


class TestScimUpdateGetter(unittest.TestCase):
    def setUp(self):
        super().setUp()
        curl_patcher = mock.patch.object(pycurl, "Curl")
        self.addCleanup(curl_patcher.stop)
        self.curl_mock = curl_patcher.start()

    def testGetUpdatesWithPagination(self):
        """Test that pagination works correctly by reading from SCIM response."""
        mock_conn = mock.Mock()
        mock_conn.getinfo.return_value = 200
        self.curl_mock.return_value = mock_conn
        
        config = {
            "base_url": "https://api.example.com/scim",
            "auth_token": "test_token"
        }
        source = scimsource.ScimSource(config)
        
        # Mock the first page response with pagination info
        first_page_response = {
            "totalResults": 75,
            "itemsPerPage": 50,
            "startIndex": 1,
            "Resources": [{"id": str(i), "userName": f"user{i}"} for i in range(1, 51)]
        }
        
        # Mock the second page response
        second_page_response = {
            "totalResults": 75,
            "itemsPerPage": 25,
            "startIndex": 51,
            "Resources": [{"id": str(i), "userName": f"user{i}"} for i in range(51, 76)]
        }
        
        with mock.patch.object(curl, 'CurlFetch') as mock_curl_fetch:
            mock_curl_fetch.side_effect = [
                (200, "", json.dumps(first_page_response).encode('utf-8')),
                (200, "", json.dumps(second_page_response).encode('utf-8'))
            ]
            
            getter = scimsource.UpdateGetter()
            getter.source = source
            
            # Mock the parser and its pagination metadata
            mock_parser = mock.Mock()
            
            # Mock the first map returned by GetMap 
            mock_first_map = mock.Mock()
            mock_first_map.__len__ = mock.Mock(return_value=50)
            
            # Mock the second map returned by GetMap
            mock_second_map = mock.Mock()
            mock_second_map.__len__ = mock.Mock(return_value=75)  # Total items after both pages
            
            # Track which call we're on
            call_count = 0
            
            # Configure GetMap to return the mocked maps and update pagination metadata
            def mock_get_map(cache_info, data):
                nonlocal call_count
                call_count += 1
                
                if call_count == 1:
                    # First page
                    mock_parser._pagination_metadata = {
                        'totalResults': 75,
                        'itemsPerPage': 50,
                        'startIndex': 1
                    }
                    return mock_first_map
                else:
                    # Second page  
                    mock_parser._pagination_metadata = {
                        'totalResults': 75,
                        'itemsPerPage': 25,
                        'startIndex': 51
                    }
                    return mock_second_map
            
            mock_parser.GetMap = mock.Mock(side_effect=mock_get_map)
            
            getter.GetParser = mock.Mock(return_value=mock_parser)
            getter.CreateMap = mock.Mock(return_value=mock.Mock())
            
            result = getter.GetUpdates(source, "https://api.example.com/scim/Users", None)
            
            # Should call CurlFetch twice (first page + second page)
            self.assertEqual(mock_curl_fetch.call_count, 2)
            
            # Should call GetMap twice (first page + second page)  
            self.assertEqual(mock_parser.GetMap.call_count, 2)
            
            # Verify the URLs include pagination parameters
            call_args = mock_curl_fetch.call_args_list
            self.assertIn("Users", call_args[0][0][0])  # First call should be to base URL
            self.assertIn("startIndex=51", call_args[1][0][0])  # Second call should have pagination


class TestScimPasswdUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestScimPasswdUpdateGetter, self).setUp()
        self.config = {
            "path_username": "userName",
            "path_uid": "id",
            "path_gid": "id",
            "path_home_directory": "homeDirectory",
            "path_login_shell": "loginShell"
        }
        self.updater = scimsource.PasswdUpdateGetter(self.config)

    def testGetParser(self):
        """Test that GetParser returns correct parser type."""
        self.updater.source = mock.Mock()
        parser = self.updater.GetParser()
        self.assertTrue(isinstance(parser, scimsource.ScimPasswdMapParser))

    def testCreateMap(self):
        """Test that CreateMap returns PasswdMap."""
        passwd_map = self.updater.CreateMap()
        self.assertTrue(isinstance(passwd_map, passwd.PasswdMap))

    def testCreateMapMissingRequiredConfig(self):
        """Test that CreateMap raises error when required config is missing."""
        incomplete_config = {"path_username": "userName"}
        updater = scimsource.PasswdUpdateGetter(incomplete_config)
        
        with self.assertRaises(error.ConfigurationError) as cm:
            updater.CreateMap()
        
        self.assertIn("required for the passwd map", str(cm.exception))


class TestScimGroupUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestScimGroupUpdateGetter, self).setUp()
        self.config = {"path_gid": "id"}
        self.updater = scimsource.GroupUpdateGetter(self.config)

    def testGetParser(self):
        """Test that GetParser returns correct parser type."""
        self.updater.source = mock.Mock()
        parser = self.updater.GetParser()
        self.assertTrue(isinstance(parser, scimsource.ScimGroupMapParser))

    def testCreateMap(self):
        """Test that CreateMap returns GroupMap."""
        group_map = self.updater.CreateMap()
        self.assertTrue(isinstance(group_map, group.GroupMap))

    def testCreateMapMissingRequiredConfig(self):
        """Test that CreateMap raises error when required config is missing."""
        incomplete_config = {}
        updater = scimsource.GroupUpdateGetter(incomplete_config)
        
        with self.assertRaises(error.ConfigurationError) as cm:
            updater.CreateMap()
        
        self.assertIn("scim_path_gid configuration is required", str(cm.exception))


class TestScimSshkeyUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestScimSshkeyUpdateGetter, self).setUp()
        self.config = {"path_ssh_keys": "sshKeys"}
        self.updater = scimsource.SshkeyUpdateGetter(self.config)

    def testGetParser(self):
        """Test that GetParser returns correct parser type."""
        self.updater.source = mock.Mock()
        parser = self.updater.GetParser()
        self.assertTrue(isinstance(parser, scimsource.ScimSshkeyMapParser))

    def testCreateMap(self):
        """Test that CreateMap returns SshkeyMap."""
        sshkey_map = self.updater.CreateMap()
        self.assertTrue(isinstance(sshkey_map, sshkey.SshkeyMap))

    def testCreateMapMissingRequiredConfig(self):
        """Test that CreateMap raises error when required config is missing."""
        incomplete_config = {}
        updater = scimsource.SshkeyUpdateGetter(incomplete_config)
        
        with self.assertRaises(error.ConfigurationError) as cm:
            updater.CreateMap()
        
        self.assertIn("scim_path_ssh_keys configuration is required", str(cm.exception))


class TestScimMapParser(unittest.TestCase):
    def setUp(self):
        super(TestScimMapParser, self).setUp()
        self.mock_source = mock.Mock()
        self.mock_source.conf = {
            "path_username": "userName",
            "scim_path_uid": "id"
        }
        self.parser = scimsource.ScimMapParser(self.mock_source)

    def testGetMapConfig(self):
        """Test _GetMapConfig method."""
        # Test stripped key lookup
        result = self.parser._GetMapConfig("scim_path_username", "default")
        self.assertEqual(result, "userName")
        
        # Test exact key lookup
        result = self.parser._GetMapConfig("scim_path_uid", "default")
        self.assertEqual(result, "id")
        
        # Test default value
        result = self.parser._GetMapConfig("nonexistent_key", "default")
        self.assertEqual(result, "default")

    def testExtractFromPath(self):
        """Test _ExtractFromPath method."""
        data = {
            "userName": "testuser",
            "name": {
                "givenName": "Test",
                "familyName": "User"
            }
        }
        
        # Test simple path
        result = self.parser._ExtractFromPath(data, "userName")
        self.assertEqual(result, "testuser")
        
        # Test nested path
        result = self.parser._ExtractFromPath(data, "name/givenName")
        self.assertEqual(result, "Test")
        
        # Test nonexistent path
        result = self.parser._ExtractFromPath(data, "nonexistent", "default")
        self.assertEqual(result, "default")

    def testGetMapWithValidJson(self):
        """Test GetMap with valid SCIM JSON response."""
        scim_response = {
            "Resources": [
                {"id": "1", "userName": "user1"},
                {"id": "2", "userName": "user2"}
            ]
        }
        
        mock_cache_info = mock.Mock()
        mock_cache_info.read.return_value = json.dumps(scim_response)
        
        mock_data = mock.Mock()
        mock_data.Add.return_value = True
        mock_data.__len__ = mock.Mock(return_value=2)
        
        # Mock _ReadEntry to return mock entries
        self.parser._ReadEntry = mock.Mock(side_effect=[mock.Mock(), mock.Mock()])
        
        result = self.parser.GetMap(mock_cache_info, mock_data)
        
        self.assertEqual(result, mock_data)
        self.assertEqual(self.parser._ReadEntry.call_count, 2)

    def testGetMapWithInvalidJson(self):
        """Test GetMap with invalid JSON response."""
        mock_cache_info = mock.Mock()
        mock_cache_info.read.return_value = "invalid json"
        
        mock_data = mock.Mock()
        mock_data.__len__ = mock.Mock(return_value=0)
        
        result = self.parser.GetMap(mock_cache_info, mock_data)
        
        self.assertEqual(result, mock_data)


class TestScimPasswdMapParser(unittest.TestCase):
    def setUp(self):
        super(TestScimPasswdMapParser, self).setUp()
        self.mock_source = mock.Mock()
        self.mock_source.conf = {
            "path_username": "userName",
            "path_uid": "id",
            "path_gid": "id",
            "path_home_directory": "homeDirectory",
            "path_login_shell": "loginShell"
        }
        self.parser = scimsource.ScimPasswdMapParser(self.mock_source)

    def testReadEntryValidUser(self):
        """Test _ReadEntry with valid user data."""
        user_data = {
            "id": "1001",
            "userName": "testuser",
            "homeDirectory": "/home/testuser",
            "loginShell": "/bin/bash",
            "name": {"formatted": "Test User"}
        }
        
        entry = self.parser._ReadEntry(user_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testuser")
        self.assertEqual(entry.uid, 1001)
        self.assertEqual(entry.gid, 1001)
        self.assertEqual(entry.dir, "/home/testuser")
        self.assertEqual(entry.shell, "/bin/bash")
        self.assertEqual(entry.gecos, "Test User")

    def testReadEntryMissingUsername(self):
        """Test _ReadEntry with missing username."""
        user_data = {"id": "1001"}
        
        entry = self.parser._ReadEntry(user_data)
        
        self.assertIsNone(entry)

    def testReadEntryMissingUid(self):
        """Test _ReadEntry with missing UID."""
        user_data = {"userName": "testuser"}
        
        entry = self.parser._ReadEntry(user_data)
        
        self.assertIsNone(entry)


class TestScimSshkeyMapParser(unittest.TestCase):
    def setUp(self):
        super(TestScimSshkeyMapParser, self).setUp()
        self.mock_source = mock.Mock()
        self.mock_source.conf = {
            "path_username": "userName",
            "path_ssh_keys": "sshKeys"
        }
        self.parser = scimsource.ScimSshkeyMapParser(self.mock_source)

    def testReadEntryWithSshKeys(self):
        """Test _ReadEntry with SSH keys."""
        user_data = {
            "userName": "testuser",
            "sshKeys": [
                "ssh-rsa AAAAB3NzaC1yc2EAAAA... user@host1",
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... user@host2"
            ]
        }
        
        entries = self.parser._ReadEntry(user_data)
        
        self.assertEqual(len(entries), 2)
        for entry in entries:
            self.assertEqual(entry.name, "testuser")
            self.assertTrue(entry.sshkey.startswith("ssh-"))

    def testReadEntryNoSshKeysPath(self):
        """Test _ReadEntry when SSH keys path is not configured."""
        self.mock_source.conf = {"path_username": "userName"}
        parser = scimsource.ScimSshkeyMapParser(self.mock_source)
        
        user_data = {"userName": "testuser"}
        
        entries = parser._ReadEntry(user_data)
        
        self.assertEqual(len(entries), 0)


class TestScimGroupMapParser(unittest.TestCase):
    def setUp(self):
        super(TestScimGroupMapParser, self).setUp()
        self.mock_source = mock.Mock()
        self.mock_source.conf = {
            "path_gid": "id",
            "path_username": "members/value"
        }
        self.parser = scimsource.ScimGroupMapParser(self.mock_source)

    def testReadEntryValidGroup(self):
        """Test _ReadEntry with valid group data."""
        group_data = {
            "id": "2001",
            "displayName": "testgroup",
            "members": [
                {"value": "user1"},
                {"value": "user2"}
            ]
        }
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testgroup")
        self.assertEqual(entry.gid, 2001)
        self.assertEqual(entry.members, ["user1", "user2"])

    def testReadEntryMissingGid(self):
        """Test _ReadEntry with missing GID."""
        group_data = {"displayName": "testgroup"}
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNone(entry)

    def testReadEntryWithNestedMemberPath(self):
        """Test _ReadEntry with nested member path like 'members/username'."""
        self.mock_source.conf["path_username"] = "members/username"
        
        group_data = {
            "id": "2003",
            "displayName": "testgroup3",
            "members": [
                {"username": "user5", "display": "User Five"},
                {"username": "user6", "display": "User Six"}
            ]
        }
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testgroup3")
        self.assertEqual(entry.gid, 2003)
        self.assertEqual(entry.members, ["user5", "user6"])

    def testReadEntryWithSimpleMemberPath(self):
        """Test _ReadEntry with simple member path (no slash)."""
        self.mock_source.conf["path_username"] = "userName"
        
        group_data = {
            "id": "2004",
            "displayName": "testgroup4",
            "members": [
                {"userName": "user7"},
                {"userName": "user8"}
            ]
        }
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testgroup4")
        self.assertEqual(entry.gid, 2004)
        self.assertEqual(entry.members, ["user7", "user8"])

    def testReadEntryWithStringMembers(self):
        """Test _ReadEntry with string members."""
        self.mock_source.conf["path_username"] = "userName"
        
        group_data = {
            "id": "2005",
            "displayName": "testgroup5",
            "members": ["user9", "user10"]
        }
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testgroup5")
        self.assertEqual(entry.gid, 2005)
        self.assertEqual(entry.members, ["user9", "user10"])

    def testReadEntryWithEmptyMembers(self):
        """Test _ReadEntry with empty members array."""
        group_data = {
            "id": "2006",
            "displayName": "testgroup6",
            "members": []
        }
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testgroup6")
        self.assertEqual(entry.gid, 2006)
        self.assertEqual(entry.members, [])

    def testReadEntryWithMissingMembers(self):
        """Test _ReadEntry with missing members field."""
        group_data = {
            "id": "2007",
            "displayName": "testgroup7"
        }
        
        entry = self.parser._ReadEntry(group_data)
        
        self.assertIsNotNone(entry)
        self.assertEqual(entry.name, "testgroup7")
        self.assertEqual(entry.gid, 2007)
        self.assertEqual(entry.members, [])


if __name__ == "__main__":
    unittest.main()
