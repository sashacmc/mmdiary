#!/usr/bin/python3

import whisper
import os
import sys
import logging
import log
import json
import time

from photo_importer import fileprop
from photo_importer import config as pi_config
from datetime import datetime

TIME_OUT_FORMAT = "%Y-%m-%d %H:%M:%S"


class Transcriber(object):
    def __init__(self, model):
        logging.info("Transcriber initialization...")
        self.__fileprop = fileprop.FileProp(pi_config.Config())
        self.__model = whisper.load_model(model)
        self.__modelname = "whisper/" + model
        logging.info("Transcriber inited")

    def transcribe(self, file):
        return self.__model.transcribe(file, language="ru")

    def extract_caption(self, text):
        res = ""
        if len(text) != 0:
            res = text[0].upper()
            for ch in text[1:]:
                res += ch
                if ch in ('\n', '.', '?', '!', ';'):
                    break
        return res

    def to_text(self, res):
        if "segments" in res:
            return "\n".join([s.get("text", "").strip() for s in res["segments"]])
        else:
            return ""

    def duration(self, res):
        if "segments" in res:
            if len(res["segments"]) > 0:
                return res["segments"][-1]["end"]
        return 0

    def save_json(self, cont, out_file):
        with open(out_file, "w") as f:
            json.dump(cont, f, ensure_ascii=False, indent=2)

    def get_out_filename(self, in_file):
        return os.path.splitext(in_file)[0] + ".json"

    def process(self, file):
        logging.info(f"Process file: {file}")

        prop = self.__fileprop.get(file)
        if prop.type() != fileprop.AUDIO:
            logging.info(f"Not audio file, skip")
            return

        res = self.transcribe(file)
        text = self.to_text(res)

        cont = {
            "caption": self.extract_caption(text),
            "text": text,
            "model": self.__modelname,
            "type": "audio",
            "source": os.path.split(file)[1],
            "duration": self.duration(res),
            "recordtime": prop.time().strftime(TIME_OUT_FORMAT) if prop.time() is not None else "",
            "processtime": datetime.now().strftime(TIME_OUT_FORMAT),
        }

        out_file = self.get_out_filename(file)
        self.save_json(cont, out_file)

        logging.info(f"Saved to: {out_file}")


if __name__ == "__main__":
    log.initLogger()
    in_file = sys.argv[1]

    tr = Transcriber("medium")

    if os.path.isfile(in_file):
        tr.process(in_file)
    elif os.path.isdir(in_file):
        for dirpath, dirs, files in os.walk(in_file):
            for filename in files:
                fname = os.path.join(dirpath, filename)
                tr.process(fname)
