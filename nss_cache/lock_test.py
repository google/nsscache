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
"""Unit tests for nss_cache/lock.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

import builtins
import errno
import fcntl
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import unittest
from unittest import mock

from nss_cache import lock


class TestPidFile(unittest.TestCase):
    """Unit tests for PidFile class in lock.py."""

    # Note that we do not test whether fcntl actually works as expected.
    # That is outside the scope of unit tests and I'm not going to fork
    # a child to test this, at least not now.
    #
    # Rest assured, it works as expected and fcntl throws an exception if
    # another process has the lock.
    #
    # We also do not test if os.kill works as expected :)

    def setUp(self):
        super(TestPidFile, self).setUp()
        self.workdir = tempfile.mkdtemp()
        self.filename = '%s/%s' % (self.workdir, 'pidfile')

    def tearDown(self):
        shutil.rmtree(self.workdir)
        super(TestPidFile, self).tearDown()

    def testInit(self):
        locker = lock.PidFile()

        pid = os.getpid()
        filename = os.path.basename(sys.argv[0])
        filename = '%s/%s' % (locker.STATE_DIR, filename)

        self.assertTrue(isinstance(locker, lock.PidFile))
        self.assertEqual(locker.pid, pid)
        self.assertEqual(locker.filename, filename)
        self.assertEqual(locker._locked, False)
        self.assertEqual(locker._file, None)

        # also check the case where argv[0] is empty (interactively loaded)
        full_path = sys.argv[0]
        sys.argv[0] = ''
        self.assertRaises(TypeError, lock.PidFile)
        sys.argv[0] = full_path

    def testHandleArgumentsProperly(self):
        filename = 'TEST'
        pid = 10
        locker = lock.PidFile(filename=filename, pid=pid)
        self.assertEqual(locker.filename, filename)
        self.assertEqual(locker.pid, pid)

    def testDestructorUnlocks(self):
        yes = lock.PidFile()
        with mock.patch.object(yes, 'Locked') as locked, mock.patch.object(
                yes, 'Unlock') as unlock:
            locked.return_value = True
            yes.__del__()
            # Destructor should unlock
            unlock.assert_called_once()

        no = lock.PidFile()
        with mock.patch.object(no, 'Locked') as locked, mock.patch.object(
                yes, 'Unlock') as unlock:
            locked.return_value = False
            no.__del__()
            # No unlock needed if already not locked.
            unlock.assert_not_called()

    def testOpenCreatesAppropriateFileWithPerms(self):
        locker = lock.PidFile(filename=self.filename)
        locker._Open()

        self.assertTrue(os.path.exists(self.filename))

        file_mode = os.stat(self.filename)[stat.ST_MODE]
        correct_mode = (stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR |
                        stat.S_IRGRP | stat.S_IROTH)
        self.assertEqual(file_mode, correct_mode)

        os.remove(self.filename)

    def testLockCreatesPidfiles(self):
        locker = lock.PidFile()
        with mock.patch.object(locker, '_Open') as open:
            open.side_effect = NotImplementedError()
            self.assertRaises(NotImplementedError, locker.Lock)

        # Note that testing when self._file is not None is covered below.

    @mock.patch('fcntl.lockf')
    def testLockLocksWithFcntl(self, lockf):
        locker = lock.PidFile(pid='PID')

        with mock.patch.object(locker, '_file') as f:
            locker.Lock()
            self.assertTrue(locker._locked)
            lockf.assert_called_once_with(f, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def testLockStoresPid(self):
        locker = lock.PidFile(filename=self.filename, pid='PID')
        locker.Lock()

        pid_file = open(self.filename, 'r')

        self.assertEqual(pid_file.read(), 'PID\n')

        pid_file.close()

        os.remove(self.filename)

    def testLockTrapsPermissionDeniedOnly(self):
        locker = lock.PidFile()
        with mock.patch.object(locker, '_Open') as open:
            open.side_effect = [
                IOError(errno.EACCES, ''),
                IOError(errno.EIO, '')
            ]

            self.assertEqual(False, locker.Lock())
            self.assertRaises(IOError, locker.Lock)

    def testForceLockTerminatesAndClearsLock(self):
        locker = lock.PidFile(pid='PID')
        with mock.patch.object(locker, 'SendTerm'), mock.patch.object(
                locker, 'ClearLock'), mock.patch.object(locker, '_file') as f:
            with mock.patch('fcntl.lockf') as lockf:
                # This is a little weird due to recursion.
                # The first time through lockf throws an error and we retry the lock.
                # The 2nd time through we should fail, because lockf will still throw
                # an error, so we expect False back and the above mock objects
                # invoked.
                lockf.side_effect = [
                    IOError(errno.EAGAIN, ''),
                    IOError(errno.EAGAIN, '')
                ]
                self.assertFalse(locker.Lock(force=True))
                lockf.assert_has_calls(
                    (mock.call(locker._file, fcntl.LOCK_EX | fcntl.LOCK_NB),
                     mock.call(locker._file, fcntl.LOCK_EX | fcntl.LOCK_NB)))

    def testSendTermMatchesCommandAndSendsTerm(self):
        locker = lock.PidFile()
        # Program mocks
        mock_re = mock.create_autospec(re.Pattern)
        mock_re.match.return_value = True
        with mock.patch('re.compile') as regexp, mock.patch(
                'os.kill') as kill, mock.patch.object(locker, '_file') as f:
            f.read.return_value = '1234'
            regexp.return_value = mock_re

            # Create a file we open() in SendTerm().
            proc_dir = '%s/1234' % self.workdir
            proc_filename = '%s/cmdline' % proc_dir
            os.mkdir(proc_dir)
            proc_file = open(proc_filename, 'w')
            proc_file.write('TEST')
            proc_file.flush()
            proc_file.close()
            locker.PROC_DIR = self.workdir

            # Actually exercise the mocks
            locker.SendTerm()

            # Assert the mocks
            regexp.assert_called_with(r'.*nsscache')
            kill.assert_called_once_with(1234, signal.SIGTERM)
            f.read.assert_called()
            f.seek.assert_called_with(0)
            os.remove(proc_filename)
            os.rmdir(proc_dir)

    def testSendTermNoPid(self):
        locker = lock.PidFile()
        with mock.patch.object(locker,
                               '_file') as f, mock.patch('os.kill') as kill:
            f.read.return_value = '\n'
            locker.PROC = self.workdir
            locker.SendTerm()
            f.read.assert_called()
            kill.assert_not_called()

    def testSendTermNonePid(self):
        locker = lock.PidFile()
        with mock.patch.object(locker,
                               '_file') as f, mock.patch('os.kill') as kill:
            f.read.return_value = None
            locker.PROC = self.workdir
            locker.SendTerm()
            f.read.assert_called()
            kill.assert_not_called()

    def testSendTermTrapsENOENT(self):
        locker = lock.PidFile()
        with mock.patch.object(locker, '_file') as f, mock.patch(
                'os.kill') as kill, mock.patch('builtins.open') as mock_open:
            f.read.return_value = '1234\n'
            mock_open.side_effect = IOError(errno.ENOENT, '')
            # self.workdir/1234/cmdline should not exist :)
            self.assertFalse(os.path.exists('%s/1234/cmdline' % self.workdir))
            locker.PROC = self.workdir
            locker.SendTerm()
            f.read.assert_called()
            f.seek.assert_called_with(0)

    def testClearLockRemovesPidFile(self):
        # Create a pid file.
        pidfile = open(self.filename, 'w')
        pidfile.write('foo')
        pidfile.flush()

        locker = lock.PidFile(filename=self.filename)

        # Cheat instead of calling open.
        locker._file = pidfile

        locker.ClearLock()

        self.assertFalse(os.path.exists(self.filename))

    def testLockedPredicate(self):
        locker = lock.PidFile()

        locker._locked = True
        self.assertTrue(locker.Locked())

        locker._locked = False
        self.assertFalse(locker.Locked())

    def testUnlockReleasesFcntlLock(self):
        locker = lock.PidFile()
        locker._file = 'FILE_OBJECT'
        with mock.patch('fcntl.lockf') as lockf:
            locker.Unlock()
            self.assertFalse(locker._locked)
            lockf.assert_called_once_with('FILE_OBJECT', fcntl.LOCK_UN)


if __name__ == '__main__':
    unittest.main()
