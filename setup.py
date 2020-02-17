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
"""Distutils setup for nsscache tool and nss_cache package."""

__author__ = 'jaq@google.com (Jamie Wilkinson)'

from setuptools import setup, find_packages

import nss_cache

setup(
    name='nsscache',
    version=nss_cache.__version__,
    author='Jamie Wilkinson',
    author_email='jaq@google.com',
    url='https://github.com/google/nsscache',
    description='nsscache tool and library',
    license='GPL',
    long_description=
    """nsscache is a Python library and a commandline frontend to that library
that synchronises a local NSS cache against a remote directory service, such
as LDAP.""",
    classifiers=[
        'Development Status :: 4 - Beta', 'Environment :: Console',
        'Indended Audience :: System Administrators',
        'License :: OSI Approved :: GPL', 'Operating System :: POSIX',
        'Programming Language :: Python', 'Topic :: System'
    ],
    packages=[
        'nss_cache', 'nss_cache.caches', 'nss_cache.maps', 'nss_cache.util',
        'nss_cache.update', 'nss_cache.sources'
    ],
    scripts=['nsscache'],
    data_files=[('config', ['nsscache.conf'])],
    python_requires='~=3.4',
    setup_requires=['pytest-runner'],
    tests_require=['pytest', 'mox3', 'pytest-cov', 'python-coveralls'],
    extras_require={
        'bdb': ['bsddb3'],
        'ldap': ['python3-ldap', 'python-ldap'],
        'http': ['pycurl'],
        's3': ['boto3'],
        'consul': ['pycurl'],
    },
)
