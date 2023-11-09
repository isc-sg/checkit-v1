#!/usr/bin/env python
import sys
import cython
import compare_images_v4_bg
import argparse


parser = argparse.ArgumentParser(description='Checkit image comparison')
parser.add_argument('list_of_cameras', metavar='N', type=int, nargs='*')

args = parser.parse_args()


if __name__ == '__main__':
    compare_images_v4_bg.main(args.list_of_cameras)
