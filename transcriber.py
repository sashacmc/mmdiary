#!/usr/bin/python3

import argparse
import whisper
import os
import logging
import progressbar

import log
import audiolib

from photo_importer import fileprop
from datetime import datetime

TIME_OUT_FORMAT = "%Y-%m-%d %H:%M:%S"


class Transcriber(object):
    def __init__(self, model):
        logging.info("Transcriber initialization...")
        self.__model = whisper.load_model(model)
        self.__modelname = "whisper/" + model
        logging.info("Transcriber inited")

    def transcribe(self, file):
        return self.__model.transcribe(file.name(), language="ru")

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
            return "\n".join(
                [s.get("text", "").strip() for s in res["segments"]]
            )
        else:
            return ""

    def duration(self, res):
        if "segments" in res:
            if len(res["segments"]) > 0:
                return res["segments"][-1]["end"]
        return 0

    def process(self, file):
        logging.info(f"Process file: {file}")

        prop = file.prop()
        if prop.type() not in (fileprop.AUDIO, fileprop.VIDEO):
            logging.info("Not audio file, skip")
            return

        res = self.transcribe(file)
        text = self.to_text(res)

        cont = {
            "caption": self.extract_caption(text),
            "text": text,
            "model": self.__modelname,
            "type": "audio",
            "source": os.path.split(file.name())[1],
            "duration": self.duration(res),
            "recordtime": prop.time().strftime(TIME_OUT_FORMAT)
            if prop.time() is not None
            else "",
            "processtime": datetime.now().strftime(TIME_OUT_FORMAT),
        }

        file.save_json(cont)

        logging.info(f"Saved to: {file.json_name()}")


def __args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('inpath', help='Input path')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument(
        '-u', '--update', help='Update existing', action='store_true'
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.initLogger(args.logfile)

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (audiolib.AudioFile(args.inpath),)
    elif os.path.isdir(args.inpath):
        lib = audiolib.AudioLib(args.inpath)
        fileslist = lib.get_all() if args.update else lib.get_new()

    if len(fileslist) == 0:
        return

    print("Model loading... ", end='', flush=True)
    tr = Transcriber("medium")
    print("done")

    pbar = progressbar.ProgressBar(
        maxval=len(fileslist),
        widgets=[
            "Transcribe: ",
            progressbar.SimpleProgress(),
            " (",
            progressbar.Percentage(),
            ") ",
            progressbar.Bar(),
            " ",
            progressbar.ETA(),
        ],
    ).start()

    for af in fileslist:
        try:
            tr.process(af)
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
