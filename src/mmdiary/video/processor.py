#!/usr/bin/python3
# pylint: disable=too-many-arguments

import argparse
import logging
import os
from datetime import datetime

import mixvideoconcat

from mmdiary.utils import log, datelib, progressbar
from mmdiary.utils.medialib import TIME_OUT_FORMAT


DESCRIPTION = """
Concatente siary videos and generate aggregated JSON file
Please declare enviromnent variables before use:
    VIDEO_LIB_ROOTS - List of video library root dirs
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

    def __process_date(self, date):
        logging.info("Start: %s", date)
        res_mf = self.__lib.results()[date]
        starttime = datetime.now()
        mfiles = self.__lib.get_files_by_date(date, for_upload=True)
        fnames = [mf.name() for mf in mfiles]
        logging.info("found %i files", len(fnames))

        if os.path.exists(res_mf.name()) and not self.__json_only:
            logging.debug("Remove existing result: %s", res_mf.name())
            os.unlink(res_mf.name())

        fileinfos = mixvideoconcat.concat(
            fnames, res_mf.name(), self.__work_dir, dry_run=self.__json_only
        )

        videos_info = []
        for mf, info in zip(mfiles, fileinfos):
            mf_info = mf.json()
            info["caption"] = mf_info["caption"].strip()
            info["text"] = mf_info["text"].strip()
            info["timestamp"] = mf.prop().time().strftime(TIME_OUT_FORMAT)
            videos_info.append(info)

        processduration = (datetime.now() - starttime).total_seconds()

        fields = {
            "videos": videos_info,
            "processduration": processduration,
            "processtime": datetime.now().strftime(TIME_OUT_FORMAT),
            "source": os.path.split(res_mf.name())[1],
            "recordtime": date,
            "type": "mergedvideo",
        }
        self.__lib.set_converted(date, fields)

        logging.info("Done: %s: %s", date, res_mf.json_name())

    def process_date(self, date):
        if not self.__update_existing and not self.__json_only:
            if self.__lib.get_state(date) != datelib.STATE_NONE:
                logging.warning("date: %s already processed, skip", date)
                return

        self.__lib.set_in_progress(date)
        try:
            self.__process_date(date)
        except (Exception, KeyboardInterrupt):
            self.__lib.set_not_processed(date)
            raise

    def process_all(self):
        toprocess = []
        if self.__json_only:
            toprocess = list(self.__lib.get_converted()) + list(self.__lib.get_uploaded())
        else:
            toprocess = list(self.__lib.get_nonprocessed())

        pbar = progressbar.start("Process", len(toprocess))
        for date in toprocess:
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
    main()
