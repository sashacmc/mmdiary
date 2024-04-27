#!/usr/bin/python3

import os
import argparse
import json

JSON_EXT = ".json"


def load_json(file):
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def process_list(fileslist, text):
    for file in fileslist:
        data = load_json(file)
        tp = data["type"]
        if tp not in ("audio", "video"):
            return
        if text in data["caption"] or text in data["text"]:
            print(file)
            print(data["caption"])
            print(data["text"])
            print()


def scan_files(inpath):
    res = []
    for root, _, files in os.walk(inpath):
        for fname in files:
            if os.path.splitext(fname)[1] == JSON_EXT:
                res.append(os.path.join(root, fname))

    res.sort()
    return res


def args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('inpath', nargs="+", help='Input path(s)')
    parser.add_argument("text", help="Text for search")
    return parser.parse_args()


def main():
    args = args_parse()

    for path in args.inpath:
        process_list(scan_files(path), args.text)


if __name__ == '__main__':
    main()
