#!/usr/bin/python3
# pylint: disable=import-outside-toplevel,too-few-public-methods

import argparse
import logging
import os
from datetime import datetime

from photo_importer import fileprop

from mmdiary.utils import log, medialib, progressbar
from mmdiary.utils.medialib import TIME_OUT_FORMAT

from mmdiary.transcriber.verifier import check_text

DESCRIPTION = """
Transcribes audio/video file(s).
Result will be saved to json file along with the original file.
Optional environment variables:
    MMDIARY_TRANSCRIBE_MODEL - Transcribe model (default: "medium")
        See details: https://github.com/openai/whisper?tab=readme-ov-file#available-models-and-languages
    MMDIARY_TRANSCRIBE_LANGUAGE - Transcribe language (default: "ru")
"""


class Transcriber:
    def __init__(self, model, language):
        import whisper

        logging.info("Transcriber initialization...")
        self.__model = whisper.load_model(model)
        self.__modelname = "whisper/" + model
        self.__language = language
        logging.info("Transcriber inited")

    def __transcribe(self, file):
        return self.__model.transcribe(file.name(), language=self.__language)

    def __extract_caption(self, text):
        res = ""
        if len(text) != 0:
            res = text[0].upper()
            for ch in text[1:]:
                res += ch
                if ch in ('\n', '.', '?', '!', ';'):
                    break
        return res.strip()

    def __to_text(self, res):
        if "segments" in res:
            return "\n".join([s.get("text", "").strip() for s in res["segments"]])
        return ""

    def __duration(self, res):
        if "segments" in res:
            if len(res["segments"]) > 0:
                return res["segments"][-1]["end"]
        return 0

    def process(self, file):
        logging.info("Process file: %s", file)

        prop = file.prop()
        tp = ""
        if prop.type() == fileprop.AUDIO:
            tp = "audio"
        elif prop.type() == fileprop.VIDEO:
            tp = "video"
        else:
            logging.info("Not audio file, skip")
            return

        res = self.__transcribe(file)
        text = self.__to_text(res)
        text = check_text(text, self.__language)

        cont = {
            "caption": self.__extract_caption(text),
            "text": text,
            "model": self.__modelname,
            "type": tp,
            "source": os.path.split(file.name())[1],
            "duration": self.__duration(res),
            "recordtime": prop.time().strftime(TIME_OUT_FORMAT) if prop.time() is not None else "",
            "processtime": datetime.now().strftime(TIME_OUT_FORMAT),
        }

        file.save_json(cont)

        logging.info("Saved to: %s", file.json_name())


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('inpath', help='Input path (single file or dir for search)')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument('-u', '--update', help='Update existing', action='store_true')
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)

    fileslist = []
    if os.path.isfile(args.inpath):
        fileslist = (medialib.MediaFile(args.inpath),)
    elif os.path.isdir(args.inpath):
        lib = medialib.MediaLib(args.inpath)
        fileslist = lib.get_all() if args.update else lib.get_new()

    if len(fileslist) == 0:
        return

    print("Model loading... ", end='', flush=True)
    tr = Transcriber(
        os.getenv("MMDIARY_TRANSCRIBE_MODEL", "medium"),
        os.getenv("MMDIARY_TRANSCRIBE_LANGUAGE", "ru"),
    )
    print("done")

    pbar = progressbar.start("Transcribe", len(fileslist))

    for af in fileslist:
        try:
            tr.process(af)
        except Exception:
            logging.exception("Transcribe failed")
        pbar.increment()

    pbar.finish()
    logging.info("Done.")


if __name__ == "__main__":
    main()
