# coding: utf-8

import os
import os.path
import re
import shutil
from subprocess import check_call
import sys

_ompi_url = ('https://www.open-mpi.org/software/ompi/'
             'v{}/downloads/openmpi-{}.tar.bz2')

_mpich_url = ('http://www.mpich.org/static/'
              'downloads/{}/mpich-{}.tar.gz')

_mv_url = ('http://mvapich.cse.ohio-state.edu'
           '/download/mvapich/mv2/mvapich2-{}.tar.gz')

_list = {
    'openmpi-1.10.7': {
        'type': 'openmpi',
        'ver': '1.10.7',
        'url': _ompi_url.format('1.10', '1.10.7'),
    },
    'openmpi-2.0.3': {
        'type': 'openmpi',
        'ver': '2.0.3',
        'url': _ompi_url.format('2.0', '2.0.3'),
    },
    'openmpi-2.1.1': {
        'type': 'openmpi',
        'ver': '2.1.1',
        'url': _ompi_url.format('2.1', '2.1.1'),
    },
    'mpich-3.1.4': {
        'type': 'mpich',
        'ver': '3.1.4',
        'url': _mpich_url.format('3.1.4', '3.1.4'),
    },
    'mpich-3.2': {
        'type': 'mpich',
        'ver': '3.2',
        'url': _mpich_url.format('3.2', '3.2'),
    },
    'mpich-3.3a': {
        'type': 'mpich',
        'ver': '3.3a',
        'url': _mpich_url.format('3.3a', '3.3a'),
    },
    'mvapich-2.2': {
        'type': 'mvapich',
        'ver': '2.2',
        'url': _mv_url.format('2.2'),
    },
    'mvapich-2.3a': {
        'type': 'mvapich',
        'ver': '2.3a',
        'url': _mv_url.format('2.3a'),
    },
}


class BaseInstaller(object):
    def __init__(self, manager, mpi, name, verbose):
        self.mpi = mpi
        self.manager = manager
        self.name = name

        self.url = _list[mpi]['url']

        # Downloaded file name
        self.local_file = os.path.join(self.manager.cache_dir(),
                                       os.path.basename(self.url))

        # build directory name
        dir_bname = re.sub(r'(\.tar\.(gz|bz2))|(\.tgz)$',
                           '',
                           os.path.basename(self.url))

        self.ext_path = os.path.join(self.manager.build_dir(),
                                     name)
        self.dir_path = os.path.join(self.ext_path,
                                     dir_bname)

        self.prefix = os.path.join(manager.mpi_dir(), name)

        if not os.path.exists(self.ext_path):
            os.makedirs(self.ext_path)

    def clean(self):
        if os.path.exists(self.dir_path):
            print("Deleting the build directory...")
            shutil.rmtree(self.dir_path)

    def download(self):
        # TODO: check the checksum
        if not os.path.exists(self.local_file):
            with open(self.local_file, 'w') as f:
                check_call(['curl', self.url], stdout=f)

    def configure(self):
        # TODO: check configure options and re-run ./configure
        #       only when necessary
        # TODO: Support multiple verbosity level
        #       Level 0: silent
        #       Level 1: only prints "Installing..."
        #       Level 2: 
        self.download()
        print('Configuring in {}'.format(self.dir_path))

        print("ext_path={}".format(self.ext_path))
        # Extract the archive files
        if not os.path.exists(self.dir_path):
            check_call(['tar', '-xf', self.local_file],
                       cwd=self.ext_path)

        opts = os.environ.get("MPIENV_CONFIGURE_OPTS")
        if opts:
            conf_args = opts.split()
        else:
            conf_args = []

        # fix the configure argument
        try:
            idx = conf_args.index('--prefix')
            if idx >= 0:
                sys.stderr.write("Warning: --prefix argument is "
                                 "replaced by mpienv\n")
                # remove --prefix xxxx
                try:
                    conf_args[idx:idx + 2] = []
                except IndexError:
                    pass
        except ValueError:
            # If --prefix is not found
            pass

        # Check args = --help, or insert our --prefix argument
        try:
            idx = conf_args.index('--help')
            if idx >= 0:
                conf_args = ['--help']
        except ValueError:
            # if --help is not found
            conf_args += ['--prefix', self.prefix]

        print(' '.join(['./configure'] + conf_args))

        # run configure scripts
        assert(os.path.exists(self.dir_path))
        print(' '.join(['./configure'] + conf_args))
        check_call(['./configure'] + conf_args,
                   cwd=self.dir_path)

    def build(self, npar=1):
        self.configure()
        print('Building in {}'.format(self.dir_path))
        # run make
        print(' '.join(['make', '-j', str(npar)]))
        check_call(['make', '-j', str(npar)],
                   shell=True, cwd=self.dir_path)

    def install(self, npar=1):
        self.configure()
        print(' '.join(['make', 'install', '-j', str(npar)]))
        check_call(['make', 'install', '-j', str(npar)],
                   cwd=self.dir_path)


class OmpiInstaller(BaseInstaller):
    def __init__(self, *args):
        BaseInstaller.__init__(self, *args)


class MpichInstaller(BaseInstaller):
    def __init__(self, *args):
        BaseInstaller.__init__(self, *args)


class MvapichInstaller(BaseInstaller):
    def __init__(self, *args):
        BaseInstaller.__init__(self, *args)


def list_avail():
    for k in sorted(_list):
        print(' ' + k)


def create_installer(manager, mpi, name, verbose):
    if name in manager:
        sys.stderr.write("Error: MPI name "
                         "'{}' already exists.\n".format(name))
        exit(-1)

    if mpi not in _list.keys():
        sys.stderr.write("Error: Unknown MPI: '{}'\n".format(mpi))
        exit(-1)

    if name is None:
        name = mpi

    mpi_type = _list[mpi]['type']

    if mpi_type == 'openmpi':
        return OmpiInstaller(manager, mpi, name, verbose)
    elif mpi_type == 'mvapich':
        return MvapichInstaller(manager, mpi, name, verbose)
    elif mpi_type == 'mpich':
        return MpichInstaller(manager, mpi, name, verbose)

    raise RuntimeError("")
