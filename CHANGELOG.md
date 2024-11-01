# Changelog

## 1.0.0 - UNRELEASED

- Add mmdiary script: global initialization and batch mode
- JSON cache leazy loading
- Logging cleanup and confgiration by MMDIARY_LOGGING_LEVEL env variable
- Catch token refresh exception
- Add disable_date action
- Add blacklisted video processing
- Improve proxy usage

## 0.4.0 - 2024-06-02

- Add Dailymotion uploader
- Add proxy support for Dailymotion
- Add YouTube upload verification
- Reorganize video uploader scripts
- Store provider/account/id in place of URL
- Save critical files not directly, but via temp file

## 0.3.0 - 2024-05-23

- Add `list_files` command to `mmdiary-utils-datelib`
- Add update mode to video processor
- Update video on YouTube without reupload
- Add env variables to setup YouTube auth
- Unify environment variable names
- Rework hall texts processing
- Remove duplicate lines and long words during verification
- Add possibility to process/upload videos by date mask
- Add video upload verification
- Add Notion/YouTube setup to README.md
- Add Auxiliary Tools to README.md
- Improve deleted videos processing

## 0.2.0 - 2024-05-08

- Rework verifier to use regexp
- Switch notion cachedb to pickle in place of sqlite3
- Add jsoncache
- Rework to save state/url in results json. Remove Video DB.
- JSON regeneration for processed videos.
- Description/commnets for video processor.
- Upload video to Notion 
- Notion initialisation

## 0.1.1 - 2024-05-01

- Update README.md

## 0.1.0 - 2024-05-01

Initial release with base funtionality:
- Transcribe audio/video files
- Upload audio diary to Notion
- Concatenite video diary and upload to YouTube
- Telegam bot for access to audio notes library
