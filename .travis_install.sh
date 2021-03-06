#!/bin/sh

mkdir -p $HOME/mpi
mkdir -p $HOME/tmp


# Install zsh
if [ ! -x $HOME/zsh/bin/zsh ]; then
    rm -f zsh-5.3.1.tar.gz
    rm -rf zsh  # clear zsh/ directory
    
    mkdir $HOME/zsh
    wget --no-check-certificate 'https://downloads.sourceforge.net/project/zsh/zsh/5.3.1/zsh-5.3.1.tar.gz?r=http%3A%2F%2Fzsh.sourceforge.net%2FArc%2Fsource.html&ts=1495843150&use_mirror=jaist' -O zsh-5.3.1.tar.gz

    tar -xf zsh-5.3.1.tar.gz
    cd zsh-5.3.1
    echo configure
    ./configure --prefix=$HOME/zsh >/dev/null 2>&1
    echo make
    make -j2  >/dev/null 2>&1
    echo make install
    make install >/dev/null 2>&1
    cd
else
    echo zsh is ready
    $HOME/zsh/bin/zsh --version
fi

PREFIX=$HOME/mpi

cd $HOME/tmp

echo ls $PREFIX
ls $PREFIX

# Remove Open MPI version which we no longer use
rm -rf $PREFIX/openmpi-1.10*

for VER in 2.1.1; do
    if [ ! -x $PREFIX/openmpi-${VER}/bin/mpiexec ]; then
        echo "==============================================="
        echo "Installing Open MPI ${VER}"
        echo "==============================================="
        VER_SHORT=$(echo $VER | grep -oE '^[0-9]+\.[0-9]+')
        wget --no-check-certificate https://www.open-mpi.org/software/ompi/v${VER_SHORT}/downloads/openmpi-${VER}.tar.gz
        tar -xf openmpi-${VER}.tar.gz
        cd openmpi-${VER}
        echo ./configure --prefix=$PREFIX/openmpi-${VER} --disable-mpi-fortran
        ./configure --prefix=$PREFIX/openmpi-${VER} \
                    --disable-mpi-fortran >/dev/null 2>&1
        echo make
        make -j4 >/dev/null 2>&1
        echo make install
        make install >/dev/null 2>&1
        cd ..
    else
        echo "Open MPI ${VER} looks good."
        $PREFIX/openmpi-${VER}/bin/mpiexec --version
    fi
    echo
    echo
done

# MPICH
cd $HOME/tmp
for VER in 3.2; do
    if [ ! -x $PREFIX/mpich-${VER}/bin/mpiexec ]; then
        echo "==============================================="
        echo "Installing MPICH ${VER}"
        echo "==============================================="
        wget --no-check-certificate http://www.mpich.org/static/downloads/${VER}/mpich-${VER}.tar.gz
        tar -xf mpich-${VER}.tar.gz
        cd mpich-${VER}
        echo ./configure
        ./configure --enable-fortran=no \
                    --enable-silent-rules \
                    --disable-dependency-tracking \
                    --prefix=$PREFIX/mpich-${VER}  >/dev/null 2>&1
        echo make
        make -j4  >/dev/null 2>&1
        echo make install
        make install  >/dev/null 2>&1
        cd ..
    else
        echo "MPICH ${VER} looks good."
        $PREFIX/mpich-${VER}/bin/mpiexec --version
    fi
    echo
    echo
done

# MVAPICH
cd $HOME/tmp
for VER in 2.2; do
    if [ ! -x $PREFIX/mvapich2-2.2/bin/mpiexec ]; then
        echo "==============================================="
        echo "Installing MVAPICH ${VER}"
        echo "==============================================="
        wget --no-check-certificate http://mvapich.cse.ohio-state.edu/download/mvapich/mv2/mvapich2-${VER}.tar.gz
        tar -xf mvapich2-${VER}.tar.gz
        cd mvapich2-${VER}
        echo ./configure
        ./configure --disable-fortran --prefix=$PREFIX/mvapich2-2.2 \
                    --disable-mcast  >/dev/null 2>&1
        echo make
        make -j4 >/dev/null 2>&1
        echo make install
        make install >/dev/null 2>&1
        cd ..
    else
        echo "MPVAPICH ${VER} looks good."
        $PREFIX/mvapich2-2.2/bin/mpiexec --version
    fi
    echo
    echo
done
