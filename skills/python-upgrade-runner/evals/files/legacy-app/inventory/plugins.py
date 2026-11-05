"""Load pricing plugins from single Python files."""
import imp
import os


def load_plugin(path):
    name = os.path.splitext(os.path.basename(path))[0]
    return imp.load_source(name, path)
