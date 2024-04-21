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

import googleapiclient.discovery

YOUTUBE_MAX_DESCRIPTION = 5000


def rotate_if_needs(c):
    logging.info(f"{c.filename} rotation: {c.rotation}")
    if c.rotation in (90, 270):
        c = c.fx(resize, c.size[::-1])
        c.rotation = 0
    return c


REENCODE_FPS = "25"
FFMPEG_CODEC = "libx264"
FFMPEG_PARAMS = [
    "-c:a",
    "aac",  # use the native encoder to produce an AAC audio stream.
    "-q:a",
    "1",  # sets the highest quality for the audio. Better than setting a bitrate manually.
    "-ac",
    "2",  # rematrixes audio to stereo.
    "-ar",
    "48000",  # resamples audio to 48000 Hz.
]


def concatenate_by_ffmpeg(filenames, outputfile, tmpdirname):
    if len(filenames) == 0:
        logging.warning("empty filenames list")
        return
    listfile = os.path.join(tmpdirname, 'list.txt')
    with open(listfile, 'w') as f:
        for fname in filenames:
            f.write(f"file '{fname}'\n")

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        listfile,
        "-vf",
        "yadif,format=yuv420p",
        "-c:v",
        FFMPEG_CODEC,
        "-crf",
        "17",  # produce a visually lossless file. Better than setting a bitrate manually.
        "-bf",
        "2",  # limit consecutive B-frames to 2
        "-use_editlist",
        "0",  # avoids writing edit lists
        "-movflags",
        "+faststart",  # places moov atom/box at front of the output file.
    ]
    command += FFMPEG_PARAMS
    command.append(outputfile)
    logging.info(f"start: {command}")
    subprocess.run(command)
    logging.info(f"file saved: {outputfile}")


def stabilize_by_ffmpeg(in_file, out_file):
    command = [
        "ffmpeg",
        "-i",
        in_file,
        "-y",
        "-vf",
        "vidstabdetect=stepsize=32:shakiness=10:accuracy=10:result=transforms.trf",
        "-f",
        "null",
        "-",
    ]
    logging.info(f"start stab prep: {command}")
    subprocess.run(command)

    command = [
        "ffmpeg",
        "-i",
        in_file,
        "-y",
        "-qp",
        "0",
        "-preset",
        "ultrafast",
        "-vf",
        "vidstabtransform=input=transforms.trf:zoom=0:smoothing=10,unsharp=5:5:0.8:3:3:0.4",
        "-acodec",
        "copy",
        "-c:v",
        FFMPEG_CODEC,
        out_file,
    ]
    logging.info(f"start stab: {command}")
    subprocess.run(command)


def resize_by_ffmpeg(in_file, out_file, w, h):
    filters = [
        "yadif",
        "format=yuv420p",
        f"scale=w='if(gt(a,{w}/{h}),{w},trunc(oh*a/2)*2)':h='if(gt(a,{w}/{h}),trunc(ow/a/2)*2,{h})'",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
    ]
    command = [
        "ffmpeg",
        "-i",
        in_file,
        "-y",
        "-r",
        REENCODE_FPS,
        "-qp",
        "0",
        "-preset",
        "ultrafast",
        "-vf",
        ",".join(filters),
        "-c:v",
        FFMPEG_CODEC,
    ]
    command += FFMPEG_PARAMS
    command.append(out_file)
    logging.info(f"start resize: {command}")
    subprocess.run(command)


def concatenate_to_mp4(filenames, outputfile, dry_run=False):
    max_height = 0
    max_width = 0
    durations = []
    for f in filenames:
        with VideoFileClip(f) as c:
            c = rotate_if_needs(c)
            durations.append(c.duration)
            if c.w > max_width:
                max_width = c.w
                max_height = c.h
            c.close()

    logging.info(f"Result video: width={max_width}, height={max_height}")

    tmpfilenames = []

    if dry_run:
        return durations

    with tempfile.TemporaryDirectory() as tmpdirname:
        tmpdirname = "/tmp"
        for i, f in enumerate(filenames):
            tfname = os.path.join(tmpdirname, f"{i}.mp4")
            tfname_stab = os.path.join(tmpdirname, f"{i}_stab.mp4")
            logging.info(f"saving '{f}' to '{tfname}'")
            resize_by_ffmpeg(f, tfname, max_width, max_height)
            stabilize_by_ffmpeg(tfname, tfname_stab)
            tmpfilenames.append(tfname_stab)

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

        # TODO: uncomment
        # self.upload_video(tempfilename, date, time_labels)

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
