nsscache - Asynchronously synchronise local NSS databases with remote directory services
========================================================================================

![ci](https://github.com/google/nsscache/workflows/CI/badge.svg)
[![codecov](https://codecov.io/gh/google/nsscache/branch/master/graph/badge.svg)](https://codecov.io/gh/google/nsscache)

*nsscache* is a commandline tool and Python library that synchronises a local NSS cache from a remote directory service, such as LDAP.

As soon as you have more than one machine in your network, you want to share usernames between those systems. Linux administrators have been brought up on the convention of LDAP or NIS as a directory service, and `/etc/nsswitch.conf`, `nss_ldap.so`, and `nscd` to manage their nameservice lookups.

Even small networks will have experienced intermittent name lookup failures, such as a mail receiver sometimes returning "User not found" on a mailbox destination because of a slow socket over a congested network, or erratic cache behaviour by `nscd`. To combat this problem, we have separated the network from the NSS lookup codepath, by using an asynchronous cron job and a glorified script, to improve the speed and reliability of NSS lookups. We presented a talk at [linux.conf.au 2008](http://lca2008.linux.org.au/) ([PDF slides](http://mirror.linux.org.au/linux.conf.au/2008/slides/056-posix-jaq-v.pdf)) on the problems in NSS and the requirements for a solution.

Here, we present to you this glorified script, which is just a little more extensible than

    ldapsearch | awk > /etc/passwd
    
Read the [Google Code blog announcement](http://www.anchor.com.au/blog/2009/02/nsscache-and-ldap-reliability/) for nsscache, or more about the [motivation behind this tool](https://github.com/google/nsscache/wiki/MotivationBehindNssCache).

Here's a [testimonial from Anchor Systems](http://www.anchor.com.au/blog/2009/02/nsscache-and-ldap-reliability/) on their deployment of nsscache.


Pair *nsscache* with https://github.com/google/libnss-cache to integrate the local cache with your name service switch.

---

Mailing list: https://groups.google.com/forum/#!forum/nsscache-discuss

Issue history is at https://code.google.com/p/nsscache/issues/list

---

# Contributions

Please format your code with https://github.com/google/yapf (installable as `pip install yapf` or the `yapf3` package on Debian systems) before sending pull requests.
