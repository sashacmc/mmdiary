#!/usr/bin/python3

import logging
import os

from photo_importer import config as pi_config
from photo_importer import fileprop

from mmdiary.utils import jsoncache

TIME_OUT_FORMAT = "%Y-%m-%d %H:%M:%S"

JSON_EXT = ".json"
MP4_EXT = ".mp4"

NO_SCAN_MARKER = ".mmdiaryskip"

g_fileprop = fileprop.FileProp(pi_config.Config())
g_cache = jsoncache.JsonCache()


class MediaFile:
    def __init__(self, filename, jsonname=None):
        if filename is None and jsonname is None:
            raise UserWarning("filename and jsonname is None")

        self.__filename = filename
        if self.__filename is None:
            self.__filename = os.path.splitext(jsonname)[0] + MP4_EXT

        self.__jsonname = jsonname
        if self.__jsonname is None:
            self.__jsonname = os.path.splitext(filename)[0] + JSON_EXT

        self.__have_file = self.__filename is not None and os.path.exists(self.__filename)
        self.__have_json = self.__jsonname is not None and os.path.exists(self.__jsonname)

        self.__prop = None
        self.__json = None

    def name(self):
        return self.__filename

    def json_name(self):
        return self.__jsonname

    def have_json(self):
        return self.__have_json

    def have_file(self):
        return self.__have_file

    def load_json(self):
        if not self.have_json():
            return None

        return g_cache.get(self.json_name())

    def save_json(self, cont):
        g_cache.set(cont, self.json_name())
        self.__json = cont
        self.__have_json = True

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
        return self.__filename if self.__filename is not None else self.__jsonname

    def __str__(self):
        return self.__filename if self.__filename is not None else self.__jsonname

    def type(self):
        return self.json()["type"]

    def recordtime(self):
        return self.json()["recordtime"]

    def recorddate(self):
        return get_date_from_timestring(self.recordtime())

    def state(self):
        return self.json().get("state")

    def get_field(self, filedname):
        return self.json()[filedname]

    def have_field(self, filedname):
        return filedname in self.json()

    def update_fields(self, fields):
        if self.have_json():
            self.json().update(fields)
        else:
            self.__json = fields
        self.save_json({k: v for k, v in self.__json.items() if v is not None})

    def remove_json(self):
        if not self.__have_json:
            return
        os.unlink(self.json_name())
        self.__json = None
        self.__have_json = False


class MediaLib:
    def __init__(self, root):
        self.__root = root

        self.__supported_exts = []
        for ext, tp in g_fileprop.EXT_TO_TYPE.items():
            if tp in (fileprop.AUDIO, fileprop.VIDEO):
                self.__supported_exts.append(ext)

    def __on_walk_error(self, err):
        logging.error('scan files error: %s', err)

    def __scan_files(self, inpath):
        res_files = {}
        json_files = {}
        for root, _, files in os.walk(inpath, onerror=self.__on_walk_error):
            if NO_SCAN_MARKER in files:
                continue
            for fname in files:
                base, ext = os.path.splitext(fname)
                lext = ext.lower()
                full_name = os.path.join(root, fname)
                if lext in self.__supported_exts:
                    if base in res_files:
                        logging.error('duplicate %s, %s', full_name, res_files[base])
                    res_files[base] = full_name
                elif lext == JSON_EXT:
                    json_files[base] = full_name

        return res_files, json_files

    def get_all(self):
        files, json_files = self.__scan_files(self.__root)
        return [
            MediaFile(files.get(base, None), json_files.get(base, None))
            for base in set(files.keys()) | set(json_files.keys())
        ]

    def get_processed(self, should_have_file=True):
        return sorted(
            list(
                filter(
                    lambda mf: mf.have_json() and (not should_have_file or mf.have_file()),
                    self.get_all(),
                )
            )
        )

    def get_new(self):
        return sorted(list(filter(lambda mf: not mf.have_json(), self.get_all())))


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


def get_time_from_timestring(time):
    return time[10:]


def main():
    lib = MediaLib(os.getenv("MMDIARY_AUDIO_LIB_ROOT"))
    for f in lib.get_new():
        print(f)


if __name__ == "__main__":
    main()
