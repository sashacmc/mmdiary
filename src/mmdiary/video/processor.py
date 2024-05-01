#!/usr/bin/python3

import argparse
import json
import logging
import os
import random
from datetime import datetime

import datelib
import log
import mixvideoconcat
import progressbar
from audiolib import TIME_OUT_FORMAT


class VideoProcessor:
    def __init__(self, update_existing):
        self.__update_existing = update_existing
        self.__work_dir = os.getenv("VIDEO_PROCESSOR_WORK_DIR")
        os.makedirs(self.__work_dir, exist_ok=True)
        self.__res_dir = os.getenv("VIDEO_PROCESSOR_RES_DIR")
        os.makedirs(self.__res_dir, exist_ok=True)

        self.__lib = datelib.DateLib()

    def __save_json(self, videos_info, processduration, filename):
        data = {
            "videos": videos_info,
            "processduration": processduration,
            "processtime": datetime.now().strftime(TIME_OUT_FORMAT),
            "type": "mergedvideo",
        }
        with open(filename, "w", encoding="utf-8") as f:
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
            fnames, resfilename, self.__work_dir, dry_run=False
        )

        videos_info = []
        for af, info in zip(afiles, fileinfos):
            af_info = af.load_json()
            info["caption"] = af_info["caption"].strip()
            info["text"] = af_info["text"].strip()
            info["timestamp"] = af.prop().time().strftime(TIME_OUT_FORMAT)
            videos_info.append(info)

        processduration = (datetime.now() - starttime).total_seconds()
        self.__save_json(videos_info, processduration, resfilename_json)

        logging.info("Done: %s", date)

    def process_date(self, date):
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
        nonprocessed = list(self.__lib.get_nonprocessed())
        random.shuffle(nonprocessed)

        pbar = progressbar.ProgressBar(
            maxval=len(nonprocessed),
            widgets=[
                "Process: ",
                progressbar.SimpleProgress(),
                " (",
                progressbar.Percentage(),
                ") ",
                progressbar.Bar(),
                ' ',
                progressbar.ETA(),
            ],
        ).start()

        for date, _ in nonprocessed:
            try:
                self.process_date(date)
            except Exception:
                logging.exception("Video processing failed")
            pbar.increment()

        pbar.finish()


def __args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument("dates", nargs="*", help="Date to process")
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument(
        '-u', '--update', help='Update existing', action='store_true'
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

    vp = VideoProcessor(args.update)

    if len(args.dates) == 0:
        vp.process_all()
    else:
        for date in args.dates:
            vp.process_date(date)

    logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Main failed")
