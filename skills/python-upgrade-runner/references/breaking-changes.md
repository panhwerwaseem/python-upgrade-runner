# Breaking changes by Python version

What `scripts/compat_scan.py` checks, version by version, and a short list of
changes it cannot see. This file mirrors `scripts/compat_rules.json`; a unit
test fails if a rule is missing here.

The list is deliberately incomplete. It holds standard-library removals and
deprecations whose version is certain. It does not cover third-party packages,
C API changes, or changes in behaviour. For the full list read the official
page for each version you pass through:

`https://docs.python.org/3/whatsnew/<version>.html` (for example `3.12.html`)

Read the "Removed", "Deprecated" and "Porting to Python X.Y" sections.

## Contents

- [How to read the scanner's statuses](#how-to-read-the-scanners-statuses)
- [Python 3.8](#python-38)
- [Python 3.9](#python-39)
- [Python 3.10](#python-310)
- [Python 3.11](#python-311)
- [Python 3.12](#python-312)
- [Python 3.13](#python-313)
- [Python 3.14](#python-314)
- [What the scanner cannot see](#what-the-scanner-cannot-see)

## How to read the scanner's statuses

| Status | Meaning | Action |
|---|---|---|
| `removed` | The name does not exist at the target version | Fix before running tests on the target |
| `later` | Present at the target, removed in a later version | Fix now if the replacement works on the current version; otherwise plan it |
| `deprecated` | Emits a DeprecationWarning at the target; no removal version in the table | Fix; do not filter the warning |
| `silenced` | `warnings.filterwarnings` or `warnings.simplefilter` with `"ignore"` that covers DeprecationWarning | Find out what it hides, fix that, then remove or narrow the filter |
| `guarded` | The use sits in `try/except ImportError` (or `AttributeError`), or under a `sys.version_info` or `hasattr` check | Read both branches and confirm the fallback works on the target |
| `shadowed` | A module of the same name exists next to the importing file, at the top of the scanned path, or in its `src/` folder | Confirm the import really resolves to the project's module |

## Python 3.8

| Removed | Replacement |
|---|---|
| `macpath` (module) | `os.path` |
| `time.clock` | `time.perf_counter()` or `time.process_time()` |
| `platform.linux_distribution`, `platform.dist` | `platform.freedesktop_os_release()` (Python 3.10+) or the third-party `distro` package |
| `cgi.escape` | `html.escape()`. It also escapes quotes unless `quote=False` |
| `cgi.parse_qs`, `cgi.parse_qsl` | `urllib.parse.parse_qs()`, `urllib.parse.parse_qsl()` |

## Python 3.9

| Removed | Replacement |
|---|---|
| `dummy_threading`, `_dummy_thread` (modules) | `threading`, `_thread` |
| `fractions.gcd` | `math.gcd()` |
| `base64.encodestring`, `base64.decodestring` | `base64.encodebytes()`, `base64.decodebytes()` |
| `sys.getcheckinterval`, `sys.setcheckinterval` | `sys.getswitchinterval()`, `sys.setswitchinterval()` |
| `asyncio.Task.current_task`, `asyncio.Task.all_tasks` | `asyncio.current_task()`, `asyncio.all_tasks()` |
| `plistlib.readPlist`, `plistlib.writePlist` | `plistlib.load()`, `plistlib.dump()` |
| `plistlib.readPlistFromBytes`, `plistlib.writePlistToBytes` | `plistlib.loads()`, `plistlib.dumps()` |

Not scanned (methods on objects): `Thread.isAlive()` (use `is_alive()`),
`array.array.tostring()` and `fromstring()` (use `tobytes()` and
`frombytes()`), `Element.getchildren()` and `getiterator()` in
`xml.etree.ElementTree` (use `list(elem)` and `iter()`), and the `encoding`
argument of `json.loads()`.

## Python 3.10

| Removed | Replacement |
|---|---|
| `formatter` (module) | None in the standard library |
| `parser` (module) | `ast` |
| The ABC aliases in `collections`, listed below | The same name in `collections.abc` |

The removed `collections` aliases: `AsyncGenerator`, `AsyncIterable`,
`AsyncIterator`, `Awaitable`, `ByteString`, `Callable`, `Collection`,
`Container`, `Coroutine`, `Generator`, `Hashable`, `ItemsView`, `Iterable`,
`Iterator`, `KeysView`, `Mapping`, `MappingView`, `MutableMapping`,
`MutableSequence`, `MutableSet`, `Reversible`, `Sequence`, `Set`, `Sized`,
`ValuesView`. `collections.OrderedDict`, `defaultdict`, `namedtuple`, `deque`,
`Counter` and `ChainMap` are not affected.

| Deprecated in 3.10 | Replacement |
|---|---|
| `threading.currentThread`, `threading.activeCount` | `threading.current_thread()`, `threading.active_count()` |

Not scanned: the `loop` parameter was removed from most of asyncio's
high-level API in 3.10. Calls that still pass `loop=` fail with a TypeError.

## Python 3.11

| Removed | Replacement |
|---|---|
| `binhex` (module) | None in the standard library |
| `binascii.a2b_hqx`, `binascii.b2a_hqx`, `binascii.rlecode_hqx`, `binascii.rledecode_hqx` | None in the standard library |
| `inspect.getargspec` | `inspect.signature()` or `inspect.getfullargspec()` |
| `inspect.formatargspec` | `str(inspect.signature(func))` |
| `asyncio.coroutine` | `async def`, with `await` in place of `yield from` |
| `gettext.lgettext`, `gettext.ldgettext`, `gettext.lngettext`, `gettext.ldngettext` | `gettext.gettext()`, `dgettext()`, `ngettext()`, `dngettext()` |
| `gettext.bind_textdomain_codeset` | Remove the call |

| Deprecated in 3.11 | Replacement |
|---|---|
| `locale.getdefaultlocale` | `locale.setlocale()`, `locale.getlocale()` and `locale.getencoding()` |

`inspect.getfullargspec()` returns a different named tuple from
`getargspec()`: the third field is `varkw`, not `keywords`, and there are
extra fields. Check every place the result is unpacked or indexed.

Not scanned: `open()` no longer accepts `"U"` in the mode string, and
`random.shuffle()` no longer accepts its second (`random`) argument.

## Python 3.12

| Removed | Replacement |
|---|---|
| `distutils` (module, PEP 632) | `setuptools` for building. PEP 632 lists a replacement for each submodule |
| `distutils.core` | `setuptools` (`setup` and `Extension` import from `setuptools`) |
| `distutils.version` | `packaging.version` from the third-party `packaging` project |
| `distutils.sysconfig` | `sysconfig` |
| `distutils.util.strtobool` | None. Write a small helper |
| `distutils.util.get_platform` | `sysconfig.get_platform()` |
| `distutils.spawn.find_executable` | `shutil.which()` |
| `distutils.dir_util.copy_tree` | `shutil.copytree()`; `dirs_exist_ok=True` needs Python 3.8+ |
| `imp` (module) | `importlib` |
| `imp.reload` | `importlib.reload()` |
| `imp.load_source` | `importlib.util.spec_from_file_location()`, `importlib.util.module_from_spec()` and `spec.loader.exec_module()` |
| `imp.find_module` | `importlib.util.find_spec()` |
| `imp.load_module` | `importlib.import_module()` |
| `imp.new_module` | `types.ModuleType()` |
| `asyncore`, `asynchat` (modules) | `asyncio` |
| `smtpd` (module) | The third-party `aiosmtpd` package |
| `configparser.SafeConfigParser` | `configparser.ConfigParser` |
| `locale.format` | `locale.format_string()` |
| `ssl.wrap_socket` | `wrap_socket()` on an `ssl.SSLContext` |
| `ssl.match_hostname` | Remove the call. An `SSLContext` with `check_hostname` enabled verifies the hostname |
| `ssl.RAND_pseudo_bytes` | `os.urandom()` or `ssl.RAND_bytes()` |
| `pkgutil.ImpImporter`, `pkgutil.ImpLoader` | No direct replacement. Use `importlib` |
| `importlib.find_loader` | `importlib.util.find_spec()` |
| `importlib.util.set_package`, `importlib.util.set_loader`, `importlib.util.module_for_loader` | Remove the decorator. The import machinery sets these attributes; loaders implement `exec_module()` |
| `importlib.abc.Finder` | `importlib.abc.MetaPathFinder` or `importlib.abc.PathEntryFinder` |
| `sqlite3.enable_shared_cache` | Open the database in URI mode with `cache=shared` |
| `sqlite3.OptimizedUnicode` | `str` |

`unittest.TestCase` method aliases removed in 3.12. The scanner matches them
by name on calls of the form `self.<alias>(...)`:

| Removed alias | Use |
|---|---|
| `failUnless`, `assert_` | `assertTrue` |
| `failIf` | `assertFalse` |
| `failUnlessEqual`, `assertEquals` | `assertEqual` |
| `failIfEqual`, `assertNotEquals` | `assertNotEqual` |
| `failUnlessAlmostEqual`, `assertAlmostEquals` | `assertAlmostEqual` |
| `failIfAlmostEqual`, `assertNotAlmostEquals` | `assertNotAlmostEqual` |
| `failUnlessRaises` | `assertRaises` |
| `assertRegexpMatches` | `assertRegex` |
| `assertNotRegexpMatches` | `assertNotRegex` |
| `assertRaisesRegexp` | `assertRaisesRegex` |

| Deprecated in 3.12 | Replacement |
|---|---|
| `datetime.datetime.utcnow` | `datetime.datetime.now(datetime.timezone.utc)` |
| `datetime.datetime.utcfromtimestamp` | `datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)` |

The `utcnow()` replacements return timezone-aware datetimes. Code that
compares the result with naive datetimes, or stores it in a column that
expects naive values, changes behaviour. Treat each call as a hand edit, not a
search and replace.

Not scanned:

- Virtual environments created by `venv` on 3.12 no longer contain
  `setuptools`. Code that imports `pkg_resources`, or that relied on
  setuptools being present without declaring it, fails with an ImportError.
- `import distutils` can still succeed on 3.12 when setuptools is installed,
  because setuptools ships its own copy. The scanner reports the import
  anyway: the standard library no longer provides it, so the project has an
  undeclared dependency on setuptools until the import is replaced.
- `ConfigParser.readfp()` was removed. Use `read_file()`.
- An invalid escape sequence in a string literal, such as `"\d"` outside a raw
  string, now produces a SyntaxWarning instead of a DeprecationWarning.

## Python 3.13

The remaining PEP 594 modules were removed:

| Removed module | Replacement |
|---|---|
| `aifc`, `audioop`, `cgitb`, `chunk`, `msilib`, `nis`, `nntplib`, `ossaudiodev`, `spwd`, `sunau`, `xdrlib` | None in the standard library. PEP 594 and the 3.13 What's New page discuss third-party options |
| `cgi` | `urllib.parse.parse_qsl()` for query strings; the `email.message` module for headers and multipart bodies |
| `crypt` | `hashlib` for simple hashing; otherwise a third-party library such as bcrypt, passlib or argon2-cffi |
| `imghdr`, `sndhdr` | A third-party library such as filetype, puremagic or python-magic |
| `mailcap` | `mimetypes` |
| `pipes` | `subprocess`. `pipes.quote` becomes `shlex.quote()` |
| `telnetlib` | A third-party library such as telnetlib3 or Exscript |
| `uu` | `base64` |

| Also removed in 3.13 | Replacement |
|---|---|
| `lib2to3` (module) and the `2to3` program | A third-party parser such as LibCST or parso |
| `tkinter.tix` (module) | `tkinter.ttk` |
| `typing.io` | Import `IO`, `TextIO` and `BinaryIO` from `typing` directly |
| `typing.re` | `re.Pattern` and `re.Match` |
| `unittest.makeSuite` | `unittest.TestLoader().loadTestsFromTestCase()` |
| `unittest.findTestCases` | `unittest.TestLoader().loadTestsFromModule()` |
| `unittest.getTestCaseNames` | `unittest.TestLoader().getTestCaseNames()` |
| `locale.resetlocale` | `locale.setlocale(locale.LC_ALL, "")` |

## Python 3.14

| Removed | Replacement |
|---|---|
| `ast.Num`, `ast.Str`, `ast.Bytes`, `ast.NameConstant`, `ast.Ellipsis` | `ast.Constant` |
| `pkgutil.find_loader`, `pkgutil.get_loader` | `importlib.util.find_spec()` |
| `asyncio.get_child_watcher`, `asyncio.set_child_watcher` | Remove the call. asyncio chooses the child watcher itself |
| `asyncio.AbstractChildWatcher`, `asyncio.SafeChildWatcher`, `asyncio.FastChildWatcher`, `asyncio.MultiLoopChildWatcher`, `asyncio.PidfdChildWatcher`, `asyncio.ThreadedChildWatcher` | Remove the use |
| `sqlite3.version`, `sqlite3.version_info` | `sqlite3.sqlite_version`, `sqlite3.sqlite_version_info` (the SQLite library version) |
| `urllib.request.URLopener`, `urllib.request.FancyURLopener` | `urllib.request.urlopen()` or `urllib.request.build_opener()` |
| `importlib.abc.ResourceReader`, `importlib.abc.Traversable`, `importlib.abc.TraversableResources` | The classes in `importlib.resources.abc` (Python 3.11+) |

Not scanned, and able to change behaviour without an import error:

- On Linux the default `multiprocessing` start method changed from `fork` to
  `forkserver`. Code that relied on child processes inheriting module state
  must set the start method explicitly or pass the state.
- Annotations are evaluated lazily (PEP 649 and PEP 749). Code that reads
  `__annotations__` directly may see different results.
- `tarfile` extraction uses the `data` filter by default, which rejects
  archive members that the old default accepted.

The table stops at 3.14. For a later target the scanner prints a note and
checks only what is listed here.

## What the scanner cannot see

- **Methods on objects.** `thread.isAlive()` or `parser.readfp()` cannot be
  tied to a type without running the code. Only `self.<alias>()` calls of the
  unittest aliases are matched by name.
- **Removed parameters and changed behaviour.** For example `loop=` in
  asyncio, or the changes listed as "Not scanned" above.
- **Names reached indirectly.** `getattr(module, name)`, star imports,
  re-exports through the project's own modules, and names that the same file
  binds in more than one way.
- **Third-party packages.** See `references/dependency-strategy.md`.
- **Non-Python files.** `setup.cfg`, `pyproject.toml`, `tox.ini`, CI
  workflows, Dockerfiles, and warning filters set in pytest configuration or
  `PYTHONWARNINGS`.
- **Files it cannot parse.** A file with syntax newer than the interpreter
  running the scan is reported as not scanned. Run the scan with the newest
  interpreter available.

The test suite on the target interpreter, with DeprecationWarning turned into
an error, is what finds the rest.
