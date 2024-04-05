#!/usr/bin/python3

import os
import json
import logging

from photo_importer import fileprop
from photo_importer import config as pi_config

JSON_EXT = ".json"

g_fileprop = fileprop.FileProp(pi_config.Config())


class AudioFile(object):
    def __init__(self, filename):
        self.__filename = filename

    def name(self):
        return self.__filename

    def json_name(self):
        return os.path.splitext(self.name())[0] + JSON_EXT

    def has_json(self):
        return os.path.exists(self.json_name())

    def load_json(self):
        if not self.has_json():
            return None

        with open(self.json_name(), "r") as f:
            return json.load(f)

    def save_json(self, cont):
        with open(self.json_name(), "w") as f:
            json.dump(cont, f, ensure_ascii=False, indent=2)

    def prop(self):
        return g_fileprop.get(self.name())

    def __repr__(self):
        return self.__filename

    def __str__(self):
        return self.__filename


class AudioLib(object):
    def __init__(self, root):
        self.__root = root

    def __on_walk_error(self, err):
        logging.error('scan files error: %s' % err)

    def __scan_files(self, inpath):
        res = []
        for root, dirs, files in os.walk(inpath, onerror=self.__on_walk_error):
            dup = set()
            for fname in files:
                base, ext = os.path.splitext(fname)
                if ext != JSON_EXT:
                    if base in dup:
                        logging.error('duplicate %s in %s' % (base, root))
                    res.append(os.path.join(root, fname))
                    dup.add(base)

        res.sort()
        return res

    def get_all(self):
        files = self.__scan_files(self.__root)
        return [AudioFile(f) for f in files]

    def get_processed(self):
        return list(filter(lambda af: af.has_json(), self.get_all()))

    def get_new(self):
        return list(filter(lambda af: not af.has_json(), self.get_all()))


def main():
    root = os.getenv("AUDIO_NOTES_ROOT")
    lib = AudioLib(root)
    for f in lib.get_new():
        print(f.prop().type())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Main failed")
