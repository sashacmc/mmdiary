import os
import copy
import pickle
import json
import atexit


class JsonCache:
    def __init__(self):
        filename = os.getenv("MMDIARY_CACHE")
        if filename is not None:
            self.__filename = os.path.expanduser(filename)
        else:
            self.__filename = None
        self.__load()
        self.__changed = False
        atexit.register(self.__save)

    def __load(self):
        if self.__filename is None or not os.path.exists(self.__filename):
            self.__data = {}
            return
        with open(self.__filename, "rb") as f:
            self.__data = pickle.load(f)

    def __save(self):
        if self.__filename is None or not self.__changed:
            return
        tmpfile = self.__filename + ".tmp"
        with open(tmpfile, "wb") as f:
            pickle.dump(self.__data, f)
        os.replace(tmpfile, self.__filename)

    def __load_json(self, filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)

    def __save_json(self, cont, filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(cont, f, ensure_ascii=False, indent=2)

    def get(self, filename):
        try:
            file_stat = os.stat(filename)
            try:
                time, cont = self.__data[filename]
                if file_stat.st_mtime == time:
                    return copy.deepcopy(cont)
            except KeyError:
                pass
            cont = self.__load_json(filename)
            self.__data[filename] = (file_stat.st_mtime, cont)
            self.__changed = True
            return copy.deepcopy(cont)
        except FileNotFoundError:
            if filename in self.__data:
                del self.__data[filename]
                self.__changed = True
            raise

    def set(self, cont, filename):
        self.__save_json(cont, filename)
        file_stat = os.stat(filename)
        self.__data[filename] = (file_stat.st_mtime, cont)
        self.__changed = True
