# Copyright 2011 Google Inc.
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
"""Timestamp handling routines."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import logging
import os.path
import tempfile
import time
import stat


def ReadTimestamp(filename):
  """Return a timestamp from a file.

  The timestamp file format is a single line, containing a string in the
  ISO-8601 format YYYY-MM-DDThh:mm:ssZ (i.e. UTC time).  We do not support
  all ISO-8601 formats for reasons of convenience in the code.

  Timestamps internal to nss_cache deliberately do not carry milliseconds.

  Args:
    filename:  A String naming the file to read from.

  Returns:
    A time.struct_time, or None if the timestamp file doesn't
    exist or has errors.
  """
  if not os.path.exists(filename):
    return None

  try:
    timestamp_file = open(filename, 'r')
    timestamp_string = timestamp_file.read().strip()
  except IOError as e:
    logging.warning('error opening timestamp file: %s', e)
    timestamp_string = None
  else:
    timestamp_file.close()

  logging.debug('read timestamp %s from file %r', timestamp_string, filename)

  if timestamp_string is not None:
    try:
      # Append UTC to force the timezone to parse the string in.
      timestamp = time.strptime(timestamp_string + ' UTC',
                                '%Y-%m-%dT%H:%M:%SZ %Z')
    except ValueError as e:
      logging.error('cannot parse timestamp file %r: %s', filename, e)
      timestamp = None
  else:
    timestamp = None

  logging.debug('Timestamp is: %r', timestamp)
  now = time.gmtime()
  logging.debug('      Now is: %r', now)
  if timestamp > now:
    logging.warning('timestamp %r (%r) from %r is in the future, now is %r',
                    timestamp_string, time.mktime(timestamp), filename,
                    time.mktime(now))
    if time.mktime(timestamp) - time.mktime(now) >= 60 * 60:
      logging.info('Resetting timestamp to now.')
      timestamp = now

  return timestamp


def WriteTimestamp(timestamp, filename):
  """Write a given timestamp out to a file, converting to the ISO-8601 format.

  We convert internal timestamp format (epoch) to ISO-8601 format, i.e.
  YYYY-MM-DDThh:mm:ssZ which is basically UTC time, then write it out to a
  file.

  Args:
    timestamp: A struct time.struct_time or time tuple.
    filename: A String naming the file to write to.

  Returns:
     A boolean indicating success of write.
  """
  # TODO(jaq): hack
  if timestamp is None:
    return True

  timestamp_dir = os.path.dirname(filename)

  (filedesc, temp_filename) = tempfile.mkstemp(
      prefix='nsscache-update-', dir=timestamp_dir)

  time_string = time.strftime('%Y-%m-%dT%H:%M:%SZ', timestamp)

  try:
    os.write(filedesc, b'%s\n' % time_string.encode())
    os.fsync(filedesc)
    os.close(filedesc)
  except OSError:
    os.unlink(temp_filename)
    logging.warning('writing timestamp failed!')
    return False

  os.chmod(temp_filename,
           stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
  os.rename(temp_filename, filename)
  logging.debug('wrote timestamp %s to file %r', time_string, filename)
  return True
