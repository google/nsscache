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
import ldap.sasl
import urllib
import re
import sys
import struct
from distutils.version import StrictVersion

from nss_cache import error
from nss_cache.maps import automount
from nss_cache.maps import group
from nss_cache.maps import netgroup
from nss_cache.maps import passwd
from nss_cache.maps import shadow
from nss_cache.maps import sshkey
from nss_cache.sources import source


IS_LDAP24_OR_NEWER = StrictVersion(ldap.__version__) >= StrictVersion('2.4')

# ldap.LDAP_CONTROL_PAGE_OID is unavailable on some systems, so we define it here
LDAP_CONTROL_PAGE_OID = '1.2.840.113556.1.4.319'

def RegisterImplementation(registration_callback):
  registration_callback(LdapSource)

def makeSimplePagedResultsControl(page_size):
  # The API for this is different on older versions of python-ldap, so we need
  # to handle this case.
  if IS_LDAP24_OR_NEWER:
    return ldap.controls.SimplePagedResultsControl(True, size=page_size, cookie='')
  else:
    return ldap.controls.SimplePagedResultsControl(LDAP_CONTROL_PAGE_OID, True, (page_size, ''))

def getCookieFromControl(pctrl):
  if IS_LDAP24_OR_NEWER:
    return pctrl.cookie
  else:
    return pctrl.controlValue[1]

def setCookieOnControl(control, cookie, page_size):
  if IS_LDAP24_OR_NEWER:
    control.cookie = cookie
  else:
    control.controlValue = (page_size, cookie)

  return cookie

def sidToStr(sid):
  """ Converts a hexadecimal string returned from the LDAP query to a
  string version of the SID in format of S-1-5-21-1270288957-3800934213-3019856503-500
  This function was based from: http://www.gossamer-threads.com/lists/apache/bugs/386930
  """
  # The revision level (typically 1)
  if sys.version_info.major < 3:
      revision = ord(sid[0])
  else:
      revision = sid[0]
  # The number of dashes minus 2
  if sys.version_info.major < 3:
      number_of_sub_ids = ord(sid[1])
  else:
      number_of_sub_ids = sid[1]
  # Identifier Authority Value (typically a value of 5 representing "NT Authority")
  # ">Q" is the format string. ">" specifies that the bytes are big-endian.
  # The "Q" specifies "unsigned long long" because 8 bytes are being decoded.
  # Since the actual SID section being decoded is only 6 bytes, we must precede it with 2 empty bytes.
  iav = struct.unpack('>Q', b'\x00\x00' + sid[2:8])[0]
  # The sub-ids include the Domain SID and the RID representing the object
  # '<I' is the format string. "<" specifies that the bytes are little-endian. "I" specifies "unsigned int".
  # This decodes in 4 byte chunks starting from the 8th byte until the last byte
  sub_ids = [struct.unpack('<I', sid[8 + 4 * i:12 + 4 * i])[0]
             for i in range(number_of_sub_ids)]

  return 'S-{0}-{1}-{2}'.format(revision, iav, '-'.join([str(sub_id) for sub_id in sub_ids]))


class LdapSource(source.Source):
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

  # for registration
  name = 'ldap'

  # Page size for paged LDAP requests
  # Value chosen based on default Active Directory MaxPageSize
  PAGE_SIZE = 1000

  def __init__(self, conf, conn=None):
    """Initialise the LDAP Data Source.

    Args:
      conf: config.Config instance
      conn: An instance of ldap.LDAPObject that'll be used as the connection.
    """
    super(LdapSource, self).__init__(conf)
    self._dn_requested = False  # dn is a special-cased attribute

    self._SetDefaults(conf)
    self._conf = conf
    self.ldap_controls = makeSimplePagedResultsControl(self.PAGE_SIZE)

    # Used by _ReSearch:
    self._last_search_params = None

    if conn is None:
      # ReconnectLDAPObject should handle interrupted ldap transactions.
      # also, ugh
      rlo = ldap.ldapobject.ReconnectLDAPObject
      self.conn = rlo(uri=conf['uri'],
                      retry_max=conf['retry_max'],
                      retry_delay=conf['retry_delay'])
      if conf['tls_starttls'] == 1:
          self.conn.start_tls_s()
      if 'ldap_debug' in conf:
        self.conn.set_option(ldap.OPT_DEBUG_LEVEL, conf['ldap_debug'])
    else:
      self.conn = conn

    # TODO(v): We should bind on-demand instead.
    # (although binding here makes it easier to simulate a dropped network)
    self.Bind(conf)

  def _SetDefaults(self, configuration):
    """Set defaults if necessary."""
    # LDAPI URLs must be url escaped socket filenames; rewrite if necessary.
    if 'uri' in configuration:
      if configuration['uri'].startswith('ldapi://'):
        configuration['uri'] = 'ldapi://' + urllib.quote(configuration['uri'][8:], '')
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
    if not 'tls_starttls' in configuration:
      configuration['tls_starttls'] = 0

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

    if not 'sasl_authzid' in configuration:
      configuration['sasl_authzid'] = ''

    # Should we issue STARTTLS?
    if configuration['tls_starttls'] in (1, '1', 'on', 'yes', 'true'):
        configuration['tls_starttls'] = 1
    #if not configuration['tls_starttls']:
    else:
      configuration['tls_starttls'] = 0

    # Setting global ldap defaults.
    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT,
                    configuration['tls_require_cert'])
    if 'tls_cacertdir' in configuration:
        ldap.set_option(ldap.OPT_X_TLS_CACERTDIR, configuration['tls_cacertdir'])
    if 'tls_cacertfile' in configuration:
        ldap.set_option(ldap.OPT_X_TLS_CACERTFILE, configuration['tls_cacertfile'])
    if 'tls_certfile' in configuration:
        ldap.set_option(ldap.OPT_X_TLS_CERTFILE, configuration['tls_certfile'])
    if 'tls_keyfile' in configuration:
        ldap.set_option(ldap.OPT_X_TLS_KEYFILE, configuration['tls_keyfile'])
    ldap.version = ldap.VERSION3  # this is hard-coded, we only support V3

  def _SetCookie(self, cookie):
    return setCookieOnControl(self.ldap_controls, cookie, self.PAGE_SIZE)

  def Bind(self, configuration):
    """Bind to LDAP, retrying if necessary."""
    # If the server is unavailable, we are going to find out now, as this
    # actually initiates the network connection.
    retry_count = 0
    while retry_count < configuration['retry_max']:
      self.log.debug('opening ldap connection and binding to %s',
                     configuration['uri'])
      try:
        if 'use_sasl' in configuration and configuration['use_sasl']:
          if ('sasl_mech' in configuration and
              configuration['sasl_mech'] and
              configuration['sasl_mech'].lower() == 'gssapi'):
            sasl = ldap.sasl.gssapi(configuration['sasl_authzid'])
          # TODO: Add other sasl mechs
          else:
            raise error.ConfigurationError('SASL mechanism not supported')

          self.conn.sasl_interactive_bind_s('', sasl)
        else:
          self.conn.simple_bind_s(who=configuration['bind_dn'],
                                cred=str(configuration['bind_password']))
        break
      except ldap.SERVER_DOWN, e:
        retry_count += 1
        self.log.warning('Failed LDAP connection: attempt #%s.', retry_count)
        self.log.debug('ldap error is %r', e)
        if retry_count == configuration['retry_max']:
          self.log.debug('max retries hit')
          raise error.SourceUnavailable(e)
        self.log.debug('sleeping %d seconds', configuration['retry_delay'])
        time.sleep(configuration['retry_delay'])

  def _ReSearch(self):
    """
    Performs self.Search again with the previously used parameters.

    Returns:
     self.Search result.
    """
    self.Search(*self._last_search_params)

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
    self._last_search_params = (search_base, search_filter, search_scope, attrs)

    self.log.debug('searching for base=%r, filter=%r, scope=%r, attrs=%r',
                   search_base, search_filter, search_scope, attrs)
    if 'dn' in attrs: self._dn_requested = True  # special cased attribute
    self.message_id = self.conn.search_ext(base=search_base,
                                           filterstr=search_filter,
                                           scope=search_scope,
                                           attrlist=attrs,
                                           serverctrls=[self.ldap_controls])

  def __iter__(self):
    """Iterate over the data from the last search.

    Probably not threadsafe.

    Yields:
      Search results from the prior call to self.Search()
    """
    # Acquire data to yield:
    while True:
      result_type, data = None, None

      timeout_retries = 0
      while timeout_retries < self._conf['retry_max']:
        try:
          result_type, data, _, serverctrls = self.conn.result3(
            self.message_id, all=0, timeout=self.conf['timelimit'])

          # Paged requests return a new cookie in serverctrls at the end of a page,
          # so we search for the cookie and perform another search if needed.
          if len(serverctrls) > 0:
            # Search for appropriate control
            simple_paged_results_controls = [
              control
              for control in serverctrls
              if control.controlType == LDAP_CONTROL_PAGE_OID
            ]
            if simple_paged_results_controls:
              # We only expect one control; just take the first in the list.
              cookie = getCookieFromControl(simple_paged_results_controls[0])

              if len(cookie) > 0:
                # If cookie is non-empty, call search_ext and result3 again
                self._SetCookie(cookie)
                self._ReSearch()
                result_type, data, _, serverctrls = self.conn.result3(
                  self.message_id, all=0, timeout=self.conf['timelimit'])
              # else: An empty cookie means we are done.

          # break loop once result3 doesn't time out and reset cookie
          setCookieOnControl(self.ldap_controls, '', self.PAGE_SIZE)
          break
        except ldap.SIZELIMIT_EXCEEDED:
          self.log.warning('LDAP server size limit exceeded; using page size {0}.'.format(self.PAGE_SIZE))
          return
        except ldap.NO_SUCH_OBJECT:
          self.log.debug('Returning due to ldap.NO_SUCH_OBJECT')
          return
        except ldap.TIMELIMIT_EXCEEDED:
          timeout_retries += 1
          self.log.warning('Timeout on LDAP results, attempt #%s.', timeout_retries)
          if timeout_retries >= self._conf['retry_max']:
            self.log.debug('max retries hit, returning')
            return
          self.log.debug('sleeping %d seconds', self._conf['retry_delay'])
          time.sleep(self.conf['retry_delay'])

      if result_type == ldap.RES_SEARCH_RESULT:
        self.log.debug('Returning due to RES_SEARCH_RESULT')
        return

      if result_type != ldap.RES_SEARCH_ENTRY:
        self.log.info('Unknown result type %r, ignoring.', result_type)

      if not data:
        self.log.debug('Returning due to len(data) == 0')
        return

      for record in data:
        # If the dn is requested, return it along with the payload,
        # otherwise ignore it.
        if self._dn_requested:
          merged_records = {'dn': record[0]}
          merged_records.update(record[1])
          yield merged_records
        else:
          yield record[1]

  def GetSshkeyMap(self, since=None):
    """Return the sshkey map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of maps.SshkeyMap
    """
    return SshkeyUpdateGetter(self.conf).GetUpdates(source=self,
                                           search_base=self.conf['base'],
                                           search_filter=self.conf['filter'],
                                           search_scope=self.conf['scope'],
                                           since=since)
  def GetPasswdMap(self, since=None):
    """Return the passwd map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of maps.PasswdMap
    """
    return PasswdUpdateGetter(self.conf).GetUpdates(source=self,
                                           search_base=self.conf['base'],
                                           search_filter=self.conf['filter'],
                                           search_scope=self.conf['scope'],
                                           since=since)

  def GetGroupMap(self, since=None):
    """Return the group map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of maps.GroupMap
    """
    return GroupUpdateGetter(self.conf).GetUpdates(source=self,
                                          search_base=self.conf['base'],
                                          search_filter=self.conf['filter'],
                                          search_scope=self.conf['scope'],
                                          since=since)

  def GetShadowMap(self, since=None):
    """Return the shadow map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of ShadowMap
    """
    return ShadowUpdateGetter(self.conf).GetUpdates(source=self,
                                           search_base=self.conf['base'],
                                           search_filter=self.conf['filter'],
                                           search_scope=self.conf['scope'],
                                           since=since)

  def GetNetgroupMap(self, since=None):
    """Return the netgroup map from this source.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
      for all data.

    Returns:
      instance of NetgroupMap
    """
    return NetgroupUpdateGetter(self.conf).GetUpdates(source=self,
                                             search_base=self.conf['base'],
                                             search_filter=self.conf['filter'],
                                             search_scope=self.conf['scope'],
                                             since=since)

  def GetAutomountMap(self, since=None, location=None):
    """Return an automount map from this source.

    Note that autmount maps are stored in multiple locations, thus we expect
    a caller to provide a location.  We also follow the automount spec and
    set our search scope to be 'one'.

    Args:
      since: Get data only changed since this timestamp (inclusive) or None
        for all data.
      location: Currently a string containing our search base, later we
        may support hostname and additional parameters.

    Returns:
      instance of AutomountMap
    """
    if location is None:
      self.log.error('A location is required to retrieve an automount map!')
      raise error.EmptyMap

    autofs_filter = '(objectclass=automount)'
    return AutomountUpdateGetter(self.conf).GetUpdates(source=self,
                                              search_base=location,
                                              search_filter=autofs_filter,
                                              search_scope='one',
                                              since=since)

  def GetAutomountMasterMap(self):
    """Return the autmount master map from this source.

    The automount master map is a special-case map which points to a dynamic
    list of additional maps. We currently support only the schema outlined at
    http://docs.sun.com/source/806-4251-10/mapping.htm commonly used by linux
    automount clients, namely ou=auto.master and objectclass=automount entries.

    Returns:
      an instance of maps.AutomountMap
    """
    search_base = self.conf['base']
    search_scope = ldap.SCOPE_SUBTREE

    # auto.master is stored under ou=auto.master with objectclass=automountMap
    search_filter = '(&(objectclass=automountMap)(ou=auto.master))'
    self.log.debug('retrieving automount master map.')
    self.Search(search_base=search_base, search_filter=search_filter,
                search_scope=search_scope, attrs=['dn'])

    search_base = None
    for obj in self:
      # the dn of the matched object is our search base
      search_base = obj['dn']

    if search_base is None:
      self.log.critical('Could not find automount master map!')
      raise error.EmptyMap

    self.log.debug('found ou=auto.master at %s', search_base)
    master_map = self.GetAutomountMap(location=search_base)

    # fix our location attribute to contain the data we
    # expect returned to us later, namely the new search base(s)
    for map_entry in master_map:
      # we currently ignore hostname and just look for the dn which will
      # be the search_base for this map.  third field, colon delimited.
      map_entry.location = map_entry.location.split(':')[2]
      # and strip the space seperated options
      map_entry.location = map_entry.location.split(' ')[0]
      self.log.debug('master map has: %s' % map_entry.location)

    return master_map

  def Verify(self, since=None):
    """Verify that this source is contactable and can be queried for data."""
    if since is None:
      # one minute in the future
      since = int(time.time() + 60)
    results = self.GetPasswdMap(since=since)
    return len(results)


class UpdateGetter(object):
  """Base class that gets updates from LDAP."""
  def __init__(self, conf):
    super(UpdateGetter, self).__init__()
    self.conf = conf

  def FromLdapToTimestamp(self, ldap_ts_string):
    """Transforms a LDAP timestamp into the nss_cache internal timestamp.

    Args:
      ldap_ts_string: An LDAP timestamp string in the format %Y%m%d%H%M%SZ

    Returns:
      number of seconds since epoch.
    """
    try:
      t = time.strptime(ldap_ts_string, '%Y%m%d%H%M%SZ')
    except ValueError:
      # Some systems add a decimal component; try to filter it:
      m = re.match('([0-9]*)(\.[0-9]*)?(Z)', ldap_ts_string)
      if m:
        ldap_ts_string = m.group(1) + m.group(3)
      t = time.strptime(ldap_ts_string, '%Y%m%d%H%M%SZ')
    return int(calendar.timegm(t))

  def FromTimestampToLdap(self, ts):
    """Transforms nss_cache internal timestamp into a LDAP timestamp.

    Args:
      ts: number of seconds since epoch

    Returns:
      LDAP format timestamp string.
    """
    t = time.strftime('%Y%m%d%H%M%SZ', time.gmtime(ts))
    return t

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
    elif search_scope in ['one', 'onelevel']:
      search_scope = ldap.SCOPE_ONELEVEL
    elif search_scope in ['sub', 'subtree']:
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

      try:
        obj_ts = self.FromLdapToTimestamp(obj['modifyTimestamp'][0])
      except KeyError:
        obj_ts = self.FromLdapToTimestamp(obj['modifyTimeStamp'][0])

      if max_ts is None or obj_ts > max_ts:
        max_ts = obj_ts

      try:
        if not data_map.Add(self.Transform(obj)):
          logging.info('could not add obj: %r', obj)
      except AttributeError, e:
        logging.warning('error %r, discarding malformed obj: %r',
                        str(e), obj)
    # Perform some post processing on the data_map.
    self.PostProcess(data_map, source, search_filter, search_scope)

    data_map.SetModifyTimestamp(max_ts)

    return data_map

  def PostProcess(self, data_map, source, search_filter, search_scope):
    """Perform some post-process of the data."""
    pass


class PasswdUpdateGetter(UpdateGetter):
  """Get passwd updates."""

  def __init__(self, conf):
    super(PasswdUpdateGetter, self).__init__(conf)
    self.attrs = ['uid', 'uidNumber', 'gidNumber', 'gecos', 'cn',
                  'homeDirectory', 'loginShell', 'fullName']
    if self.conf.get('ad'):
      self.attrs.extend(('sAMAccountName', 'objectSid', 'displayName', 'unixHomeDirectory'))
      self.essential_fields = ['sAMAccountName', 'objectSid']
    else:
      if 'uidattr' in self.conf:
        self.attrs.append(self.conf['uidattr'])
      if 'uidregex' in self.conf:
        self.uidregex = re.compile(self.conf['uidregex'])
      self.essential_fields = ['uid', 'uidNumber', 'gidNumber']
    self.log = logging.getLogger(self.__class__.__name__)

  def CreateMap(self):
    """Returns a new PasswdMap instance to have PasswdMapEntries added to it."""
    return passwd.PasswdMap()

  def Transform(self, obj):
    """Transforms a LDAP posixAccount data structure into a PasswdMapEntry."""

    pw = passwd.PasswdMapEntry()

    if 'displayName' in obj:
      pw.gecos = obj['displayName'][0]
    elif 'gecos' in obj:
      pw.gecos = obj['gecos'][0]
    elif 'cn' in obj:
      pw.gecos = obj['cn'][0]
    elif 'fullName' in obj:
      pw.gecos = obj['fullName'][0]
    else:
      raise ValueError('Neither gecos nor cn found')

    pw.gecos = pw.gecos.replace('\n','')

    if self.conf.get('ad'):
      pw.name = obj['sAMAccountName'][0]
    elif 'uidattr' in self.conf:
      pw.name = obj[self.conf['uidattr']][0]
    else:
      pw.name = obj['uid'][0]

    if hasattr(self, 'uidregex'):
      pw.name = ''.join([x for x in self.uidregex.findall(pw.name)])

    if 'override_shell' in self.conf:
      pw.shell = self.conf['override_shell']
    elif 'loginShell' in obj:
      pw.shell = obj['loginShell'][0]
    else:
      pw.shell = ''

    if self.conf.get('ad'):
      if self.conf.get('uidnumber'):
        try:
          pw.uid = int(obj['uidNumber'][0])
        except KeyError:
          pw.uid = int(sidToStr(obj['objectSid'][0]).split('-')[-1])
      else:
        pw.uid = int(sidToStr(obj['objectSid'][0]).split('-')[-1])
      if self.conf.get('gidnumber'):
        try:
          pw.uid = int(obj['gidNumber'][0])
        except KeyError:
          pw.gid = int(sidToStr(obj['objectSid'][0]).split('-')[-1])
      else:
        pw.gid = int(sidToStr(obj['objectSid'][0]).split('-')[-1])
    else:
      pw.uid = int(obj['gidNumber'][0])
      pw.gid = int(obj['gidNumber'][0])

    if 'offset' in self.conf:
      pw.uid = int(pw.uid + self.conf['offset'])
      pw.gid = int(pw.gid + self.conf['offset'])

    if self.conf.get('home_dir'):
      pw.dir = '/home/%s' % pw.name
    elif 'unixHomeDirectory' in obj:
      pw.dir = obj['unixHomeDirectory'][0]
    elif 'homeDirectory' in obj:
      pw.dir = obj['homeDirectory'][0]
    else:
      pw.dir = ''

    # hack
    pw.passwd = 'x'

    return pw


class GroupUpdateGetter(UpdateGetter):
  """Get group updates."""

  def __init__(self, conf):
    super(GroupUpdateGetter, self).__init__(conf)
    # TODO: Merge multiple rcf2307bis[_alt] options into a single option.
    if self.conf.get('ad'):
      self.attrs = ['sAMAccountName', 'gidNumber', 'member', 'objectSid']
      self.essential_fields = ['sAMAccountName']
    else:
      if conf.get('rfc2307bis'):
        self.attrs = ['cn', 'gidNumber', 'member']
      elif conf.get('rfc2307bis_alt'):
        self.attrs = ['cn', 'gidNumber', 'uniqueMember']
      else:
        self.attrs = ['cn', 'gidNumber', 'memberUid']
      if 'groupregex' in conf:
        self.groupregex = re.compile(self.conf['groupregex'])
      self.essential_fields = ['cn']
    self.log = logging.getLogger(self.__class__.__name__)

  def CreateMap(self):
    """Return a GroupMap instance."""
    return group.GroupMap()

  def Transform(self, obj):
    """Transforms a LDAP posixGroup object into a group(5) entry."""

    gr = group.GroupMapEntry()

    if self.conf.get('ad'):
      gr.name = obj['sAMAccountName'][0]
    else:
      gr.name = obj['cn'][0]
    # group passwords are deferred to gshadow
    gr.passwd = '*'
    base = self.conf.get("base")
    members = []
    group_members = []
    if 'memberUid' in obj:
      if hasattr(self, 'groupregex'):
        members.extend(''.join([x for x in self.groupregex.findall(obj['memberUid'])]))
      else:
        members.extend(obj['memberUid'])
    elif 'member' in obj:
      for member_dn in obj['member']:
        member_uid = member_dn.split(',')[0].split('=')[1]
        # Note that there is not currently a way to consistently distinguish
        # a group from a person
        group_members.append(member_uid)
        if hasattr(self, 'groupregex'):
          members.append(''.join([x for x in self.groupregex.findall(member_uid)]))
        else:
          members.append(member_uid)
    elif 'uniqueMember' in obj:
      """ This contains a DN and is processed in PostProcess in GetUpdates."""
      members.extend(obj['uniqueMember'])
    members.sort()

    if self.conf.get('ad'):
      if self.conf.get('gidnumber'):
        try:
          gr.gid = int(obj['gidnumber'][0])
        except KeyError:
          gr.gid = int(sidToStr(obj['objectSid'][0]).split('-')[-1])
      else:
        gr.gid = int(sidToStr(obj['objectSid'][0]).split('-')[-1])
    else:
      gr.gid = int(obj['gidnumber'][0])

    if 'offset' in self.conf:
      gr.gid = int(gr.gid + self.conf['offset'])

    gr.members = members
    gr.groupmembers = group_members

    return gr

  def PostProcess(self, data_map, source, search_filter, search_scope):
    """Perform some post-process of the data."""
    if 'uniqueMember' in self.attrs:
      for gr in data_map:
        uidmembers=[]
        for member in gr.members:
          source.Search(search_base=member,
                        search_filter='(objectClass=*)',
                        search_scope=ldap.SCOPE_BASE,
                        attrs=['uid'])
          for obj in source:
            if 'uid' in obj:
              uidmembers.extend(obj['uid'])
        del gr.members[:]
        gr.members.extend(uidmembers)

    _group_map = {i.name: i for i in data_map}
    
    def _expand_members(obj, visited=None):
      """Expand all subgroups recursively"""
      for member_name in obj.groupmembers:
        if member_name in _group_map and member_name not in visited:
          gmember = _group_map[member_name]
          for member in gmember.members:
            if member not in obj.members:
              obj.members.append(member)
          for submember_name in gmember.groupmembers:
            if submember_name in _group_map and submember_name not in visited:
              visited.append(submember_name)
              _expand_members(_group_map[submember_name], visited)
    
    if self.conf.get("nested_groups"):
      self.log.info("Expanding nested groups")
      for gr in data_map:
        _expand_members(gr, [gr.name])


class ShadowUpdateGetter(UpdateGetter):
  """Get Shadow updates from the LDAP Source."""

  def __init__(self, conf):
    super(ShadowUpdateGetter, self).__init__(conf)
    self.attrs = ['uid', 'shadowLastChange', 'shadowMin',
                  'shadowMax', 'shadowWarning', 'shadowInactive',
                  'shadowExpire', 'shadowFlag', 'userPassword']
    if self.conf.get('ad'):
      self.attrs.extend(('sAMAccountName', 'pwdLastSet'))
      self.essential_fields = ['sAMAccountName']
    else:
      if 'uidattr' in self.conf:
        self.attrs.append(self.conf['uidattr'])
      if 'uidregex' in self.conf:
        self.uidregex = re.compile(self.conf['uidregex'])
      self.essential_fields = ['uid']
    self.log = logging.getLogger(self.__class__.__name__)

  def CreateMap(self):
    """Return a ShadowMap instance."""
    return shadow.ShadowMap()

  def Transform(self, obj):
    """Transforms an LDAP shadowAccont object into a shadow(5) entry."""
    shadow_ent = shadow.ShadowMapEntry()
    if self.conf.get('ad'):
      shadow_ent.name = obj['sAMAccountName'][0]
    elif 'uidattr' in self.conf:
      shadow_ent.name = obj[self.conf['uidattr']][0]
    else:
      shadow_ent.name = obj['uid'][0]

    if hasattr(self, 'uidregex'):
      shadow_ent.name = ''.join([x for x in self.uidregex.findall(shadow_end.name)])

    # TODO(jaq): does nss_ldap check the contents of the userPassword
    # attribute?
    shadow_ent.passwd = '*'
    if 'pwdLastSet' in obj:
      shadow_ent.lstchg = int((int(obj['pwdLastSet'][0])/10000000 - 11644473600) / 86400 )
    elif 'shadowLastChange' in obj:
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
      if passwd[:7].lower() == '{crypt}':
        shadow_ent.passwd = passwd[7:]
      else:
        logging.info('Ignored password that was not in crypt format')
    return shadow_ent


class NetgroupUpdateGetter(UpdateGetter):
  """Get netgroup updates."""

  def __init__(self, conf):
    super(NetgroupUpdateGetter, self).__init__(conf)
    self.attrs = ['cn', 'memberNisNetgroup', 'nisNetgroupTriple']
    self.essential_fields = ['cn']

  def CreateMap(self):
    """Return a NetgroupMap instance."""
    return netgroup.NetgroupMap()

  def Transform(self, obj):
    """Transforms an LDAP nisNetgroup object into a netgroup(5) entry."""
    netgroup_ent = netgroup.NetgroupMapEntry()
    netgroup_ent.name = obj['cn'][0]

    entries = set()
    if 'memberNisNetgroup' in obj:
      entries.update(obj['memberNisNetgroup'])
    if 'nisNetgroupTriple' in obj:
      entries.update(obj['nisNetgroupTriple'])

    # final data is stored as a string in the object
    netgroup_ent.entries = ' '.join(sorted(entries))

    return netgroup_ent


class AutomountUpdateGetter(UpdateGetter):
  """Get specific automount maps."""

  def __init__(self, conf):
    super(AutomountUpdateGetter, self).__init__(conf)
    self.attrs = ['cn', 'automountInformation']
    self.essential_fields = ['cn']

  def CreateMap(self):
    """Return a AutomountMap instance."""
    return automount.AutomountMap()

  def Transform(self, obj):
    """Transforms an LDAP automount object into an autofs(5) entry."""
    automount_ent = automount.AutomountMapEntry()
    automount_ent.key = obj['cn'][0]

    automount_information = obj['automountInformation'][0]

    if automount_information.startswith('ldap'):
      # we are creating an autmount master map, pointing to other maps in LDAP
      automount_ent.location = automount_information
    else:
      # we are creating normal automount maps, with filesystems and options
      automount_ent.options = automount_information.split(' ')[0]
      automount_ent.location = automount_information.split(' ')[1]

    return automount_ent


class SshkeyUpdateGetter(UpdateGetter):
  """Fetches SSH keys."""

  def __init__(self, conf):
    super(SshkeyUpdateGetter, self).__init__(conf)
    self.attrs = ['uid', 'sshPublicKey']
    if 'uidattr' in self.conf:
      self.attrs.append(self.conf['uidattr'])
    if 'uidregex' in self.conf:
       self.uidregex = re.compile(self.conf['uidregex'])
    self.essential_fields = ['uid']

  def CreateMap(self):
    """Returns a new SshkeyMap instance to have SshkeyMapEntries added to it."""
    return sshkey.SshkeyMap()

  def Transform(self, obj):
    """Transforms a LDAP posixAccount data structure into a SshkeyMapEntry."""

    skey = sshkey.SshkeyMapEntry()

    if 'uidattr' in self.conf:
      skey.name = obj[uidattr][0]
    else:
      skey.name = obj['uid'][0]

    if hasattr(self, 'uidregex'):
      skey.name = ''.join([x for x in self.uidregex.findall(pw.name)])

    if 'sshPublicKey' in obj:
      skey.sshkey = obj['sshPublicKey']
    else:
      skey.sshkey = ''

    return skey
