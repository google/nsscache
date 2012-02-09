#!/usr/bin/python
#
# Copyright 2010 Google Inc.
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

"""ZSync data source for nss_cache."""

__author__ = 'blaedd@google.com (David MacKinnon)'


import os
import re
import tempfile
import time
import urlparse

import pycurl
import zsync

try:
  import pyme.core
except ImportError:
  pyme = None

import nss_cache
from nss_cache import config
from nss_cache import error
from nss_cache.sources import source
from nss_cache.util import curl


def RegisterImplementation(registration_callback):
  registration_callback(ZSyncSource)


class ZSyncSource(source.FileSource):
  """File based source using ZSync."""

  # Update method used by this source
  UPDATER = config.UPDATER_FILE

  # zsync defaults
  ZSYNC_SUFFIX = '.zsync'
  RETRY_DELAY = 5
  RETRY_MAX = 3
  PASSWD_URL = ''
  SHADOW_URL = ''
  GROUP_URL = ''
  AUTOMOUNT_BASE_URL = ''
  NETGROUP_URL = ''
  GPG = False
  GPG_PUBKEYFILE = '/var/lib/nsscache/nsscache.pub'
  GPG_SUFFIX = '.asc'

  TLS_CACERTFILE = '/etc/ssl/certs/ca-certificates.crt'

  CONTENT_RANGE_RE = re.compile((r'content-range: bytes '
                                 '(?P<start>\d+)-(?P<end>\d+)/(?P<total>\d+)'),
                                re.I)

  name = 'zsync'

  def __init__(self, conf, conn=None):
    """Initialize the ZSync data source.

    Args:
      conf: config.Config instance
      conn: A pycurl.Curl instance that will be used as the connection for
            range requests.
    """
    super(ZSyncSource, self).__init__(conf)

    self._SetDefaults(conf)
    if conn is None:
      conn = self._NewConnection()
    self.conn = conn
    if self.conf['gpg']:
      if not pyme:
        self.log.fatal('Configured to use GPG but the pyme python library is'
                       ' unavailable.')

  def _NewConnection(self):
    """Create a new pycurl connection."""
    conn = pycurl.Curl()
    conn.setopt(pycurl.NOPROGRESS, 1)
    conn.setopt(pycurl.NOSIGNAL, 1)
    conn.setopt(pycurl.USERAGENT, 'nsscache_%s' % nss_cache.__version__)
    conn.setopt(pycurl.HTTPHEADER, ['Pragma:'])
    if self.conf['http_proxy']:
      conn.setopt(pycurl.PROXY, self.conf['http_proxy'])
    return conn

  def _ImportPubKey(self):
    """Import the GPG public key given in the config file."""
    gpg_context = pyme.core.Context()
    try:
      self.log.debug('Opening %s to read in the gpg pub key',
                     self.conf['gpg_pubkeyfile'])
      self.log.debug('Access: %s', os.access(self.conf['gpg_pubkeyfile'], os.R_OK))
      sigfile = pyme.core.Data(file=self.conf['gpg_pubkeyfile'])
      gpg_context.op_import(sigfile)
      gpg_result = gpg_context.op_import_result()
      self.log.debug('keys considered: %s, imported: %s, not imported %s',
                     gpg_result.considered, gpg_result.imported,
                     gpg_result.not_imported)
      if gpg_result.considered > 0:
        self.conf['gpg_fingerprint'] = gpg_result.imports[0].fpr
    except pyme.errors.GPGMEError, e:
      self.log.error(e.getstring())
      self.log.fatal('Unable to import pubkeyfile, aborting')

  def _SetDefaults(self, configuration):
    """Set defaults, if necessary."""
    if not 'automount_base_url' in configuration:
      configuration['automount_base_url'] = self.AUTOMOUNT_BASE_URL
    if not 'passwd_url' in configuration:
      configuration['passwd_url'] = self.PASSWD_URL
    if not 'shadow_url' in configuration:
      configuration['shadow_url'] = self.SHADOW_URL
    if not 'group_url' in configuration:
      configuration['group_url'] = self.GROUP_URL
    if not 'netgroup_url' in configuration:
      configuration['netgroup_url'] = self.GROUP_URL
    if not 'retry_delay' in configuration:
      configuration['retry_delay'] = self.RETRY_DELAY
    if not 'retry_max' in configuration:
      configuration['retry_max'] = self.RETRY_MAX
    if not 'tls_cacertfile' in configuration:
      configuration['tls_cacertfile'] = self.TLS_CACERTFILE
    if not 'zsync_suffix' in configuration:
      configuration['zsync_suffix'] = self.ZSYNC_SUFFIX
    if not 'gpg' in configuration:
      configuration['gpg'] = self.GPG
    if not 'gpg_pubkeyfile' in configuration:
      configuration['gpg_pubkeyfile'] = self.GPG_PUBKEYFILE
    if not 'gpg_suffix' in configuration:
      configuration['gpg_suffix'] = self.GPG_SUFFIX
    if not 'http_proxy' in configuration:
      configuration['http_proxy'] = None

  def _GPGVerify(self, local_path, remote_sig, context=None):
    """Verify the file with a GPG signature.

    Args:
      local_path: Path to local file
      remote_sig: URL to signature file
      context: pyme Context object
    Returns:
      Bool
    """
    if not self.conf.get('gpg_fingerprint'):
      self._ImportPubKey()
    self.log.debug('fetching: %s', remote_sig)
    self.conn.setopt(pycurl.RANGE, '0-')
    (resp_code, _, sig) = curl.CurlFetch(remote_sig, self.conn, self.log)
    if resp_code not in (200, 206):
      self.log.error('Could not fetch %s', remote_sig)
      return False
    if not context:
      context = pyme.core.Context()
    sig = pyme.core.Data(sig)
    self.log.debug('gpg verify: %s', local_path)
    signed = pyme.core.Data(file=local_path)
    context.op_verify(sig, signed, None)
    result = context.op_verify_result()
    if len(result.signatures) > 0:
      sign = result.signatures[0]
    else:
      self.log.error('No signatures in result: %s', result)
      return False
    while sign:
      if self.conf.get('gpg_fingerprint') == sign.fpr:
        self.log.info('Successfully verified file %r signed by %r', local_path,
                      context.get_key(sign.fpr, 0).uids[0].uid)
        return True
      if hasattr(sign, 'next'):
        sign = sign.next
      else:
        sign = None
    return False

  def _GetFile(self, remote, local_path, current_file):
    """Retrieve a file.

    Try a zsync against the local cache, however if that fails try doing
    a full update via zsync.

    Args:
      remote: Remote URL to fetch.
      local_path: local file to use.
      current_file: path to the current cache file.
    Returns:
      local path
    """
    try:
      return self._GetFileViaZsync(remote, local_path, current_file)
    except error.InvalidMap:
      if current_file:
        self.log.warning('Partial zsync failed - trying full zsync...')
        return self._GetFileViaZsync(remote, local_path, None)
      else:
        raise

  def _GetFileViaZsync(self, remote, local_path, current_file):
    """Retrieve a file using zsync.

    Args:
      remote: Remote url to fetch
      local_path: local filename to use.
      current_file: path to the current cache file.
    Returns:
      local path
    """
    self.log.debug('ZSync URL: %s', remote)
    zs = zsync.Zsync(conn=self.conn,
                     retry_max=self.conf['retry_max'],
                     retry_delay=self.conf['retry_delay'])
    try:
      zs.Begin(remote + self.conf['zsync_suffix'])
      if current_file and os.path.exists(current_file):
        zs.SubmitSource(current_file)
      zs.Fetch(local_path)
    except zsync.error.Error, e:
      raise error.InvalidMap('Unable to retrieve zsync file: %s' % e)

    if not os.path.exists(local_path):
      raise error.EmptyMap()

    if self.conf['gpg']:
      remote_sig = remote + self.conf['gpg_suffix']
      if not self._GPGVerify(local_path, remote_sig):
        self.log.warning('Invalid GPG signature for %s', remote)
        raise error.InvalidMap('Unable to verify map')

    return local_path

  def GetPasswdFile(self, dst_file, current_file):
    """Retrieve passwd file via zsync.

    Args:
      dst_file: Destination file (temp)
      current_file: path to the current cache file.
    Returns:
      file object
    """
    tmp = self._GetFile(self.conf['passwd_url'], dst_file, current_file)
    return open(tmp)

  def GetGroupFile(self, dst_file, current_file):
    """Retrieve group file via zsync.

    Args:
      dst_file: Destination file (temp)
      current_file: path to the current cache file.
    Returns:
      file object
    """
    tmp = self._GetFile(self.conf['group_url'], dst_file, current_file)
    return open(tmp)

  def GetShadowFile(self, dst_file, current_file):
    """Retrieve shadow file via zsync.

    Args:
      dst_file: Destination file (temp)
      current_file: path to the current cache file.
    Returns:
      file object
    """
    tmp = self._GetFile(self.conf['shadow_url'], dst_file, current_file)
    return open(tmp)

  def GetNetgroupFile(self, dst_file, current_file):
    """Retrieve netgroup file via zsync.

    Args:
      dst_file: Destination file (temp)
      current_file: path to the current cache file.
    Returns:
      file object
    """
    tmp = self._GetFile(self.conf['netgroup_url'], dst_file, current_file)
    return open(tmp)

  def GetAutomountFile(self, dst_file, current_file, location):
    """Retrieve automount file via zsync.

    Args:
      dst_file: Destination file (temp)
      current_file: path to the current cache file.
      location: name of the automount
    Returns:
      path to cache
    """
    self.log.debug('Automount location: %s', location)
    if location is None:
      self.log.error('A location is required to retrieve an automount map!')
      raise error.EmptyMap()
    automount_url = urlparse.urljoin(self.conf['automount_base_url'],
                                     location)
    tmp = self._GetFile(automount_url, dst_file, current_file)
    return tmp

  def GetAutomountMasterFile(self, dst_file):
    """Retrieve the automount master map.

    Args:
      dst_file: Destination file (temp)
    Returns:
      path to cache
    """
    return self.GetAutomountFile(dst_file, None, 'auto.master')

  def Verify(self, since=None):
    """Verify that this source is contactable and can be queried for data."""
    tmpfile = tempfile.NamedTemporaryFile()
    # zsync's librcksum creates its own temp files in the cwd, so
    # let's chdir to where our tempfile goes so that it can rename its
    # tempfile to our tempfile without going across filesystems. Yo dawg.
    old_dir = os.getcwd()
    os.chdir(os.path.dirname(tmpfile.name))
    if self.conf['passwd_url']:
      self.GetPasswdFile(tmpfile.name, None)
    os.chdir(old_dir)
    return 0
