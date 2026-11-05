"""Inspect uploaded attachments."""
import cgi
import imghdr


def content_type(header):
    value, params = cgi.parse_header(header)
    return value, params.get("charset", "utf-8")


def is_image(path):
    return imghdr.what(path) is not None
