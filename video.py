#!/usr/bin/python3

import os
import log
import progressbar
import logging
import argparse
import datelib
import tempfile
import subprocess

from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.fx.resize import resize
import moviepy.video.fx.all as vfx

import googleapiclient.discovery

YOUTUBE_MAX_DESCRIPTION = 5000


def add_round2(n):
    return n - n // 2 * 2


def resize_with_black_padding(clip, new_width=None, new_height=None):
    if new_width == clip.w and new_height == clip.h:
        return clip

    src_ratio = clip.w / clip.h
    dst_ratio = new_width / new_height

    if src_ratio == dst_ratio:
        return clip.fx(resize, width=new_width, height=new_height)

    image_width = clip.w
    image_height = clip.h
    if src_ratio > dst_ratio:
        image_width = new_width
        image_height = int(image_width / src_ratio)
    else:
        image_height = new_height
        image_width = int(image_height * src_ratio)

    print(f"Image size: {image_width}x{image_height}")
    resized_clip = clip.fx(resize, width=image_width, height=image_height)
    # correction to have result divisible by 2
    add_w = add_round2(resized_clip.w)
    add_h = add_round2(resized_clip.h)
    res = resized_clip.fx(
        vfx.margin,
        left=(new_width - image_width) // 2 + add_w,
        right=(new_width - image_width) // 2,
        top=(new_height - image_height) // 2 + add_h,
        bottom=(new_height - image_height) // 2,
        color=(0, 0, 0),
    )  # Black color padding

    if res.h != new_height or res.w != new_width:
        raise Exception(
            f"Incorrect resize: {res.w}x{res.h} != {new_width}x{new_height}"
        )
    return res


def rotate_if_needs(c):
    logging.info(f"{c.filename} rotation: {c.rotation}")
    if c.rotation in (90, 270):
        c = c.fx(resize, c.size[::-1])
        c.rotation = 0
    return c


def concatenate_by_ffmpeg(filenames, outputfile, tmpdirname):
    if len(filenames) == 0:
        logging.warning("empty filenames list")
        return
    listfile = os.path.join(tmpdirname, 'list.txt')
    with open(listfile, 'w') as f:
        for fname in filenames:
            f.write(f"file '{fname}'\n")

    command = [
        'ffmpeg',
        '-y',
        '-f',
        'concat',
        '-safe',
        '0',
        '-i',
        listfile,
        '-c',
        'copy',
        outputfile,
    ]
    logging.info(f"start: {command}")
    subprocess.run(command)
    logging.info(f"file saved: {outputfile}")


FFMPEG_CODEC = "libx264"
FFMPEG_FPS = 25
FFMPEG_PARAMS = [
    "-vf",
    "yadif,format=yuv420p",  # deinterlace videos if they're interlaced, produce pixel format with 4:2:0 chroma subsampling.
    "-b:v",
    "20M",  # set video bitrate.
    "-bf",
    "2",  # limit consecutive B-frames to 2
    "-c:a",
    "aac",  # use the native encoder to produce an AAC audio stream.
    "-b:a",
    "384k",  # sets audio bitrate.
    "-ac",
    "2",  # rematrixes audio to stereo.
    "-ar",
    "48000",  # resamples audio to 48000 Hz.
    "-use_editlist",
    "0",  # avoids writing edit lists
    "-movflags",
    "+faststart",  # places moov atom/box at front of the output file.
    "-fflags",
    "+genpts",  # Generate presentation timestamps
]


def concatenate_to_mp4(filenames, outputfile, dry_run=False):
    clips_info = []
    for f in filenames:
        with VideoFileClip(f) as c:
            c = rotate_if_needs(c)
            clips_info.append({"w": c.w, "h": c.h})
            c.close()

    max_height = 0
    max_width = 0
    for c in clips_info:
        if c["w"] > max_width:
            max_width = c["w"]
            max_height = c["h"]

    durations = []
    tmpfilenames = []

    # TODO: add detection
    skip_recode = True

    if dry_run:
        skip_recode = True

    with tempfile.TemporaryDirectory() as tmpdirname:
        for i, f in enumerate(filenames):
            try:
                tfname = os.path.join(tmpdirname, f"{i}.mp4")
                with VideoFileClip(f) as c:
                    if skip_recode:
                        tfname = f
                    else:
                        c = rotate_if_needs(c)
                        c = resize_with_black_padding(c, max_width, max_height)
                        logging.info(f"saving '{c.filename}' to '{tfname}'")
                        c.write_videofile(
                            tfname,
                            codec=FFMPEG_CODEC,
                            ffmpeg_params=FFMPEG_PARAMS,
                            fps=FFMPEG_FPS,
                        )
                    durations.append(c.duration)
                    tmpfilenames.append(tfname)
                    c.close()
            except Exception:
                logging.exception("file '{f}' processing failed")

        if not dry_run:
            concatenate_by_ffmpeg(tmpfilenames, outputfile, tmpdirname)

    return durations


def get_youtube_credentials(client_secrets, token_file):
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]

    if os.path.exists(token_file):
        from google.oauth2.credentials import Credentials

        return Credentials.from_authorized_user_file(token_file, scopes=scopes)

    import google_auth_oauthlib.flow

    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets,
        scopes=scopes,
        redirect_uri="urn:ietf:wg:oauth:2.0:oob",
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent"
    )

    print(f"Please go to this URL and authorize access: {authorization_url}")
    authorization_code = input("Enter the authorization code: ")

    flow.fetch_token(code=authorization_code)
    credentials = flow.credentials

    with open(token_file, "w") as token:
        token.write(credentials.to_json())

    return credentials


def seconds_to_time(seconds):
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def generate_description_full(time_labels):
    description = ""
    pos = 0.0
    for duration, label in time_labels:
        time = seconds_to_time(int(pos))
        description += f"{time} - {label}\n"
        pos += duration
    logging.info(f"full description len: {len(description)}")
    return description


def generate_description_redused(time_labels):
    description = ""
    pos = 0.0
    last_pos = -100
    for duration, label in time_labels:
        if pos - last_pos > 20 and len(label) > 15:  # sec
            time = seconds_to_time(int(pos))
            label = label[:50]
            description += f"{time} - {label}\n"
            last_pos = pos
        pos += duration
    logging.info(f"reduced description len: {len(description)}")
    return description


def generate_description(time_labels):
    description = generate_description_full(time_labels)
    if len(description) < YOUTUBE_MAX_DESCRIPTION:
        return description

    description = generate_description_redused(time_labels)
    if len(description) < YOUTUBE_MAX_DESCRIPTION:
        return description

    logging.warn("description cutted")
    return description[:YOUTUBE_MAX_DESCRIPTION]


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
        self.__credentials = get_youtube_credentials(
            "client_secrets.json", "token.json"
        )

    def upload_video(self, fname, title, time_labels):
        youtube = googleapiclient.discovery.build(
            "youtube", "v3", credentials=self.__credentials
        )

        # Upload video
        request_body = {
            "snippet": {
                "title": title,
                "description": generate_description(time_labels),
                "tags": ["daily"],
            },
            "status": {"privacyStatus": "unlisted"},
        }

        media_file = googleapiclient.http.MediaFileUpload(
            fname, chunksize=-1, resumable=True
        )
        response_upload = (
            youtube.videos()
            .insert(
                part="snippet,status", body=request_body, media_body=media_file
            )
            .execute()
        )

        vid = response_upload["id"]
        logging.info(f"Video uploaded: {vid}")

    def process_date(self, date):
        logging.info(f"Start: {date}")
        afiles = self.__lib.get_files_by_date(date)
        fnames = [af.name() for af in afiles]
        logging.info(f"found {len(fnames)} files")

        tempfilename = "/mnt/multimedia/tmp/00_test_concat.mp4"
        durations = concatenate_to_mp4(fnames, tempfilename)

        time_labels = []
        for af, duration in zip(afiles, durations):
            time = af.prop().time().strftime("%H: %M: %S")
            caption = af.load_json()["caption"].strip()
            time_labels.append((duration, f"[{time}] {caption}"))

        logging.info(time_labels)

        self.upload_video(tempfilename, date, time_labels)

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
    logging.getLogger("py.warnings").setLevel(logging.ERROR)

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
