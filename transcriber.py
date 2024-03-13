#!/usr/bin/python3

import argparse
import whisper
import os
import logging
import log
import json
import progressbar

from photo_importer import fileprop
from photo_importer import config as pi_config
from datetime import datetime

TIME_OUT_FORMAT = "%Y-%m-%d %H:%M:%S"
JSON_EXT = ".json"


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
        return os.path.splitext(in_file)[0] + JSON_EXT

    def process(self, file, overwrite_exiting=False):
        logging.info(f"Process file: {file}")

        out_file = self.get_out_filename(file)
        if not overwrite_exiting:
            if os.path.isfile(out_file):
                logging.info("Already processed, skip")
                return

        prop = self.__fileprop.get(file)
        if prop.type() != fileprop.AUDIO:
            logging.info("Not audio file, skip")
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

        self.save_json(cont, out_file)

        logging.info(f"Saved to: {out_file}")


def __on_walk_error(err):
    logging.error('Scan files error: %s' % err)


def __scan_files(inpath):
    res = []
    for root, dirs, files in os.walk(inpath, onerror=__on_walk_error):
        for fname in files:
            if os.path.splitext(fname)[1] != JSON_EXT:
                res.append(os.path.join(root, fname))

    res.sort()
    logging.info(f"Found {len(res)} files")
    return res


def __args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('inpath', help='Input path')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument('-u', '--update', help='Update existing', action='store_true')
    return parser.parse_args()


def main():
    args = __args_parse()
    log.initLogger(args.logfile)

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (args.inpath,)
    elif os.path.isdir(args.inpath):
        fileslist = __scan_files(args.inpath)

    if len(fileslist) == 0:
        return

    pbar = progressbar.ProgressBar(
        maxval=len(fileslist),
        widgets=[
            "Transcribe",
            ' ',
            progressbar.Percentage(),
            ' ',
            progressbar.Bar(),
            ' ',
            progressbar.ETA(),
        ],
    ).start()

    tr = Transcriber("medium")

    for fname in fileslist:
        try:
            tr.process(fname, args.update)
        except Exception:
            logging.exception("Transcribe failed")
        pbar.increment()

    pbar.finish()
    logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Main failed")
