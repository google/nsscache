"""An implementation of a consul data source for nsscache."""

__author__ = "hexedpackets@gmail.com (William Huba)"

import base64
import collections
import logging
import json

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import httpsource


def RegisterImplementation(registration_callback):
    registration_callback(ConsulFilesSource)


class ConsulFilesSource(httpsource.HttpFilesSource):
    """Source for data fetched via Consul."""

    # Consul defaults
    DATACENTER = "dc1"
    TOKEN = ""

    # for registration
    name = "consul"

    def _SetDefaults(self, configuration):
        """Set defaults if necessary."""

        super(ConsulFilesSource, self)._SetDefaults(configuration)

        if "token" not in configuration:
            configuration["token"] = self.TOKEN
        if "datacenter" not in configuration:
            configuration["datacenter"] = self.DATACENTER

        for url in ["passwd_url", "group_url", "shadow_url"]:
            configuration[url] = "{}?recurse&token={}&dc={}".format(
                configuration[url], configuration["token"], configuration["datacenter"]
            )

    def GetPasswdMap(self, since=None):
        """Return the passwd map from this source.

        Args:
          since: Get data only changed since this timestamp (inclusive) or None
          for all data.

        Returns:
          instance of passwd.PasswdMap
        """
        return PasswdUpdateGetter().GetUpdates(self, self.conf["passwd_url"], since)

    def GetGroupMap(self, since=None):
        """Return the group map from this source.

        Args:
          since: Get data only changed since this timestamp (inclusive) or None
          for all data.

        Returns:
          instance of group.GroupMap
        """
        return GroupUpdateGetter().GetUpdates(self, self.conf["group_url"], since)

    def GetShadowMap(self, since=None):
        """Return the shadow map from this source.

        Args:
          since: Get data only changed since this timestamp (inclusive) or None
          for all data.

        Returns:
          instance of shadow.ShadowMap
        """
        return ShadowUpdateGetter().GetUpdates(self, self.conf["shadow_url"], since)


class PasswdUpdateGetter(httpsource.UpdateGetter):
    """Get passwd updates."""

    def GetParser(self):
        """Returns a MapParser to parse FilesPasswd cache."""
        return ConsulPasswdMapParser()

    def CreateMap(self):
        """Returns a new PasswdMap instance to have PasswdMapEntries added to
        it."""
        return passwd.PasswdMap()


class GroupUpdateGetter(httpsource.UpdateGetter):
    """Get group updates."""

    def GetParser(self):
        """Returns a MapParser to parse FilesGroup cache."""
        return ConsulGroupMapParser()

    def CreateMap(self):
        """Returns a new GroupMap instance to have GroupMapEntries added to
        it."""
        return group.GroupMap()


class ShadowUpdateGetter(httpsource.UpdateGetter):
    """Get shadow updates."""

    def GetParser(self):
        """Returns a MapParser to parse FilesShadow cache."""
        return ConsulShadowMapParser()

    def CreateMap(self):
        """Returns a new ShadowMap instance to have ShadowMapEntries added to
        it."""
        return shadow.ShadowMap()


class ConsulMapParser(object):
    """A base class for parsing nss_files module cache."""

    def __init__(self):
        self.log = logging.getLogger(__name__)

    def GetMap(self, cache_info, data):
        """Returns a map from a cache.

        Args:
          cache_info: file like object containing the cache.
          data: a Map to populate.
        Returns:
          A child of Map containing the cache data.
        """

        entries = collections.defaultdict(dict)
        for line in json.loads(cache_info.read()):
            key = line.get("Key", "").split("/")
            value = line.get("Value", "")
            if not value or not key:
                continue
            value = base64.b64decode(value)
            name = str(key[-2])
            entry_piece = key[-1]
            entries[name][entry_piece] = value

        for name, entry in list(entries.items()):
            map_entry = self._ReadEntry(name, entry)
            if map_entry is None:
                self.log.warning(
                    "Could not create entry from line %r in cache, skipping", entry
                )
                continue
            if not data.Add(map_entry):
                self.log.warning(
                    "Could not add entry %r read from line %r in cache",
                    map_entry,
                    entry,
                )
        return data


class ConsulPasswdMapParser(ConsulMapParser):
    """Class for parsing nss_files module passwd cache."""

    def _ReadEntry(self, name, entry):
        """Return a PasswdMapEntry from a record in the target cache."""

        map_entry = passwd.PasswdMapEntry()
        # maps expect strict typing, so convert to int as appropriate.
        map_entry.name = name
        map_entry.passwd = entry.get("passwd", "x")

        try:
            map_entry.uid = int(entry["uid"])
            map_entry.gid = int(entry["gid"])
        except (ValueError, KeyError):
            return None

        map_entry.gecos = entry.get("comment", "")
        map_entry.dir = entry.get("home", "/home/{}".format(name))
        map_entry.shell = entry.get("shell", "/bin/bash")

        return map_entry


class ConsulGroupMapParser(ConsulMapParser):
    """Class for parsing a nss_files module group cache."""

    def _ReadEntry(self, name, entry):
        """Return a GroupMapEntry from a record in the target cache."""

        map_entry = group.GroupMapEntry()
        # map entries expect strict typing, so convert as appropriate
        map_entry.name = name
        map_entry.passwd = entry.get("passwd", "x")

        try:
            map_entry.gid = int(entry["gid"])
        except (ValueError, KeyError):
            return None

        try:
            s = entry.get("members", "").decode("utf-8")
            members = s.split("\n")
        except AttributeError:
            members = entry.get("members", "").split("\n")
        except (ValueError, TypeError):
            members = [""]
        map_entry.members = members
        return map_entry


class ConsulShadowMapParser(ConsulMapParser):
    """Class for parsing nss_files module shadow cache."""

    def _ReadEntry(self, name, entry):
        """Return a ShadowMapEntry from a record in the target cache."""

        map_entry = shadow.ShadowMapEntry()
        # maps expect strict typing, so convert to int as appropriate.
        map_entry.name = name
        map_entry.passwd = entry.get("passwd", "*")
        if isinstance(map_entry.passwd, bytes):
            map_entry.passwd = map_entry.passwd.decode("ascii")

        for attr in ["lstchg", "min", "max", "warn", "inact", "expire"]:
            try:
                setattr(map_entry, attr, int(entry[attr]))
            except (ValueError, KeyError):
                continue

        return map_entry
