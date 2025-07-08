"""An implementation of a SCIM data source for nsscache."""

import json
import logging
import pycurl
import os
from io import StringIO

from nss_cache import error
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import sshkey
from nss_cache.sources import source
from nss_cache.sources.httpsource import UpdateGetter as HttpUpdateGetter


def RegisterImplementation(registration_callback):
    registration_callback(ScimSource)


class ScimSource(source.Source):
    """Source for data fetched via SCIM using the UpdateGetter pattern."""

    # SCIM defaults
    USERS_ENDPOINT = "Users"
    GROUPS_ENDPOINT = "Groups"
    AUTH_TOKEN = ""
    TIMEOUT = 60
    VERIFY_SSL = True
    RETRY_DELAY = 5
    RETRY_MAX = 3
    DEFAULT_SHELL = "/bin/bash"

    # for registration
    name = "scim"

    def __init__(self, conf, conn=None):
        """Initialise the SCIM Data Source.

        Args:
          conf: config.Config instance
          conn: pycurl.Curl object
        """
        super(ScimSource, self).__init__(conf)
        self._SetDefaults(conf)
        if not conn:
            conn = pycurl.Curl()
            conn.setopt(pycurl.NOPROGRESS, 1)
            conn.setopt(pycurl.NOSIGNAL, 1)
            # Don't hang on to connections from broken servers indefinitely.
            conn.setopt(pycurl.TIMEOUT, self.conf.get("timeout", self.TIMEOUT))
            conn.setopt(pycurl.USERAGENT, "nsscache")
            if not self.conf.get("verify_ssl", self.VERIFY_SSL):
                conn.setopt(pycurl.SSL_VERIFYPEER, 0)
                conn.setopt(pycurl.SSL_VERIFYHOST, 0)

        self.conn = conn

        # Validate required configuration
        if not self.conf.get("base_url") or not self.conf.get("auth_token"):
            raise error.ConfigurationError(f"SCIM base_url and auth_token are required. Got base_url='{self.conf.get('base_url')}', auth_token='{'redacted' if self.conf.get('auth_token') else None}'")

    def _SetDefaults(self, configuration):
        """Set defaults if necessary."""
        if "users_endpoint" not in configuration:
            configuration["users_endpoint"] = self.USERS_ENDPOINT
        if "groups_endpoint" not in configuration:
            configuration["groups_endpoint"] = self.GROUPS_ENDPOINT
        if "timeout" not in configuration:
            configuration["timeout"] = self.TIMEOUT
        if "verify_ssl" not in configuration:
            configuration["verify_ssl"] = self.VERIFY_SSL
        if "retry_delay" not in configuration:
            configuration["retry_delay"] = self.RETRY_DELAY
        if "retry_max" not in configuration:
            configuration["retry_max"] = self.RETRY_MAX
        if "default_shell" not in configuration:
            configuration["default_shell"] = self.DEFAULT_SHELL
        if "auth_token" not in configuration:
            configuration["auth_token"] = os.environ.get('NSSCACHE_SCIM_AUTH_TOKEN', self.AUTH_TOKEN)
    def GetPasswdMap(self, since=None):
        """Return the passwd map from this source.

        Args:
          since: Get data only changed since this timestamp (inclusive) or None
          for all data.

        Returns:
          instance of passwd.PasswdMap
        """
        users_url = f"{self.conf['base_url']}/{self.conf['users_endpoint']}"
        return PasswdUpdateGetter(self.conf).GetUpdates(self, users_url, since)

    def GetGroupMap(self, since=None):
        """Return the group map from this source.

        Args:
          since: Get data only changed since this timestamp (inclusive) or None
          for all data.

        Returns:
          instance of group.GroupMap
        """
        groups_url = f"{self.conf['base_url']}/{self.conf['groups_endpoint']}"
        return GroupUpdateGetter(self.conf).GetUpdates(self, groups_url, since)

    def GetSshkeyMap(self, since=None):
        """Return the sshkey map from this source.

        Args:
          since: Get data only changed since this timestamp (inclusive) or None
          for all data.

        Returns:
          instance of sshkey.SshkeyMap
        """
        users_url = f"{self.conf['base_url']}/{self.conf['users_endpoint']}"
        return SshkeyUpdateGetter(self.conf).GetUpdates(self, users_url, since)

class UpdateGetter(HttpUpdateGetter):
    """SCIM-specific update getter that extends HTTP functionality."""

    def GetUpdates(self, source, url, since):
        """Get updates from a SCIM source with pagination support.
        
        Fetches all pages using SCIM pagination.
        """
        # Store the source for parser creation
        self.source = source

        # Set SCIM-specific headers
        conn = source.conn
        headers = [
            f'Authorization: Bearer {source.conf["auth_token"]}',
            'Content-Type: application/scim+json',
            'Accept: application/scim+json'
        ]
        conn.setopt(pycurl.HTTPHEADER, headers)

        # Initialize the parser with the source
        parser = self.GetParser()
        
        # Initialize pagination variables
        current_start_index = 1
        page_map = self.CreateMap()
        
        # Use do-while pattern to fetch all pages
        while True:
            # Build URL with pagination parameters
            separator = "&" if "?" in url else "?"
            paginated_url = f"{url}{separator}startIndex={current_start_index}"

            # Fetch current page
            scim_body_bytes, _ = self.FetchUrlData(source, paginated_url, since)
            
            # Parse this page and add to existing map
            page_map = parser.GetMap(cache_info=scim_body_bytes, data=page_map)
            
            # Get pagination metadata from the parser
            pagination_metadata = parser._pagination_metadata
            total_results = pagination_metadata.get('totalResults', 0)
            items_per_page = pagination_metadata.get('itemsPerPage', 0)
            current_start_index = pagination_metadata.get('startIndex', 1)
            
            # Check if we have more pages to fetch
            if current_start_index + items_per_page - 1 >= total_results:
                break
            
            # Move to next page
            current_start_index = current_start_index + items_per_page

        return page_map or self.CreateMap()

class PasswdUpdateGetter(UpdateGetter):
    """Get passwd updates."""

    def __init__(self, conf):
        """Initialize with configuration."""
        super().__init__()
        self.conf = conf

    def GetParser(self):
        """Returns a MapParser to parse SCIM Users cache."""
        return ScimPasswdMapParser(self.source)

    def CreateMap(self):
        """Returns a new PasswdMap instance to have PasswdMapEntries added to
        it."""
        scim_path_username = self.conf.get("path_username")
        scim_path_uid = self.conf.get("path_uid")
        scim_path_gid = self.conf.get("path_gid")
        scim_path_home_directory = self.conf.get("path_home_directory")
        scim_path_login_shell = self.conf.get("path_login_shell")

        if not scim_path_gid or not scim_path_uid or not scim_path_username or not scim_path_home_directory or not scim_path_login_shell:
            raise error.ConfigurationError("The following configuration (scim_path_username, scim_path_uid, scim_path_gid, scim_path_home_directory, scim_path_login_shell) is required for the passwd map but not set in [passwd] section")

        return passwd.PasswdMap()

class GroupUpdateGetter(UpdateGetter):
    """Get group updates."""

    def __init__(self, conf):
        """Initialize with configuration."""
        super().__init__()
        self.conf = conf

    def GetParser(self):
        """Returns a MapParser to parse SCIM Groups cache."""
        return ScimGroupMapParser(self.source)

    def CreateMap(self):
        """Returns a new GroupMap instance to have GroupMapEntries added to
        it."""
        scim_path_gid = self.conf.get("path_gid")

        if not scim_path_gid:
            raise error.ConfigurationError("scim_path_gid configuration is required for group id extraction but not set in [group] section")

        return group.GroupMap()

class SshkeyUpdateGetter(UpdateGetter):
    """Get sshkey updates."""

    def __init__(self, conf):
        """Initialize with configuration."""
        super().__init__()
        self.conf = conf

    def GetParser(self):
        """Returns a MapParser to parse SCIM SSH keys cache."""
        return ScimSshkeyMapParser(self.source)

    def CreateMap(self):
        """Returns a new SshkeyMap instance to have SshkeyMapEntries added to
        it."""
        ssh_keys_path = self.conf.get("path_ssh_keys")

        if not ssh_keys_path:
            raise error.ConfigurationError("scim_path_ssh_keys configuration is required for SSH key extraction but not set in [sshkey] section")

        return sshkey.SshkeyMap()

class ScimMapParser(object):
    """A base class for parsing nss_files module cache."""

    def __init__(self, source=None):
        self.log = logging.getLogger(__name__)
        self.source = source
        self._store_pagination_metadata = True
        self._pagination_metadata = {}

    def _GetMapConfig(self, key, default=None):
        """Get configuration value from map-specific section, fallback to [DEFAULT].

        Args:
            key: Configuration key to look up (e.g., "scim_path_username")
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        if not (self.source and hasattr(self.source, 'conf')):
            return default

        # The config system strips the "scim_" prefix from keys in per-map sections
        # So "scim_path_username" becomes "path_username"
        stripped_key = key.replace("scim_", "", 1) if key.startswith("scim_") else key

        # First try map-specific config section (source config has map-specific values)
        if stripped_key in self.source.conf:
            return self.source.conf[stripped_key]

        # Then try the exact key name in case it's in the source config
        if key in self.source.conf:
            return self.source.conf[key]

        return default

    def _ExtractFromPath(self, data, path, default=None):
        """Extract value from SCIM data using a configurable path.

        Args:
            data: The SCIM resource data
            path: Slash-separated path like 'userName' or 'urn:enterprise:2.0:User/employeeNumber'
            default: Default value if path not found

        Returns:
            Extracted value or default
        """
        if not path:
            return default

        try:
            current = data
            for part in path.split('/'):
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return default
                if current is None:
                    return default
            return current
        except (KeyError, TypeError, AttributeError):
            return default

    def GetMap(self, cache_info, data):
        """Returns a map from a SCIM JSON response.

        Args:
          cache_info: file like object containing the SCIM JSON response.
          data: a Map to populate.
        Returns:
          A child of Map containing the cache data.
        """
        try:
            # Parse the SCIM JSON response
            scim_response = json.loads(cache_info.read())

            # Store pagination metadata
            self._pagination_metadata = {
                'totalResults': scim_response.get('totalResults', 0),
                'itemsPerPage': scim_response.get('itemsPerPage', 0),
                'startIndex': scim_response.get('startIndex', 1),
            }

            # SCIM responses have a "Resources" array
            resources = scim_response.get("Resources", [])

            for resource in resources:
                map_entries = self._ReadEntry(resource)

                # Handle both single entries and lists of entries
                if not isinstance(map_entries, list):
                    map_entries = [map_entries] if map_entries is not None else []

                for map_entry in map_entries:
                    if map_entry is None:
                        continue
                    if not data.Add(map_entry):
                        self.log.warning(
                            "Could not add entry %r from SCIM resource %r",
                            map_entry,
                            resource,
                        )

            self.log.info("Created %s map with %d entries", self.__class__.__name__, len(data))
            return data

        except json.JSONDecodeError as e:
            self.log.error("Failed to parse SCIM JSON response: %s", e)
            return data
        except Exception as e:
            self.log.error("Error processing SCIM response: %s", e)
            return data

class ScimPasswdMapParser(ScimMapParser):
    """Class for parsing SCIM Users into passwd cache."""

    def __init__(self, source=None):
        """Initialize with optional source for configuration access."""
        super().__init__(source)

    def _ReadEntry(self, user_data):
        """Return a PasswdMapEntry from a SCIM user resource."""

        # Extract username using configurable path
        username = self._ExtractUsername(user_data)
        if not username:
            self.log.warning("SCIM user missing userName, skipping")
            return None

        map_entry = passwd.PasswdMapEntry()
        map_entry.name = username
        map_entry.passwd = "x"  # Always use shadow passwords

        # Extract UID using configurable path
        uid = self._ExtractUid(user_data)
        if uid is None:
            self.log.warning("User %s missing UID, skipping", username)
            return None
        map_entry.uid = uid

        # Extract GID using configurable path
        gid = self._ExtractGid(user_data)
        if gid is None:
            gid = uid  # Default to same as UID
        map_entry.gid = gid

        # Extract other fields using configurable paths
        map_entry.gecos = self._ExtractGecos(user_data)
        map_entry.dir = self._ExtractHomeDir(user_data)
        map_entry.shell = self._ExtractShell(user_data)

        return map_entry

    def _ExtractUsername(self, user_data):
        """Extract username using configurable path."""
        username_path = self._GetMapConfig("scim_path_username", "userName")
        return self._ExtractFromPath(user_data, username_path) or user_data.get("userName")

    def _ExtractUid(self, user_data):
        """Extract UID using configurable path."""
        uid_path = self._GetMapConfig("scim_path_uid", "id")

        # Try the configured path first
        value = self._ExtractFromPath(user_data, uid_path)
        if value is not None:
            try:
                return int(value)
            except (ValueError, TypeError):
                pass

        # Fallback to standard SCIM locations
        fallback_sources = [
            lambda d: d.get("id"),
            lambda d: d.get("externalId"),
            lambda d: d.get("urn:ietf:params:scim:schemas:extension:enterprise:2.0:User", {}).get("employeeNumber"),
        ]

        for extractor in fallback_sources:
            try:
                value = extractor(user_data)
                if value is not None:
                    return int(value)
            except (ValueError, TypeError):
                continue

        return None

    def _ExtractGid(self, user_data):
        """Extract GID using configurable path."""
        gid_path = self._GetMapConfig("scim_path_gid", "")

        # Try the configured path first
        if gid_path:
            value = self._ExtractFromPath(user_data, gid_path)
            if value is not None:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
        return None

    def _ExtractGecos(self, user_data):
        """Extract GECOS (full name) from SCIM user data."""
        # Try to get full name from standard SCIM name structure
        name_data = user_data.get("name", {})
        if isinstance(name_data, dict):
            if name_data.get("formatted"):
                return name_data["formatted"]

            # Build from parts
            name_parts = []
            if name_data.get("givenName"):
                name_parts.append(name_data["givenName"])
            if name_data.get("familyName"):
                name_parts.append(name_data["familyName"])
            if name_parts:
                return " ".join(name_parts)

        # Fallback to displayName
        if user_data.get("displayName"):
            return user_data["displayName"]

        return ""

    def _ExtractHomeDir(self, user_data):
        """Extract home directory using configurable path."""
        home_path = self._GetMapConfig("scim_path_home_directory", "")

        # Try the configured path first
        if home_path:
            home_dir = self._ExtractFromPath(user_data, home_path)
            if home_dir:
                return home_dir

        # Fallback to enterprise extension
        enterprise_ext = user_data.get("urn:ietf:params:scim:schemas:extension:enterprise:2.0:User", {})
        home_dir = enterprise_ext.get("homeDirectory")
        if home_dir:
            return home_dir

        # Default to /home/username
        username = self._ExtractUsername(user_data)
        return f"/home/{username}" if username else "/home/unknown"

    def _ExtractShell(self, user_data):
        """Extract shell using configurable path."""
        shell_path = self._GetMapConfig("scim_path_login_shell", "")
        default_shell = self._GetMapConfig("scim_default_shell", "/bin/bash")

        # Try the configured path first
        if shell_path:
            shell = self._ExtractFromPath(user_data, shell_path)
            if shell:
                return shell

        # Fallback to enterprise extension
        enterprise_ext = user_data.get("urn:ietf:params:scim:schemas:extension:enterprise:2.0:User", {})
        shell = enterprise_ext.get("loginShell")
        if shell:
            return shell

        # Return the configured default shell
        return default_shell


class ScimSshkeyMapParser(ScimMapParser):
    """Class for parsing SCIM Users into sshkey cache."""

    def __init__(self, source=None):
        """Initialize with optional source for configuration access."""
        super().__init__(source)

    def _ReadEntry(self, user_data):
        """Return SshkeyMapEntry instances from a SCIM user resource."""
        entries = []

        # Extract username using configurable path
        username_path = self._GetMapConfig("scim_path_username", "userName")
        username = self._ExtractFromPath(user_data, username_path) or user_data.get("userName")

        if not username:
            self.log.warning("SCIM user missing userName, skipping SSH key extraction")
            return entries

        # Extract SSH keys using strictly config-driven path
        ssh_keys_path = self._GetMapConfig("scim_path_ssh_keys")
        if not ssh_keys_path:
            self.log.debug("No scim_path_ssh_keys configured, skipping SSH key extraction for user %s", username)
            return entries

        ssh_keys = self._ExtractFromPath(user_data, ssh_keys_path, [])

        # Ensure ssh_keys is a list
        if isinstance(ssh_keys, str):
            ssh_keys = [ssh_keys]
        elif not isinstance(ssh_keys, list):
            ssh_keys = []

        # Create an entry for each SSH key
        for ssh_key in ssh_keys:
            if ssh_key and ssh_key.strip():
                map_entry = sshkey.SshkeyMapEntry()
                map_entry.name = username
                map_entry.sshkey = ssh_key.strip()
                entries.append(map_entry)

        if ssh_keys:
            self.log.debug("Extracted %d SSH keys for user %s", len(ssh_keys), username)

        return entries


class ScimGroupMapParser(ScimMapParser):
    """Class for parsing SCIM Groups into group cache."""

    def __init__(self, source=None):
        """Initialize with optional source for configuration access."""
        super().__init__(source)

    def _ReadEntry(self, group_data):
        """Return a GroupMapEntry from a SCIM group resource."""

        # Use displayName or fallback to other name fields
        group_name = (group_data.get("displayName") or
                     group_data.get("name") or
                     group_data.get("id"))

        if not group_name:
            self.log.warning("SCIM group missing name, skipping")
            return None

        map_entry = group.GroupMapEntry()
        map_entry.name = group_name
        map_entry.passwd = "x"

        # Extract GID
        gid = self._ExtractGroupGid(group_data)
        if gid is None:
            self.log.warning("Group %s missing GID, skipping", group_name)
            return None
        map_entry.gid = gid

        # Extract members
        members = self._ExtractGroupMembers(group_data)
        map_entry.members = members

        return map_entry

    def _ExtractGroupGid(self, group_data):
        """Extract GID from SCIM group data using configurable path."""
        gid_path = self._GetMapConfig("scim_path_gid", "")

        # Try the configured path first
        if gid_path:
            value = self._ExtractFromPath(group_data, gid_path)
            if value is not None:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass

        return None

    def _ExtractGroupMembers(self, group_data):
        """Extract group members from SCIM group data using configurable path."""
        username_path = self._GetMapConfig("scim_path_username", "userName")
        members = []

        # Parse the username path to handle nested structures like "members/userName"
        if "/" in username_path:
            parts = username_path.split("/", 1)
            members_key = parts[0]
            username_key = parts[1]
            
            # Get the members array from the group data
            group_members = group_data.get(members_key, [])
            
            for member in group_members:
                if isinstance(member, dict):
                    # Extract username using the remaining path
                    username = self._ExtractFromPath(member, username_key)
                    if username:
                        members.append(username)
        else:
            # Handle simple case where username_path is just a field name
            group_members = group_data.get("members", [])
            
            for member in group_members:
                if isinstance(member, dict):
                    # Extract username using the configured path
                    username = self._ExtractFromPath(member, username_path)
                    if username:
                        members.append(username)
                elif isinstance(member, str):
                    # If member is already a string, use it directly
                    members.append(member)

        return members
