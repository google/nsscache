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
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

"""Minor curl methods."""

__author__ = 'blaedd@google.com (David MacKinnon)'


import cStringIO
import logging
import pycurl

from nss_cache import error


def CurlFetch(url, conn=None, logger=None):
  if not logger:
    logger=logging

  if not conn:
    conn = pycurl.Curl()

  conn.setopt(pycurl.URL, url)
  conn.body = cStringIO.StringIO()
  conn.headers = cStringIO.StringIO()
  conn.setopt(pycurl.WRITEFUNCTION, conn.body.write)
  conn.setopt(pycurl.HEADERFUNCTION, conn.headers.write)
  try:
    conn.perform()
  except Exception, e:
    HandleCurlError(e, logger)
    raise error.Error(e)
  resp_code = conn.getinfo(pycurl.RESPONSE_CODE)
  return (resp_code, conn.headers.getvalue(), conn.body.getvalue())


def HandleCurlError(e, logger=None):
  """Handle a curl exception.

  See http://curl.haxx.se/libcurl/c/libcurl-errors.html for a list of codes.

  Args:
    e: pycurl.error
    logger: logger object

  Raises:
    ConfigurationError:
    PermissionDenied:
    SourceUnavailable:
    Error:
  """
  if not logger:
    logger = logging

  code = e[0]
  msg = e[1]

  # Config errors
  if code in (pycurl.E_UNSUPPORTED_PROTOCOL,
              pycurl.E_URL_MALFORMAT,
              pycurl.E_SSL_ENGINE_NOTFOUND,
              pycurl.E_SSL_ENGINE_SETFAILED,
              pycurl.E_SSL_CACERT_BADFILE):
    raise error.ConfigurationError(msg)

  # Possibly transient errors, try again
  if code in (pycurl.E_FAILED_INIT,
              pycurl.E_COULDNT_CONNECT,
              pycurl.E_PARTIAL_FILE,
              pycurl.E_WRITE_ERROR,
              pycurl.E_READ_ERROR,
              pycurl.E_OPERATION_TIMEOUTED,
              pycurl.E_SSL_CONNECT_ERROR,
              pycurl.E_COULDNT_RESOLVE_PROXY,
              pycurl.E_COULDNT_RESOLVE_HOST,
              pycurl.E_GOT_NOTHING):
    logger.debug('Possibly transient error: %s', msg)
    return

  # SSL issues
  if code in (pycurl.E_SSL_PEER_CERTIFICATE,):
    raise error.SourceUnavailable(msg)

  # Anything else
  raise error.Error(msg)

