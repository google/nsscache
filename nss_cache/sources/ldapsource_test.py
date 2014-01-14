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

import time
import unittest

import ldap
import mox

from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.sources import ldapsource


class TestLdapSource(mox.MoxTestBase):

  def setUp(self):
    """Initialize a basic config dict."""
    super(TestLdapSource, self).setUp()
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

  def testDefaultConfiguration(self):
    config = {'uri': 'ldap://foo'}
    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(cred='', who='')
    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(uri='ldap://foo',
                                        retry_max=3,
                                        retry_delay=5).AndReturn(mock_rlo)
    self.mox.ReplayAll()
    source = ldapsource.LdapSource(config)

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

  def testOverrideDefaultConfiguration(self):
    config = dict(self.config)
    config['scope'] = ldap.SCOPE_BASE
    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(cred='TEST_BIND_PASSWORD', who='TEST_BIND_DN')
    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY',
        uri='TEST_URI').AndReturn(mock_rlo)
    self.mox.ReplayAll()
    source = ldapsource.LdapSource(config)

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

  def testTrapServerDownAndRetry(self):
    config = dict(self.config)
    config['bind_dn'] = ''
    config['bind_password'] = ''
    config['retry_delay'] = 5
    config['retry_max'] = 3

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='',
        who='').MultipleTimes().AndRaise(ldap.SERVER_DOWN)

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max=3,
        retry_delay=5).MultipleTimes().AndReturn(mock_rlo)

    self.mox.StubOutWithMock(time, 'sleep')
    time.sleep(5)
    time.sleep(5)

    self.mox.ReplayAll()

    self.assertRaises(error.SourceUnavailable,
                      ldapsource.LdapSource,
                      config)

  def testIterationOverLdapDataSource(self):
    config = dict(self.config)

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base=config['base'],
                    filterstr='TEST_FILTER',
                    scope='TEST_SCOPE',
                    attrlist='TEST_ATTRLIST').AndReturn('TEST_RES')

    dataset = [('dn', 'payload')]
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, dataset))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    source.Search(search_base=config['base'],
                  search_filter='TEST_FILTER',
                  search_scope='TEST_SCOPE',
                  attrs='TEST_ATTRLIST')

    count = 0
    for r in source:
      self.assertEqual(dataset[0][1], r)
      count += 1

    self.assertEqual(1, count)

  def testGetPasswdMap(self):
    test_posix_account = ('cn=test,ou=People,dc=example,dc=com',
                          {'uidNumber': [1000],
                           'gidNumber': [1000],
                           'uid': ['Testguy McTest'],
                           'cn': ['test'],
                           'homeDirectory': ['/home/test'],
                           'loginShell': ['/bin/sh'],
                           'userPassword': ['p4ssw0rd'],
                           'modifyTimestamp': ['20070227012807Z']})
    config = dict(self.config)
    attrlist = ['uid', 'uidNumber', 'gidNumber',
                'gecos', 'cn', 'homeDirectory',
                'fullName',
                'loginShell', 'modifyTimestamp']

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr='TEST_FILTER',
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_posix_account]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetPasswdMap()

    self.assertEqual(1, len(data))

    first = data.PopItem()

    self.assertEqual('Testguy McTest', first.name)

  def testGetGroupMap(self):
    test_posix_group = ('cn=test,ou=Group,dc=example,dc=com',
                        {'gidNumber': [1000],
                         'cn': ['testgroup'],
                         'memberUid': ['testguy', 'fooguy', 'barguy'],
                         'modifyTimestamp': ['20070227012807Z']})

    config = dict(self.config)
    attrlist = ['cn', 'gidNumber', 'memberUid',
                'modifyTimestamp']

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr='TEST_FILTER',
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_posix_group]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetGroupMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('testgroup', ent.name)

  def testGetShadowMap(self):
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
    config = dict(self.config)
    attrlist = ['uid', 'shadowLastChange',
                'shadowMin', 'shadowMax',
                'shadowWarning', 'shadowInactive',
                'shadowExpire', 'shadowFlag',
                'userPassword', 'modifyTimestamp']

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr='TEST_FILTER',
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_shadow]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetShadowMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('test', ent.name)
    self.assertEqual('p4ssw0rd', ent.passwd)

  def testGetNetgroupMap(self):
    test_posix_netgroup = ('cn=test,ou=netgroup,dc=example,dc=com',
                           {'cn': ['test'],
                            'memberNisNetgroup': ['admins'],
                            'nisNetgroupTriple': ['(-,hax0r,)'],
                            'modifyTimestamp': ['20070227012807Z'],
                           })
    config = dict(self.config)
    attrlist = ['cn', 'memberNisNetgroup',
                'nisNetgroupTriple',
                'modifyTimestamp']

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr='TEST_FILTER',
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_posix_netgroup]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetNetgroupMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('test', ent.name)
    self.assertEqual('(-,hax0r,) admins', ent.entries)

  def testGetNetgroupMapWithDupes(self):
    test_posix_netgroup = ('cn=test,ou=netgroup,dc=example,dc=com',
                           {'cn': ['test'],
                            'memberNisNetgroup': ['(-,hax0r,)'],
                            'nisNetgroupTriple': ['(-,hax0r,)'],
                            'modifyTimestamp': ['20070227012807Z'],
                           })
    config = dict(self.config)
    attrlist = ['cn', 'memberNisNetgroup',
                'nisNetgroupTriple',
                'modifyTimestamp']

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr='TEST_FILTER',
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_posix_netgroup]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetNetgroupMap()

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('test', ent.name)
    self.assertEqual('(-,hax0r,)', ent.entries)

  def testGetAutomountMap(self):
    test_automount = ('cn=user,ou=auto.home,ou=automounts,dc=example,dc=com',
                      {'cn': ['user'],
                       'automountInformation': ['-tcp,rw home:/home/user'],
                       'modifyTimestamp': ['20070227012807Z'],
                      })
    config = dict(self.config)
    attrlist = ['cn', 'automountInformation',
                'modifyTimestamp']
    filterstr = '(objectclass=automount)'

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr=filterstr,
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_automount]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetAutomountMap(location='TEST_BASE')

    self.assertEqual(1, len(data))

    ent = data.PopItem()

    self.assertEqual('user', ent.key)
    self.assertEqual('-tcp,rw', ent.options)
    self.assertEqual('home:/home/user', ent.location)

  def testGetAutomountMasterMap(self):
    test_master_ou = ('ou=auto.master,ou=automounts,dc=example,dc=com',
                      {'ou': ['auto.master']})
    test_automount = ('cn=/home,ou=auto.master,ou=automounts,dc=example,dc=com',
                      {'cn': ['/home'],
                       'automountInformation': ['ldap:ldap:ou=auto.home,'
                                                'ou=automounts,dc=example,'
                                                'dc=com'],
                       'modifyTimestamp': ['20070227012807Z']})
    config = dict(self.config)
    # first search for the dn of ou=auto.master
    attrlist = ['dn']
    filterstr = '(&(objectclass=automountMap)(ou=auto.master))'
    scope = ldap.SCOPE_SUBTREE

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr=filterstr,
                    scope=scope,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_master_ou]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))
    # then search for the entries under ou=auto.master
    attrlist = ['cn', 'automountInformation',
                'modifyTimestamp']
    filterstr = '(objectclass=automount)'
    scope = ldap.SCOPE_ONELEVEL
    base = 'ou=auto.master,ou=automounts,dc=example,dc=com'

    mock_rlo.search(base=base,
                    filterstr=filterstr,
                    scope=scope,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_ENTRY, [test_automount]))
    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))

    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()

    source = ldapsource.LdapSource(config)
    data = source.GetAutomountMasterMap()
    self.assertEqual(1, len(data))

    ent = data.PopItem()
    self.assertEqual('/home', ent.key)
    self.assertEqual('ou=auto.home,ou=automounts,dc=example,dc=com',
                     ent.location)
    self.assertEqual(None, ent.options)

  def testVerify(self):
    attrlist = ['uid', 'uidNumber', 'gidNumber',
                'gecos', 'cn', 'homeDirectory',
                'fullName',
                'loginShell', 'modifyTimestamp']
    filterstr = '(&TEST_FILTER(modifyTimestamp>=19700101000001Z))'

    mock_rlo = self.mox.CreateMock(ldap.ldapobject.ReconnectLDAPObject)
    mock_rlo.simple_bind_s(
        cred='TEST_BIND_PASSWORD',
        who='TEST_BIND_DN')
    mock_rlo.search(base='TEST_BASE',
                    filterstr=filterstr,
                    scope=ldap.SCOPE_ONELEVEL,
                    attrlist=mox.SameElementsAs(attrlist)).AndReturn(
                        'TEST_RES')

    mock_rlo.result('TEST_RES',
                    all=0,
                    timeout='TEST_TIMELIMIT').AndReturn(
                        (ldap.RES_SEARCH_RESULT, None))
    self.mox.StubOutWithMock(ldap, 'ldapobject')
    ldap.ldapobject.ReconnectLDAPObject(
        uri='TEST_URI',
        retry_max='TEST_RETRY_MAX',
        retry_delay='TEST_RETRY_DELAY').AndReturn(mock_rlo)

    self.mox.ReplayAll()
    source = ldapsource.LdapSource(self.config)
    self.assertEquals(0, source.Verify(0))


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
    expected_ldap_ts = '20091201041705Z'
    self.assertEquals(expected_ldap_ts,
                      ldapsource.UpdateGetter().FromTimestampToLdap(ts))

  def testFromLdapToTimestamp(self):
    expected_ts = 1259641025
    ldap_ts = '20091201041705Z'
    self.assertEquals(expected_ts,
                      ldapsource.UpdateGetter().FromLdapToTimestamp(ldap_ts))

  def testPasswdEmptySourceGetUpdates(self):
    """Test that getUpdates on the PasswdUpdateGetter works."""
    getter = ldapsource.PasswdUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(passwd.PasswdMap, type(data))

  def testGroupEmptySourceGetUpdates(self):
    """Test that getUpdates on the GroupUpdateGetter works."""
    getter = ldapsource.GroupUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(group.GroupMap, type(data))

  def testShadowEmptySourceGetUpdates(self):
    """Test that getUpdates on the ShadowUpdateGetter works."""
    getter = ldapsource.ShadowUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(shadow.ShadowMap, type(data))

  def testAutomountEmptySourceGetsUpdates(self):
    """Test that getUpdates on the AutomountUpdateGetter works."""
    getter = ldapsource.AutomountUpdateGetter()

    data = getter.GetUpdates(self.source, 'TEST_BASE',
                             'TEST_FILTER', 'base', None)

    self.failUnlessEqual(automount.AutomountMap, type(data))

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
