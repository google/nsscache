"""An implementation of a S3 data source for nsscache."""

__author__ = 'pikin@workato.com'

import base64
import collections
import logging
import json
import datetime
import boto3
from botocore.exceptions import ClientError

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import source

def RegisterImplementation(registration_callback):
  registration_callback(S3FilesSource)


class S3FilesSource(source.Source):
  """Source for data fetched from S3."""

  # S3 defaults
  BUCKET = ''
  PASSWD_OBJECT = ''
  GROUP_OBJECT = ''
  SHADOW_OBJECT = ''

  # for registration
  name = 's3'

  def __init__(self, conf):
    """Initialise the S3FilesSource object.

    Args:
      conf: A dictionary of key/value pairs.

    Raises:
      RuntimeError: object wasn't initialised with a dict
    """
    super(S3FilesSource, self).__init__(conf)
    self._SetDefaults(conf)
    self.s3_client = boto3.client('s3')

  def _SetDefaults(self, configuration):
    """Set defaults if necessary."""

    if 'bucket' not in configuration:
      configuration['bucket'] = self.BUCKET
    if 'passwd_object' not in configuration:
      configuration['passwd_object'] = self.PASSWD_OBJECT
    if 'group_object' not in configuration:
      configuration['group_object'] = self.GROUP_OBJECT
    if 'shadow_object' not in configuration:
      configuration['shadow_object'] = self.SHADOW_OBJECT

  def GetPasswdMap(self, since=None):
    """Return the passwd map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of passwd.PasswdMap
    """
    return PasswdUpdateGetter().GetUpdates(self.s3_client, self.conf['bucket'], self.conf['passwd_object'], since)

  def GetGroupMap(self, since=None):
    """Return the group map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of group.GroupMap
    """
    return GroupUpdateGetter().GetUpdates(self.s3_client, self.conf['bucket'], self.conf['group_object'], since)

  def GetShadowMap(self, since=None):
    """Return the shadow map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of shadow.ShadowMap
    """
    return ShadowUpdateGetter().GetUpdates(self.s3_client, self.conf['bucket'], self.conf['shadow_object'], since)

class S3UpdateGetter(object):
  """Base class that gets updates from s3."""

  def __init__(self):
    self.log = logging.getLogger(self.__class__.__name__)

  def FromTimestampToDateTime(self, ts):
    """Converts internal nss_cache timestamp to datetime object.

    Args:
      ts: number of seconds since epoch
    Returns:
      datetime object
    """
    return datetime.datetime.utcfromtimestamp(ts)

  def FromDateTimeToTimestamp(self, datetime_obj):
    """Converts datetime object to internal nss_cache timestamp.

    Args:
      datetime object
    Returns:
      number of seconds since epoch
    """
    return int((datetime_obj - datetime.datetime(1970,1,1)).total_seconds())

  def GetUpdates(self, s3_client, bucket, object, since):
    """Get updates from a source.

    Args:
      s3_client: initialized s3 client
      bucket: s3 bucket
      object: object with the data
      since: a timestamp representing the last change (None to force-get)

    Returns:
      A tuple containing the map of updates and a maximum timestamp

    Raises:
      ValueError: an object in the source map is malformed
      ConfigurationError:
    """
    try:
      if since is not None:
        response = s3_client.get_object(
          Bucket=bucket,
          IfModifiedSince=self.FromTimestampToDateTime(since),
          Key=object
        )
        # !!!
        # if response["code"] == 304:
        #   reutrn []
      else:
        response = s3_client.get_object(Bucket=bucket, Key=object)
      body = response["Body"]
      last_modified_ts = self.FromDateTimeToTimestamp(response["LastModified"])
    except ClientError as e:
      log.debug('error getting S3 object: {}'.format(e))
      raise error.SourceUnavailable('unable to download object from S3')

    data_map = self.GetMap(cache_info=body)
    data_map.SetModifyTimestamp(last_modified_ts)
    return data_map

  def GetParser(self):
    """Return the appropriate parser. Must be implemented by child class."""
    raise NotImplementedError

  def GetMap(self, cache_info):
    """Creates a Map from the cache_info data.

    Args:
      cache_info: file-like object containing the data to parse

    Returns:
      A child of Map containing the cache data.
    """
    return self.GetParser().GetMap(cache_info, self.CreateMap())


class PasswdUpdateGetter(S3UpdateGetter):
  """Get passwd updates."""

  def GetParser(self):
    """Returns a MapParser to parse FilesPasswd cache."""
    return S3PasswdMapParser()

  def CreateMap(self):
    """Returns a new PasswdMap instance to have PasswdMapEntries added to it."""
    return passwd.PasswdMap()


class GroupUpdateGetter(S3UpdateGetter):
  """Get group updates."""

  def GetParser(self):
    """Returns a MapParser to parse FilesGroup cache."""
    return S3GroupMapParser()

  def CreateMap(self):
    """Returns a new GroupMap instance to have GroupMapEntries added to it."""
    return group.GroupMap()


class ShadowUpdateGetter(S3UpdateGetter):
  """Get shadow updates."""

  def GetParser(self):
    """Returns a MapParser to parse FilesShadow cache."""
    return S3ShadowMapParser()

  def CreateMap(self):
    """Returns a new ShadowMap instance to have ShadowMapEntries added to it."""
    return shadow.ShadowMap()

class S3MapParser(object):
  """A base class for parsing nss_files module cache."""

  def __init__(self):
    self.log = logging.getLogger(self.__class__.__name__)

  def GetMap(self, cache_info, data):
    """Returns a map from a cache.

    Args:
      cache_info: file like object containing the cache.
      data: a Map to populate.
    Returns:
      A child of Map containing the cache data.
    """
    for obj in json.loads(cache_info.read()):
      key = obj.get('Key', '')
      value = obj.get('Value', '')
      if not value or not key:
        continue
      map_entry = self._ReadEntry(key, value)
      if map_entry is None:
        self.log.warn('Could not create entry from line %r in cache, skipping', value)
        continue
      if not data.Add(map_entry):
        self.log.warn('Could not add entry %r read from line %r in cache', map_entry, value)
    return data


class S3PasswdMapParser(S3MapParser):
  """Class for parsing nss_files module passwd cache."""

  def _ReadEntry(self, name, entry):
    """Return a PasswdMapEntry from a record in the target cache."""

    map_entry = passwd.PasswdMapEntry()
    # maps expect strict typing, so convert to int as appropriate.
    map_entry.name = name
    map_entry.passwd = entry.get('passwd', 'x')

    try:
      map_entry.uid = int(entry['uid'])
      map_entry.gid = int(entry['gid'])
    except (ValueError, KeyError):
      return None

    map_entry.gecos = entry.get('comment', '')
    map_entry.dir = entry.get('home', '/home/{}'.format(name))
    map_entry.shell = entry.get('shell', '/bin/bash')

    return map_entry


class S3GroupMapParser(S3MapParser):
  """Class for parsing a nss_files module group cache."""

  def _ReadEntry(self, name, entry):
    """Return a GroupMapEntry from a record in the target cache."""

    map_entry = group.GroupMapEntry()
    # map entries expect strict typing, so convert as appropriate
    map_entry.name = name
    map_entry.passwd = entry.get('passwd', 'x')

    try:
      map_entry.gid = int(entry['gid'])
    except (ValueError, KeyError):
      return None

    try:
      members = entry.get('members', '').split('\n')
    except (ValueError, TypeError):
      members = ['']
    map_entry.members = members
    return map_entry

class S3ShadowMapParser(S3MapParser):
  """Class for parsing nss_files module shadow cache."""

  def _ReadEntry(self, name, entry):
    """Return a ShadowMapEntry from a record in the target cache."""

    map_entry = shadow.ShadowMapEntry()
    # maps expect strict typing, so convert to int as appropriate.
    map_entry.name = name
    map_entry.passwd = entry.get('passwd', '*')

    for attr in ['lstchg', 'min', 'max', 'warn', 'inact', 'expire']:
      try:
        setattr(map_entry, attr, int(entry[attr]))
      except (ValueError, KeyError):
        continue

    return map_entry
