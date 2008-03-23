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

"""Distutils setup for nsscache tool and nss_cache package."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

import distutils.core

import nss_cache

distutils.core.setup(name='nsscache',
                     version=nss_cache.__version__,
                     author='Jamie Wilkinson',
                     author_email='jaq@google.com',
                     url='http://code.google.com/p/nsscache/',
                     description='nsscache tool and library',
                     license='GPL',
                     classifiers=['Development Status :: 4 - Beta',
                                  'Environment :: Console',
                                  'Indended Audience :: System Administrators',
                                  'License :: OSI Approved :: GPL',
                                  'Operating System :: POSIX',
                                  'Programming Language :: Python',
                                  'Topic :: System'],
                     packages=['nss_cache',
                               'nss_cache.caches',
                               'nss_cache.maps',
                               'nss_cache.sources'],
                     scripts=['nsscache',
                              'runtests.py'],
                     data_files=[('/etc', ['nsscache.conf'])])
