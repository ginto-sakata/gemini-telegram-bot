# Gemini Telegram Bot (EN)

[Русская версия](README.ru.md)

This Telegram bot allows interaction with the Google Gemini API for generating and editing images, as well as conducting text-based conversations. The bot utilizes interactive keyboards for convenient control over generation and editing parameters.

## 🤖 Core Features

*   **Image Generation:**
    *   Create images from text prompts (`/img`, `!`).
    *   Support for arguments to specify type, style, artist, and aspect ratio (`--type`, `--style`, `--artist`, `--ar`).
    *   Generation with random parameters (`!!<prompt>` or `/img <prompt> --random`).
*   **Image Editing:**
    *   **Interactive Buttons:** Modify aspect ratio (AR), type, style, artist, and prompt using buttons beneath the generated image.
    *   **Apply Changes:** The "✅ Apply" button uses the current image and selected settings for *targeted editing*, attempting to preserve the main subject.
    *   **`/edit` Command:** Modify the *last* image generated by the bot using a new prompt or parameters (`/edit <new prompt/flags>`).
    *   **Text Reply:** Reply to the bot's image message with text to modify it based on your prompt.
*   **Image Combination:**
    *   Reply to the bot's image message with another image.
    *   Send two images together (as a media group).
*   **Text Chat:**
    *   Converse with the Gemini text model (`/ask`, `?`).
    *   Supports conversation history (replies to bot messages).
    *   Customize the system instruction (`/reset`).
*   **Management & Customization:**
    *   Clear text chat history (`/clear`).
    *   View history (`/history`).
    *   Manage the image generation prefix (`/prompt`).
    *   Toggle the display of Gemini's text response in image captions (`/toggle_llm`).
*   **Persistence:** Keyboard state is saved across bot restarts (within TTL).
*   **Authorization:** Restrict access based on user and group IDs.

## 🛠️ Installation and Setup

### Prerequisites

*   Python 3.10+
*   pip (Python package manager)
*   Google Cloud account with Gemini API access (or Gemini API keys)
*   Telegram Bot Token (obtained from BotFather)

### Installation Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/ginto-sakata/gemini-telegram-bot
    cd gemini-telegram-bot
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Configure the `.env` file:**
    *   Create a `.env` file in the root directory (you can copy `.env.example` if it exists, or create it manually).
    *   Fill in the required variables:
        *   `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
        *   `GEMINI_API_KEYS`: One or more Gemini API keys, separated by commas.
        *   `ADMIN_TELEGRAM_ID`: Your Telegram User ID for error notifications and admin authorization.
        *   `AUTHORIZED_USER_IDS`: Comma-separated User IDs allowed access (Admin ID is added automatically). Leave empty if access is not restricted by user (except admin).
        *   `AUTHORIZED_GROUP_IDS`: Comma-separated Group IDs where the bot should operate. Leave empty if access is not restricted by group.
    *   *Optional:* You can specify different Gemini models (`GEMINI_IMAGE_MODEL`, `GEMINI_TEXT_MODEL`) or the base API URL (`GEMINI_API_BASE_URL`).

4.  **Configure YAML files (optional):**
    *   Styles, types, artists, emojis, and their aliases are configured in `config/styles.yaml`.
    *   System prompts and templates are configured in `config/prompts.yaml`.

### Running the Bot

*   **Simple execution:**
    ```bash
    python bot.py
    ```
    (The bot will stop when the terminal is closed or Ctrl+C is pressed).

*   **Running in the background (Systemd):**
    Use the `manage_bot.sh` script (requires `conda`/`miniconda`).

## 🚀 Using `manage_bot.sh` (Systemd)

This script helps manage the bot as a `systemd` **user service**. This allows the bot to run in the background and restart automatically on failure or system reboot (if configured correctly).

**IMPORTANT:**

*   This assumes you are using `conda` or `miniconda` for Python environment management.
*   **Edit `manage_bot.sh`:** Set the correct name of your conda environment in the `CONDA_ENV_NAME` variable (e.g., `CONDA_ENV_NAME="gemini"`).
*   The script should be located in the project's root folder.

**Commands:**

1.  **Install the service:**
    ```bash
    bash manage_bot.sh install
    ```
    *   This command creates the `.service` file in `~/.config/systemd/user/`.
    *   **Important:** To allow the service to run after you log out, enable "lingering" for your user (only needs to be done once):
        ```bash
        sudo loginctl enable-linger $(whoami)
        ```
    *   **Important:** Enable the service to start automatically on user login:
        ```bash
        systemctl --user enable gemini_bot.service
        # or:
        bash manage_bot.sh enable
        ```

2.  **Start the bot:**
    ```bash
    bash manage_bot.sh start
    # or:
    systemctl --user start gemini_bot.service
    ```

3.  **Stop the bot:**
    ```bash
    bash manage_bot.sh stop
    # or:
    systemctl --user stop gemini_bot.service
    ```

4.  **Restart the bot:**
    ```bash
    bash manage_bot.sh restart
    # or:
    systemctl --user restart gemini_bot.service
    ```

5.  **Check status:**
    ```bash
    bash manage_bot.sh status
    # or:
    systemctl --user status gemini_bot.service
    ```

6.  **View logs:**
    *   Show the last 100 lines and follow new entries (`-f`):
        ```bash
        bash manage_bot.sh logs
        # or specify line count:
        bash manage_bot.sh logs 500
        ```
    *   Direct `journalctl` usage:
        ```bash
        journalctl --user -u gemini_bot.service -f -n 200 # last 200 lines
        ```

7.  **Enable/Disable auto-start:**
    ```bash
    bash manage_bot.sh enable
    bash manage_bot.sh disable
    ```

## 📋 Main Commands (Quick Reference)

```text
/img - <prompt> Generate image (supports --type, --style, --artist, --ar, --random).
/edit - <prompt or flags> Edit the last generated image.
/ask - <question> Ask the text model (uses history).
/clear - Clear text conversation history.
/history - Show text conversation history.
/prompt - [text|reset|clear] Manage image generation prefix.
/reset - [instruction] Set/reset system instruction for the text model.
/toggle_llm - Toggle display of Gemini text in image captions.
/help - Show command help.
/start - Show welcome message and help.
```

**Shortcut Commands:**

*   `!<prompt>` : Same as `/img`.
*   `!!<prompt>` : Same as `!<prompt> --random`.
*   `?<question>` : Same as `/ask`.

## 📞 Contacts

*   **Development:** https://t.me/gin7o
*   **Bot Group:** https://t.me/ginto_bots
```
