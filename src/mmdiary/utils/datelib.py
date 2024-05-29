#!/usr/bin/python3

import argparse
import logging
import os

from fnmatch import fnmatch
from collections import defaultdict

from mmdiary.utils import log, medialib

DESCRIPTION = """
Diary video dates DB manipulation tool
Please declare enviromnent variables before use:
    MMDIARY_VIDEO_LIB_ROOTS - List of video library root dirs
    MMDIARY_VIDEO_RES_DIR - Video processor result dir

Possible actions:
    list_dates - Print all dates with status
    list_files - Print all files for date
    disable_video - Set a flag for video file to disable concatenating and uploading,
                    also mark corresponded date as not processed for future regeneration
    list_disabled_videos - List videos marked as disabled 
    set_reupload - Mark a video as not uploaded for future reupload
                   (e.g. if video was deleted on the YouTube)
"""

STATE_NONE = "none"
STATE_INPROCESS = "inprocess"
STATE_CONVERTED = "converted"
STATE_UPLOADED = "uploaded"
STATE_UPLOAD_VERIFICATION = "uploadverification"

VALID_STATES = set(
    [
        STATE_NONE,
        STATE_INPROCESS,
        STATE_CONVERTED,
        STATE_UPLOADED,
        STATE_UPLOAD_VERIFICATION,
    ]
)


class DateLib:
    def __init__(self):
        self.__scan_paths = list(
            filter(
                None,
                os.getenv("MMDIARY_VIDEO_LIB_ROOTS").split(":"),
            ),
        )
        self.__res_dir = os.getenv("MMDIARY_VIDEO_RES_DIR")
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
        if fields is not None:
            new_fields.update(fields)
        new_fields["state"] = STATE_CONVERTED
        self.results()[date].update_fields(new_fields)

    def set_uploaded(self, date, provider, for_verification=False):
        self.results()[date].update_fields(
            {
                "state": STATE_UPLOAD_VERIFICATION if for_verification else STATE_UPLOADED,
                "provider": provider,
            }
        )

    def set_state(self, date, state):
        if state not in VALID_STATES:
            raise UserWarning(f"Incorrect state: {state}")
        self.results()[date].update_fields({"state": state})

    def get_nonprocessed(self, masks=None):
        all_dates = set(self.sources().keys())
        processed_dates = set(self.__get_results_dates_by_state(VALID_STATES - set([STATE_NONE])))
        return sorted(self.__filter_by_masks(list(all_dates - processed_dates), masks))

    def __filter_by_masks(self, dates, masks):
        if masks is None or len(masks) == 0 or dates is None or len(dates) == 0:
            return dates
        if isinstance(next(iter(dates)), tuple):
            return filter(lambda date: any(fnmatch(date[0], mask) for mask in masks), dates)
        return filter(lambda date: any(fnmatch(date, mask) for mask in masks), dates)

    def __get_results_dates_by_state(self, states, masks=None):
        for state in states:
            if state not in VALID_STATES:
                raise UserWarning(f"Incorrect state: {state}")
        res = []
        for date, mf in self.results().items():
            if mf.state() in states:
                res.append(date)
        return sorted(self.__filter_by_masks(res, masks))

    def get_converted(self, masks=None):
        return self.__get_results_dates_by_state([STATE_CONVERTED], masks)

    def get_uploaded(self, masks=None, for_verification=False):
        return self.__get_results_dates_by_state(
            [STATE_UPLOAD_VERIFICATION] if for_verification else [STATE_UPLOADED], masks
        )

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

    def list_dates(self, state, masks):
        if state is None:
            res = {date: STATE_NONE for date in set(self.sources().keys())}
            res.update({date: mf.state() for date, mf in self.results().items()})
            return sorted(self.__filter_by_masks(res.items(), masks))

        if state == STATE_NONE:
            return [(date, STATE_NONE) for date in self.get_nonprocessed(masks)]

        return [(date, state) for date in self.__get_results_dates_by_state([state], masks)]

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
            "list_files",
            "disable_video",
            "set_reupload",
        ],
    )
    parser.add_argument("-f", "--file", help="File name (for disable_video)")
    parser.add_argument("-e", "--date", help="Date (for set_reupload, list_files)")
    parser.add_argument("-s", "--state", help="State for (list_dates)")
    return parser.parse_args()


def main():
    args = __args_parse()
    log.init_logger(level=logging.DEBUG)
    lib = DateLib()

    if args.action == "list_dates":
        dates = lib.list_dates(args.state, [args.date] if args.date is not None else None)
        for date, state in dates:
            print(date, state)
        print("Total:", len(dates))
    elif args.action == "list_disabled_videos":
        filenames = lib.list_disabled_videos()
        for filename in filenames:
            print(filename)
        print("Total:", len(filenames))
    elif args.action == "list_files":
        mfs = lib.get_files_by_date(args.date)
        for mf in mfs:
            print(mf)
        print("Total:", len(mfs))
    elif args.action == "disable_video":
        lib.disable_video(args.file)
        logging.info("Done.")
    elif args.action == "set_reupload":
        if lib.get_state(args.date) != STATE_UPLOADED:
            logging.warning("Specified date not yet uploaded: %s", args.date)
        lib.set_converted(args.date, {})
        logging.info("Done.")


if __name__ == "__main__":
    main()
