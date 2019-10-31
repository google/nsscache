#!/usr/bin/python
# vim: ts=4 sts=4 et:
# pylint: disable=invalid-name,line-too-long
"""OpenSSH AuthorizedKeysCommand: NSSCache input Copyright 2016 Gentoo Foundation Written by Robin H.

Johnson <robbat2@gentoo.org> Distributed under the BSD-3 license.
This script returns one or more authorized keys for use by SSH, by extracting
them from a local cache file /etc/sshkey.cache.

Two variants are supported, based on the existing nsscache code:
Format 1:
 username:key1
 username:key2
Format 2:
 username:['key1', 'key2']

Ensure this script is mentioned in the sshd_config like so:
AuthorizedKeysCommand /path/to/nsscache/authorized-keys-command.py

If you have sufficently new OpenSSH, you can also narrow down the search:
AuthorizedKeysCommand /path/to/nsscache/authorized-keys-command.py
--username="%u" --key-type="%t" --key-fingerprint="%f" --key-blob="%k"

Future improvements:
- Validate SSH keys more strictly:
    - validate options string
    - validate X509 cert strings
- Implement command line options to:
    - filter keys based on options better (beyond regex)
    - filter keys based on comments better (beyond regex)
    - filter X509 keys based on DN/subject
    - support multiple inputs for conditions
    - add an advanced conditional filter language
"""

from ast import literal_eval
import sys
import errno
import argparse
import re
import base64
import hashlib
import copy
import textwrap

DEFAULT_SSHKEY_CACHE = '/etc/sshkey.cache'

REGEX_BASE64 = r'(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?'
# All of the SSH blobs starts with 3 null bytes , which encode to 'AAAA' in base64
REGEX_BASE64_START3NULL = r'AAAA' + REGEX_BASE64
# This regex needs a lot of work
KEYTYPE_REGEX_STRICT = r'\b(?:ssh-(?:rsa|dss|ed25519)|ecdsa-sha2-nistp(?:256|384|521))\b'
# Docs:
# http://www.iana.org/assignments/ssh-parameters/ssh-parameters.xhtml#ssh-parameters-19
# RFC6187, etc
KEYTYPE_REGEX_LAZY_NOX509 = r'\b(?:(?:spki|pgp|x509|x509v3)-)?(?:(?:ssh|sign)-(?:rsa|dss|ed25519)|ecdsa-[0-9a-z-]+|rsa2048-sha256)(?:-cert-v01@openssh\.com|\@ssh\.com)?\b'
KEYTYPE_REGEX_LAZY_X509 = r'\bx509(?:v3)?-(?:(?:ssh|sign)-(?:rsa|dss|ed25519)|ecdsa-[0-9a-z-]+|rsa2048-sha256)(?:-cert-v01@openssh\.com|\@ssh\.com)?\b'
X509_WORDDN = r'(?:(?i)(?:Distinguished[ _-]?Name|DN|Subject)[=:]?)'  # case insensitive!
KEY_REGEX = r'(.*)\s*(?:(' + KEYTYPE_REGEX_LAZY_NOX509 + r')\s+(' + REGEX_BASE64_START3NULL + r')\s*(.*)|(' + KEYTYPE_REGEX_LAZY_X509 + r')\s+(' + X509_WORDDN + '.*))'

# Group 1: options
# Branch 1:
#  Group 2: keytype (any, including x509)
#  Group 3: key blob (non-x509), always starts with AAAA (3 nulls in base64), no whitespace!
#  Group 4: comment (non-x509)
# Branch 2:
#  Group 5: keytype (x509)
#  Group 6: x509 WORDDN followed by x509-specific blob or DN, including whitespace
#
# If the keytype is x509v3-*, then the data block can actually be a certificate
# XOR a base64 block.
# The cert specifier is "DN:/OU=.../SN=.../C=.." etc. By implication, this
# EXCLUDEs the use of an comments, as you CANNOT detect when the DN ends.


def warning(*objs):
  """ Helper function for output to stderr. """
  print('WARNING: ', *objs, file=sys.stderr)


def parse_key(full_key_line):
  """
    Explode an authorized_keys line including options into the various parts.
    """
  #print(KEY_REGEX)
  m = re.match(KEY_REGEX, full_key_line)
  if m is None:
    warning('Failed to match', full_key_line)
    return (None, None, None, None)
  options = m.group(1)
  key_type = m.group(2)
  blob = m.group(3)
  comment = m.group(4)
  if m.group(5) is not None:
    key_type = m.group(5)
    blob = m.group(6)
    comment = None
  return (options, key_type, blob, comment)


def fingerprint_key(keyblob, fingerprint_format='SHA256'):
  """
    Generate SSH key fingerprints, using the requested format.
    """
  # Don't try to fingerprint x509 blobs
  if keyblob is None or not keyblob.startswith('AAAA'):
    return None
  try:
    binary_blob = base64.b64decode(keyblob)
  except TypeError as e:
    warning(e, keyblob)
    return None
  if fingerprint_format == 'MD5':
    raw = hashlib.md5(binary_blob).digest()
    return 'MD5:' + ':'.join('{:02x}'.format(ord(c)) for c in raw)
  elif fingerprint_format in ['SHA256', 'SHA512', 'SHA1']:
    h = hashlib.new(fingerprint_format)
    h.update(binary_blob)
    raw = h.digest()
    return fingerprint_format + ':' + base64.b64encode(raw).rstrip('=')
  return None


def detect_fingerprint_format(fpr):
  """
    Given a fingerprint, try to detect what fingerprint format is used.
    """
  if fpr is None:
    return None
  for prefix in ['SHA256', 'SHA512', 'SHA1', 'MD5']:
    if fpr.startswith(prefix + ':'):
      return prefix
  if re.match(r'^(MD5:)?([0-9a-f]{2}:)+[0-9a-f]{2}$', fpr) is not None:
    return 'MD5'
  # Cannot detect the format
  return None


def validate_key(candidate_key, conditions, strict=False):
  # pylint: disable=invalid-name,line-too-long,too-many-locals
  """
    Validate a potential authorized_key line against multiple conditions
    """
  # Explode the key
  (candidate_key_options, \
          candidate_key_type, \
          candidate_key_blob, \
          candidate_key_comment) = parse_key(candidate_key)

  # Set up our conditions with their defaults
  key_type = conditions.get('key_type', None)
  key_blob = conditions.get('key_blob', None)
  key_fingerprint = conditions.get('key_fingerprint', None)
  key_options_re = conditions.get('key_options_re', None)
  key_comment_re = conditions.get('key_comment_re', None)

  # Try to detect the fingerprint format
  fingerprint_format = detect_fingerprint_format(key_fingerprint)
  # Force MD5 prefix on old fingerprints
  if fingerprint_format is 'MD5':
    if not key_fingerprint.startswith('MD5:'):
      key_fingerprint = 'MD5:' + key_fingerprint
  # The OpenSSH base64 fingerprints drops the trailing padding, ensure we do
  # the same on provided input
  if fingerprint_format is not 'MD5' \
          and key_fingerprint is not None:
    key_fingerprint = key_fingerprint.rstrip('=')
  # Build the fingerprint for the candidate key
  # (the func does the padding strip as well)
  candidate_key_fingerprint = \
          fingerprint_key(candidate_key_blob,
                          fingerprint_format)

  match = True
  strict_pass = False
  if key_type is not None and \
          candidate_key_type is not None:
    strict_pass = True
    match = match and \
            (candidate_key_type == key_type)
  if key_fingerprint is not None and \
          candidate_key_fingerprint is not None:
    strict_pass = True
    match = match and \
            (candidate_key_fingerprint == key_fingerprint)
  if key_blob is not None and \
          candidate_key_blob is not None:
    strict_pass = True
    match = match and \
            (candidate_key_blob == key_blob)
  if key_comment_re is not None and \
          candidate_key_comment is not None:
    strict_pass = True
    match = match and \
            key_comment_re.search(candidate_key_comment) is not None
  if key_options_re is not None:
    strict_pass = True
    match = match and \
            key_options_re.search(candidate_key_options) is not None
  if strict:
    return match and strict_pass
  return match


PROG_EPILOG = textwrap.dedent("""\
Strict match will require that at least one condition matched.
Conditions marked with X may not work correctly with X509 authorized_keys lines.
""")
PROG_DESC = 'OpenSSH AuthorizedKeysCommand to read from cached keys file'

if __name__ == '__main__':
  parser = argparse.ArgumentParser(
      prog='AUTHKEYCMD',
      description=PROG_DESC,
      epilog=PROG_EPILOG,
      formatter_class=argparse.RawDescriptionHelpFormatter,
      add_help=False)
  # Arguments
  group = parser.add_argument_group('Mandatory arguments')
  group.add_argument(
      'username', metavar='USERNAME', nargs='?', type=str, help='Username')
  group.add_argument(
      '--username',
      metavar='USERNAME',
      dest='username_opt',
      type=str,
      help='Username (alternative form)')
  # Conditions
  group = parser.add_argument_group('Match Conditions (optional)')
  group.add_argument(
      '--key-type', metavar='KEY-TYPE', type=str, help='Key type')
  group.add_argument(
      '--key-fingerprint',
      '--key-fp',
      metavar='KEY-FP',
      type=str,
      help='Key fingerprint X')
  group.add_argument(
      '--key-blob',
      metavar='KEY-BLOB',
      type=str,
      help='Key blob (Base64 section) X')
  group.add_argument(
      '--key-comment-re',
      metavar='REGEX',
      type=str,
      help='Regex to match on comments X')
  group.add_argument(
      '--key-options-re',
      metavar='REGEX',
      type=str,
      help='Regex to match on options')
  # Setup parameters:
  group = parser.add_argument_group('Misc settings')
  group.add_argument(
      '--cache-file',
      metavar='FILENAME',
      default=DEFAULT_SSHKEY_CACHE,
      type=argparse.FileType('r'),
      help='Cache file [%s]' % (DEFAULT_SSHKEY_CACHE,),
  )
  group.add_argument(
      '--strict',
      action='store_true',
      default=False,
      help='Strict match required')
  group.add_argument('--help', action='help', default=False, help='This help')
  # Fire it all
  args = parser.parse_args()

  # Handle that we support both variants
  lst = [args.username, args.username_opt]
  cnt = lst.count(None)
  if cnt == 2:
    parser.error('Username was not specified')
  elif cnt == 0:
    parser.error('Username must be specified either as an option XOR argument.')
  else:
    args.username = [x for x in lst if x is not None][0]

  # Strict makes no sense without at least one condition being specified
  if args.strict:
    d = copy.copy(vars(args))
    for k in ['cache_file', 'strict', 'username']:
      d.pop(k, None)
    if not any(v is not None for v in list(d.values())):
      parser.error('At least one condition must be specified with --strict')

  if args.key_comment_re is not None:
    args.key_comment_re = re.compile(args.key_comment_re)
  if args.key_options_re is not None:
    args.key_options_re = re.compile(args.key_options_re)

  try:
    key_conditions = {
        'key_options_re': args.key_options_re,
        'key_type': args.key_type,
        'key_blob': args.key_blob,
        'key_fingerprint': args.key_fingerprint,
        'key_comment_re': args.key_comment_re,
    }
    with args.cache_file as f:
      for line in f:
        (username, key) = line.split(':', 1)
        if username != args.username:
          continue
        key = key.strip()
        if key.startswith('[') and key.endswith(']'):
          # Python array, but handle it safely!
          keys = [i.strip() for i in literal_eval(key)]
        else:
          # Raw key
          keys = [key.strip()]
        for k in keys:
          if validate_key(
              candidate_key=k, conditions=key_conditions, strict=args.strict):
            print(k)
  except IOError as err:
    if err.errno in [errno.EPERM, errno.ENOENT]:
      pass
    else:
      raise err
