"""An implementation of a mock GCS data source for nsscache."""

import unittest

from nss_cache.maps import group
from nss_cache.maps import shadow
from nss_cache.sources import gcssource
from nss_cache.util import file_formats

class TestGcsSource(unittest.TestCase):

    def setUp(self):
        super(TestGcsSource, self).setUp()
        self.config = {
            'passwd_object': 'PASSWD_OBJ',
            'group_object': 'GROUP_OBJ',
            'bucket': 'TEST_BUCKET',
        }

    def testDefaultConfiguration(self):
        source = gcssource.GcsFilesSource({})
        self.assertEqual(source.conf['bucket'], gcssource.GcsFilesSource.BUCKET)
        self.assertEqual(source.conf['passwd_object'],
                         gcssource.GcsFilesSource.PASSWD_OBJECT)

    def testOverrideDefaultConfiguration(self):
        source = gcssource.GcsFilesSource(self.config)
        self.assertEqual(source.conf['bucket'], 'TEST_BUCKET')
        self.assertEqual(source.conf['passwd_object'], 'PASSWD_OBJ')
        self.assertEqual(source.conf['group_object'], 'GROUP_OBJ')


class TestPasswdUpdateGetter(unittest.TestCase):

    def setUp(self):
        super(TestPasswdUpdateGetter, self).setUp()
        self.updater = gcssource.PasswdUpdateGetter()

    def testGetParser(self):
        self.assertIsInstance(self.updater.GetParser(),
                              file_formats.FilesPasswdMapParser)


class TestShadowUpdateGetter(unittest.TestCase):

    def setUp(self):
        super(TestShadowUpdateGetter, self).setUp()
        self.updater = gcssource.ShadowUpdateGetter()

    def testGetParser(self):
        self.assertIsInstance(self.updater.GetParser(),
                              file_formats.FilesShadowMapParser)

    def testCreateMap(self):
        self.assertIsInstance(self.updater.CreateMap(), shadow.ShadowMap)


class TestGroupUpdateGetter(unittest.TestCase):

    def setUp(self):
        super(TestGroupUpdateGetter, self).setUp()
        self.updater = gcssource.GroupUpdateGetter()

    def testGetParser(self):
        self.assertIsInstance(self.updater.GetParser(),
                              file_formats.FilesGroupMapParser)

    def testCreateMap(self):
        self.assertIsInstance(self.updater.CreateMap(), group.GroupMap)



if __name__ == '__main__':
    unittest.main()
