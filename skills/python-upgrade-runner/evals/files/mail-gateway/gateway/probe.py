"""Check that the relay answers on its management port."""
import sys

if sys.version_info < (3, 13):
    import telnetlib
else:
    telnetlib = None


def relay_banner(host, port=2525, timeout=5):
    if telnetlib is None:
        raise RuntimeError("relay probe is not available on this Python")
    connection = telnetlib.Telnet(host, port, timeout)
    try:
        return connection.read_until(b"\n", timeout).decode("ascii", "replace").strip()
    finally:
        connection.close()
