"""An implementation of a mock GCS data source for nsscache."""

import datetime
import io
import unittest
from unittest import mock

from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import gcssource
from nss_cache.util import file_formats
from nss_cache.util import timestamps


class TestGcsSource(unittest.TestCase):
    def setUp(self):
        super(TestGcsSource, self).setUp()
        self.config = {
            "passwd_object": "PASSWD_OBJ",
            "group_object": "GROUP_OBJ",
            "bucket": "TEST_BUCKET",
        }

    def testDefaultConfiguration(self):
        source = gcssource.GcsFilesSource({})
        self.assertEqual(source.conf["bucket"], gcssource.GcsFilesSource.BUCKET)
        self.assertEqual(
            source.conf["passwd_object"], gcssource.GcsFilesSource.PASSWD_OBJECT
        )

    def testOverrideDefaultConfiguration(self):
        source = gcssource.GcsFilesSource(self.config)
        self.assertEqual(source.conf["bucket"], "TEST_BUCKET")
        self.assertEqual(source.conf["passwd_object"], "PASSWD_OBJ")
        self.assertEqual(source.conf["group_object"], "GROUP_OBJ")


class TestPasswdUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestPasswdUpdateGetter, self).setUp()
        self.updater = gcssource.PasswdUpdateGetter()

    def testGetParser(self):
        self.assertIsInstance(
            self.updater.GetParser(), file_formats.FilesPasswdMapParser
        )

    def testCreateMap(self):
        self.assertIsInstance(self.updater.CreateMap(), passwd.PasswdMap)


class TestShadowUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestShadowUpdateGetter, self).setUp()
        self.updater = gcssource.ShadowUpdateGetter()

    def testGetParser(self):
        self.assertIsInstance(
            self.updater.GetParser(), file_formats.FilesShadowMapParser
        )

    def testCreateMap(self):
        self.assertIsInstance(self.updater.CreateMap(), shadow.ShadowMap)

    def testShadowGetUpdatesWithContent(self):
        mock_client = mock.Mock()
        mock_bucket = mock_client.bucket.return_value
        mock_blob = mock_bucket.get_blob.return_value
        mock_blob.open.return_value = io.StringIO(
            """usera:x:::::::
userb:x:::::::
"""
        )
        mock_blob.updated = datetime.datetime.now()

        result = self.updater.GetUpdates(mock_client, "test-bucket", "passwd", None)

        self.assertEqual(len(result), 2)
        mock_bucket.get_blob.assert_called_with("passwd")
        mock_client.bucket.assert_called_with("test-bucket")

    def testShadowGetUpdatesSinceAfterUpdatedTime(self):
        mock_client = mock.Mock()
        mock_bucket = mock_client.bucket.return_value
        mock_blob = mock_bucket.get_blob.return_value
        now = datetime.datetime.now()
        mock_blob.updated = now

        result = self.updater.GetUpdates(
            mock_client,
            "test-bucket",
            "passwd",
            timestamps.FromDateTimeToTimestamp(now + datetime.timedelta(days=1)),
        )

        self.assertEqual(len(result), 0)
        mock_bucket.get_blob.assert_called_with("passwd")
        mock_client.bucket.assert_called_with("test-bucket")


class TestGroupUpdateGetter(unittest.TestCase):
    def setUp(self):
        super(TestGroupUpdateGetter, self).setUp()
        self.updater = gcssource.GroupUpdateGetter()

    def testGetParser(self):
        self.assertIsInstance(
            self.updater.GetParser(), file_formats.FilesGroupMapParser
        )

    def testCreateMap(self):
        self.assertIsInstance(self.updater.CreateMap(), group.GroupMap)


if __name__ == "__main__":
    unittest.main()
