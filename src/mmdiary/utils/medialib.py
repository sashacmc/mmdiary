#!/usr/bin/python3

import json
import logging
import os

from photo_importer import config as pi_config
from photo_importer import fileprop

TIME_OUT_FORMAT = "%Y-%m-%d %H:%M:%S"

JSON_EXT = ".json"

g_fileprop = fileprop.FileProp(pi_config.Config())


class MediaFile:
    def __init__(self, filename):
        self.__filename = filename
        self.__prop = None
        self.__json = None

    def name(self):
        return self.__filename

    def json_name(self):
        return os.path.splitext(self.name())[0] + JSON_EXT

    def has_json(self):
        return os.path.exists(self.json_name())

    def load_json(self):
        if not self.has_json():
            return None

        with open(self.json_name(), "r", encoding="utf-8") as f:
            return json.load(f)

    def save_json(self, cont):
        with open(self.json_name(), "w", encoding="utf-8") as f:
            json.dump(cont, f, ensure_ascii=False, indent=2)
        self.__json = cont

    def json(self):
        if self.__json is None:
            self.__json = self.load_json()
        return self.__json

    def prop(self):
        if self.__prop is None:
            self.__prop = g_fileprop.get(self.name())
        return self.__prop

    def __lt__(self, other):
        return self.name() < other.name()

    def __repr__(self):
        return self.__filename

    def __str__(self):
        return self.__filename


class MediaLib:
    def __init__(self, root=None):
        if root is None:
            root = os.getenv("AUDIO_NOTES_ROOT")  # TODO: made proper init
        self.__root = root

        self.__supported_exts = []
        for ext, tp in g_fileprop.EXT_TO_TYPE.items():
            if tp in (fileprop.AUDIO, fileprop.VIDEO):
                self.__supported_exts.append(ext)

    def __on_walk_error(self, err):
        logging.error('scan files error: %s', err)

    def __scan_files(self, inpath):
        res = []
        for root, _, files in os.walk(inpath, onerror=self.__on_walk_error):
            dup = set()
            for fname in files:
                base, ext = os.path.splitext(fname)
                if ext.lower() in self.__supported_exts:
                    if base in dup:
                        logging.error('duplicate %s in %s', base, root)
                    res.append(os.path.join(root, fname))
                    dup.add(base)

        res.sort()
        return res

    def get_all(self):
        files = self.__scan_files(self.__root)
        return [MediaFile(f) for f in files]

    def get_processed(self):
        return list(filter(lambda af: af.has_json(), self.get_all()))

    def get_new(self):
        return list(filter(lambda af: not af.has_json(), self.get_all()))


def split_large_text(text, max_block_size):
    block_len = 0
    block = []
    blocks = []
    for s in text.split("\n"):
        s_len = len(s) + 1
        if block_len + s_len < max_block_size:
            block.append(s)
            block_len += s_len
        else:
            blocks.append("\n".join(block))
            block = []
            block_len = 0

    if len(block) != 0:
        blocks.append("\n".join(block))

    return blocks


def get_date_from_timestring(time):
    return time[:10]


def main():
    lib = MediaLib()
    for f in lib.get_new():
        print(f)


if __name__ == "__main__":
    main()
