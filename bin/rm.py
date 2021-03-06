# coding: utf-8

import argparse

from common import manager


parser = argparse.ArgumentParser(
    prog='mpienv rm', description='Remove a specific MPI environment.')
parser.add_argument('targets', type=str, nargs='+')
parser.add_argument('-i', action="store_true", default=False)


def main():
    args = parser.parse_args()

    # Remove a link
    for trg in args.targets:
        manager.rm(trg, prompt=args.i)


if __name__ == "__main__":
    main()
