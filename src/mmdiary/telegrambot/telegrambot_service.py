#!/usr/bin/python3

import logging
import os
import random
from collections import defaultdict
from datetime import datetime

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    JobQueue,
    MessageHandler,
    filters,
)

from mmdiary.utils import log, medialib

MAX_MESSAGE_SIZE = 1024

g_audiofiles = medialib.MediaLib(os.getenv("MMDIARY_AUDIO_LIB_ROOT")).get_processed()


class DateSelector:
    EXIT = 0
    YEAR = 1
    MONTH = 2
    DAY = 3
    END = 4
    RETURN = "<<"

    def __init__(self):
        self.__type = self.YEAR
        self.__year = None
        self.__month = None
        self.__day = None
        self.__load()

    def __load(self):
        self.__files = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [])))
        for af in g_audiofiles:
            data = af.load_json()
            rtime = data["recordtime"]  # "YYYY-MM-DD hh-mm-ss"
            year = rtime[:4]
            month = rtime[5:7]
            day = rtime[8:10]
            self.__files[year][month][day].append(af)

    def __get_years(self):
        return sorted(self.__files.keys())

    def __get_months(self, year):
        return sorted(self.__files[year].keys())

    def __get_days(self, year, month):
        return sorted(self.__files[year][month].keys())

    def __get_notes(self, year, month, day):
        return sorted(self.__files[year][month][day])

    def get_items(self):
        if self.__type == self.YEAR:
            return self.__get_years()
        if self.__type == self.MONTH:
            return self.__get_months(self.__year)
        if self.__type == self.DAY:
            return self.__get_days(self.__year, self.__month)
        return []

    def get_caption(self):
        if self.__type == self.YEAR:
            return "year"
        if self.__type == self.MONTH:
            return "month"
        if self.__type == self.DAY:
            return "day"
        if self.__type == self.END:
            return "back"
        return ""

    def select_item(self, val):
        if self.__type == self.YEAR:
            self.__year = val
            if val != self.RETURN:
                self.__type = self.MONTH
            else:
                self.__type = self.EXIT
        elif self.__type == self.MONTH:
            self.__month = val
            if val != self.RETURN:
                self.__type = self.DAY
            else:
                self.__type = self.YEAR
        elif self.__type == self.DAY:
            self.__day = val
            if val != self.RETURN:
                self.__type = self.END
            else:
                self.__type = self.MONTH
        elif self.__type == self.END:
            if val == self.RETURN:
                self.__type = self.DAY

    def result(self):
        if self.__type == self.END:
            return self.__get_notes(self.__year, self.__month, self.__day)
        return None


def audiofile_to_message(audiofile):
    data = audiofile.load_json()
    texts = medialib.split_large_text(data["text"], MAX_MESSAGE_SIZE)

    return {
        "audio": audiofile.name(),
        "title": "[" + data["recordtime"] + "] " + data["caption"],
        "caption": texts[0],
    }, texts[1:]


async def check_auth(update, context):
    if update.effective_user.username.lower() not in context.application.auth_users:
        await update.message.reply_html("You not registered, contact admin")
        return False
    return True


async def command_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    username = update.message.chat.username
    chat_id = update.message.chat.id
    logging.info("New user: %s (%s)", username, chat_id)
    await update.message.reply_html(f"Hi {username}!")
    await check_auth(update, context)


async def job_random(context: ContextTypes.DEFAULT_TYPE) -> None:
    audio, texts = audiofile_to_message(random.choice(g_audiofiles))
    for chat_id in context.application.auto_send_chats:
        logging.info("Audio %s sent to %s", audio['audio'], chat_id)
        await context.bot.send_audio(chat_id, **audio)
        for text in texts:
            await context.bot.send_message(chat_id, text)


async def command_random(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update, context):
        return
    audio, texts = audiofile_to_message(random.choice(g_audiofiles))
    await update.message.reply_audio(**audio)
    for text in texts:
        await update.message.reply_text(text)


async def command_get(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await check_auth(update, context):
        return
    query = update.callback_query
    resp = update.message
    selector = None
    if query is None:
        selector = DateSelector()
        context.user_data["selector"] = selector
    else:
        selector = context.user_data["selector"]
        await query.answer()
        selector.select_item(query.data)
        resp = query.message

    button_list = [InlineKeyboardButton(it, callback_data=it) for it in selector.get_items()]
    if len(button_list) == 0:
        res = selector.result()
        if res is None:
            await resp.reply_text("Bye")
            selector = None
            return
        for af in res:
            audio, texts = audiofile_to_message(af)
            await resp.reply_audio(**audio)
            for text in texts:
                await resp.reply_text(text)

    reply_markup = InlineKeyboardMarkup(
        build_menu(
            button_list,
            n_cols=3,
            footer_buttons=[
                InlineKeyboardButton("<<", callback_data="<<"),
            ],
        )
    )
    await resp.reply_markdown(
        text="Choose " + selector.get_caption(),
        reply_markup=reply_markup,
    )


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


async def echo(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(update.message.text)


def main() -> None:
    log.init_logger(None, level=logging.DEBUG)

    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    token = os.getenv("MMDIARY_TELEGRAM_BOT_TOKEN")

    job_queue = JobQueue()
    job_queue.run_daily(
        job_random,
        datetime.strptime(os.getenv("MMDIARY_TELEGRAM_AUTO_SEND_TIME"), '%H:%M:%S').time(),
    )
    # job_queue.run_repeating(job_random, 60)

    application = Application.builder().token(token).job_queue(job_queue).build()

    application.auth_users = list(
        map(
            lambda u: u.lower(),
            os.getenv("MMDIARY_TELEGRAM_USERS").split(","),
        )
    )
    application.auto_send_chats = list(
        map(
            int,
            filter(
                lambda v: v != '',
                os.getenv("MMDIARY_TELEGRAM_AUTO_SEND_CHATS").split(","),
            ),
        )
    )
    application.add_handler(CommandHandler("start", command_start))
    application.add_handler(CommandHandler("random", command_random))
    application.add_handler(CommandHandler("get", command_get))
    application.add_handler(CallbackQueryHandler(command_get))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.run_polling(poll_interval=1, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
