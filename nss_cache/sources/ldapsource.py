#!/usr/bin/python2.4
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

"""An implementation of an ldap data source for nsscache."""

__author__ = ('jaq@google.com (Jamie Wilkinson)',
              'vasilios@google.com (Vasilios Hoffman)')

import calendar
import logging
import time
import ldap

from nss_cache import error
from nss_cache import maps
from nss_cache.sources import base


class LdapSource(base.Source):
  """Source for data in LDAP.

  After initialisation, one can search the data source for 'objects'
  under a particular part of the LDAP tree, with some filter, and have it
  return only some set of attributes.

  'objects' in this sense means some structured blob of data, not a Python
  object.
  """
  # ldap defaults
  BIND_DN = ''
  BIND_PASSWORD = ''
  RETRY_DELAY = 5
  RETRY_MAX = 3
  SCOPE = 'one'
  TIMELIMIT = -1
  TLS_REQUIRE_CERT = 'demand'  # one of never, hard, demand, allow, try
  TLS_CACERTDIR = '/usr/share/ssl'
  # the ldap client library requires TLS_CACERTDIR to be an absolute path
  TLS_CACERTFILE = TLS_CACERTDIR + '/cert.pem'

  # for registration
  name = 'ldap'

  def __init__(self, config, conn=None):
    """Initialise the LDAP Data Source.

    Args:
      config: config.Config instance
      conn: An instance of ldap.LDAPObject that'll be used as the connection.
    """
    super(LdapSource, self).__init__(config)

    self._SetDefaults(config)

    if conn is None:
      # ReconnectLDAPObject should handle interrupted ldap transactions.
      # also, ugh
      rlo = ldap.ldapobject.ReconnectLDAPObject
      self.conn = rlo(uri=config['uri'],
                      retry_max=config['retry_max'],
                      retry_delay=config['retry_delay'])
    else:
      self.conn = conn

    # TODO(v): We should bind on-demand instead.
    # (although binding here makes it easier to simulate a dropped network)
    self.Bind(config)

  def _SetDefaults(self, configuration):
    """Set defaults if necessary."""
    if not 'bind_dn' in configuration:
      configuration['bind_dn'] = self.BIND_DN
    if not 'bind_password' in configuration:
      configuration['bind_password'] = self.BIND_PASSWORD
    if not 'retry_delay' in configuration:
      configuration['retry_delay'] = self.RETRY_DELAY
    if not 'retry_max' in configuration:
      configuration['retry_max'] = self.RETRY_MAX
    if not 'scope' in configuration:
      configuration['scope'] = self.SCOPE
    if not 'timelimit' in configuration:
      configuration['timelimit'] = self.TIMELIMIT
    # TODO(jaq): XXX EVIL.  ldap client libraries change behaviour if we use
    # polling, and it's nasty.  So don't let the user poll.
    if configuration['timelimit'] == 0:
      configuration['timelimit'] = -1
    if not 'tls_require_cert' in configuration:
      configuration['tls_require_cert'] = self.TLS_REQUIRE_CERT
    if not 'tls_cacertdir' in configuration:
      configuration['tls_cacertdir'] = self.TLS_CACERTDIR
    if not 'tls_cacertfile' in configuration:
      configuration['tls_cacertfile'] = self.TLS_CACERTFILE

    # Translate tls_require into appropriate constant, if necessary.
    if configuration['tls_require_cert'] == 'never':
      configuration['tls_require_cert'] = ldap.OPT_X_TLS_NEVER
    elif configuration['tls_require_cert'] == 'hard':
      configuration['tls_require_cert'] = ldap.OPT_X_TLS_HARD
    elif configuration['tls_require_cert'] == 'demand':
      configuration['tls_require_cert'] = ldap.OPT_X_TLS_DEMAND
    elif configuration['tls_require_cert'] == 'allow':
      configuration['tls_require_cert'] = ldap.OPT_X_TLS_ALLOW
    elif configuration['tls_require_cert'] == 'try':
      configuration['tls_require_cert'] = ldap.OPT_X_TLS_TRY

    # Setting global ldap defaults.
    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT,
                    configuration['tls_require_cert'])
    ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, configuration['tls_cacertdir'])
    ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, configuration['tls_cacertfile'])
    ldap.version = ldap.VERSION3  # this is hard-coded, we only support V3

  def Bind(self, configuration):
    """Bind to LDAP, retrying if necessary."""
    # If the server is unavailable, we are going to find out now, as this
    # actually initiates the network connection.
    retry_count = 0
    while retry_count < configuration['retry_max']:
      self.log.debug('opening ldap connection and binding to %s',
                     configuration['uri'])
      try:
        self.conn.simple_bind_s(who=configuration['bind_dn'],
                                cred=configuration['bind_password'])
        break
      except ldap.SERVER_DOWN, e:
        retry_count += 1
        self.log.warning('Failed LDAP connection: attempt #%s.', retry_count)
        if retry_count == configuration['retry_max']:
          self.log.debug('max retries hit')
          raise error.SourceUnavailable(e)
        self.log.debug('sleeping %d seconds', configuration['retry_delay'])
        time.sleep(configuration['retry_delay'])

  def Search(self, search_base, search_filter, search_scope, attrs):
    """Search the data source.

    The search is asynchronous; data should be retrieved by iterating over
    the source object itself (see __iter__() below).

    Args:
     search_base: the base of the tree being searched
     search_filter: a filter on the objects to be returned
     search_scope: the scope of the search from ldap.SCOPE_*
     attrs: a list of attributes to be returned

    Returns:
     nothing.
    """
    self.log.debug('searching for base=%r, filter=%r, scope=%r, attrs=%r',
                   search_base, search_filter, search_scope, attrs)
    self.message_id = self.conn.search(base=search_base,
                                       filterstr=search_filter,
                                       scope=search_scope, attrlist=attrs)

  def __iter__(self):
    """Iterate over the data from the last search.

    Probably not threadsafe.

    Yields:
      Search results from the prior call to self.Search()
    """
    while True:
      result_type, data = self.conn.result(self.message_id, all=0,
                                           timeout=self.config['timelimit'])

      if result_type == ldap.RES_SEARCH_RESULT:
        self.log.debug('Returning due to RES_SEARCH_RESULT')
        return

      if result_type != ldap.RES_SEARCH_ENTRY:
        self.log.info('Unknown result type %r, ignoring.', result_type)

      if not data:
        self.log.debug('Returning due to len(data) == 0')
        return

      for record in data:
        # Ignore the DN, which is the first element of each record tuple,
        # and yield only the payload
        yield record[1]

  def GetPasswdMap(self, since=None):
    """Return the passwd map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of maps.PasswdMap
    """
    return PasswdUpdateGetter().GetUpdates(source=self,
                                           search_base=self.config['base'],
                                           search_filter=self.config['filter'],
                                           search_scope=self.config['scope'],
                                           since=since)

  def GetGroupMap(self, since=None):
    """Return the group map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of maps.GroupMap
    """
    return GroupUpdateGetter().GetUpdates(source=self,
                                          search_base=self.config['base'],
                                          search_filter=self.config['filter'],
                                          search_scope=self.config['scope'],
                                          since=since)

  def GetShadowMap(self, since=None):
    """Return the shadow map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of ShadowMap
    """
    return ShadowUpdateGetter().GetUpdates(source=self,
                                           search_base=self.config['base'],
                                           search_filter=self.config['filter'],
                                           search_scope=self.config['scope'],
                                           since=since)

  def GetNetgroupMap(self, since=None):
    """Return the netgroup map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of NetgroupMap
    """
    return NetgroupUpdateGetter().GetUpdates(source=self,
                                             search_base=self.config['base'],
                                             search_filter=self.config['filter'],
                                             search_scope=self.config['scope'],
                                             since=since)

  def GetAutomount(self):
    pass

  def Verify(self, since=None):
    """Verify that this source is contactable and can be queried for data."""
    if since is None:
      # one minute in the future
      since = time.time() + 60
    results = self.GetPasswdMap(since=since)
    return len(results)


class UpdateGetter(object):
  """Base class that gets updates from LDAP."""

  def FromLdapToTimestamp(self, ldap_ts_string):
    """Transforms a LDAP timestamp into the nss_cache internal timestamp.

    Args:
      ldap_ts_string: An LDAP timestamp string in the format %Y%m%d%H%M%SZ

    Returns:
      number of seconds since epoch.
    """
    t = time.strptime(ldap_ts_string, '%Y%m%d%H%M%SZ')
    return calendar.timegm(t)

  def FromTimestampToLdap(self, ts):
    """Transforms nss_cache internal timestamp into a LDAP timestamp.

    Args:
      ts: number of seconds since epoch
    Returns:
      LDAP format timestamp string.
    """
    ts = time.gmtime(ts)
    return time.strftime('%Y%m%d%H%M%SZ', ts)

  def GetUpdates(self, source, search_base, search_filter,
                 search_scope, since):
    """Get updates from a source.

    Args:
      source: a data source
      search_base: the LDAP base of the tree
      search_filter: the LDAP object filter
      search_scope:  the LDAP scope filter, one of 'base', 'one', or 'sub'.
      since: a timestamp to get updates since (None for 'get everything')

    Returns:
      a tuple containing the map of updates and a maximum timestamp

    Raises:
      error.ConfigurationError: scope is invalid
      ValueError: an object in the source map is malformed
    """
    self.attrs.append('modifyTimestamp')

    if since is not None:
      ts = self.FromTimestampToLdap(since)
      # since openldap disallows modifyTimestamp "greater than" we have to
      # increment by one second.
      ts = int(ts.rstrip('Z')) + 1
      ts = '%sZ' % ts      
      search_filter = ('(&%s(modifyTimestamp>=%s))' % (search_filter, ts))

    if search_scope == 'base':
      search_scope = ldap.SCOPE_BASE
    elif search_scope == 'one':
      search_scope = ldap.SCOPE_ONELEVEL
    elif search_scope == 'sub':
      search_scope = ldap.SCOPE_SUBTREE
    else:
      raise error.ConfigurationError('Invalid scope: %s' % search_scope)

    source.Search(search_base=search_base, search_filter=search_filter,
                  search_scope=search_scope, attrs=self.attrs)

    # Don't initialize with since, because we really want to get the
    # latest timestamp read, and if somehow a larger 'since' slips through
    # the checks in main(), we'd better catch it here.
    max_ts = None

    data_map = self.CreateMap()

    for obj in source:
      for field in self.essential_fields:
        if field not in obj:
          logging.warn('invalid object passed: %r not in %r', field, obj)
          raise ValueError('Invalid object passed: %r', obj)

      obj_ts = self.FromLdapToTimestamp(obj['modifyTimestamp'][0])

      if max_ts is None or obj_ts > max_ts:
        max_ts = obj_ts

      try:
        if not data_map.Add(self.Transform(obj)):
          logging.info('could not add obj: %r', obj)
      except AttributeError, e:
        logging.warning('error %r, discarding malformed obj: %r',
                        str(e), obj)

    data_map.SetModifyTimestamp(max_ts)

    return data_map


class PasswdUpdateGetter(UpdateGetter):
  """Get passwd updates."""

  def __init__(self):
    super(PasswdUpdateGetter, self).__init__()
    self.attrs = ['uid', 'uidNumber', 'gidNumber', 'gecos', 'cn',
                  'homeDirectory', 'loginShell']
    self.essential_fields = ['uid', 'uidNumber', 'gidNumber', 'homeDirectory']

  def CreateMap(self):
    """Returns a new PasswdMap instance to have PasswdMapEntries added to it."""
    return maps.PasswdMap()

  def Transform(self, obj):
    """Transforms a LDAP posixAccount data structure into a PasswdMapEntry."""

    pw = maps.PasswdMapEntry()

    if 'gecos' in obj:
      pw.gecos = obj['gecos'][0]
    elif 'cn' in obj:
      pw.gecos = obj['cn'][0]
    else:
      raise ValueError('Neither gecos nor cn found')

    pw.name = obj['uid'][0]
    if 'loginShell' in obj:
      pw.shell = obj['loginShell'][0]
    else:
      pw.shell = ''

    pw.uid = int(obj['uidNumber'][0])
    pw.gid = int(obj['gidNumber'][0])
    pw.dir = obj['homeDirectory'][0]

    # hack
    pw.passwd = 'x'

    return pw


class GroupUpdateGetter(UpdateGetter):
  """Get group updates."""

  def __init__(self):
    super(GroupUpdateGetter, self).__init__()
    self.attrs = ['cn', 'gidNumber', 'memberUid']
    self.essential_fields = ['cn']

  def CreateMap(self):
    """Return a GroupMap instance."""
    return maps.GroupMap()

  def Transform(self, obj):
    """Transforms a LDAP posixGroup object into a group(5) entry."""

    gr = maps.GroupMapEntry()

    gr.name = obj['cn'][0]
    # group passwords are deferred to gshadow
    gr.passwd = '*'
    members = []
    if 'memberUid' in obj:
      members.extend(obj['memberUid'])
    members.sort()

    gr.gid = int(obj['gidNumber'][0])
    gr.members = members

    return gr


class ShadowUpdateGetter(UpdateGetter):
  """Get Shadow updates from the LDAP Source."""

  def __init__(self):
    super(ShadowUpdateGetter, self).__init__()
    self.attrs = ['uid', 'shadowLastChange', 'shadowMin',
                  'shadowMax', 'shadowWarning', 'shadowInactive',
                  'shadowExpire', 'shadowFlag', 'userPassword']
    self.essential_fields = ['uid']

  def CreateMap(self):
    """Return a ShadowMap instance."""
    return maps.ShadowMap()

  def Transform(self, obj):
    """Transforms an LDAP shadowAccont object into a shadow(5) entry."""
    shadow_ent = maps.ShadowMapEntry()
    shadow_ent.name = obj['uid'][0]
    # TODO(jaq): does nss_ldap check the contents of the userPassword
    # attribute?
    shadow_ent.passwd = '*'
    if 'shadowLastChange' in obj:
      shadow_ent.lstchg = int(obj['shadowLastChange'][0])
    if 'shadowMin' in obj:
      shadow_ent.min = int(obj['shadowMin'][0])
    if 'shadowMax' in obj:
      shadow_ent.max = int(obj['shadowMax'][0])
    if 'shadowWarning' in obj:
      shadow_ent.warn = int(obj['shadowWarning'][0])
    if 'shadowInactive' in obj:
      shadow_ent.inact = int(obj['shadowInactive'][0])
    if 'shadowExpire' in obj:
      shadow_ent.expire = int(obj['shadowExpire'][0])
    if 'shadowFlag' in obj:
      shadow_ent.flag = int(obj['shadowFlag'][0])
    if shadow_ent.flag is None:
      shadow_ent.flag = 0
    if 'userPassword' in obj:
      passwd = obj['userPassword'][0]
      if passwd[:7] == "{CRYPT}":
        shadow_ent.passwd = passwd[7:]
      else:
        logging.info('Ignored password that was not in crypt format')
    return shadow_ent


class NetgroupUpdateGetter(UpdateGetter):
  """Get netgroup updates."""

  def __init__(self):
    super(NetgroupUpdateGetter, self).__init__()
    self.attrs = ['cn', 'memberNisNetgroup', 'nisNetgroupTriple']
    self.essential_fields = ['cn']

  def CreateMap(self):
    """Return a NetgroupMap instance."""
    return maps.NetgroupMap()

  def Transform(self, obj):
    """Transforms an LDAP nisNetgroup object into a netgroup(5) entry."""
    netgroup_ent = maps.NetgroupMapEntry()
    netgroup_ent.name = obj['cn'][0]

    if 'memberNisNetgroup' in obj:
      netgroup_ent.entries.extend(obj['memberNisNetgroup'])
    if 'nisNetgroupTriple' in obj:
      netgroup_ent.entries.extend(obj['nisNetgroupTriple'])

    return netgroup_ent


# Finally, register the Source
base.RegisterImplementation(LdapSource)
