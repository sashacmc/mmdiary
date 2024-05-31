# Multimedia Diary Tools 

![CodeQL](https://github.com/sashacmc/mmdiary/workflows/CodeQL/badge.svg)
[![PyPI - Version](https://img.shields.io/pypi/v/mmdiary.svg)](https://pypi.org/project/mmdiary)
[![PyPI - Downloads](https://pepy.tech/badge/mmdiary)](https://pepy.tech/project/mmdiary)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.commdiarym/psf/black)

Multimedia Diary Tools is a Python toolkit designed to automate the process of managing multimedia content for diary entries. This toolkit offers functionalities to scan specified folders, identify audio and video files, perform speech-to-text transcription, merge video files, and upload the resulting video content to YouTube/Dailymotion. Additionally, it integrates with Notion to create a calendar and populate it with transcribed text from audio and video notes, accompanied by links to the original media. A Telegram bot is also provided for easy access to audio notes.

## Installation

You can install MultiMedia Diary Tools via pip:

```bash
pip install mmdiary
```

## Environment Setup

Ensure you set the necessary environment variables:

- `MMDIARY_AUDIO_LIB_ROOT`: Root directory for audio notes.
- `MMDIARY_VIDEO_LIB_ROOTS`: Root directories for video notes (multiple roots can be specified, separated by semicolon).
- `MMDIARY_VIDEO_WORK_DIR`: Work dir for video processing (can be HUGE)
- `MMDIARY_VIDEO_RES_DIR`: Results dir for video diary files
- `MMDIARY_NOTION_API_KEY`: Your Notion API Key (see below).
- `MMDIARY_NOTION_TOKEN`: Your Notion Auth Token v2 (see below).
- `MMDIARY_NOTION_CACHE`: Notion uploader cache file
- `MMDIARY_CACHE`: JSON processing cache file (to avoid reading all transribed files each run)
- `MMDIARY_YOUTUBE_CLIENT_SECRETS`: Path to `client_secrets.json` (see below)
- `MMDIARY_YOUTUBE_TOKEN`: Path to `token.json` (see below)
- `MMDIARY_DAILYMOTION_ACCOUNTS`: Path to Dailymotion accounts configuration (see below)
- `MMDIARY_NOTION_AUDIO_DB_ID`: Notion Audio DB ID (see below)
- `MMDIARY_NOTION_VIDEO_DB_ID`: Notion Video DB ID (see below) 


Example:

```bash
export MMDIARY_AUDIO_LIB_ROOT="/path/to/audio/library"
export MMDIARY_VIDEO_LIB_ROOTS="/path/to/video/library1:/path/to/video/library2"
export MMDIARY_VIDEO_WORK_DIR=/"path/to/work/dir"
export MMDIARY_VIDEO_RES_DIR="/path/to/wideo/result/dir"
export MMDIARY_NOTION_API_KEY="your_notion_api_key_here"
export MMDIARY_NOTION_TOKEN="your_notion_auth_token_v2_here"
export MMDIARY_NOTION_CACHE="~/.mmdiary/notion_cache.pickle"
export MMDIARY_CACHE="~/.mmdiary/json_cache.pickle"
export MMDIARY_YOUTUBE_CLIENT_SECRETS="~/.mmdiary/client_secrets.json"
export MMDIARY_YOUTUBE_TOKEN="~/.mmdiary/token.json"
export MMDIARY_DAILYMOTION_ACCOUNTS="~/.mmdiary/dailymotion_accounts.json"
export MMDIARY_NOTION_AUDIO_DB_ID="7da1480baa9f565198d3fa54c49b1b23"
export MMDIARY_NOTION_VIDEO_DB_ID="25225aac51ea5cf0bcc74f8c225fbb63"
```

## Recommended Tools

To ensure unique filenames for your files, it is recommended to use the [photo-importer](https://github.com/sashacmc/photo-importer) tool.

## Notion Setup

To integrate Multimedia Diary Tools with Notion, you'll need to set up both an API Key and an Auth Token v2. This dual setup is necessary because the API Key allows for fast and efficient operations via the official API, while the Auth Token v2 enables functionalities not available through the official API, such as file uploads and locking pages for editing.

### Obtaining and Setting Up the Notion API Key

1. **Create an Integration in Notion**:
   - Go to [Notion Integrations](https://www.notion.so/my-integrations) and click on "New Integration".
   - Follow the instructions to create a new integration and obtain your API Key.

2. **Set the Environment Variable**:
   - Save the API Key in an environment variable named `MMDIARY_NOTION_API_KEY`.
   - Example for Unix-based systems:
     ```bash
     export MMDIARY_NOTION_API_KEY="your_notion_api_key_here"
     ```

### Obtaining and Setting Up the Notion Auth Token v2

1. **Extract the Auth Token v2 from Your Browser**:
   - Open Notion in your web browser and log in.
   - Open the developer tools (usually by pressing `F12` or right-clicking on the page and selecting "Inspect").
   - Go to the "Application" tab and find the `token_v2` under Cookies for `notion.so`.
   - Copy the value of the `token_v2`.

2. **Set the Environment Variable**:
   - Save the Auth Token v2 in an environment variable named `MMDIARY_NOTION_TOKEN`.
   - Example for Unix-based systems:
     ```bash
     export MMDIARY_NOTION_TOKEN="your_notion_auth_token_v2_here"
     ```

### Initializing Notion Databases

Before you can upload audio (with text) and links to videos (with text) to Notion, you need to create the necessary databases. Follow these steps:

1. **Run the Initialization Script**:
   - Use the `mmdiary-notion-upload` utility with the `--init` option to create the required databases on a specified Notion page.
   - Command:
     ```bash
     mmdiary-notion-upload --init ROOT_PAGE_ID
     ```
   - Make sure the integration has access to this page.

2. **Set the Database IDs as Environment Variables**:
   - After running the script, two databases will be created on the specified page. Retrieve their IDs and save them in environment variables.
   - Example:
     ```bash
     export MMDIARY_NOTION_AUDIO_DB_ID='7da1480baa9f565198d3fa54c49b1b23'
     export MMDIARY_NOTION_VIDEO_DB_ID='25225aac51ea5cf0bcc74f8c225fbb63'
     ```

3. **Move the Databases if Needed**:
   - You can move the databases to other pages or to the root of your workspace. If you do this, ensure the integration still has access to them.

## YouTube Setup

### Obtaining and Setting Up the YouTube API Client Secrets

1. **Create a Project in Google Developers Console**:
   - Go to the [Google Developers Console](https://console.developers.google.com/).
   - Create a new project or select an existing project.
   - Enable the YouTube Data API v3 for the project.

2. **Obtain the Client Secrets File**:
   - Go to the Credentials section in your project.
   - Click on "Create Credentials" and select "OAuth 2.0 Client IDs".
   - Follow the instructions to create an OAuth 2.0 Client ID.
   - Download the `client_secrets.json` file and save it and provide a path in an environment variable named `MMDIARY_YOUTUBE_CLIENT_SECRETS`.
   - Example for Unix-based systems:
     ```bash
     export MMDIARY_YOUTUBE_CLIENT_SECRETS="~/.mmdiary/client_secrets.json"
     ```
### Setting the Upload Limit

By default, the maximum number of videos that can be uploaded via the YouTube API is 4 per day. To request an extension:

1. **Go to the YouTube API Quota Request Form**:
   - Visit the [YouTube API Quota Request Form](https://support.google.com/youtube/contact/yt_api_form).

2. **Submit the Request**:
   - Fill out the form with the necessary details about your project and the reasons for needing a higher quota.
   - Submit the form and wait for approval from the YouTube API team.

### Authenticating with YouTube API

On the first run of `mmdiary-video-upload-youtube`, a URL will be provided. Follow these steps:

1. **Open the URL**:
   - Copy the provided URL and paste it into your web browser.
   - Select the Google account authorized for your `client_secrets.json`.

2. **Enter the Authentication Code**:
   - Copy the authentication code provided after logging in.
   - Paste the authentication code into the prompt in your terminal.
   - This code will be saved in file specified by `MMDIARY_YOUTUBE_TOKEN` environment variable, and you won't need to repeat this process for future uploads.

## Dailymotion Setup

### Generating API Keys

1. **Create a Dailymotion Account**:
   - If you do not already have a Dailymotion account, create one at [Dailymotion](https://www.dailymotion.com).

2. **Create an Application**:
   - Go to the [Dailymotion Studio](https://www.dailymotion.com/partner/).
   - Select "Organization setting/API keys"
   - Click on "Generate API key" This will provide you with an `api_key` and `api_secret`.

3. **Repeat for Multiple Accounts**:
   - If you plan to use multiple Dailymotion accounts, repeat the process for each account to generate their respective `api_key` and `api_secret`.

### Setting Up the Configuration File

The configuration file should be a JSON file that contains the details of all Dailymotion accounts you wish to use. This file's path must be specified by the environment variable `MMDIARY_DAILYMOTION_ACCOUNTS`.

### Note for Multiple Accounts

A single Dailymotion account allows uploading only 15 videos per 24 hours. If you need to upload more videos within this period, you can set up multiple accounts.

### Configuration File Format

The configuration file should be structured as follows:

```json
{
  "accounts": [
    {
      "name": "account01",
      "username": "account01@example.com",
      "password": "your_password",
      "api_key": "your_api_key",
      "api_secret": "your_api_secret"
    },
    {
      "name": "account02",
      "username": "account02@example.com",
      "password": "your_password",
      "api_key": "your_api_key",
      "api_secret": "your_api_secret"
    }
  ]
}
```

Replace the placeholder values with the actual account details, API keys, and API secrets.

### Setting the Environment Variable

To use the configuration file, set the environment variable `MMDIARY_DAILYMOTION_ACCOUNTS` to the path of your configuration file.

Example for Unix-based systems:

```bash
export MMDIARY_DAILYMOTION_ACCOUNTS="~/.mmdiary/dailymotion_accounts.json"
```
     
## Step-By-Step Process Overview

### Audio Diary

#### Speech Recognition

Use the `mmdiary-transcriber-run` utility to perform speech-to-text transcription on audio files.

Command:

```bash
mmdiary-transcriber-run /path/to/audio/files
```

#### Upload to Notion

Use the `mmdiary-notion-upload` utility to upload the transcribed text and audio files to Notion.

Command:
```bash
mmdiary-notion-upload /path/to/audio/files
```

### Video Diary

#### Speech Recognition

Use the `mmdiary-transcriber-run` utility to perform speech-to-text transcription on video files.

Command:

```bash
mmdiary-transcriber-run /path/to/video/files
```

#### Daily Video Concatenation

Use the `mmdiary-video-concat` utility to merge video files into a single daily video.

Command:
```bash
mmdiary-video-concat [dates ...]
```

#### Upload to YouTube or Dailymotion

Use the `mmdiary-video-upload-youtube` or `mmdiary-video-upload-dailymotion` utility to upload the concatenated video to YouTube/Dailymotion.

Command:
```bash
mmdiary-video-upload-youtube [dates ...]
or
mmdiary-video-upload-dailymotion [dates ...]
```

#### Upload to Notion

Use the `mmdiary-notion-upload` utility to upload the transcribed text with YouTube links to Notion.

Command:
```bash
mmdiary-notion-upload "$MMDIARY_VIDEO_RES_DIR"
```

## Auxiliary Tools

### mmdiary-transcriber-search

The `mmdiary-transcriber-search` utility allows you to search through transcribed texts for specific strings. This can be useful for quickly finding occurrences of certain keywords or phrases within your audio or video transcriptions.

#### Usage

```bash
mmdiary-transcriber-search /path/to/transcribed/files "search string"
```

### mmdiary-transcriber-verify

The `mmdiary-transcriber-verify` utility checks the generated text from the speech-to-text transcriptions and filters out any garbage data. By default, this verification is performed automatically. Manual invocation of this tool is only necessary if the code has been modified (either manually or after updating the version) to avoid re-running the entire lengthy speech recognition process from scratch.

#### Usage

Simply run the utility specifying the paths to the directories or files you wish to verify in interactive mode

```bash
mmdiary-transcriber-verify /path/to/transcribed/files
```

Or run the utility with flag `-d` to check all and after with flag `-f` to apply all

```bash
mmdiary-transcriber-verify /path/to/transcribed/files -d
[check output]
mmdiary-transcriber-verify /path/to/transcribed/files -f
```

### mmdiary-utils-datelib

The `mmdiary-utils-datelib` utility provides various functions for managing and querying your multimedia video diary files by date. It includes options to list dates, list files, disable videos, list disabled videos, and set videos for re-upload.

#### Usage

Possible actions:

- `list_dates`: Print all dates with status.
- `list_files`: Print all files for a date.
- `disable_video`: Set a flag for a video file to disable concatenating and uploading, also mark the corresponding date as not processed for future regeneration.
- `list_disabled_videos`: List videos marked as disabled.
- `set_reupload`: Mark a video as not uploaded for future re-upload (e.g., if the video was deleted on YouTube).

Example:

```bash
# list all dates with status "converted"
mmdiary-utils-datelib -a list_dates -s converted

# list files for date 2010-09-13
mmdiary-utils-datelib -a list_files --date 2010-09-13

# disable video
mmdiary-utils-datelib -a disable_video -f 2010-04-14_17-09-50

# set date 2024-03-15 to reupload
mmdiary-utils-datelib -a set_reupload -e 2024-03-15
```

## Contributing

Contributions are welcome! Please feel free to submit issues, feature requests, or pull requests.

## Show your support
Give a ⭐️ if this project helped you!
