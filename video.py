#!/usr/bin/python3

import os
import log
import progressbar
import logging
import argparse
import datelib

from moviepy.editor import VideoFileClip, concatenate_videoclips
import moviepy.video.fx.all as vfx


def resize_with_black_padding(clip, new_width=None, new_height=None):
    if new_width == clip.w and new_height == clip.h:
        return clip

    src_ratio = clip.w / clip.h
    dst_ratio = new_width / new_height

    if src_ratio == dst_ratio:
        return clip.resize(width=new_width, height=new_height)

    image_width = clip.w
    image_height = clip.h
    if src_ratio > dst_ratio:
        image_width = new_width
        image_height = int(image_width / src_ratio)
    else:
        image_height = new_height
        image_width = int(image_height * src_ratio)

    print(f"Image size: {image_width}x{image_height}")
    resized_clip = clip.resize(width=image_width, height=image_height)
    res = resized_clip.fx(
        vfx.margin,
        left=(new_width - image_width) // 2,
        right=(new_width - image_width) // 2,
        top=(new_height - image_height) // 2,
        bottom=(new_height - image_height) // 2,
        color=(0, 0, 0),
    )  # Black color padding

    if res.h != new_height or res.w != new_width:
        raise Exception(
            f"Incorrect resize: {res.w}x{res.h} != {new_width}x{new_height}"
        )
    return res


def concatenate_to_mp4(filenames, outputfile):
    clips = [VideoFileClip(c) for c in filenames]

    max_height = max([c.h for c in clips])
    max_width = max([c.w for c in clips])

    clips = [
        resize_with_black_padding(c, max_width, max_height) for c in clips
    ]

    final_clip = concatenate_videoclips(clips)

    final_clip.write_videofile(
        outputfile,
        codec="libx264",
        ffmpeg_params=[
            "-vf",
            "yadif,format=yuv420p",  # deinterlace videos if they're interlaced, produce pixel format with 4:2:0 chroma subsampling.
            "-crf",
            "18",  # produce a visually lossless file. Better than setting a bitrate manually.
            "-bf",
            "2",  # limit consecutive B-frames to 2
            "-c:a",
            "aac",  # use the native encoder to produce an AAC audio stream.
            "-q:a",
            "1",  # sets the highest quality for the audio. Better than setting a bitrate manually.
            "-ac",
            "2",  # rematrixes audio to stereo.
            "-ar",
            "48000",  # resamples audio to 48000 Hz.
            "-use_editlist",
            "0",  # avoids writing edit lists
            "-movflags",
            "+faststart",  # places moov atom/box at front of the output file.
        ],
    )


class VideoProcessor(object):
    def __init__(self, update_existing):
        self.__update_existing = update_existing
        scan_paths = list(
            filter(
                None,
                os.getenv("VIDEO_LIB_ROOTS").split(":"),
            ),
        )
        db_file = os.getenv("VIDEO_LIB_DB")
        self.__lib = datelib.DateLib(scan_paths, db_file)

    def upload_video(self, fname):
        pass

    def process_date(self, date):
        logging.info(f"Start: {date}")
        fnames = []
        texts = []
        for af in self.__lib.get_files_by_date(date):
            fnames.append(af.name())
            texts.append(af.load_json())

        logging.info(f"found {len(fnames)} files")

        tempfilename = "/mnt/multimedia/tmp/00_test_concat.mp4"
        concatenate_to_mp4(fnames, tempfilename)
        self.upload_video(tempfilename)

        logging.info(f"Done: {date}")

    def process_all(self, dirname, filenames):
        nonprocessed = list(self.__lib.get_nonprocessed())

        pbar = progressbar.ProgressBar(
            maxval=len(nonprocessed),
            widgets=[
                "Process",
                ' ',
                progressbar.Percentage(),
                ' ',
                progressbar.Bar(),
                ' ',
                progressbar.ETA(),
            ],
        ).start()

        for date, url in nonprocessed:
            try:
                self.process_date(date)
            except Exception:
                logging.exception("Video processing failed")
            pbar.increment()

        pbar.finish()


def __args_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('date', help='Date to process')
    parser.add_argument('-l', '--logfile', help='Log file', default=None)
    parser.add_argument(
        '-u', '--update', help='Update existing', action='store_true'
    )
    return parser.parse_args()


def main():
    args = __args_parse()
    log.initLogger(args.logfile)

    vp = VideoProcessor(args.update)

    if args.date is None:
        vp.process_all()
    else:
        vp.process_date(args.date)

    logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Main failed")
