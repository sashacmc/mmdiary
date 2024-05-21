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
Concatente diary videos and generate aggregated JSON file
Please declare enviromnent variables before use:
    MMDIARY_VIDEO_LIB_ROOTS - List of video library root dirs
    MMDIARY_VIDEO_WORK_DIR - Work dir for temp files (can be huge!) 
    MMDIARY_VIDEO_RES_DIR - Result dir
"""


class VideoProcessor:
    def __init__(self, update_existing, json_only, force, dry_run):
        self.__update_existing = update_existing
        self.__json_only = json_only
        self.__force = force
        self.__dry_run = dry_run
        self.__work_dir = os.getenv("MMDIARY_VIDEO_WORK_DIR")
        if not self.__work_dir:
            raise UserWarning("MMDIARY_VIDEO_WORK_DIR not defined")
        os.makedirs(self.__work_dir, exist_ok=True)
        self.__res_dir = os.getenv("MMDIARY_VIDEO_RES_DIR")
        if not self.__res_dir:
            raise UserWarning("MMDIARY_VIDEO_WORK_DIR not defined")
        os.makedirs(self.__res_dir, exist_ok=True)

        self.__lib = datelib.DateLib()

    def __check_info_changed(self, mfiles, res_mf):
        if not res_mf.have_field("videos"):
            return len(mfiles) != 0

        videos = {info["name"]: info for info in res_mf.get_field("videos")}
        if len(videos) != len(mfiles):
            return True

        for mf in mfiles:
            if mf.name() not in videos:
                return True
            info = videos[mf.name()]
            if (
                info["caption"] != mf.get_field("caption").strip()
                or info["text"] != mf.get_field("text").strip()
                or info["timestamp"] != mf.get_field("recordtime")
            ):
                return True
        return False

    def __process_date(self, date):
        logging.info("Start: %s", date)
        res_mf = self.__lib.results()[date]
        starttime = datetime.now()
        mfiles = self.__lib.get_files_by_date(date, for_upload=True)
        fnames = [mf.name() for mf in mfiles]
        logging.info("found %i files", len(fnames))

        if not self.__force and not self.__check_info_changed(mfiles, res_mf):
            logging.debug("Date: %s not chnaged, skip", date)
            return None

        if os.path.exists(res_mf.name()) and not self.__json_only:
            logging.debug("Remove existing result: %s", res_mf.name())
            os.unlink(res_mf.name())

        fileinfos = mixvideoconcat.concat(
            fnames, res_mf.name(), self.__work_dir, dry_run=(self.__json_only or self.__dry_run)
        )

        videos_info = []
        for mf, info in zip(mfiles, fileinfos):
            mf_info = mf.json()
            info["caption"] = mf_info["caption"].strip()
            info["text"] = mf_info["text"].strip()
            info["timestamp"] = mf_info["recordtime"]
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
        logging.info("Done: %s: %s", date, res_mf.json_name())
        return fields

    def process_date(self, date):
        if not self.__update_existing and not self.__json_only:
            if self.__lib.get_state(date) != datelib.STATE_NONE:
                logging.warning("date: %s already processed, skip", date)
                return

        if not self.__dry_run:
            old_state = self.__lib.get_state(date)
            self.__lib.set_in_progress(date)
            try:
                fields = self.__process_date(date)
                if fields is not None:
                    self.__lib.set_converted(date, fields)
                else:
                    self.__lib.set_state(date, old_state)
            except:
                self.__lib.set_state(date, old_state)
                raise
        else:
            fields = self.__process_date(date)
            logging.debug("dry_run result: %s", fields)

    def process_all(self, masks):
        toprocess = []
        if self.__update_existing:
            toprocess = sorted(self.__lib.get_converted(masks) + self.__lib.get_uploaded(masks))
        else:
            toprocess = self.__lib.get_nonprocessed(masks)

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
    parser.add_argument("-l", "--logfile", help="Log file", default=None)
    parser.add_argument(
        "-u", "--update", help="Update already processed, if changed", action="store_true"
    )
    parser.add_argument("-f", "--force", help="Force update already processed", action="store_true")
    parser.add_argument(
        "-d", "--dry-run", help="Only analize, without real changes", action="store_true"
    )
    parser.add_argument(
        "--json-only",
        help="Only generate JSONs without video files generation",
        action="store_true",
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(args.logfile, logging.DEBUG)
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

    vp = VideoProcessor(args.update, args.json_only, args.force, args.dry_run)

    vp.process_all(args.dates)

    logging.info("Processor done.")


if __name__ == "__main__":
    main()
