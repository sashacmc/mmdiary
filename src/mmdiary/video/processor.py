#!/usr/bin/python3
# pylint: disable=too-many-arguments

import argparse
import json
import logging
import os
import random
from datetime import datetime

import mixvideoconcat

from mmdiary.utils import log, datelib, progressbar
from mmdiary.utils.medialib import TIME_OUT_FORMAT


DESCRIPTION = """
Concatente siary videos and generate aggregated JSON file
Please declare enviromnent variables before use:
    VIDEO_LIB_ROOTS - List of video library root dirs
    VIDEO_LIB_DB - sqlite3 DB for store library state
    VIDEO_PROCESSOR_WORK_DIR - Work dir for temp files (can be huge!) 
    VIDEO_PROCESSOR_RES_DIR - Result dir
"""


class VideoProcessor:
    def __init__(self, update_existing, json_only):
        self.__update_existing = update_existing
        self.__json_only = json_only
        self.__work_dir = os.getenv("VIDEO_PROCESSOR_WORK_DIR")
        if not self.__work_dir:
            raise UserWarning("VIDEO_PROCESSOR_WORK_DIR not defined")
        os.makedirs(self.__work_dir, exist_ok=True)
        self.__res_dir = os.getenv("VIDEO_PROCESSOR_RES_DIR")
        if not self.__res_dir:
            raise UserWarning("VIDEO_PROCESSOR_WORK_DIR not defined")
        os.makedirs(self.__res_dir, exist_ok=True)

        self.__lib = datelib.DateLib()

    def __save_json(self, videos_info, processduration, date, filename, jsonname):
        data = {
            "videos": videos_info,
            "processduration": processduration,
            "processtime": datetime.now().strftime(TIME_OUT_FORMAT),
            "source": os.path.split(filename)[1],
            "recordtime": date,
            "type": "mergedvideo",
        }
        with open(jsonname, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def __process_date(self, date):
        logging.info("Start: %s", date)
        starttime = datetime.now()
        afiles = self.__lib.get_files_by_date(date, for_upload=True)
        fnames = [af.name() for af in afiles]
        logging.info("found %i files", len(fnames))

        resfilename = os.path.join(self.__res_dir, f"{date}.mp4")
        resfilename_json = os.path.join(self.__res_dir, f"{date}.json")
        fileinfos = mixvideoconcat.concat(
            fnames, resfilename, self.__work_dir, dry_run=self.__json_only
        )

        videos_info = []
        for af, info in zip(afiles, fileinfos):
            af_info = af.load_json()
            info["caption"] = af_info["caption"].strip()
            info["text"] = af_info["text"].strip()
            info["timestamp"] = af.prop().time().strftime(TIME_OUT_FORMAT)
            videos_info.append(info)

        processduration = (datetime.now() - starttime).total_seconds()
        self.__save_json(videos_info, processduration, date, resfilename, resfilename_json)

        logging.info("Done: %s: %s", date, resfilename_json)

    def process_date(self, date):
        if not self.__update_existing and not self.__json_only:
            if self.__lib.get_state(date) != datelib.PROCESSED_NONE:
                logging.debug("date: %s already processed, skip", date)

        if not self.__lib.set_in_progress(date):
            logging.warning("date: %s already in progress", date)
            return

        try:
            self.__process_date(date)
            self.__lib.set_converted(date)
        except (Exception, KeyboardInterrupt):
            self.__lib.set_not_processed(date)
            raise

    def process_all(self):
        toprocess = []
        if self.__json_only:
            toprocess = list(self.__lib.get_converted()) + list(self.__lib.get_uploaded())
        else:
            toprocess = list(self.__lib.get_nonprocessed())
            random.shuffle(toprocess)  # REMOVE !!!

        pbar = progressbar.start("Process", len(toprocess))
        for date, _ in toprocess:
            try:
                self.process_date(date)
            except Exception:
                logging.exception("Video processing failed")
            pbar.increment()
        pbar.finish()


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "dates", nargs="*", help="Date to process (otherwise all dates will be processed)"
    )
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument('-u', '--update', help='Update existing', action='store_true')
    parser.add_argument(
        '--json-only',
        help='Only regenerate existing JSONs without video files regeneration',
        action='store_true',
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

    vp = VideoProcessor(args.update, args.json_only)

    if len(args.dates) == 0:
        vp.process_all()
    else:
        for date in args.dates:
            vp.process_date(date)

    logging.info("Processor done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Video processor main failed")
