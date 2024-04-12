#!/usr/bin/python3

import os
import log
import progressbar
import logging
import argparse

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


class VideoProcessor(object):
    def __init__(self, update_existing):
        self.__update_existing = update_existing

    def concatenate(self, filenames, outputfile):
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

    def process_one(self, filename):
        pass

    def process_dir(self, dirname, filenames):
        self.concatenate(
            [os.path.join(dirname, fn) for fn in filenames],
            "/mnt/multimedia/tmp/00_test_concat.mp4",
        )


def __on_walk_error(err):
    logging.error('Scan files error: %s' % err)


def __scan_files(inpath):
    res = []
    for root, dirs, files in os.walk(inpath, onerror=__on_walk_error):
        if len(files) != 0:
            res.append((root, sorted(files)))

    res.sort()
    logging.info(f"Found {len(res)} folders")
    return res


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

    vp = VideoProcessor(args.update)

    if os.path.isfile(args.inpath):
        vp.process_one(args.inpath)
        return

    if not os.path.isdir(args.inpath):
        logging.info("Not a folder")
        return

    dirlist = __scan_files(args.inpath)

    if len(dirlist) == 0:
        return

    pbar = progressbar.ProgressBar(
        maxval=len(dirlist),
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

    for dr in dirlist:
        try:
            vp.process_dir(dr[0], dr[1])
        except Exception:
            logging.exception("Video processing failed")
        pbar.increment()

    pbar.finish()
    logging.info("Done.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Main failed")
