#!/usr/bin/python
#
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

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import logging
import time
import unittest
import ldap

from nss_cache import error
from nss_cache import maps
from nss_cache.sources import ldapsource

import pmock


class TestLdapSource(pmock.MockTestCase):

  def setUp(self):
    """Initialize a basic config dict."""
    self.config = {'uri': 'TEST_URI',
                   'base': 'TEST_BASE',
                   'filter': 'TEST_FILTER',
                   'bind_dn': 'TEST_BIND_DN',
                   'bind_password': 'TEST_BIND_PASSWORD',
                   'retry_delay': 'TEST_RETRY_DELAY',
                   'retry_max': 'TEST_RETRY_MAX',
                   'timelimit': 'TEST_TIMELIMIT',
                   'tls_require_cert': 0,
                   'tls_cacertdir': 'TEST_TLS_CACERTDIR',
                   'tls_cacertfile': 'TEST_TLS_CACERTFILE',
                  }

    logging.disable(logging.CRITICAL)

  #
  # Functions used to generate shared mocks and stubs.
  #

  def ConnMock(self, success=None):
    """Return a mock for ldap connections."""
    ldap_conn = self.mock()

    if success is True:
      ldap_conn\
                 .expects(pmock.once())\
                 .method('simple_bind_s')
    elif success is False:
      ldap_conn\
                 .expects(pmock.at_least_once())\
                 .method('simple_bind_s')\
                 .will(pmock.raise_exception(ldap.SERVER_DOWN))
    elif success is None:
      # do nothing, this is here for clarity -- we aren't expected to be
      # called with any methods but need to hold values like conn.timelimit
      pass

    return ldap_conn

  def FakeBind(self):
    """Return an unbound method for mocking Bind() in __init__()."""

    def StubBind(self, configuration):
      """Stub method for testing."""
      pass
    return StubBind

  def FakeDefaults(self):
    """Return an unbound method for mocking _SetDefaults in __init__()."""

    def StubDefaults(self, configuration):
      """Stub method for testing."""
      pass
    return StubDefaults

  def MockedSource(self, configuration, mock_defaults=True, mock_bind=True):
    """Return a source object with __init__ mocked."""

    if configuration is None:
      configuration = {'uri': 'ldap://foo'}

    if mock_defaults is True:
      original_set_defaults = ldapsource.LdapSource._SetDefaults
      ldapsource.LdapSource._SetDefaults = self.FakeDefaults()
    if mock_bind is True:
      original_bind = ldapsource.LdapSource.Bind
      ldapsource.LdapSource.Bind = self.FakeBind()

    source = ldapsource.LdapSource(configuration, conn=self.ConnMock())

    if mock_defaults is True:
      ldapsource.LdapSource._SetDefaults = original_set_defaults
    if mock_bind is True:
      ldapsource.LdapSource.Bind = original_bind

    return source

  #
  # Our tests are defined below here.
  #

  def testDefaults(self):
    """Test that we set the expected defaults for LDAP connections."""
    # get a mocked source, but don't mock _SetDefaults!
    source = self.MockedSource(configuration=None, mock_defaults=False)

    self.assertEquals(source.conf['bind_dn'],
                      ldapsource.LdapSource.BIND_DN)
    self.assertEquals(source.conf['bind_password'],
                      ldapsource.LdapSource.BIND_PASSWORD)
    self.assertEquals(source.conf['retry_max'],
                      ldapsource.LdapSource.RETRY_MAX)
    self.assertEquals(source.conf['retry_delay'],
                      ldapsource.LdapSource.RETRY_DELAY)
    self.assertEquals(source.conf['scope'], ldapsource.LdapSource.SCOPE)
    self.assertEquals(source.conf['timelimit'],
                      ldapsource.LdapSource.TIMELIMIT)
    self.assertEquals(source.conf['tls_require_cert'],
                      ldap.OPT_X_TLS_DEMAND)
    self.assertEquals(source.conf['tls_cacertdir'],
                      ldapsource.LdapSource.TLS_CACERTDIR)
    self.assertEquals(source.conf['tls_cacertfile'],
                      ldapsource.LdapSource.TLS_CACERTFILE)

  def testOverrideDefaults(self):
    """Test that we override the defaults for LDAP connections."""
    configuration = self.config
    configuration['scope'] = ldap.SCOPE_BASE
    source = self.MockedSource(configuration=configuration,
                               mock_defaults=False)

    # Wow.  This is a freakin weird bug.  A mock that goes unused
    # raises a type error unless we call dir() on a list's iterator.
    #
    # Comment the below out if you don't believe me!
    #
    # The iterator returned is a python listiterator generated from
    # an empty list stored in pmock.Mock()._invokables, called via
    # Mock.verify() by the pmock MockTestCase framework.
    #
    # This is not reproducible via a simple MockTestCase setup,
    # so frankly, I'm stumped for now.  I'm leaving this in so we can
    # take a further look and confirm a possible python bug, instead
    # of working around it another way.
    dir(source.conn._get_match_order_invokables().__iter__())

    self.assertEquals(source.conf['scope'], ldap.SCOPE_BASE)
    self.assertEquals(source.conf['bind_dn'], 'TEST_BIND_DN')
    self.assertEquals(source.conf['bind_password'], 'TEST_BIND_PASSWORD')
    self.assertEquals(source.conf['retry_delay'], 'TEST_RETRY_DELAY')
    self.assertEquals(source.conf['retry_max'], 'TEST_RETRY_MAX')
    self.assertEquals(source.conf['timelimit'], 'TEST_TIMELIMIT')
    self.assertEquals(source.conf['tls_require_cert'], 0)
    self.assertEquals(source.conf['tls_cacertdir'], 'TEST_TLS_CACERTDIR')
    self.assertEquals(source.conf['tls_cacertfile'],
                      'TEST_TLS_CACERTFILE')

  def testTrapAndRetryServerDown(self):
    """We trap ldap.SERVER_DOWN and retry as per configuration."""
    self.config['retry_delay'] = 5
    self.config['retry_max'] = 3
    self.config['bind_dn'] = ''
    self.config['bind_password'] = ''

    sleep_mock = self.mock()
    sleep_mock\
                .expects(pmock.once())\
                .sleep(pmock.eq(5))
    sleep_mock\
                .expects(pmock.once())\
                .sleep(pmock.eq(5))

    original_sleep = time.sleep
    time.sleep = sleep_mock.sleep

    self.assertRaises(error.SourceUnavailable, ldapsource.LdapSource,
                      conf=self.config, conn=self.ConnMock(success=False))

    time.sleep = original_sleep

  #
  # TODO(jaq):  Convert all unit tests below here to generate any shared mocks.
  #

  def testIteration(self):
    """Test that iteration over the LDAPDataSource behaves correctly."""
    ldap_conn = self.mock()

    # Expect a simple bind
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq(''),
                              cred=pmock.eq(''))

    # Expect a search and returning the msg id 37.
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq(self.config['base']),
                       filterstr=pmock.eq('TEST_FILTER'),
                       scope=pmock.eq('TEST_SCOPE'),
                       attrlist=pmock.eq('TEST_ATTRLIST'))\
               .after('simple_bind_s')\
               .will(pmock.return_value(37))

    # Expect result on the same msg id, and return a dataset
    dataset = [('dn', 'payload')]
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0), timeout=pmock.eq(-1))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY, dataset)))\
               .id('res #1')

    # Expect another call to result, and return that we're at the end of the
    # list.
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq(-1))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    dummy_config = {'uri': 'foo'}
    source = ldapsource.LdapSource(dummy_config, ldap_conn)
    source.Search(search_base=self.config['base'],
                  search_filter='TEST_FILTER',
                  search_scope='TEST_SCOPE',
                  attrs='TEST_ATTRLIST')

    count = 0
    for r in source:
      self.assertEqual(dataset[0][1], r)
      count += 1

    self.assertEqual(1, count)

  def testGetPasswdMap(self):
    """Test that GetPasswdMap returns a sensible passwd map."""
    test_posix_account = ('cn=test,ou=People,dc=example,dc=com',
                          {'uidNumber': [1000],
                           'gidNumber': [1000],
                           'uid': ['Testguy McTest'],
                           'cn': ['test'],
                           'homeDirectory': ['/home/test'],
                           'loginShell': ['/bin/sh'],
                           'userPassword': ['p4ssw0rd'],
                           'modifyTimestamp': ['20070227012807Z']})

    ldap_conn = self.mock()
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('TEST_FILTER'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['uid', 'uidNumber', 'gidNumber',
                                          'gecos', 'cn', 'homeDirectory',
                                          'loginShell', 'modifyTimestamp']))\
               .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_posix_account])))\
               .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetPasswdMap()

    self.assertEqual(1, len(data))

    first = data.PopItem()

    self.assertEqual('Testguy McTest', first.name)

  def testGetGroupMap(self):
    """Test that GetGroupmap returns a sensible map."""
    test_posix_group = ('cn=test,ou=Group,dc=example,dc=com',
                        {'gidNumber': [1000],
                         'cn': ['testgroup'],
                         'memberUid': ['testguy', 'fooguy', 'barguy'],
                         'modifyTimestamp': ['20070227012807Z']})

    ldap_conn = self.mock()
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('TEST_FILTER'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['cn', 'gidNumber', 'memberUid',
                                          'modifyTimestamp']))\
               .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_posix_group])))\
               .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetGroupMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('testgroup', ent.name)

  def testGetShadowMap(self):
    """Test that GetShadowMap returns a sensible map."""
    test_shadow = ('cn=test,ou=People,dc=example,dc=com',
                   {'uid': ['test'],
                    'shadowLastChange': ['11296'],
                    'shadowMax': ['99999'],
                    'shadowWarning': ['7'],
                    'shadowInactive': ['-1'],
                    'shadowExpire': ['-1'],
                    'shadowFlag': ['134537556'],
                    'modifyTimestamp': ['20070227012807Z'],
                    'userPassword': ['{CRYPT}p4ssw0rd']})

    ldap_conn = self.mock()
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('TEST_FILTER'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['uid', 'shadowLastChange',
                                          'shadowMin', 'shadowMax',
                                          'shadowWarning', 'shadowInactive',
                                          'shadowExpire', 'shadowFlag',
                                          'userPassword', 'modifyTimestamp']))\
               .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_shadow])))\
               .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetShadowMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('test', ent.name)
    self.assertEqual('p4ssw0rd', ent.passwd)

  def testGetNetgroupMap(self):
    """Test that GetNetgroupMap returns a sensible map."""
    test_posix_netgroup = ('cn=test,ou=netgroup,dc=example,dc=com',
                           {'cn': ['test'],
                            'memberNisNetgroup': ['admins'],
                            'nisNetgroupTriple': ['(-,hax0r,)'],
                            'modifyTimestamp': ['20070227012807Z'],
                           })

    ldap_conn = self.mock()
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('TEST_FILTER'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['cn', 'memberNisNetgroup',
                                          'nisNetgroupTriple',
                                          'modifyTimestamp']))\
                                          .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_posix_netgroup])))\
                                         .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetNetgroupMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('test', ent.name)
    self.assertEqual('(-,hax0r,) admins', ent.entries)

  def testGetNetgroupMapWithDupes(self):
    """Test that GetNetgroupMap returns a sensible map."""
    test_posix_netgroup = ('cn=test,ou=netgroup,dc=example,dc=com',
                           {'cn': ['test'],
                            'memberNisNetgroup': ['(-,hax0r,)'],
                            'nisNetgroupTriple': ['(-,hax0r,)'],
                            'modifyTimestamp': ['20070227012807Z'],
                           })

    ldap_conn = self.mock()
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('TEST_FILTER'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['cn', 'memberNisNetgroup',
                                          'nisNetgroupTriple',
                                          'modifyTimestamp']))\
                                          .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_posix_netgroup])))\
                                         .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetNetgroupMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('test', ent.name)
    self.assertEqual('(-,hax0r,)', ent.entries)

  def testGetAutomountMap(self):
    """Test that GetAutomountMap returns a sensible map."""
    test_automount = ('cn=user,ou=auto.home,ou=automounts,dc=example,dc=com',
                      {'cn': ['user'],
                       'automountInformation': ['-tcp,rw home:/home/user'],
                       'modifyTimestamp': ['20070227012807Z'],
                      })

    ldap_conn = self.mock()
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('(objectclass=automount)'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['cn', 'automountInformation',
                                          'modifyTimestamp']))\
                                          .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_automount])))\
                                         .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetAutomountMap(location='TEST_BASE')

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('user', ent.key)
    self.assertEqual('-tcp,rw', ent.options)
    self.assertEqual('home:/home/user', ent.location)

  def testGetAutomountMasterMap(self):
    """Test that GetAutomountMasterMap returns a sensible map."""
    test_master_ou = ('ou=auto.master,ou=automounts,dc=example,dc=com',
                      {'ou': ['auto.master']})
    test_automount = ('cn=/home,ou=auto.master,ou=automounts,dc=example,dc=com',
                      {'cn': ['/home'],
                       'automountInformation': ['ldap:ldap:ou=auto.home,'
                                                'ou=automounts,dc=example,'
                                                'dc=com'],
                       'modifyTimestamp': ['20070227012807Z']})

    ldap_conn = self.mock()
    # first the search for the dn of ou=auto.master
    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq('(&(objectclass=automountMap)'
                                          '(ou=auto.master))'),
                       scope=pmock.eq(ldap.SCOPE_SUBTREE),
                       attrlist=pmock.eq(['dn']))\
                       .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_master_ou])))\
                                         .id('res #1')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #1')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))
    # next the search for the entries under ou=auto.master
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('ou=auto.master,ou=automounts,dc=example'
                                     ',dc=com'),
                       filterstr=pmock.eq('(objectclass=automount)'),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['cn', 'automountInformation',
                                          'modifyTimestamp']))\
                       .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('search')\
               .will(pmock.return_value((ldap.RES_SEARCH_ENTRY,
                                         [test_automount])))\
                                         .id('res #2')
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .after('res #2')\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))
    
    source = ldapsource.LdapSource(self.config, conn=ldap_conn)

    data = source.GetAutomountMasterMap()
    self.assertEqual(1, len(data))

    ent = data.PopItem()
    self.assertEqual('/home', ent.key)
    self.assertEqual('ou=auto.home,ou=automounts,dc=example,dc=com',
                     ent.location)
    self.assertEqual(None, ent.options)

  def testVerify(self):
    ldap_conn = self.mock()

    ldap_conn\
               .expects(pmock.once())\
               .simple_bind_s(who=pmock.eq('TEST_BIND_DN'),
                              cred=pmock.eq('TEST_BIND_PASSWORD'))
    filtstr = '(&TEST_FILTER(modifyTimestamp>=19700101000001Z))'
    ldap_conn\
               .expects(pmock.once())\
               .search(base=pmock.eq('TEST_BASE'),
                       filterstr=pmock.eq(filtstr),
                       scope=pmock.eq(ldap.SCOPE_ONELEVEL),
                       attrlist=pmock.eq(['uid', 'uidNumber', 'gidNumber',
                                          'gecos', 'cn', 'homeDirectory',
                                          'loginShell', 'modifyTimestamp']))\
               .will(pmock.return_value(37))
    ldap_conn\
               .expects(pmock.once())\
               .result(pmock.eq(37), all=pmock.eq(0),
                       timeout=pmock.eq('TEST_TIMELIMIT'))\
               .will(pmock.return_value((ldap.RES_SEARCH_RESULT, None)))

    source = ldapsource.LdapSource(self.config, conn=ldap_conn)
    self.assertEquals(0, source.Verify(time.gmtime(0)))


class TestUpdateGetter(unittest.TestCase):

  def setUp(self):
    """Create a dummy source object."""

    class DummySource(list):
      """Dummy Source class for this test.

      Inherits from list as Sources are iterables.
      """

      def Search(self, search_base, search_filter, search_scope, attrs):
        pass

    self.source = DummySource()

  def testPasswdEmptySourceGetUpdates(self):
    """Test that getUpdates on the PasswdUpdateGetter works."""
    getter = ldapsource.PasswdUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(maps.PasswdMap, type(data))

  def testGroupEmptySourceGetUpdates(self):
    """Test that getUpdates on the GroupUpdateGetter works."""
    getter = ldapsource.GroupUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(maps.GroupMap, type(data))

  def testShadowEmptySourceGetUpdates(self):
    """Test that getUpdates on the ShadowUpdateGetter works."""
    getter = ldapsource.ShadowUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(maps.ShadowMap, type(data))

  def testAutomountEmptySourceGetsUpdates(self):
    """Test that getUpdates on the AutomountUpdateGetter works."""
    getter = ldapsource.AutomountUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(maps.AutomountMap, type(data))

  def testBadScopeException(self):
    """Test that a bad scope raises a config.ConfigurationError."""
    # One of the getters is sufficient, they all inherit the
    # exception-raising code.
    getter = ldapsource.PasswdUpdateGetter()

    self.assertRaises(error.ConfigurationError, getter.GetUpdates,
                      self.source, 'TEST_BASE', 'TEST_FILTER',
                      'BAD_SCOPE', None)

if __name__ == '__main__':
  unittest.main()
