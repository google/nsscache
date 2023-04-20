"""An implementation of a GCS data source for nsscache."""

import io
import logging

from google.cloud import exceptions
from google.cloud import storage

from nss_cache import error
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import source
from nss_cache.util import file_formats


class GcsFilesSource(source.Source):
    """Source for data fetched from GCS."""

    # GCS Defaults
    BUCKET = ''
    PASSWD_OBJECT = ''
    GROUP_OBJECT = ''
    SHADOW_OBJECT = ''

    # for registration
    name = 'gcs'

    def __init__(self, conf):
        """Initialize the GcsFilesSource object.

        Args:
          conf: A dictionary of key/value pairs.

        Raises:
          RuntimeError: object wasn't initialized with a dict.
        """
        super(GcsFilesSource, self).__init__(conf)
        self._SetDefaults(conf)
        self._gcs_client = None

    def _GetClient(self):
        if self._gcs_client is None:
            self._gcs_client = storage.Client()

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

    def GetPasswdMap(self):
        """Return the passwd map from this source.

        Returns:
          instnace of passwd.PasswdMap
        """
        return PasswdUpdateGetter().GetUpdates(self._GetClient(),
                                               self.conf['bucket'],
                                               self.conf['passwd_object'])

    def GetGroupMap(self):
        """Return the group map from this source.

        Returns:
          instance of group.GroupMap
        """
        return GroupUpdateGetter().GetUpdates(self._GetClient(),
                                              self.conf['bucket'],
                                              self.conf['group_object'])

    def GetShadowMap(self):
        """Return the shadow map from this source.

        Returns:
          instance of shadow.ShadowMap
        """
        return ShadowUpdateGetter().GetUpdates(self._GetClient(),
                                               self.conf['bucket'],
                                               self.conf['shadow_object'])


class GcsUpdateGetter(object):
    """Base class that gets updates from GCS."""

    def __init__(self):
        self.log = logging.getLogger(__name__)

    def GetUpdates(self, gcs_client, bucket_name, obj):
        """Gets updates from a source.

      Args:
        gcs_client: initialized gcs client
        bucket_name: gcs bucket name
        obj: object with the data
      """
        try:
            bucket = gcs_client.bucket(bucket_name)
            blob = bucket.blob(obj)
            # Saving blob text in an IO object to reuse FilesMapParser as-is:
            contents = io.StringIO(blob.download_as_text())
        except exceptions.NotFound as e:
            self.log.error('error getting GCS blob ({}): {}', obj, e)
            raise error.SourceUnavailable('unable to download blob from GCS')
        data_map = self.GetMap(cache_info=contents)
        return data_map

    def GetParser(self):
        """Return the approriate parser.

      Must be implemented by child class.
      """
        raise NotImplementedError

    def GetMap(self, cache_info):
        """Creates a Map from the cache_info data.

      Args:
        cache_info: file-like object containing the data to parse

      Returns:
        A child of Map containing the cache data.
      """
        return self.GetParser().GetMap(cache_info, self.CreateMap())


class PasswdUpdateGetter(GcsUpdateGetter):
    """Get passwd updates."""

    def GetParser(self):
        """Returns a MapParser to parse FilesPasswd cache."""
        return file_formats.FilesPasswdMapParser()

    def CreateMap(self):
        """Returns a new PasswdMap instance to have PasswdMapEntries added to it."""
        return passwd.PasswdMap()


class GroupUpdateGetter(GcsUpdateGetter):
    """Get group updates."""

    def GetParser(self):
        """Returns a MapParser to parse FilesGroup cache."""
        return file_formats.FilesGroupMapParser()

    def CreateMap(self):
        """Returns a new GroupMap instance to have GroupMapEntries added to it."""
        return group.GroupMap()


class ShadowUpdateGetter(GcsUpdateGetter):
    """Get shadow updates."""

    def GetParser(self):
        """Returns a MapParser to parse FilesShadow cache."""
        return file_formats.FilesShadowMapParser()

    def CreateMap(self):
        """Returns a new ShadowMap instance to have ShadowMapEntries added to it."""
        return shadow.ShadowMap()
