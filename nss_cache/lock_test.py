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
from mox3 import mox

from nss_cache import lock


class TestPidFile(mox.MoxTestBase):
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
    self.mox.StubOutWithMock(yes, 'Locked')
    self.mox.StubOutWithMock(yes, 'Unlock')
    yes.Locked().AndReturn(True)
    yes.Unlock()

    no = lock.PidFile()
    self.mox.StubOutWithMock(no, 'Locked')
    no.Locked().AndReturn(False)

    self.mox.ReplayAll()

    # test the case where locked returns True.
    yes.__del__()

    # test the case where self.Locked() returns False.
    no.__del__()

  def testOpenCreatesAppropriateFileWithPerms(self):
    locker = lock.PidFile(filename=self.filename)
    locker._Open()

    self.assertTrue(os.path.exists(self.filename))

    file_mode = os.stat(self.filename)[stat.ST_MODE]
    correct_mode = (stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP
                    | stat.S_IROTH)
    self.assertEqual(file_mode, correct_mode)

    os.remove(self.filename)

  def testLockCreatesPidfiles(self):
    locker = lock.PidFile()
    self.mox.StubOutWithMock(locker, '_Open')
    locker._Open().AndRaise(NotImplementedError)
    self.mox.ReplayAll()

    self.assertRaises(NotImplementedError, locker.Lock)

    # Note that testing when self._file is not None is covered below.

  def testLockLocksWithFcntl(self):
    locker = lock.PidFile(pid='PID')

    self.mox.StubOutWithMock(locker, '_file', use_mock_anything=True)
    locker._file.truncate()
    locker._file.write('PID\n')
    locker._file.flush()

    self.mox.StubOutWithMock(fcntl, 'lockf')
    fcntl.lockf(locker._file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    self.mox.ReplayAll()

    locker.Lock()
    self.assertTrue(locker._locked)

    # force __del__ to skip Unlock()
    locker._locked = False

  def testLockStoresPid(self):
    locker = lock.PidFile(filename=self.filename, pid='PID')
    locker.Lock()

    pid_file = open(self.filename, 'r')

    self.assertEqual(pid_file.read(), 'PID\n')

    os.remove(self.filename)

  def testLockTrapsPermissionDeniedOnly(self):
    locker = lock.PidFile()
    self.mox.StubOutWithMock(locker, '_Open')
    locker._Open().AndRaise(IOError(errno.EACCES, ''))
    locker._Open().AndRaise(IOError(errno.EIO, ''))
    self.mox.ReplayAll()

    self.assertEqual(False, locker.Lock())
    self.assertRaises(IOError, locker.Lock)

  def testForceLockTerminatesAndClearsLock(self):
    locker = lock.PidFile(pid='PID')
    self.mox.StubOutWithMock(locker, 'SendTerm')
    locker.SendTerm()
    self.mox.StubOutWithMock(locker, 'ClearLock')
    locker.ClearLock()
    self.mox.StubOutWithMock(locker, '_file')
    self.mox.StubOutWithMock(fcntl, 'lockf')
    fcntl.lockf(locker._file,
                fcntl.LOCK_EX | fcntl.LOCK_NB).AndRaise(
                    IOError(errno.EAGAIN, ''))
    fcntl.lockf(locker._file,
                fcntl.LOCK_EX | fcntl.LOCK_NB).AndRaise(
                    IOError(errno.EAGAIN, ''))
    self.mox.ReplayAll()

    # This is a little weird due to recursion.
    # The first time through lockf throws an error and we retry the lock.
    # The 2nd time through we should fail, because lockf will still throw
    # an error, so we expect False back and the above mock objects
    # invoked.
    self.assertFalse(locker.Lock(force=True))

  def testSendTermMatchesCommandAndSendsTerm(self):
    locker = lock.PidFile()
    self.mox.StubOutWithMock(locker, '_file', use_mock_anything=True)
    locker._file.read().AndReturn('1234')
    locker._file.seek(0)

    # Mock used in place of an re.compile() pattern -- expects the contents
    # of our proc_file!
    mock_re = self.mox.CreateMockAnything()
    mock_re.match('TEST').AndReturn(True)
    self.mox.StubOutWithMock(re, 'compile')
    re.compile('.*nsscache').AndReturn(mock_re)

    self.mox.StubOutWithMock(os, 'kill')
    os.kill(1234, signal.SIGTERM)

    # Create a file we open() in SendTerm().
    proc_dir = '%s/1234' % self.workdir
    proc_filename = '%s/cmdline' % proc_dir
    os.mkdir(proc_dir)
    proc_file = open(proc_filename, 'w')
    proc_file.write('TEST')
    proc_file.flush()
    proc_file.close()
    locker.PROC_DIR = self.workdir

    self.mox.ReplayAll()

    locker.SendTerm()

    os.remove(proc_filename)
    os.rmdir(proc_dir)

  def testSendTermNoPid(self):
    locker = lock.PidFile()
    self.mox.StubOutWithMock(locker, '_file', use_mock_anything=True)
    locker._file.read().AndReturn('\n')
    locker.PROC = self.workdir

    self.mox.ReplayAll()

    locker.SendTerm()

  def testSendTermNonePid(self):
    locker = lock.PidFile()
    self.mox.StubOutWithMock(locker, '_file', use_mock_anything=True)
    locker._file.read().AndReturn(None)
    locker.PROC = self.workdir

    self.mox.ReplayAll()

    locker.SendTerm()

  def testSendTermTrapsENOENT(self):
    locker = lock.PidFile()
    self.mox.StubOutWithMock(locker, '_file', use_mock_anything=True)
    locker._file.read().AndReturn('1234\n')
    locker._file.seek(0)
    locker.PROC = self.workdir

    self.mox.StubOutWithMock(builtins, 'open', use_mock_anything=True)
    builtins.open(mox.IgnoreArg(), 'r').AndRaise(IOError(errno.ENOENT, ''))

    self.mox.ReplayAll()

    # self.workdir/1234/cmdline should not exist :)
    self.assertFalse(os.path.exists('%s/1234/cmdline' % self.workdir))

    locker.SendTerm()

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
    self.mox.StubOutWithMock(fcntl, 'lockf')
    fcntl.lockf('FILE_OBJECT', fcntl.LOCK_UN)

    self.mox.ReplayAll()
    locker.Unlock()

    self.assertFalse(locker._locked)


if __name__ == '__main__':
  unittest.main()
