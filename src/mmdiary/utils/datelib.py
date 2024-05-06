#!/usr/bin/python3

import argparse
import logging
import os

from collections import defaultdict

from mmdiary.utils import log, medialib

DESCRIPTION = """
Diary video dates DB manipulation tool
Please declare enviromnent variables before use:
    VIDEO_LIB_ROOTS - List of video library root dirs
    VIDEO_PROCESSOR_RES_DIR - Video processor result dir

Possible actions:
    list_dates - Print all dates with starus
    disable_video - Set a flag for video file to disable concatenneting and uploading,
                    also mark corresponded date as not processed for future regeneration
    set_reupload - Mark a video as not uploaded for future reupload
                   (e.g. if video was deleted on the YouTube)
"""

STATE_NONE = "none"
STATE_INPROCESS = "inprocess"
STATE_CONVERTED = "converted"
STATE_UPLOADED = "uploaded"


class DateLib:
    def __init__(self):
        self.__scan_paths = list(
            filter(
                None,
                os.getenv("VIDEO_LIB_ROOTS").split(":"),
            ),
        )
        self.__res_dir = os.getenv("VIDEO_PROCESSOR_RES_DIR")
        self.__results = None
        self.__sources = None

    def __load_results(self):
        res = {}
        logging.debug("Process results: %s", self.__res_dir)
        lib = medialib.MediaLib(self.__res_dir)
        for mf in lib.get_processed(should_have_file=False):
            res[mf.recorddate()] = mf
        return res

    def __load_sources(self):
        res = defaultdict(lambda: [])
        for path in self.__scan_paths:
            logging.debug("Process sources: %s", path)
            lib = medialib.MediaLib(path)
            for mf in lib.get_processed():
                res[mf.recorddate()].append(mf)
        return res

    def results(self):
        if self.__results is None:
            self.__results = self.__load_results()
        return self.__results

    def sources(self):
        if self.__sources is None:
            self.__sources = self.__load_sources()
        return self.__sources

    def get_state(self, date):
        if date in self.results():
            return self.results()[date].state()
        return STATE_NONE

    def set_not_processed(self, date):
        self.results()[date].update_fields({"state": STATE_NONE})

    def set_in_progress(self, date):
        fields = {"state": STATE_INPROCESS}
        if date not in self.results():
            self.results()[date] = medialib.MediaFile(
                os.path.join(self.__res_dir, date + medialib.MP4_EXT),
                os.path.join(self.__res_dir, date + medialib.JSON_EXT),
            )
            fields["recordtime"] = date
            fields["type"] = "mergedvideo"
        self.results()[date].update_fields(fields)

    def set_converted(self, date, fields):
        new_fields = {}
        new_fields.update(fields)
        new_fields["state"] = STATE_CONVERTED
        self.results()[date].update_fields(new_fields)

    def set_uploaded(self, date, url):
        self.results()[date].update_fields({"state": STATE_UPLOADED, "url": url})

    def get_nonprocessed(self):
        all_dates = set(self.sources().keys())
        processed_dates = set(self.__get_results_dates_by_state(STATE_NONE))
        return all_dates - processed_dates

    def __get_results_dates_by_state(self, state):
        res = []
        for date, mf in self.results().items():
            if mf.state() == state:
                res.append(date)
        res.sort()
        return res

    def get_converted(self):
        return self.__get_results_dates_by_state(STATE_CONVERTED)

    def get_uploaded(self):
        return self.__get_results_dates_by_state(STATE_UPLOADED)

    def get_files_by_date(self, date, for_upload=False):
        mfs = self.sources()[date]
        if for_upload:
            mfs = list(filter(lambda mf: mf.json().get("upload", True), mfs))
        mfs.sort(key=lambda mf: mf.recordtime())
        return mfs

    def __find_in_sources(self, subfilename):
        """
        Find source file by part of name or by full name
        If part matched for many files, returns None
        """
        res = None
        for mfs in self.sources().values():
            for mf in mfs:
                if subfilename == mf.name():
                    return mf
                if subfilename in mf.name():
                    if res is None:
                        res = mf
                    else:
                        return None
        return res

    def disable_video(self, filename):
        if filename is None:
            logging.warning("File not specified")
            return
        mf = self.__find_in_sources(filename)
        if mf is None:
            logging.warning("File not found or matched to many")
            return

        mf.update_fields({"upload": False})

        self.set_not_processed(mf.recorddate())
        logging.info("Video file %s disabled", mf.name())

    def list_dates(self, state):
        if state is None:
            res = {date: STATE_NONE for date in set(self.sources().keys())}
            res.update({date: mf.state() for date, mf in self.results().items()})
            res = list(res.items())
            res.sort()
            return res

        if state == STATE_NONE:
            return [(date, STATE_NONE) for date in self.get_nonprocessed()]

        return [(date, state) for date in self.__get_results_dates_by_state(state)]

    def list_disabled_videos(self):
        res = []
        for mfs in self.sources().values():
            for mf in mfs:
                if not mf.json().get("upload", True):
                    res.append(mf.name())
        res.sort()
        return res


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "-a",
        "--action",
        help="Action",
        required=True,
        choices=[
            "list_dates",
            "list_disabled_videos",
            "disable_video",
            "set_reupload",
        ],
    )
    parser.add_argument("-f", "--file", help="File name (for disable_video)")
    parser.add_argument("-e", "--date", help="Date (for set_reupload)")
    parser.add_argument("-s", "--state", help="State for (list_dates)")
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(level=logging.DEBUG)
    lib = DateLib()

    if args.action == "list_dates":
        for date, state in lib.list_dates(args.state):
            print(date, state)
    elif args.action == "list_disabled_videos":
        for filename in lib.list_disabled_videos():
            print(filename)
    elif args.action == "disable_video":
        lib.disable_video(args.file)
    elif args.action == "set_reupload":
        if lib.get_state(args.date) != STATE_UPLOADED:
            logging.warning("Specified date not yet uploaded: %s", args.date)
        lib.set_converted(args.date, {})
    logging.info("Done.")


if __name__ == "__main__":
    main()
