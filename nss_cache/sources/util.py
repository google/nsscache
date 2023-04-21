"""Utility methods for source classes."""

import datetime


def FromTimestampToDateTime(ts):
    """Converts internal nss_cache timestamp to datetime object.

    Args:
      ts: number of seconds since epoch
    Returns:
      datetime object
    """
    return datetime.datetime.utcfromtimestamp(ts)


def FromDateTimeToTimestamp(datetime_obj):
    """Converts datetime object to internal nss_cache timestamp.

    Args:
      datetime object
    Returns:
      number of seconds since epoch
    """
    dt = datetime_obj.replace(tzinfo=None)
    return int((dt - datetime.datetime(1970, 1, 1)).total_seconds())
