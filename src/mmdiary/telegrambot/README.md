# Multimedia Diary Tools Telegram Bot

This bot can:
1. Send a random audio note to a specified users at a specified time.
2. Get audio notes for a specified date in interactive mode.

## Bot Setup

### Step 1: Create a Bot in Telegram

1. Open Telegram and search for the user "BotFather".
2. Start a chat with BotFather and send the command `/start`.
3. To create a new bot, send the command `/newbot`.
4. Follow the prompts to choose a name and username for your bot.
5. Once created, you will receive a bot token. Save this token as it will be used later for the bot setup.

### Step 2: Setup the Service

1. **Create environment file**: Create an environment file `/etc/telegrambot.env` based on the [example](systemd/telegrambot.env.example) provided.

   Example content of `/etc/telegrambot.env`:
    ```bash
    MMDIARY_TELEGRAM_BOT_TOKEN="YOUR_BOT_TOKEN_HERE"
    MMDIARY_TELEGRAM_USERS="user1,user2"
    MMDIARY_TELEGRAM_AUTO_SEND_CHATS="chat_id1,chat_id2"
    MMDIARY_AUDIO_LIB_ROOT="/path/to/audio/library"
    MMDIARY_TELEGRAM_AUTO_SEND_TIME="13:00:00"
    ```

2. **Create systemd service file**: Copy the [`telegrambot.service`](systemd/telegrambot.service) file to the systemd directory and adjust the paths and user information as needed.
    ```bash
    sudo cp systemd/telegrambot.service /lib/systemd/system/audio-notes-telegrambot.service
    sudo systemctl daemon-reload
    sudo systemctl enable audio-notes-telegrambot.service
    sudo systemctl start audio-notes-telegrambot.service
    ```

3. **Adjust the paths and user information** in the `telegrambot.service` file to match your setup.

### Step 3: Setup `MMDIARY_TELEGRAM_AUTO_SEND_CHATS`

1. Run the bot using the command:
    ```bash
    sudo systemctl start audio-notes-telegrambot.service
    ```

2. Open Telegram and find your bot by searching for its username.

3. Start a chat with your bot and send the command `/start`.

4. Find the `chat_id` in the service log. You can check the log file specified in the `telegrambot.service` file, typically located at `/var/log/user/audio-notes-telegrambot.log`.

5. Update the `MMDIARY_TELEGRAM_AUTO_SEND_CHATS` in your environment file `/etc/telegrambot.env` with the `chat_id` found in the log:
    ```bash
    MMDIARY_TELEGRAM_AUTO_SEND_CHATS="chat_id"
    ```

With this setup, the Multimedia Diary Tools Telegram Bot will be ready to use, providing functionalities for sending random audio notes and retrieving audio notes interactively by date.
