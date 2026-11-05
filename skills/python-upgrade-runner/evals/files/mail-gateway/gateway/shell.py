"""Build shell commands for the nightly archive job."""
import pipes


def archive_command(source, dest):
    return "tar -czf %s %s" % (pipes.quote(dest), pipes.quote(source))
