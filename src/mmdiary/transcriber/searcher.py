#!/usr/bin/python3

import argparse

from mmdiary.utils import medialib

DESCRIPTION = """
Search for text in transcribed files.
"""


def process_list(fileslist, text):
    for file in fileslist:
        if file.type() not in ("audio", "video"):
            return
        if text in file.get_field("caption") or text in file.get_field("text"):
            print(file.json_name())
            print(file.get_field("caption"))
            print(file.get_field("text"))
            print()


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('inpath', nargs="+", help='Input path(s)')
    parser.add_argument("text", help="Text for search")
    return parser.parse_args()


def main():
    args = __args_parse()

    for path in args.inpath:
        lib = medialib.MediaLib(path)
        process_list(lib.get_processed(should_have_file=False), args.text)


if __name__ == '__main__':
    main()
