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

"""Unit tests for nss_cache/lock.py."""

__author__ = 'vasilios@google.com (Vasilios Hoffman)'

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

from nss_cache import lock

import pmock


class TestPidFile(pmock.MockTestCase):
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
    """Create a temporary working dir for unit tests."""
    self.workdir = tempfile.mkdtemp()
    self.filename = '%s/%s' % (self.workdir, 'pidfile')

  def tearDown(self):
    shutil.rmtree(self.workdir)

  def testInit(self):
    """We can create a pidfile object."""
    locker = lock.PidFile()

    pid = os.getpid()
    filename = os.path.basename(sys.argv[0])
    filename = '%s/%s' % (locker.STATE_DIR, filename)

    self.assertTrue(isinstance(locker, lock.PidFile))
    self.assertEquals(locker.pid, pid)
    self.assertEquals(locker.filename, filename)
    self.assertEquals(locker._locked, False)
    self.assertEquals(locker._file, None)

    # also check the case where argv[0] is empty (interactively loaded)
    full_path = sys.argv[0]
    sys.argv[0] = ''
    self.assertRaises(TypeError, lock.PidFile)
    sys.argv[0] = full_path

  def testInitArgs(self):
    """We handle arguments properly in init."""
    filename = 'TEST'
    pid = 10
    locker = lock.PidFile(filename=filename, pid=pid)
    self.assertEquals(locker.filename, filename)
    self.assertEquals(locker.pid, pid)

  def testDestructor(self):
    """We unlock ourself in the destructor when appropriate."""
    yes = self.mock()
    yes.expects(pmock.once()).Locked().will(pmock.return_value(True))
    yes.expects(pmock.once()).Unlock()

    no = self.mock()
    no.expects(pmock.once()).Locked().will(pmock.return_value(False))
    no.expects(pmock.never()).Unlock()

    lock_yes = lock.PidFile()
    lock_no = lock.PidFile()

    # store methods for later
    yes_locked = lock_yes.Locked
    no_locked = lock_no.Locked

    # test the case where locked returns True.
    lock_yes.Locked = yes.Locked
    lock_yes.Unlock = yes.Unlock
    lock_yes.__del__()

    # test the case where self.locked() returns False.
    lock_no.Locked = no.Locked
    lock_no.Unlock = no.Unlock
    lock_no.__del__()

    # restore methods for actual object destruction.
    lock_yes.Locked = yes_locked
    lock_no.Locked = no_locked

  def testOpen(self):
    """Open creates the appropriate file with the correct permissions."""
    locker = lock.PidFile(filename=self.filename)
    locker._Open()

    self.assertTrue(os.path.exists(self.filename))

    file_mode = os.stat(self.filename)[stat.ST_MODE]
    correct_mode = stat.S_IFREG | stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
    self.assertEquals(file_mode, correct_mode)

    os.remove(self.filename)

  def testLockCreates(self):
    """We create pidfiles when needed."""
    open_mock = self.mock()
    open_mock\
               .expects(pmock.once())\
               ._Open()\
               .will(pmock.raise_exception(NotImplementedError))

    locker = lock.PidFile()
    locker._Open = open_mock._Open

    self.assertRaises(NotImplementedError, locker.Lock)

    # Note that testing when self._file is not None is covered below.

  def testLockLocks(self):
    """Lock invokes fcntl appropriately."""

    def FakeLockf(obj, flags):
      """Stub routine for testing."""
      self.assertEquals(obj, mock_file)
      self.assertEquals(flags, fcntl.LOCK_EX | fcntl.LOCK_NB)

    locker = lock.PidFile(pid='PID')

    original_lockf = fcntl.lockf
    fcntl.lockf = FakeLockf

    mock_file = self.mock()
    mock_file.expects(pmock.once()).truncate()
    mock_file.expects(pmock.once()).write(pmock.eq('PID\n'))
    mock_file.expects(pmock.once()).flush()

    locker._file = mock_file
    locker.Lock()
    self.assertTrue(locker._locked)

    fcntl.lockf = original_lockf

    # force __del__ to skip Unlock()
    locker._locked = False

  def testLockPid(self):
    """Lock stores the pid in the file."""
    locker = lock.PidFile(filename=self.filename, pid='PID')
    locker.Lock()

    pid_file = open(self.filename, 'r')

    self.assertEquals(pid_file.read(), 'PID\n')

    os.remove(self.filename)

  def testLockTrapsPermissionDeniedOnly(self):
    """We trap and report permission denied locking errors, raise others."""
    mock_open = self.mock()
    mock_open\
               .expects(pmock.once())\
               ._Open()\
               .will(pmock.raise_exception(IOError(errno.EACCES, '')))\
               .id('first')
    mock_open\
               .expects(pmock.once())\
               ._Open()\
               .after('first')\
               .will(pmock.raise_exception(IOError(errno.EIO, '')))\

    locker = lock.PidFile()
    locker._Open = mock_open._Open

    self.assertEquals(False, locker.Lock())
    self.assertRaises(IOError, locker.Lock)

  def testForceLock(self):
    """Passing force=true invokes SendTerm() and ClearLock(), then recurses."""

    def FakeLockf(obj, flags):
      """Stub routine for testing."""
      self.assertEquals(obj, 'FILE')
      self.assertEquals(flags, fcntl.LOCK_EX | fcntl.LOCK_NB)
      raise IOError(fcntl.F_GETSIG, '')

    locker = lock.PidFile(pid='PID')

    mock_kill = self.mock()
    mock_kill\
               .expects(pmock.once())\
               .SendTerm()

    mock_clear_lock = self.mock()
    mock_clear_lock\
                     .expects(pmock.once())\
                     .ClearLock()

    locker = lock.PidFile()
    locker._file = 'FILE'
    locker.SendTerm = mock_kill.SendTerm
    locker.ClearLock = mock_clear_lock.ClearLock

    original_lockf = fcntl.lockf
    fcntl.lockf = FakeLockf

    # This is a little weird due to recursion.
    # The first time through lockf throws an error and we retry the lock.
    # The 2nd time through we should fail, because lockf will still throw
    # an error, so we expect False back and the above mock objects
    # invoked.
    self.assertFalse(locker.Lock(force=True))

    fcntl.lockf = original_lockf

  def testSendTermMatchesCommandAndSendsTerm(self):
    """SendTerm() opens a proc file and does a regex, invokes os.kill()."""
    # File mock used to return the pid.
    mock_file = self.mock()
    mock_file\
               .expects(pmock.once())\
               .read()\
               .will(pmock.return_value('1234'))
    mock_file\
               .expects(pmock.once())\
               .seek(pmock.eq(0))

    # Mock used in place of an re.compile() pattern -- expects the contents
    # of our proc_file!
    #
    # N.B.  "match" is defined already in pmock.InvocationMockerBuilder :-/
    mock_match = self.mock()
    mock_match\
                .expects(pmock.once())\
                .method('match')\
                .pwith(pmock.eq('TEST'))\
                .will(pmock.return_value(True))

    # Replace re.compile() to return our mock pattern.
    mock_compile = self.mock()
    mock_compile\
                  .expects(pmock.once())\
                  .compile(pmock.eq('.*nsscache'))\
                  .will(pmock.return_value(mock_match))

    # Replace os.kill() with a mock.
    mock_kill = self.mock()
    mock_kill\
               .expects(pmock.once())\
               .kill(pmock.eq(1234), pmock.eq(signal.SIGTERM))

    # Create a file we open() in SendTerm().
    proc_dir = '%s/1234' % self.workdir
    proc_filename = '%s/cmdline' % proc_dir
    os.mkdir(proc_dir)
    proc_file = open(proc_filename, 'w')
    proc_file.write('TEST')
    proc_file.flush()
    proc_file.close()

    # Initialize our locker and override callables with our mocks.
    locker = lock.PidFile()
    locker._file = mock_file
    locker.PROC_DIR = self.workdir
    orig_compile = re.compile
    orig_kill = os.kill
    re.compile = mock_compile.compile
    os.kill = mock_kill.kill

    # Do it!
    locker.SendTerm()

    # Clean up.
    re.compile = orig_compile
    os.kill = orig_kill
    os.remove(proc_filename)
    os.rmdir(proc_dir)

  def testSendTermTrapsENOENT(self):
    """SendTerm() traps a file not found error."""
    mock_file = self.mock()
    mock_file\
               .expects(pmock.once())\
               .read()\
               .will(pmock.return_value('1234\n'))
    mock_file\
               .expects(pmock.once())\
               .seek(pmock.eq(0))

    locker = lock.PidFile()
    locker._file = mock_file
    locker.PROC = self.workdir

    # self.workdir/1234/cmdline should not exist :)
    self.failIf(os.path.exists('%s/1234/cmdline' % self.workdir))

    # This should throw a IOError if we're not trapping it.
    # Testing that open() is actually called is handled above,
    # so if we never call open() another test will fail.
    # Thus it is not necessary (or easy) to test that here...
    locker.SendTerm()

  def testClearLock(self):
    """ClearLock removes the pid file."""
    # Create a pid file.
    pidfile = open(self.filename, 'w')
    pidfile.write('foo')
    pidfile.flush()

    locker = lock.PidFile(filename=self.filename)

    # Cheat instead of calling open.
    locker._file = pidfile

    locker.ClearLock()

    self.failIf(os.path.exists(self.filename))

  def testLocked(self):
    """Locked() returns True/False appropriately."""
    locker = lock.PidFile()

    locker._locked = True
    self.assertTrue(locker.Locked())

    locker._locked = False
    self.failIf(locker.Locked())

  def testUnlock(self):
    """Unlock releases the fcntl lock."""

    def FakeLockf(obj, flags):
      """Stub routine for testing."""
      self.assertEquals(obj, 'FILE_OBJECT')
      self.assertEquals(flags, fcntl.LOCK_UN)

    original_lockf = fcntl.lockf
    fcntl.lockf = FakeLockf

    locker = lock.PidFile()
    locker._file = 'FILE_OBJECT'
    locker.Unlock()

    self.failIf(locker._locked)

    fcntl.lockf = original_lockf


if __name__ == '__main__':
  unittest.main()
