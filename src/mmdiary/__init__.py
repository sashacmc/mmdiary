#!/usr/bin/python3
# pylint: disable=line-too-long

import os
import json
import argparse
import logging
import getpass

from mmdiary.utils import log

DESCRIPTION = """
Multimedia Diary Tools is a toolkit designed to automate the process
  of managing multimedia content for diary entries.
This toolkit offers functionalities to scan specified folders,
  identify audio and video files, perform speech-to-text transcription, merge video files,
  and upload the resulting video content to YouTube/Dailymotion.
Additionally, it integrates with Notion to create a calendar and populate it with transcribed text
  from audio and video notes, accompanied by links to the original media.
"""


def __args_parse():
    parser = argparse.ArgumentParser(
        description=DESCRIPTION, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-l", "--logfile", help="Log file", default="/dev/null")

    parser.add_argument("--init", help="Run interactive setup", action="store_true")

    parser.add_argument("--video", help="Proces video diary entries", action="store_true")
    parser.add_argument("--audio", help="Proces audio diary entries", action="store_true")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--youtube", help="Upload video diary entries to youtube", action="store_true"
    )
    group.add_argument(
        "--dailymotion", help="Upload video diary entries to dailymotion", action="store_true"
    )

    parser.add_argument("--notion", help="Upload to notion", action="store_true")

    return parser.parse_args()


def __ask(question, default_value):
    user_input = input(f"{question} [{default_value}]: ")
    return user_input.strip() or default_value


def __ask_passwd(question):
    return getpass.getpass(f"{question}: ").strip()


def __ask_bool(question, default_value):
    default_value = "y" if default_value else "n"
    while True:
        user_input = input(f"{question} (y/n) [{default_value}]: ").strip().lower()
        if user_input in ["y", "n", ""]:
            return (user_input or default_value) == "y"
        print("Invalid input. Please enter 'y' or 'n'.")


def __init_audio():
    return {"MMDIARY_AUDIO_LIB_ROOT": __ask("Enter audio lib folder", "~/audio")}


def __init_video():
    return {
        "MMDIARY_VIDEO_LIB_ROOTS": __ask("Enter video lib folder", "~/video"),
        "MMDIARY_VIDEO_WORK_DIR": __ask("Enter video work folder", "~/video/tmp"),
        "MMDIARY_VIDEO_RE_DIR": __ask("Enter video result folder", "~/video/converted"),
    }


def __init_youtube(confg_path):
    print(
        "Obtain the YouTube API Client Secrets by following the instructions:",
        "https://github.com/sashacmc/mmdiary?tab=readme-ov-file#obtaining-and-setting-up-the-youtube-api-client-secrets",
    )

    client_secrets = None
    while True:
        client_secrets = __ask(
            "Enter client_secrets file name", os.path.join(confg_path, "client_secrets.json")
        )
        if os.path.exists(os.path.expanduser(client_secrets)):
            break
        print(f"File {client_secrets} not exists")

    token_file = None
    while True:
        account = __ask("Enter account name (for internal usage only)", "youtube_account")
        token_file = os.path.join(confg_path, account + ".json")

        if not os.path.exists(os.path.expanduser(token_file)):
            break
        if __ask_bool(f"Account token file '{token_file}' already exists, overwrite?", False):
            break

    return {}


def __init_dailymotion(confg_path):
    print(
        "Generate an API key by following the instructions:",
        "https://github.com/sashacmc/mmdiary?tab=readme-ov-file#generating-api-keys",
    )
    accounts_file = __ask(
        "Enter accounts file name", os.path.join(confg_path, "dailymotion_accounts.json")
    )
    if not os.path.exists(os.path.expanduser(accounts_file)) or __ask_bool(
        "This file already exists, would you like to overwrite it?", False
    ):
        account = {
            "name": __ask("Enter account/channel name", ""),
            "username": __ask("Enter user name (E-Mail)", ""),
            "password": __ask_passwd("Enter password"),
            "api_key": __ask("Enter API key", ""),
            "api_secret": __ask_passwd("Enter API secret"),
        }
        with open(os.path.expanduser(accounts_file), "w", encoding="utf-8") as f:
            data = {"accounts": [account], "current": 0}
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(
            f"Accounts data saved to: {accounts_file}, you can add other accounts after, if needed"
        )
    return {"MMDIARY_DAILYMOTION_ACCOUNTS": accounts_file}


def __init_notion(confg_path):
    env = {}
    env["MMDIARY_NOTION_CACHE"] = os.path.join(confg_path, "notion_cache.pickle")
    return env


def __init():
    env = {}
    confg_path = __ask("Enter main configuration folder", "~/.mmdiary")
    os.makedirs(os.path.expanduser(confg_path), exist_ok=True)
    env["MMDIARY_CACHE"] = os.path.join(confg_path, "json_cache.pickle")

    if __ask_bool("Will you process audio library", True):
        env.update(__init_audio())

    if __ask_bool("Will you process video library", True):
        env.update(__init_video())

        if __ask_bool("Will you upload video on YouTube", True):
            env.update(__init_youtube(confg_path))
        if __ask_bool("Will you upload video on Dailymotion", True):
            env.update(__init_dailymotion(confg_path))

    env.update(__init_notion(confg_path))

    print("\nPlease add this lines to you environment file (e.g. ~/.bashrc):\n")
    for var, value in sorted(env.items()):
        print(f'export {var}="{value}"')


def main():
    args = __args_parse()

    log.init_logger(args.logfile, level=logging.DEBUG)

    if args.init:
        __init()
        return


if __name__ == "__main__":
    main()
