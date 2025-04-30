"""
Find modules used by a script, using bytecode analysis.

Based on the stdlib modulefinder by Thomas Heller and Just van Rossum,
but uses a graph data structure and 2.3 features

XXX: Verify all calls to import_hook (and variants) to ensure that 
imports are done in the right way.
"""
from __future__ import absolute_import, print_function

import pkg_resources

import dis
import imp
import marshal
import os
import sys
import struct
import zipimport
import re
from collections import deque

from altgraph.ObjectGraph import ObjectGraph

from itertools import count

from modulegraph import util
from modulegraph import zipio

if sys.version_info[0] == 2:
    from StringIO import StringIO as BytesIO
    from StringIO import StringIO 
    from  urllib import pathname2url
    def _Bchr(value):
        return chr(value)

else:
    from urllib.request  import pathname2url
    from io import BytesIO, StringIO

    def _Bchr(value):
        return value


# File open mode for reading (univeral newlines)
_READ_MODE = "rU"  




# Modulegraph does a good job at simulating Python's, but it can not
# handle packagepath modifications packages make at runtime.  Therefore there
# is a mechanism whereby you can register extra paths in this map for a
# package, and it will be honored.
#
# Note this is a mapping is lists of paths.
_packagePathMap = {}

# Prefix used in magic .pth files used by setuptools to create namespace
# packages without an __init__.py file. 
#
# The value is a list of such prefixes as the prefix varies with versions of 
# setuptools.
_SETUPTOOLS_NAMESPACEPKG_PTHs=(
    "import sys,types,os; p = os.path.join(sys._getframe(1).f_locals['sitedir'], *('",
    "import sys,new,os; p = os.path.join(sys._getframe(1).f_locals['sitedir'], *('",
)


def _namespace_package_path(fqname, pathnames): 
    """
    Return the __path__ for the python package in *fqname*.

    This function uses setuptools metadata to extract information
    about namespace packages from installed eggs.
    """
    path = list(pathnames)

    working_set = pkg_resources.working_set

    for dist in working_set:
        if dist.has_metadata('namespace_packages.txt'):
            namespaces = dist.get_metadata(
                    'namespace_packages.txt').splitlines()
            if fqname in namespaces:
                nspath = os.path.join(dist.location, *fqname.split('.'))
                if nspath not in path:
                    path.append(nspath)

    return path

_strs = re.compile(r'''^\s*["']([A-Za-z0-9_]+)["'],?\s*''')
def _eval_str_tuple(value):
    """
    Input is the repr of a tuple of strings, output
    is that tuple.

    This only works with a tuple where the members are
    python identifiers.
    """
    if not (value.startswith('(') and value.endswith(')')):
        raise ValueError(value)

    orig_value = value
    value = value[1:-1]

    result = []
    while value:
        m = _strs.match(value)
        if m is None:
            raise ValueError(orig_value)

        result.append(m.group(1))
        value = value[len(m.group(0)):]

    return tuple(result)


def os_listdir(path):
    """
    Deprecated name
    """
    warnings.warn("Use zipio.listdir instead of os_listdir",
            DeprecationWarning) 
    return zipio.listdir(path)


def _code_to_file(co):
    """ Convert code object to a .pyc pseudo-file """
    return BytesIO(
            imp.get_magic() + b'\0\0\0\0' + marshal.dumps(co))


def find_module(name, path=None):
    """
    A version of imp.find_module that works with zipped packages.
    """
    if path is None:
        path = sys.path

    # Support for the PEP302 importer for normal imports:
    # - Python 2.5 has pkgutil.ImpImporter
    # - In setuptools 0.7 and later there's _pkgutil.ImpImporter
    # - In earlier setuptools versions you pkg_resources.ImpWrapper
    #
    # XXX: This is a bit of a hack, should check if we can just rely on
    # PEP302's get_code() method with all recent versions of pkgutil and/or
    # setuptools (setuptools 0.6.latest, setuptools trunk and python2.[45])
    #
    # For python 3.3 this code should be replaced by code using importlib,
    # for python 3.2 and 2.7 this should be cleaned up a lot.
    try:
        from pkgutil import ImpImporter
    except ImportError:
        try:
            from _pkgutil import ImpImporter
        except ImportError:
            ImpImporter = pkg_resources.ImpWrapper

    namespace_path =[] 
    fp = None
    for entry in path:
        importer = pkg_resources.get_importer(entry)
        if importer is None:
            continue

        if sys.version_info[:2] >= (3,3) and hasattr(importer, 'find_loader'):
            loader, portions = importer.find_loader(name)

        else:
            loader = importer.find_module(name)
            portions = []

        namespace_path.extend(portions)

        if loader is None: continue

        if isinstance(importer, ImpImporter):
            filename = loader.filename
            if filename.endswith('.pyc') or filename.endswith('.pyo'):
                fp = open(filename, 'rb')
                description = ('.pyc', 'rb', imp.PY_COMPILED)
                return (fp, filename, description)

            elif filename.endswith('.py'):
                if sys.version_info[0] == 2:
                    fp = open(filename, _READ_MODE)
                else:
                    with open(filename, 'rb') as fp:
                        encoding = util.guess_encoding(fp)

                    fp = open(filename, _READ_MODE, encoding=encoding)
                description = ('.py', _READ_MODE, imp.PY_SOURCE)
                return (fp, filename, description)

            else:
                for _sfx, _mode, _type in imp.get_suffixes():
                    if _type == imp.C_EXTENSION and filename.endswith(_sfx):
                        description = (_sfx, 'rb', imp.C_EXTENSION)
                        break
                else:
                    description = ('', '', imp.PKG_DIRECTORY)

                return (None, filename, description)

        if hasattr(loader, 'path'):
            if loader.path.endswith('.pyc') or loader.path.endswith('.pyo'):
                fp = open(loader.path, 'rb')
                description = ('.pyc', 'rb', imp.PY_COMPILED)
                return (fp, loader.path, description)


        if hasattr(loader, 'path') and hasattr(loader, 'get_source'):
            source = loader.get_source(name)
            fp = StringIO(source)
            co = None

        else:
            source = None

        if source is None:
            if hasattr(loader, 'get_code'):
                co = loader.get_code(name)
                fp = _code_to_file(co)

            else:
                fp = None
                co = None

        pathname = os.path.join(entry, *name.split('.'))

        if isinstance(loader, zipimport.zipimporter):
            # Check if this happens to be a wrapper module introduced by 
            # setuptools, if it is we return the actual extension.
            zn = '/'.join(name.split('.'))
            for _sfx, _mode, _type in imp.get_suffixes():
                if _type == imp.C_EXTENSION:
                    p = loader.prefix + zn + _sfx
                    if p in loader._files:
                        description = (_sfx, 'rb', imp.C_EXTENSION)
                        return (None, pathname + _sfx, description)

        if hasattr(loader, 'is_package') and loader.is_package(name):
            return (None, pathname, ('', '', imp.PKG_DIRECTORY))

        if co is None:
            if loader.path.endswith('.py') or loader.path.endswith('.pyw'):
                return (fp, loader.path, ('.py', 'rU', imp.PY_SOURCE))
            else:
                if fp is not None:
                    fp.close()
                return (None, loader.path, (os.path.splitext(loader.path)[-1], 'rb', imp.C_EXTENSION))

        else:
            if hasattr(loader, 'path'):
                return (fp, loader.path, ('.pyc', 'rb', imp.PY_COMPILED))
            else:
                return (fp, pathname + '.pyc', ('.pyc', 'rb', imp.PY_COMPILED))

    if namespace_path:
        if fp is not None:
            fp.close()
        return (None, namespace_path[0], ('', namespace_path, imp.PKG_DIRECTORY))

    raise ImportError(name)

def moduleInfoForPath(path):
    for (ext, readmode, typ) in imp.get_suffixes():
        if path.endswith(ext):
            return os.path.basename(path)[:-len(ext)], readmode, typ
    return None

# A Public interface
import warnings
def AddPackagePath(packagename, path):
    warnings.warn("Use addPackagePath instead of AddPackagePath",
            DeprecationWarning) 

    addPackagePath(packagename, path)

def addPackagePath(packagename, path):
    paths = _packagePathMap.get(packagename, [])
    paths.append(path)
    _packagePathMap[packagename] = paths

_replacePackageMap = {}

# This ReplacePackage mechanism allows modulefinder to work around the
# way the _xmlplus package injects itself under the name "xml" into
# sys.modules at runtime by calling ReplacePackage("_xmlplus", "xml")
# before running ModuleGraph.
def ReplacePackage(oldname, newname):
    warnings.warn("use replacePackage instead of ReplacePackage",
            DeprecationWarning)
    replacePackage(oldname, newname)

def replacePackage(oldname, newname):
    _replacePackageMap[oldname] = newname

class Node(object):
    def __init__(self, identifier):
        self.debug = 0
        self.graphident = identifier
        self.identifier = identifier
        self._namespace = {}
        self.filename = None
        self.packagepath = None
        self.code = None
        # The set of global names that are assigned to in the module.
        # This includes those names imported through starimports of
        # Python modules.
        self.globalnames = set()
        # The set of starimports this module did that could not be
        # resolved, ie. a starimport from a non-Python module.
        self.starimports = set()

    def __contains__(self, name):
        return name in self._namespace

    def __getitem__(self, name):
        return self._namespace[name]

    def __setitem__(self, name, value):
        self._namespace[name] = value

    def get(self, *args):
        return self._namespace.get(*args)

    def __cmp__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return NotImplemented

        return cmp(self.graphident, otherIdent)

    def __eq__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return False

        return self.graphident == otherIdent

    def __ne__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return True

        return self.graphident != otherIdent

    def __lt__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return NotImplemented

        return self.graphident < otherIdent

    def __le__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return NotImplemented

        return self.graphident <= otherIdent

    def __gt__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return NotImplemented

        return self.graphident > otherIdent

    def __ge__(self, other):
        try:
            otherIdent = getattr(other, 'graphident')
        except AttributeError:
            return NotImplemented

        return self.graphident >= otherIdent


    def __hash__(self):
        return hash(self.graphident)

    def infoTuple(self):
        return (self.identifier,)

    def __repr__(self):
        return '%s%r' % (type(self).__name__, self.infoTuple())

class Alias(str):
    pass

class AliasNode(Node):
    def __init__(self, name, node):
        super(AliasNode, self).__init__(name)
        for k in 'identifier', 'packagepath', '_namespace', 'globalnames', 'starimports':
            setattr(self, k, getattr(node, k, None))

    def infoTuple(self):
        return (self.graphident, self.identifier)

class BadModule(Node):
    pass

class ExcludedModule(BadModule):
    pass

class MissingModule(BadModule):
    pass

class Script(Node):
    def __init__(self, filename):
        super(Script, self).__init__(filename)
        self.filename = filename

    def infoTuple(self):
        return (self.filename,)

class BaseModule(Node):
    def __init__(self, name, filename=None, path=None):
        super(BaseModule, self).__init__(name)
        self.filename = filename
        self.packagepath = path

    def infoTuple(self):
        return tuple(filter(None, (self.identifier, self.filename, self.packagepath)))

class BuiltinModule(BaseModule):
    pass

class SourceModule(BaseModule):
    pass

class CompiledModule(BaseModule):
    pass

class Package(BaseModule):
    pass

class Extension(BaseModule):
    pass

class FlatPackage(BaseModule): # nocoverage
    def __init__(self, *args, **kwds):
        warnings.warn("This class will be removed in a future version of modulegraph",
            DeprecationWarning)
        super(FlatPackage, *args, **kwds)

class ArchiveModule(BaseModule): # nocoverage
    def __init__(self, *args, **kwds):
        warnings.warn("This class will be removed in a future version of modulegraph",
            DeprecationWarning)
        super(FlatPackage, *args, **kwds)

# HTML templates for ModuleGraph generator
header = """\
<html>
  <head>
    <title>%(TITLE)s</title>
    <style>
      .node { margin:1em 0; }
    </style>
  </head>
  <body>
    <h1>%(TITLE)s</h1>"""
entry = """
<div class="node">
  <a name="%(NAME)s" />
  %(CONTENT)s
</div>"""
contpl = """<tt>%(NAME)s</tt> %(TYPE)s"""
contpl_linked = """\
<a target="code" href="%(URL)s" type="text/plain"><tt>%(NAME)s</tt></a>"""
imports = """\
  <div class="import">
%(HEAD)s:
  %(LINKS)s
  </div>
"""
footer = """
  </body>
</html>"""

class ModuleGraph(ObjectGraph):
    def __init__(self, path=None, excludes=(), replace_paths=(), implies=(), graph=None, debug=0):
        super(ModuleGraph, self).__init__(graph=graph, debug=debug)
        if path is None:
            path = sys.path
        self.path = path
        self.lazynodes = {}
        # excludes is stronger than implies
        self.lazynodes.update(dict(implies))
        for m in excludes:
            self.lazynodes[m] = None
        self.replace_paths = replace_paths

        self.nspackages = self.calc_setuptools_nspackages()

    def calc_setuptools_nspackages(self):
        # Setuptools has some magic handling for namespace
        # packages when using 'install --single-version-externally-managed'
        # (used by system packagers and also by pip)
        #
        # When this option is used namespace packages are writting to
        # disk *without* an __init__.py file, which means the regular
        # import machinery will not find them.
        # 
        # We therefore explicitly look for the hack used by
        # setuptools to get this kind of namespace packages to work.

        pkgmap = {}

        try:
            from pkgutil import ImpImporter
        except ImportError:
            try:
                from _pkgutil import ImpImporter
            except ImportError:
                ImpImporter = pkg_resources.ImpWrapper

        if sys.version_info[:2] >= (3,3):
            import importlib.machinery
            ImpImporter = importlib.machinery.FileFinder

        for entry in self.path:
            importer = pkg_resources.get_importer(entry)

            if isinstance(importer, ImpImporter):
                try:
                    ldir = os.listdir(entry)
                except os.error:
                    continue

                for fn in ldir:
                    if fn.endswith('-nspkg.pth'):
                        fp = open(os.path.join(entry, fn), 'rU')
                        try:
                            for ln in fp:
                                for pfx in _SETUPTOOLS_NAMESPACEPKG_PTHs:
                                    if ln.startswith(pfx):
                                        try:
                                            start = len(pfx)-2
                                            stop = ln.index(')', start)+1
                                        except ValueError:
                                            continue

                                        pkg = _eval_str_tuple(ln[start:stop])
                                        identifier = ".".join(pkg)
                                        subdir = os.path.join(entry, *pkg)
                                        if os.path.exists(os.path.join(subdir, '__init__.py')):
                                            # There is a real __init__.py, ignore the setuptools hack
                                            continue

                                        if identifier in pkgmap:
                                            pkgmap[identifier].append(subdir)
                                        else:
                                            pkgmap[identifier] = [subdir]
                                        break
                        finally:
                            fp.close()

        return pkgmap

    def implyNodeReference(self, node, other):
        """
        Imply that one node depends on another.
        other may be a module name or another node.

        For use by extension modules and tricky import code
        """
        if isinstance(other, Node):
            self.createReference(node, other)

        else:
            if isinstance(other, tuple):
                raise ValueError(other)

            others = self._safe_import_hook(other, node, None)
            for other in others:
                self.createReference(node, other)


    def createReference(self, fromnode, tonode, edge_data='direct'):
        """
        Create a reference from fromnode to tonode
        """
        return super(ModuleGraph, self).createReference(fromnode, tonode, edge_data=edge_data)

    def findNode(self, name):
        """
        Find a node by identifier.  If a node by that identifier exists,
        it will be returned.

        If a lazy node exists by that identifier with no dependencies (excluded),
        it will be instantiated and returned.

        If a lazy node exists by that identifier with dependencies, it and its
        dependencies will be instantiated and scanned for additional dependencies.
        """
        data = super(ModuleGraph, self).findNode(name)
        if data is not None:
            return data
        if name in self.lazynodes:
            deps = self.lazynodes.pop(name)
            if deps is None:
                # excluded module
                m = self.createNode(ExcludedModule, name)
            elif isinstance(deps, Alias):
                other = self._safe_import_hook(deps, None, None).pop()
                m = self.createNode(AliasNode, name, other)
                self.implyNodeReference(m, other)

            else:
                m = self._safe_import_hook(name, None, None).pop()
                for dep in deps:
                    self.implyNodeReference(m, dep)
            return m

        if name in self.nspackages:
            # name is a --single-version-externally-managed
            # namespace package (setuptools/distribute)
            pathnames = self.nspackages.pop(name)
            m = self.createNode(Package, name)

            # FIXME: The filename must be set to a string to ensure that py2app
            # works, it is not clear yet why that is. Setting to None would be
            # cleaner.
            m.filename = '-'
            m.packagepath = _namespace_package_path(name, pathnames)

            # As per comment at top of file, simulate runtime packagepath additions.
            m.packagepath = m.packagepath + _packagePathMap.get(name, [])
            return m

        return None

    def run_script(self, pathname, caller=None):
        """
        Create a node by path (not module name).  It is expected to be a Python
        source file, and will be scanned for dependencies.
        """
        self.msg(2, "run_script", pathname)
        pathname = os.path.realpath(pathname)
        m = self.findNode(pathname)
        if m is not None:
            return m

        if sys.version_info[0] != 2:
            with open(pathname, 'rb') as fp:
                encoding = util.guess_encoding(fp)

            fp = open(pathname, _READ_MODE, encoding=encoding)
            try:
                contents = fp.read() + '\n'
            finally:
                fp.close()
        else:
            with open(pathname, _READ_MODE) as fp:
                contents = fp.read() + '\n'

        co = compile(contents, pathname, 'exec', 0, True)
        if self.replace_paths:
            co = self.replace_paths_in_code(co)
        m = self.createNode(Script, pathname)
        m.code = co
        self.createReference(caller, m)
        self.scan_code(co, m)
        return m

    def import_hook(self, name, caller=None, fromlist=None, level=-1):
        """
        Import a module

        Return the set of modules that are imported
        """
        self.msg(3, "import_hook", name, caller, fromlist, level)
        parent = self.determine_parent(caller)
        q, tail = self.find_head_package(parent, name, level)
        m = self.load_tail(q, tail)
        modules = [m]
        if fromlist and m.packagepath:
            for s in self.ensure_fromlist(m, fromlist):
                if s not in modules:
                    modules.append(s)
        for m in modules:
            self.createReference(caller, m)
        return modules

    def determine_parent(self, caller):
        """
        Determine the package containing a node
        """
        self.msgin(4, "determine_parent", caller)
        parent = None
        if caller:
            pname = caller.identifier

            if isinstance(caller, Package):
                parent = caller

            elif '.' in pname:
                pname = pname[:pname.rfind('.')]
                parent = self.findNode(pname)

            elif caller.packagepath:
                # XXX: I have no idea why this line
                # is necessary.
                parent = self.findNode(pname)


        self.msgout(4, "determine_parent ->", parent)
        return parent

    def find_head_package(self, parent, name, level=-1):
        """
        Given a calling parent package and an import name determine the containing
        package for the name
        """
        self.msgin(4, "find_head_package", parent, name, level)
        if '.' in name:
            head, tail = name.split('.', 1)
        else:
            head, tail = name, ''

        if level == -1:
            if parent:
                qname = parent.identifier + '.' + head
            else:
                qname = head

        elif level == 0:
            qname = head

            # Absolute import, ignore the parent
            parent = None

        else:
            for i in range(level-1):
                p_fqdn = parent.identifier.rsplit('.', 1)[0]
                new_parent = self.findNode(p_fqdn)
                if new_parent is None:
                    self.msg(2, "Relative import outside package")
                assert new_parent is not parent
                parent = new_parent

            if head:
                qname = parent.identifier + '.' + head
            else:
                qname = parent.identifier


        q = self.import_module(head, qname, parent)
        if q:
            self.msgout(4, "find_head_package ->", (q, tail))
            return q, tail
        if parent:
            qname = head
            parent = None
            q = self.import_module(head, qname, parent)
            if q:
                self.msgout(4, "find_head_package ->", (q, tail))
                return q, tail
        self.msgout(4, "raise ImportError: No module named", qname)
        raise ImportError("No module named " + qname)

    def load_tail(self, mod, tail):
        self.msgin(4, "load_tail", mod, tail)
        result = mod
        while tail:
            i = tail.find('.')
            if i < 0: i = len(tail)
            head, tail = tail[:i], tail[i+1:]
            mname = "%s.%s" % (result.identifier, head)
            result = self.import_module(head, mname, result)
            if not result:
                self.msgout(4, "raise ImportError: No module named", mname)
                raise ImportError("No module named " + mname)
        self.msgout(4, "load_tail ->", result)
        return result

    def ensure_fromlist(self, m, fromlist):
        fromlist = set(fromlist)
        self.msg(4, "ensure_fromlist", m, fromlist)
        if '*' in fromlist:
            fromlist.update(self.find_all_submodules(m))
            fromlist.remove('*')
        for sub in fromlist:
            submod = m.get(sub)
            if submod is None:
                fullname = m.identifier + '.' + sub
                submod = self.import_module(sub, fullname, m)
                if submod is None:
                    raise ImportError("No module named " + fullname)
            yield submod

    def find_all_submodules(self, m):
        if not m.packagepath:
            return
        # 'suffixes' used to be a list hardcoded to [".py", ".pyc", ".pyo"].
        # But we must also collect Python extension modules - although
        # we cannot separate normal dlls from Python extensions.
        suffixes = [triple[0] for triple in imp.get_suffixes()]
        for path in m.packagepath:
            try:
                names = zipio.listdir(path)
            except (os.error, IOError):
                self.msg(2, "can't list directory", path)
                continue
            for info in (moduleInfoForPath(p) for p in names):
                if info is None: continue
                if info[0] != '__init__':
                    yield info[0]

    def import_module(self, partname, fqname, parent):
        # XXX: Review me for use with absolute imports.
        self.msgin(3, "import_module", partname, fqname, parent)
        m = self.findNode(fqname)
        if m is not None:
            self.msgout(3, "import_module ->", m)
            if parent:
                self.createReference(m, parent)
            return m

        if parent and parent.packagepath is None:
            self.msgout(3, "import_module -> None")
            return None

        try:
            searchpath = None
            if parent is not None and parent.packagepath:
                searchpath = parent.packagepath

            fp, pathname, stuff = self.find_module(partname,
                searchpath, parent)

        except ImportError:
            self.msgout(3, "import_module ->", None)
            return None

        try:
            m = self.load_module(fqname, fp, pathname, stuff)

        finally:
            if fp is not None:
                fp.close()

        if parent:
            self.msgout(4, "create reference", m, "->", parent)
            self.createReference(m, parent)
            parent[partname] = m

        self.msgout(3, "import_module ->", m)
        return m

    def load_module(self, fqname, fp, pathname, info):
        suffix, mode, typ = info
        self.msgin(2, "load_module", fqname, fp and "fp", pathname)

        if typ == imp.PKG_DIRECTORY:
            if isinstance(mode, (list, tuple)):
                packagepath = mode
            else:
                packagepath = []

            m = self.load_package(fqname, pathname, packagepath)
            self.msgout(2, "load_module ->", m)
            return m

        if typ == imp.PY_SOURCE:
            contents = fp.read()
            if isinstance(contents, bytes):
                contents += b'\n'
            else:
                contents += '\n'


            co = compile(contents, pathname, 'exec', 0, True)
            cls = SourceModule

        elif typ == imp.PY_COMPILED:
            if fp.read(4) != imp.get_magic():
                self.msgout(2, "raise ImportError: Bad magic number", pathname)
                raise ImportError("Bad magic number in %s" % pathname)
            fp.read(4)
            co = marshal.loads(fp.read())
            cls = CompiledModule

        elif typ == imp.C_BUILTIN:
            cls = BuiltinModule
            co = None

        else:
            cls = Extension
            co = None

        m = self.createNode(cls, fqname)
        m.filename = pathname
        if co:
            if self.replace_paths:
                co = self.replace_paths_in_code(co)

            m.code = co
            self.scan_code(co, m)

        self.msgout(2, "load_module ->", m)
        return m

    def _safe_import_hook(self, name, caller, fromlist, level=-1):
        # wrapper for self.import_hook() that won't raise ImportError
        try:
            mods = self.import_hook(name, caller, level=level)
        except ImportError as msg:
            self.msg(2, "ImportError:", str(msg))

            # This is a hack, but sadly enough the necessary information
            # isn't available otherwise.
            m = re.match('^No module named (\S+)$', str(msg))
            if m is not None:
                m = self.createNode(MissingModule, m.group(1))
            else:
                m = self.createNode(MissingModule, name)
            self.createReference(caller, m)
        else:
            assert len(mods) == 1
            m = list(mods)[0]

        subs = [m]
        for sub in (fromlist or ()):
            # If this name is in the module namespace already,
            # then add the entry to the list of substitutions
            if sub in m:
                sm = m[sub]
                if sm is not None:
                    if sm not in subs:
                        subs.append(sm)
                continue

            # See if we can load it
            fullname = name + '.' + sub
            sm = self.findNode(fullname)
            if sm is None:
                try:
                    sm = self.import_hook(name, caller, [sub], level=level)
                except ImportError as msg:
                    self.msg(2, "ImportError:", str(msg))
                    sm = self.createNode(MissingModule, fullname)
                else:
                    sm = self.findNode(fullname)

            m[sub] = sm
            if sm is not None:
                self.createReference(sm, m)
                if sm not in subs:
                    subs.append(sm)
        return subs

    def scan_code(self, co, m,
            HAVE_ARGUMENT=_Bchr(dis.HAVE_ARGUMENT),
            LOAD_CONST=_Bchr(dis.opname.index('LOAD_CONST')),
            IMPORT_NAME=_Bchr(dis.opname.index('IMPORT_NAME')),
            IMPORT_FROM=_Bchr(dis.opname.index('IMPORT_FROM')),
            STORE_NAME=_Bchr(dis.opname.index('STORE_NAME')),
            STORE_GLOBAL=_Bchr(dis.opname.index('STORE_GLOBAL')),
            unpack=struct.unpack):

        # Python >=2.5: LOAD_CONST flags, LOAD_CONST names, IMPORT_NAME name
        # Python < 2.5: LOAD_CONST names, IMPORT_NAME name
        extended_import = bool(sys.version_info[:2] >= (2,5))

        code = co.co_code
        constants = co.co_consts
        n = len(code)
        i = 0

        level = None
        fromlist = None

        while i < n:
            c = code[i]
            i += 1
            if c >= HAVE_ARGUMENT:
                i = i+2

            if c == IMPORT_NAME:
                if extended_import:
                    assert code[i-9] == LOAD_CONST
                    assert code[i-6] == LOAD_CONST
                    arg1, arg2 = unpack('<xHxH', code[i-9:i-3])
                    level = co.co_consts[arg1]
                    fromlist = co.co_consts[arg2]
                else:
                    assert code[-6] == LOAD_CONST
                    arg1, = unpack('<xH', code[i-6:i-3])
                    level = -1
                    fromlist = co.co_consts[arg1]

                assert fromlist is None or type(fromlist) is tuple
                oparg, = unpack('<H', code[i - 2:i])
                name = co.co_names[oparg]
                have_star = False
                if fromlist is not None:
                    fromlist = set(fromlist)
                    if '*' in fromlist:
                        fromlist.remove('*')
                        have_star = True

                #self.msgin(2, "Before import hook", repr(name), repr(m), repr(fromlist), repr(level))

                imported_module = self._safe_import_hook(name, m, fromlist, level)[0]

                if have_star:
                    m.globalnames.update(imported_module.globalnames)
                    m.starimports.update(imported_module.starimports)
                    if imported_module.code is None:
                        m.starimports.add(name)

                
                # XXX: The code below tries to find the module we're 
                # star-importing from. That code uses heuristics, which is
                # a bit lame as we already know that module: _safe_import has
                # just calculated it for us (after a small tweak to the 
                # return value of that method).
                # 
                #
                #if have_star:
                #    # We've encountered an "import *". If it is a Python module,
                #    # the code has already been parsed and we can suck out the
                #    # global names.
                #    mm = None
                #    if m.packagepath:
                #        # At this point we don't know whether 'name' is a
                #        # submodule of 'm' or a global module. Let's just try
                #        # the full name first.
                #        mm = self.findNode(m.identifier + '.' + name)
                #    if mm is None:
                #        mm = self.findNode(name)
                #
                #
                #    assert actual_mod is mm, (name, m, fromlist, actual_mod, mm)
                #    if mm is not None:
                #        m.globalnames.update(mm.globalnames)
                #        m.starimports.update(mm.starimports)
                #        if mm.code is None:
                #            m.starimports.add(name)
                #    else:
                #        m.starimports.add(name)
            elif c == STORE_NAME or c == STORE_GLOBAL:
                # keep track of all global names that are assigned to
                oparg = unpack('<H', code[i - 2:i])[0]
                name = co.co_names[oparg]
                m.globalnames.add(name)

        cotype = type(co)
        for c in constants:
            if isinstance(c, cotype):
                self.scan_code(c, m)

    def load_package(self, fqname, pathname, pkgpath):
        """
        Called only when an imp.PACKAGE_DIRECTORY is found
        """
        self.msgin(2, "load_package", fqname, pathname, pkgpath)
        newname = _replacePackageMap.get(fqname)
        if newname:
            fqname = newname
        m = self.createNode(Package, fqname)
        m.filename = pathname
        m.packagepath = _namespace_package_path(fqname, [pathname])

        if pkgpath:
            m.filename = '-'
            m.packagepath = _namespace_package_path(fqname, pkgpath)

        # As per comment at top of file, simulate runtime packagepath additions.
        m.packagepath = m.packagepath + _packagePathMap.get(fqname, [])

        

        try:
            self.msg(2, "find __init__ for %s"%(m.packagepath,))
            fp, buf, stuff = self.find_module("__init__", m.packagepath, parent=m)
        except ImportError:
            pass

        else:
            try:
                self.msg(2, "load __init__ for %s"%(m.packagepath,))
                self.load_module(fqname, fp, buf, stuff)
            finally:
                if fp is not None:
                    fp.close()
        self.msgout(2, "load_package ->", m)
        return m

    def find_module(self, name, path, parent=None):
        if parent is not None:
            # assert path is not None
            fullname = parent.identifier + '.' + name
        else:
            fullname = name

        node = self.findNode(fullname)
        if node is not None:
            self.msgout(3, "find_module -> already included?", node)
            raise ImportError(name)

        if path is None:
            if name in sys.builtin_module_names:
                return (None, None, ("", "", imp.C_BUILTIN))

            path = self.path

        fp, buf, stuff = find_module(name, path)
        try:
            if buf:
                buf = os.path.realpath(buf)

            return (fp, buf, stuff)
        except:
            fp.close()
            raise

    def create_xref(self, out=None):
        global header, footer, entry, contpl, contpl_linked, imports
        if out is None:
            out = sys.stdout
        scripts = []
        mods = []
        for mod in self.flatten():
            name = os.path.basename(mod.identifier)
            if isinstance(mod, Script):
                scripts.append((name, mod))
            else:
                mods.append((name, mod))
        scripts.sort()
        mods.sort()
        scriptnames = [name for name, m in scripts]
        scripts.extend(mods)
        mods = scripts

        title = "modulegraph cross reference for "  + ', '.join(scriptnames)
        print(header % {"TITLE": title}, file=out)

        def sorted_namelist(mods):
            lst = [os.path.basename(mod.identifier) for mod in mods if mod]
            lst.sort()
            return lst
        for name, m in mods:
            content = ""
            if isinstance(m, BuiltinModule):
                content = contpl % {"NAME": name,
                                    "TYPE": "<i>(builtin module)</i>"}
            elif isinstance(m, Extension):
                content = contpl % {"NAME": name,\
                                    "TYPE": "<tt>%s</tt>" % m.filename}
            else:
                url = pathname2url(m.filename or "")
                content = contpl_linked % {"NAME": name, "URL": url}
            oute, ince = map(sorted_namelist, self.get_edges(m))
            if oute:
                links = ""
                for n in oute:
                    links += """  <a href="#%s">%s</a>\n""" % (n, n)
                content += imports % {"HEAD": "imports", "LINKS": links}
            if ince:
                links = ""
                for n in ince:
                    links += """  <a href="#%s">%s</a>\n""" % (n, n)
                content += imports % {"HEAD": "imported by", "LINKS": links}
            print(entry % {"NAME": name,"CONTENT": content}, file=out)
        print(footer, file=out)
        

    def itergraphreport(self, name='G', flatpackages=()):
        # XXX: Can this be implemented using Dot()?
        nodes = map(self.graph.describe_node, self.graph.iterdfs(self))
        describe_edge = self.graph.describe_edge
        edges = deque()
        packagenodes = set()
        packageidents = {}
        nodetoident = {}
        inpackages = {}
        mainedges = set()

        # XXX - implement
        flatpackages = dict(flatpackages)

        def nodevisitor(node, data, outgoing, incoming):
            if not isinstance(data, Node):
                return {'label': str(node)}
            #if isinstance(d, (ExcludedModule, MissingModule, BadModule)):
            #    return None
            s = '<f0> ' + type(data).__name__
            for i,v in enumerate(data.infoTuple()[:1], 1):
                s += '| <f%d> %s' % (i,v)
            return {'label':s, 'shape':'record'}


        def edgevisitor(edge, data, head, tail):
            # XXX: This method nonsense, the edge
            # data is never initialized.
            if data == 'orphan':
                return {'style':'dashed'}
            elif data == 'pkgref':
                return {'style':'dotted'}
            return {}

        yield 'digraph %s {\n' % (name,)
        attr = dict(rankdir='LR', concentrate='true')
        cpatt  = '%s="%s"'
        for item in attr.items():
            yield '\t%s;\n' % (cpatt % item,)

        # find all packages (subgraphs)
        for (node, data, outgoing, incoming) in nodes:
            nodetoident[node] = getattr(data, 'identifier', None)
            if isinstance(data, Package):
                packageidents[data.identifier] = node
                inpackages[node] = set([node])
                packagenodes.add(node)


        # create sets for subgraph, write out descriptions
        for (node, data, outgoing, incoming) in nodes:
            # update edges
            for edge in (describe_edge(e) for e in outgoing):
                edges.append(edge)

            # describe node
            yield '\t"%s" [%s];\n' % (
                node,
                ','.join([
                    (cpatt % item) for item in
                    nodevisitor(node, data, outgoing, incoming).items()
                ]),
            )

            inside = inpackages.get(node)
            if inside is None:
                inside = inpackages[node] = set()
            ident = nodetoident[node]
            if ident is None:
                continue
            pkgnode = packageidents.get(ident[:ident.rfind('.')])
            if pkgnode is not None:
                inside.add(pkgnode)


        graph = []
        subgraphs = {}
        for key in packagenodes:
            subgraphs[key] = []

        while edges:
            edge, data, head, tail = edges.popleft()
            if ((head, tail)) in mainedges:
                continue
            mainedges.add((head, tail))
            tailpkgs = inpackages[tail]
            common = inpackages[head] & tailpkgs
            if not common and tailpkgs:
                usepkgs = sorted(tailpkgs)
                if len(usepkgs) != 1 or usepkgs[0] != tail:
                    edges.append((edge, data, head, usepkgs[0]))
                    edges.append((edge, 'pkgref', usepkgs[-1], tail))
                    continue
            if common:
                common = common.pop()
                if tail == common:
                    edges.append((edge, data, tail, head))
                elif head == common:
                    subgraphs[common].append((edge, 'pkgref', head, tail))
                else:
                    edges.append((edge, data, common, head))
                    edges.append((edge, data, common, tail))

            else:
                graph.append((edge, data, head, tail))

        def do_graph(edges, tabs):
            edgestr = tabs + '"%s" -> "%s" [%s];\n'
            # describe edge
            for (edge, data, head, tail) in edges:
                attribs = edgevisitor(edge, data, head, tail)
                yield edgestr % (
                    head,
                    tail,
                    ','.join([(cpatt % item) for item in attribs.items()]),
                )

        for g, edges in subgraphs.items():
            yield '\tsubgraph "cluster_%s" {\n' % (g,)
            yield '\t\tlabel="%s";\n' % (nodetoident[g],)
            for s in do_graph(edges, '\t\t'):
                yield s
            yield '\t}\n'

        for s in do_graph(graph, '\t'):
            yield s

        yield '}\n'

    def graphreport(self, fileobj=None, flatpackages=()):
        if fileobj is None:
            fileobj = sys.stdout
        fileobj.writelines(self.itergraphreport(flatpackages=flatpackages))

    def report(self):
        """Print a report to stdout, listing the found modules with their
        paths, as well as modules that are missing, or seem to be missing.
        """
        print()
        print("%-15s %-25s %s" % ("Class", "Name", "File"))
        print("%-15s %-25s %s" % ("-----", "----", "----"))
        # Print modules found
        sorted = [(os.path.basename(mod.identifier), mod) for mod in self.flatten()]
        sorted.sort()
        for (name, m) in sorted:
            print("%-15s %-25s %s" % (type(m).__name__, name, m.filename or ""))

    def replace_paths_in_code(self, co):
        new_filename = original_filename = os.path.normpath(co.co_filename)
        for f, r in self.replace_paths:
            f = os.path.join(f, '')
            r = os.path.join(r, '')
            if original_filename.startswith(f):
                new_filename = r + original_filename[len(f):]
                break

        else:
            return co

        consts = list(co.co_consts)
        for i in range(len(consts)):
            if isinstance(consts[i], type(co)):
                consts[i] = self.replace_paths_in_code(consts[i])

        code_func = type(co)

        if hasattr(co, 'co_kwonlyargcount'):
            return code_func(co.co_argcount, co.co_kwonlyargcount, co.co_nlocals, co.co_stacksize,
                         co.co_flags, co.co_code, tuple(consts), co.co_names,
                         co.co_varnames, new_filename, co.co_name,
                         co.co_firstlineno, co.co_lnotab,
                         co.co_freevars, co.co_cellvars)
        else:
            return code_func(co.co_argcount, co.co_nlocals, co.co_stacksize,
                         co.co_flags, co.co_code, tuple(consts), co.co_names,
                         co.co_varnames, new_filename, co.co_name,
                         co.co_firstlineno, co.co_lnotab,
                         co.co_freevars, co.co_cellvars)
