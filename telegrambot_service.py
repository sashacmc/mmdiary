#!/usr/bin/python3

import os
import logging
import random

import log
import audiolib

from telegram import (
    ForceReply,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

g_audiofiles = audiolib.AudioLib().get_processed()
MAX_MESSAGE_SIZE = 1024


class DateSelector(object):
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

    def __get_years(self):
        return [str(y) for y in range(2000, 2024)]

    def __get_months(self, year):
        return [str(y) for y in range(1, 12)]

    def __get_days(self, year, month):
        return [str(y) for y in range(1, 30)]

    def get_items(self):
        if self.__type == self.YEAR:
            return self.__get_years()
        elif self.__type == self.MONTH:
            return self.__get_months(self.__year)
        elif self.__type == self.DAY:
            return self.__get_days(self.__year, self.__month)
        else:
            return []

    def get_caption(self):
        if self.__type == self.YEAR:
            return "year"
        elif self.__type == self.MONTH:
            return "month"
        elif self.__type == self.DAY:
            return "day"
        else:
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

    def result(self):
        if self.__type == self.END:
            return f"{self.__year}-{self.__month}-{self.__day}"
        else:
            return None


g_selector = None


def audiofile_to_message(audiofile):
    data = audiofile.load_json()
    texts = audiolib.split_large_text(data["text"], MAX_MESSAGE_SIZE)

    return {
        "audio": audiofile.name(),
        "title": "[" + data["recordtime"] + "] " + data["caption"],
        "caption": texts[0],
    }, texts[1:]


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(
        rf"Hi {user.mention_html()}!",
        reply_markup=ForceReply(selective=True),
    )


async def command_help(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    await update.message.reply_text("Help!")


async def command_random(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    audio, texts = audiofile_to_message(random.choice(g_audiofiles))
    await update.message.reply_audio(**audio)
    for text in texts:
        await update.message.reply_text(text)


async def command_get(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    query = update.callback_query
    resp = update.message
    global g_selector
    if query is None:
        g_selector = DateSelector()
    else:
        await query.answer()
        g_selector.select_item(query.data)
        resp = query.message

    button_list = [
        InlineKeyboardButton(it, callback_data=it)
        for it in g_selector.get_items()
    ]
    if len(button_list) != 0:
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
            text="Choose " + g_selector.get_caption(),
            reply_markup=reply_markup,
        )
    else:
        res = g_selector.result()
        if res is None:
            res = "Bye"

        await resp.reply_text(text=res)
        g_selector = None


def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i : i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, header_buttons)
    if footer_buttons:
        menu.append(footer_buttons)
    return menu


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(update.message.text)


def main() -> None:
    log.initLogger(None, level=logging.DEBUG)

    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

    token = os.getenv("AUDIO_NOTES_TELEGRAM_BOT_TOKEN")

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", command_help))
    application.add_handler(CommandHandler("random", command_random))
    application.add_handler(CommandHandler("get", command_get))
    application.add_handler(CallbackQueryHandler(command_get))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, echo)
    )

    application.run_polling(poll_interval=1, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
