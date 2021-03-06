# coding: utf-8

import distutils.spawn
import glob
import json
import os.path
import re
import shutil
from subprocess import call
from subprocess import check_output
from subprocess import PIPE
from subprocess import Popen
import sys

from mpienv.ompi import parse_ompi_info
from mpienv.py import MPI4Py

try:
    from subprocess import DEVNULL  # py3k
except ImportError:
    import os
    DEVNULL = open(os.devnull, 'wb')

try:
    import __builtin__
except ImportError:
    import builtins


class UnknownMPI(RuntimeError):
    pass


def yes_no_input(msg):
    if hasattr(__builtin__, 'raw_input'):
        input = __builtin__.raw_input
    else:
        input = builtins.input

    try:
        choice = input("{} [y/N]: ".format(msg)).lower()
        while True:
            if choice in ['y', 'ye', 'yes']:
                return True
            elif choice in ['n', 'no']:
                return False
            else:
                choice = input(
                    "Please respond with 'yes' or 'no' [y/N]: ").lower()
    except (EOFError, KeyboardInterrupt):
        return False


class BrokenSymlinkError(Exception):
    def __init__(self, message, path):
        super(BrokenSymlinkError).__init__(self, message)
        self.path = path


def decode(s):
    if type(s) == bytes:
        return s.decode(sys.getdefaultencoding())
    else:
        return s


def encode(s):
    if type(s) == str:
        return s.encode(sys.getdefaultencoding())
    else:
        return s


def which(cmd):
    exe = distutils.spawn.find_executable(cmd)
    if exe is None:
        return None

    exe = decode(os.path.realpath(exe))
    return exe


def is_broken_symlink(path):
    return os.path.islink(path) and not os.path.exists(path)


def filter_path(proj_root, paths):
    vers = glob.glob(os.path.join(proj_root, 'versions', '*'))

    llp = []

    for p in paths:
        root = re.sub(r'/(bin|lib|lib64)/?$', '', p)
        if root not in vers:
            llp.append(p)

    return llp


def is_active(prefix):
    mpiexec1 = os.path.realpath(os.path.join(prefix, 'bin', 'mpiexec'))
    mpiexec2 = which('mpiexec')
    return mpiexec1 == mpiexec2


def _glob_list(dire, pat_list):
    """Glob all patterns `pat` in `directory`"""
    if type(dire) is list or type(dire) is tuple:
        dire = os.path.join(*dire)

    # list of lists
    lol = [glob.glob(os.path.join(dire, p)) for p in pat_list]

    # return flattened list
    return [item for sublist in lol for item in sublist]


def _get_info_mpich(prefix):
    info = {}

    # Run mpiexec --version and extract some information
    mpiexec = os.path.join(prefix, 'bin', 'mpiexec')
    out = decode(check_output([mpiexec, '--version']))

    # Parse 'Configure options' section
    # Config options are like this:
    # '--disable-option-checking' '--prefix=NONE' '--enable-cuda'
    m = re.search(r'Configure options:\s+(.*)$', out, re.MULTILINE)
    conf_str = m.group(1)
    conf_list = [s.replace("'", '') for s
                 in re.findall(r'\'[^\']+\'', conf_str)]

    m = re.search(r'Version:\s+(\S+)', out, re.MULTILINE)
    ver = m.group(1)

    if os.path.islink(prefix):
        prefix = os.path.realpath(prefix)

    info['type'] = 'MPICH'
    info['active'] = is_active(prefix)
    info['version'] = ver
    info['prefix'] = prefix
    info['configure'] = conf_list[0]
    info['conf_params'] = conf_list
    info['default_name'] = "mpich-{}".format(ver)

    return info


def _get_info_mvapich(prefix):
    info = _get_info_mpich(prefix)

    # Parse mvapich version
    mpi_h = os.path.join(prefix, 'include', 'mpi.h')
    if not os.path.exists(mpi_h):
        raise RuntimeError("Error: Cannot find {}".format(mpi_h))

    mv_ver = check_output(['grep', '-E', 'define *MVAPICH2_VERSION', mpi_h],
                          stderr=DEVNULL)
    mch_ver = check_output(['grep', '-E', 'define *MPICH_VERSION', mpi_h],
                           stderr=DEVNULL)

    mv_ver = decode(mv_ver)
    mch_ver = decode(mch_ver)

    mv_ver = re.search(r'"([.0-9]+)"', mv_ver).group(1)
    mch_ver = re.search(r'"([.0-9]+)"', mch_ver).group(1)

    info['version'] = mv_ver
    info['type'] = 'MVAPICH'
    info['mpich_ver'] = mch_ver
    info['default_name'] = "mvapich2-{}".format(mv_ver)

    return info


def _call_ompi_info(bin):
    out = check_output([bin, '--all', '--parsable'], stderr=DEVNULL)
    out = decode(out)

    return parse_ompi_info(out)


def _get_info_ompi(prefix):
    info = {}

    ompi = _call_ompi_info(os.path.join(prefix, 'bin', 'ompi_info'))

    ver = ompi.get('ompi:version:full')
    mpi_ver = ompi.get('mpi-api:version:full')

    if os.path.islink(prefix):
        prefix = os.path.realpath(prefix)

    info['type'] = 'Open MPI'
    info['active'] = is_active(prefix)
    info['version'] = ver
    info['mpi_version'] = mpi_ver
    info['prefix'] = prefix
    info['configure'] = ""
    info['conf_params'] = []
    info['default_name'] = "openmpi-{}".format(ver)
    info['c'] = ompi.get('bindings:c')
    info['c++'] = ompi.get('bindings:cxx')
    info['fortran'] = ompi.get('bindings:mpif.h')
    info['default_name'] = "openmpi-{}".format(ver)

    info['cuda'] = ompi.get('mca:opal:base:param:opal_built_with_cuda_support')

    return info


def mkdir_p(path):
    if not os.path.exists(path):
        os.makedirs(path)


DefaultConf = {
    'mpich': {
    },
    'mvapich': {
    },
    'openmpi': {
    },
}


class Manager(object):
    def __init__(self, root_dir):
        self._root_dir = root_dir
        self._vers_dir = os.path.join(os.environ.get("MPIENV_VERSIONS_DIR") or
                                      os.path.join(root_dir, 'versions'))
        self._shims_dir = os.path.join(self._vers_dir, 'shims')
        pybin = os.path.realpath(sys.executable)
        pybin_enc = re.sub(r'[^a-zA-Z0-9.]', '_', re.sub('^/', '', pybin))

        self._mpi_dir = os.path.join(self._vers_dir, 'mpi')
        self._pylib_dir = os.path.join(self._vers_dir, 'pylib', pybin_enc)
        self._cache_dir = os.environ.get("MPIENV_CACHE_DIR",
                                         os.path.join(root_dir, 'cache'))
        self._build_dir = os.environ.get("MPIENV_BUILD_DIR",
                                         os.path.join(root_dir, 'builds'))

        mkdir_p(self._vers_dir)
        mkdir_p(self._mpi_dir)
        mkdir_p(self._pylib_dir)
        mkdir_p(self._cache_dir)
        mkdir_p(self._build_dir)

        self._load_mpi_info()
        self._load_config()

    def root_dir(self):
        return self._root_dir

    def build_dir(self):
        return self._build_dir

    def cache_dir(self):
        return self._cache_dir

    def mpi_dir(self):
        return self._mpi_dir

    def pylib_dir(self):
        return self._pylib_dir

    def _load_mpi_info(self):
        # Get the current status of the MPI environment.
        self._installed = {}
        for prefix in glob.glob(os.path.join(self._mpi_dir, '*')):
            name = os.path.split(prefix)[-1]
            info = self.get_info(prefix)
            info['name'] = name
            self._installed[name] = info

    def _load_config(self):
        conf_json = os.path.join(self._root_dir, "config.json")
        if os.path.exists(conf_json):
            with open(conf_json) as f:
                conf = json.load(f)
        else:
            sys.stderr.write("Warning: Cannot find config file\n")
            conf = {}

        self._conf = DefaultConf.copy()
        self._conf.update(conf)

    def get_info_from_prefix(self, prefix):
        info = {}
        mpiexec = os.path.join(prefix, 'bin', 'mpiexec')
        mpi_h = os.path.join(prefix, 'include', 'mpi.h')

        p = Popen([mpiexec, '--version'], stderr=PIPE, stdout=PIPE)
        out, err = p.communicate()
        ver_str = decode(out + err)

        if re.search(r'OpenRTE', ver_str, re.MULTILINE):
            info.update(_get_info_ompi(prefix))

        if re.search(r'HYDRA', ver_str, re.MULTILINE):
            # MPICH or MVAPICH
            # if mpi.h is installed, check it to identiy
            # the MPI type.
            # This is because MVAPCIH uses MPICH's mpiexec,
            # so we cannot distinguish them only from mpiexec.
            ret = call(['grep', 'MVAPICH2_VERSION', '-q', mpi_h],
                       stderr=DEVNULL)
            if ret == 0:
                # MVAPICH
                info.update(_get_info_mvapich(prefix))
            else:
                # MPICH
                # on some platform, sometimes only runtime
                # is installed and developemnt kit (i.e. compilers)
                # are not installed.
                # In this case, we assume it's mpich.
                info.update(_get_info_mpich(prefix))

        if info is None:
            sys.stderr.write("ver_str = {}\n".format(ver_str))
            raise RuntimeError("Unknown MPI type '{}'".format(mpiexec))

        for bin in ['mpiexec', 'mpicc', 'mpicxx']:
            info[bin] = os.path.realpath(os.path.join(prefix, 'bin', bin))

        return info

    def prefix(self, name):
        return os.path.join(self._mpi_dir, name)

    def get_info(self, name):
        """Obtain information of the MPI installed under prefix."""
        info = {}

        mpiexec = os.path.join(self.prefix(name), 'bin', 'mpiexec')
        if is_broken_symlink(self.prefix(name)):
            # This means the symlink under versions/ directory
            # is broken.
            # (The installed MPI has been removed after registration)
            return {
                'name': name,
                'broken': True,
            }
        elif not os.path.exists(mpiexec):
            # If `name` does not exist
            return None
        else:
            # If `name` exists (would be the most cases)
            info['broken'] = False

        info['symlink'] = os.path.islink(self.prefix(name))

        info.update(self.get_info_from_prefix(self.prefix(name)))
        return info

    def items(self):
        return self._installed.items()

    def keys(self):
        return self._installed.keys()

    def __getitem__(self, key):
        return self._installed[key]

    def __contains__(self, key):
        return key in self._installed

    def mpiexec(self, name):
        return os.path.realpath(os.path.join(
            self._mpi_dir, name, 'bin', 'mpiexec'))

    def is_installed(self, path):
        # Find mpiexec in the path or something and check if it is already
        # under our control.
        assert type(path) == str or type(path) == bytes
        mpiexec = None
        path = os.path.realpath(path)
        if os.path.isdir(path):
            mpiexec = os.path.realpath(os.path.join(path, 'bin', 'mpiexec'))
        else:
            raise RuntimeError("todo: path={}".format(path))

        for name, info in self.items():
            if info.get('mpiexec', None) == mpiexec:
                return name

        return None

    def get_current_name(self):
        try:
            return next(name for name, info in self.items() if info['active'])
        except StopIteration:
            raise UnknownMPI()

    def add(self, prefix, name=None):
        info = self.get_info(prefix)

        if info is None:
            sys.stderr.write("Cannot find MPI in {}\n".format(prefix))
            exit(-1)

        n = self.is_installed(prefix)
        if n is not None:
            raise RuntimeError("{} is already managed "
                               "as '{}'".format(prefix, n))

        if self._installed.get(name) is not None:
            raise RuntimeError("Specifed name '{}' is "
                               "already taken".format(name))
        else:
            name = info['default_name']
            if name in self:
                raise RuntimeError("Recommended name for {} is {}, "
                                   "but the name is "
                                   "already used.".format(prefix, name))

        # dst -> src
        dst = os.path.join(self._mpi_dir, name)
        src = prefix

        os.symlink(src, dst)

        return name

    def rm(self, name, prompt=False):
        if name not in self:
            raise RuntimeError("No such MPI: '{}'".format(name))

        info = self.get_info(name)

        if not info.get('broken') and info['active']:
            sys.stderr.write("You cannot remove active MPI: "
                             "'{}'\n".format(name))
            exit(-1)

        path = os.path.join(self._mpi_dir, name)

        if (not prompt) or yes_no_input("Remove '{}' ?".format(name)):
            if info['symlink']:
                os.remove(path)
            else:
                shutil.rmtree(path)

    def rename(self, name_from, name_to):
        if name_from not in self:
            raise RuntimeError("No such MPI: '{}'".format(name_from))

        if name_to in self:
            raise RuntimeError("Name '{}' already exists".format(name_to))

        path_from = os.path.join(self._mpi_dir, name_from)
        path_to = os.path.join(self._mpi_dir, name_to)

        shutil.move(path_from, path_to)

    def use(self, name, mpi4py=False):
        if name not in self:
            sys.stderr.write("mpienv-use: Error: "
                             "unknown MPI installation: "
                             "'{}'\n".format(name))
            exit(-1)

        if os.path.exists(self._shims_dir):
            shutil.rmtree(self._shims_dir)

        os.mkdir(self._shims_dir)

        for d in ['bin', 'lib', 'include', 'libexec']:
            dr = os.path.join(self._shims_dir, d)
            if not os.path.exists(dr):
                os.mkdir(dr)

        info = self.get_info(name)

        if info.get('broken'):
            sys.stderr.write("mpienv-use: Error: "
                             "'{}' seems to be broken. Maybe it is removed.\n"
                             "".format(name))
            exit(-1)

        if info['type'] == 'MPICH':
            self._use_mpich(info['prefix'])
        elif info['type'] == 'Open MPI':
            self._use_openmpi(info['prefix'])
        elif info['type'] == 'MVAPICH':
            self._use_mvapich(info['prefix'])
        else:
            raise RuntimeError('Internal Error: '
                               'unknown MPI type: "{}"'.format(info['type']))

        if mpi4py:
            mpi4py = MPI4Py(self, name)
            if not mpi4py.is_installed():
                mpi4py.install()
            mpi4py.use()

    def exec_(self, cmds):
        envs = os.environ.copy()

        try:
            name = self.get_current_name()

            mpi4py = MPI4Py(self, name)
            if mpi4py.is_installed():
                envs['PYTHONPATH'] = mpi4py.pylib_dir()

            info = self.get_info(name)

            # TODO(keisukefukuda): if hostfile is given, convert it

        except UnknownMPI:
            raise RuntimeError("Internal Error: Unknown MPI")

        if info['broken']:
            sys.stderr.write("Error: the current MPI is broken\n")
            exit(-1)

        if info['type'] == 'Open MPI':
            pref = self.prefix(name)
            if os.path.islink(pref):
                pref = os.readlink(pref)

            cmds[:0] = ['--prefix', pref]
            cmds[:0] = ['-x', 'PYTHONPATH']
            # Transfer some environ vars
            vars = ['PATH', 'LD_LIBRARY_PATH']  # vars to be transferred
            vars += [v for v in os.environ if v.startswith('OMPI_')]
            for var in vars:
                if var in envs:
                    cmds[:0] = ['-x', var]

        elif info['type'] in ['MPICH', 'MVAPICH']:
            cmds[:0] = ['-genvlist', 'PATH,LD_LIBRARY_PATH,PYTHONPATH']

        # sys.stderr.write("{}\n".format(info['type']))

        mpiexec = os.path.realpath(
            os.path.join(self.prefix(name), 'bin', 'mpiexec'))

        cmds[:0] = [mpiexec]

        # sys.stderr.write(' '.join(cmds) + "\n")
        p = Popen(cmds, env=envs)
        p.wait()
        exit(p.returncode)

    def _mirror_file(self, f, dst_dir):
        dst = os.path.join(dst_dir, os.path.basename(f))

        if os.path.islink(f):
            src = os.path.realpath(f)
            os.symlink(src, dst)
        elif os.path.isdir(f):
            src = f
            os.symlink(src, dst)
        else:
            # ordinary files
            src = f
            os.symlink(src, dst)

    def _use_mpich(self, prefix):
        bin_files = _glob_list([prefix, 'bin'],
                               ['hydra_*',
                                'mpi*',
                                'parkill'])

        lib_files = _glob_list([prefix, 'lib'],
                               ['lib*mpi*.*',
                                'lib*mpl*.*',
                                'libopa.*'])

        inc_files = _glob_list([prefix, 'include'],
                               ['mpi*.h',
                                'mpi*.mod',
                                'opa*.h',
                                'primitives'])

        for f in bin_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'bin'))

        for f in lib_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'lib'))

        for f in inc_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'include'))

    def _use_mvapich(self, prefix):
        self._use_mpich(prefix)
        libexec_files = _glob_list([prefix, 'libexec'],
                                   ['osu-micro-benchmarks'])
        for f in libexec_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'libexec'))

    def _use_openmpi(self, prefix):
        bin_files = _glob_list([prefix, 'bin'],
                               ['mpi*',
                                'ompi-*',
                                'ompi_*',
                                'orte*',
                                'opal_'])

        lib_files = _glob_list([prefix, 'bin'],
                               ['libmpi*',
                                'libmca*',
                                'libompi*',
                                'libopen-pal*',
                                'libopen-rte*',
                                'openmpi',
                                'pkgconfig'])

        inc_files = _glob_list([prefix, 'include'],
                               ['mpi*.h', 'openmpi'])

        for f in bin_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'bin'))

        for f in lib_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'lib'))

        for f in inc_files:
            self._mirror_file(f, os.path.join(self._shims_dir, 'include'))


_root_dir = (os.environ.get("MPIENV_ROOT", None) or
             os.path.join(os.path.expanduser('~'), '.mpienv'))
manager = Manager(_root_dir)
