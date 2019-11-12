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
"""Lock management for nss_cache module."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import errno
import fcntl
import logging
import os
import re
import signal
import stat
import sys


# It would be interesting to subclass mutex, but we don't need the
# queueing functionality.
class PidFile(object):
    """Interprocess locking via fcntl and a pid file.

    We use fcntl to manage locks between processes, as the kernel will
    release the lock when the process dies no matter what, so it works
    quite well.

    We store the pid in the file we use so that 3rd party programs,
    primarily small shell scripts, can easily see who has (or had) the
    lock via the stored pid.  We don't clean the pid up on exit
    because most programs will have to check if the program is still
    running anyways.

    We can forcibly take a lock by deleting the file and re-creating
    it.  When we do so, we check if the pid in the file is running and
    send it a SIGTERM *if and only if* it has a commandline with
    'nsscache' somewhere in the string.

    We try to kill the process to avoid it completing after us and
    overwriting any changes.  We check for 'nsscache' to avoid killing
    a re-used PID.  We are not paranoid, we send the SIGTERM and
    assume it dies.

    WARNING:  Use over NFS with *extreme* caution.  fcntl locking can
    be configured to work, but your mileage can and will vary.
    """

    STATE_DIR = '/var/run'
    PROC_DIR = '/proc'
    PROG_NAME = 'nsscache'

    def __init__(self, filename=None, pid=None):
        """Initialize the PidFile object."""
        self._locked = False
        self._file = None
        self.filename = filename
        self.pid = pid

        # Setup logging.
        self.log = logging.getLogger(__name__)

        if self.pid is None:
            self.pid = os.getpid()

        # If no filename is given, default to the basename we were
        # invoked with.
        if self.filename is None:
            basename = os.path.basename(sys.argv[0])
            if not basename:
                # We were invoked from a python interpreter with
                # bad arguments, or otherwise loaded without sys.argv
                # being set.
                self.log.critical('Can not determine lock file name!')
                raise TypeError('missing required argument: filename')
            self.filename = '%s/%s' % (self.STATE_DIR, basename)

        self.log.debug('using %s for lock file', self.filename)

    def __del__(self):
        """Release our pid file on object destruction."""
        if self.Locked():
            self.Unlock()

    def _Open(self, filename=None):
        """Create our file and store the file object."""
        if filename is None:
            filename = self.filename

        # We want to create this file if it doesn't exist, but 'w'
        # will truncate, so we use 'a+' and seek.  We don't truncate
        # the file because we haven't tested if it is locked by
        # another program yet, this is done later by fcntl module.
        self._file = open(filename, 'a+')
        self._file.seek(0)

        # Set permissions.
        os.chmod(filename,
                 stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)

    def Lock(self, force=False):
        """Open our pid file and lock it.

        Args:
          force: optional flag to override the lock.
        Returns:
          True if successful
          False otherwise
        """
        if self._file is None:
            # Open the file and trap permission denied.
            try:
                self._Open()
            except IOError as e:
                if e.errno == errno.EACCES:
                    self.log.warning('Permission denied opening lock file: %s',
                                     self.filename)
                    return False
                raise

        # Try to get the lock.
        return_val = False
        try:
            fcntl.lockf(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return_val = True
        except IOError as e:
            if e.errno in [errno.EACCES, errno.EAGAIN]:
                # Catch the error raised when the file is locked.
                if not force:
                    self.log.debug('%s already locked!', self.filename)
                    return False
            else:
                # Otherwise re-raise it.
                raise

        # Check if we need to forcibly re-try the lock.
        if not return_val and force:
            self.log.debug('retrying lock.')
            # Try to kill the process with the lock.
            self.SendTerm()
            # Clear the lock.
            self.ClearLock()
            # Try to lock only once more -- else we might recurse forever!
            return self.Lock(force=False)

        # Store the pid.
        self._file.truncate()
        self._file.write('%s\n' % self.pid)
        self._file.flush()

        self.log.debug('successfully locked %s', self.filename)

        self._locked = True
        return return_val

    def SendTerm(self):
        """Send a SIGTERM to the process in the pidfile.

        We only send a SIGTERM if such a process exists and it has a
        commandline including the string 'nsscache'.
        """
        # Grab the pid
        pid_content = self._file.read()
        try:
            pid = int(pid_content.strip())
        except (AttributeError, ValueError) as e:
            self.log.warning(
                'Not sending TERM, could not parse pid file content: %r',
                pid_content)
            return

        self.log.debug('retrieved pid %d' % pid)

        # Reset the filehandle just in case.
        self._file.seek(0)

        # By reading cmdline out of /proc we establish:
        # a)  if a process with that pid exists.
        # b)  what the command line is, to see if it included 'nsscache'.
        proc_path = '%s/%i/cmdline' % (self.PROC_DIR, pid)
        try:
            proc_file = open(proc_path, 'r')
        except IOError as e:
            if e.errno == errno.ENOENT:
                self.log.debug('process does not exist, skipping signal.')
                return
            raise

        cmdline = proc_file.read()
        proc_file.close()

        # See if it matches our program name regex.
        cmd_re = re.compile(r'.*%s' % self.PROG_NAME)
        if not cmd_re.match(cmdline):
            self.log.debug('process is running but not %s, skipping signal',
                           self.PROG_NAME)
            return

        # Send a SIGTERM.
        self.log.debug('sending SIGTERM to %i', pid)
        os.kill(pid, signal.SIGTERM)

        # We are not paranoid about success, so we're done!
        return

    def ClearLock(self):
        """Delete the pid file to remove any locks on it."""
        self.log.debug('clearing old pid file: %s', self.filename)
        self._file.close()
        self._file = None
        os.remove(self.filename)

    def Locked(self):
        """Return True if locked, False if not."""
        return self._locked

    def Unlock(self):
        """Release our pid file."""
        fcntl.lockf(self._file, fcntl.LOCK_UN)
        self._locked = False
