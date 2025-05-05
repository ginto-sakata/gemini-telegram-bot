# Changelog

## Version 2.2.0 (2025-06-05) - Enhanced Controls & Information

This version introduces significant enhancements to user control over image generation parameters, adds comprehensive informational commands, refines randomization logic, and improves the user interface.

### Summary

Major changes include the introduction of granular randomization flags (per type, style, artist, or group), explicit short aliases for artists, informative list commands (`/types`, `/styles`, `/artists`, `/ts`, `/show_all`, `/man`), differentiation between "Apply" and "Re-Gen" logic regarding randomness, and UI updates like index prefixes and a consistent `!` command display. The `/edit` command has been removed in favor of text replies with arguments.

### ✨ Features

*   **Granular Randomization Flags:**
    *   `-t` (no value): Random Type.
    *   `-s` (no value): Random Style (globally from all).
    *   `-s0`: Random Style (relative to selected Type).
    *   `-s <GroupAlias>`: Random Style (from a specific group like 'craft', 'anime'; see `/styles`).
    *   `-a` (no value): Random Artist.
    *   `-r` / `-tsa` / `!!<prompt>`: Random Type, Global Style, and Artist.
    *   Flags can be combined (e.g., `-ts`, `-ta`).
    *   Updated argument parser (`handlers/image_gen.py`) and resolver (`_resolve_settings`).
*   **Informational Commands:** Added new commands for exploring options (`handlers/info_commands.py`):
    *   `/types`: Lists all available Types with `[Index] Emoji Alias`.
    *   `/styles`: Lists all available Styles with `[Index] Alias` and available Style Group Aliases.
    *   `/artists`: Lists all available Artists with `[Index] Emoji FullAlias (ShortAlias)`.
    *   `/ts`: Lists Types with their applicable Styles nested below.
    *   `/show_all`: Combines the output of the above list commands.
    *   `/man`: Provides a detailed, conversational explanation of parameters, interactions, and non-obvious use cases.
*   **Explicit Artist Short Aliases:**
    *   Added `alias_short` field to artist definitions in `config/styles.yaml` for precise control over short names used in commands (`-a <AliasShort>`) and button labels.
    *   Removed automatic last-name generation in favor of explicit definition.
    *   Updated `config.py`, parser, keyboards, and messages to use `alias_short`. **Requires manual population of `alias_short` in `styles.yaml`.**
*   **Argument Parsing Enhancements:**
    *   Parser now supports spaceless arguments for indices (e.g., `-t1s50a90`).
    *   Parser correctly handles combined flags (e.g., `-ts`).
*   **Reply-to-Edit with Arguments:** Users can now reply to a bot-generated image with text containing flags (`-t`, `-s`, `-a`, `-r`, etc.) to perform targeted edits or re-generations based on those arguments (`handlers/text_gen.py::handle_text_reply`).
*   **Artist Emojis:** Added support for displaying emojis next to artist names (requires defining `emoji` in `config/styles.yaml`).

### 🔧 Changes & Fixes

*   **Apply vs. Re-Gen Randomness Logic:**
    *   `🔄 Заново` (Re-Gen) now correctly reapplies the *original* randomization flags (`-t`, `-s`, `-a`, `-r`, `-s0`, groups) used when the image was first generated, preserving the randomness intent across re-generations. Original parsed arguments are stored in message state (`ui/messages.py`, `handlers/callbacks.py`).
    *   `✅ Применить` (Apply) uses the *currently selected effective settings* from the keyboard/state, creating a new baseline image state without the original randomization markers.
*   **Keyboard State Reset:** After clicking "Apply" or "Re-Gen", the original message's keyboard/caption now resets to display the settings *that specific* message was generated with (`handlers/callbacks.py`).
*   **Default LLM Text Display:** Changed the default behavior to *hide* the LLM text response in image captions. This is now configurable via the `DEFAULT_DISPLAY_LLM_TEXT` variable in `.env` (defaulting to `False`). Updated `config.py`, `/toggle_llm` command, and message generation logic.
*   **`/prompt clear` Fix:** Corrected the `/prompt` command handling so that `/prompt clear` now correctly sets the image suffix to an empty string instead of the literal word "clear" (`handlers/commands.py`, `bot.py`).
*   **Expanded Content:** Significantly increased the number and variety of Types, Styles (including groups like craft, media, technical), and Artists in `config/styles.yaml`.

### 💄 UI Updates

*   **Index Prefix:** All Type, Style, and Artist buttons and caption parameter lists now display the absolute index prepended (`[N]`).
*   **Consistent Command Prefix:** The command line example displayed in image captions now always uses `!` instead of varying between `/img` and `/edit`.
*   **Artist Button Labels:** Artist buttons now use the `alias_short` for brevity.
*   Updated help texts (`/start`, `/help`, `README.ru.md`) to reflect new commands, removed `/edit`, and clarified new argument syntax.

### 🗑️ Removed

*   **`/edit` Command:** Removed the dedicated `/edit` command and its handler. Editing is now handled via text replies with arguments or the "Apply" button.

## Version 2.1.1 (2025-05-05)

This version addresses critical errors related to the bot's shutdown sequence when stopped via Ctrl+C (SIGINT).

### Summary

The primary focus of this update was to refactor the main application lifecycle management in `bot.py` to ensure a graceful and error-free shutdown process. This resolves `RuntimeError` exceptions ("Application is still running", "Updater is still running", "Cannot close a running event loop") and prevents related `NetworkError` exceptions that occurred when the polling task was terminated abruptly during shutdown. The state saving mechanism during shutdown now operates reliably.

### Fixes & Changes

*   **Refactored Bot Execution Loop (`bot.py`):**
    *   Replaced the manual setup involving `application.initialize()`, `application.updater.start_polling()`, `application.start()`, and `asyncio.Event().wait()` with the recommended `application.run_polling()` method.
    *   `run_polling()` internally handles the application lifecycle, including receiving stop signals (like Ctrl+C), gracefully stopping the updater, running `application.shutdown()`, and managing the underlying asyncio event loop correctly.
*   **Synchronous `main` Function (`bot.py`):**
    *   Changed the `main` function from `async def main()` to `def main()` to work correctly with the blocking nature of `application.run_polling()`.
    *   Removed the `await` keyword from the `application.run_polling()` call.
*   **Simplified Entry Point (`bot.py`):**
    *   Modified the `if __name__ == "__main__":` block to call the synchronous `main()` function directly, removing the need for `asyncio.run()`.
*   **Reliable Shutdown Sequence (`bot.py`):**
    *   Removed manual `application.stop()` and `application.shutdown()` calls from the `main` function's `finally` block, as `run_polling` now manages this.
    *   The `finally` block in `main` now correctly executes *after* `run_polling` has completed its shutdown, ensuring the `save_state_on_shutdown()` function is called at the appropriate time.
*   **Outcome:** The bot now starts correctly, runs indefinitely via `run_polling`, and shuts down gracefully upon receiving Ctrl+C or other termination signals without throwing RuntimeErrors or NetworkErrors related to the event loop or updater state. State saving during shutdown is now reliable.

## Version 2.1 (2025-05-04) - Interactive Image Keyboards & State Persistence

This version introduces significant user interface and backend changes, moving from static image generation responses to interactive messages with inline keyboards. It also implements state management and persistence for these interactions.

### Summary

Image generation responses now include an inline keyboard allowing users to interactively modify parameters (Aspect Ratio, Type, Style), enhance the prompt using an LLM, and re-generate the image. The state of these selections is tracked per message and persists across bot restarts using manual save/load of `bot_data`.

### ✨ Features & Changes

*   **Interactive Inline Keyboards:**
    *   Image generation responses (`/img`, `!`, photo replies, etc.) now include an inline keyboard (`ui/keyboards.py`, `ui/messages.py`).
    *   **Aspect Ratio Control:** Buttons allow selecting common aspect ratios (1:1, 4:3, 16:9, 3:4, 9:16) via a two-page selector (`generate_ar_selection_keyboard`).
    *   **Image Type Selection:** Buttons allow selecting the main image type (e.g., Photo, Digital Art, Anime) with pagination (`generate_type_selection_keyboard`, `config.MAIN_TYPES_DATA`). Selecting a type now automatically selects a relevant random style.
    *   **Image Style Selection:** Buttons allow selecting specific styles (e.g., Pixar, Van Gogh, Cinematic Lighting). Styles shown are contextually relevant to the selected Type (or all styles if no type is chosen). Includes pagination and shows the absolute style index (`#N`) on the button (`generate_style_selection_keyboard`, `config.ALL_STYLES_DATA`).
    *   **Random Selection:** Added "🎲 Случ." (Random) buttons for Type and Style selection.
    *   **Clearing Selections:** Added "🚫 Сброс" (Reset) buttons to clear Type (which also clears Style) or just Style.
    *   **Prompt Enhancement:** Added "✨ Улучшить" (Enhance) button. This triggers a call to the text LLM (`api/gemini_api.enhance_prompt_with_gemini`) using a dedicated system prompt (`config/prompts.yaml: enhance_image_prompt_respect_style`) to refine the scene description based on the original prompt and selected Type/Style context. The enhanced prompt is then used for subsequent re-generations.
    *   **Re-generation:** Added "🔄 Заново" (Again/Re-gen) button to trigger image generation using the current effective prompt and selected settings (`_handle_regen` calling `_initiate_image_generation`).

*   **State Management (`bot_data` & `TTLCache`):**
    *   Implemented per-message state tracking for images with keyboards (`bot.py`).
    *   State is stored in `application.bot_data` (a `TTLCache` instance) using keys like `img_info:{chat_id}:{message_id}` (`config.IMAGE_STATE_CACHE_KEY_PREFIX`).
    *   The state dictionary stores the original prompt, effective prompt, selected AR/Type/Style data and indices, and UI visibility flags (`settings_visible`, `ar_state`, `type_select_visible`, etc.).

*   **State Persistence:**
    *   Keyboard state (specifically entries matching the `img_info:` prefix in `bot_data`) is now saved to a file (`persistence/keyboard_state.pkl`) on graceful shutdown (`bot.py: save_bot_data_to_file`).
    *   Saved state is loaded back into the `TTLCache` on bot startup (`bot.py: load_bot_data_from_file`). This allows keyboards on old messages to remain functional after a restart (within the TTL limit).

*   **UI Updates & Feedback:**
    *   Clicking keyboard buttons provides immediate feedback by updating the message caption and keyboard layout (`ui/messages.py: update_caption_and_keyboard`).
    *   Captions dynamically reflect the currently selected AR, Type (Alias), and Style (Alias #Index) (`ui/messages.py: _build_caption_parts`).
    *   User feedback messages (e.g., "Enhancing...", "Re-generating...") are provided via `query.answer()` or temporary message edits.

*   **Callback Handling (`handlers/callbacks.py`):**
    *   Created a dedicated module to handle all `CallbackQuery` events from the inline keyboards.
    *   Implemented `handle_callback_query` as the main dispatcher.
    *   Added various helper functions (`_handle_toggle_settings`, `_handle_set_ar`, `_handle_set_type`, `_handle_set_style`, `_handle_enhance`, `_handle_regen`, etc.) to manage state changes based on button actions.
    *   Registered the `CallbackQueryHandler` in `bot.py`.

*   **Configuration (`config/`, `.env`):**
    *   Added necessary constants (`IMAGE_STATE_CACHE_KEY_PREFIX`, `BOT_DATA_STATE_FILE`, `STATE_CACHE_TTL_SECONDS`).
    *   Added the `enhance_image_prompt_respect_style` system prompt definition in `prompts.yaml`.
    *   Refined `styles.yaml` and `config.py` loading to ensure necessary data (aliases, absolute indices, style keys per type) was available for keyboard generation and state management.

*   **Code Structure:**
    *   Introduced `ui/keyboards.py` and `handlers/callbacks.py` for better organization.
    *   Refactored image generation initiation logic (`handlers/image_gen.py: _initiate_image_generation`) to handle being called from both commands and callbacks.

## Version 2.0 (2025-05-04) - Project Restructure & Configuration Overhaul

This version marks a major architectural refactoring of the bot, moving from a single-script implementation to a modular project structure. It introduces external configuration files, enhances core functionalities like prompt generation and argument parsing, and lays the groundwork for future features.

### Summary

The bot's codebase was reorganized into distinct modules for configuration (`config/`), API interactions (`api/`), command/message handling (`handlers/`), user interface elements (`ui/`), and utility functions (`utils/`). Configuration for styles, prompts, and authorization is now managed via `.env` and YAML files, allowing for easier customization. Command handling, especially for image generation, was streamlined with a more robust argument parser.

### ✨ Features & Changes

*   **YAML Configuration (`config/`, `config.py`):**
    *   Introduced YAML files (`styles.yaml`, `prompts.yaml`) to define image styles, type-to-style mappings, prompt templates, and system prompts externally.
    *   Created `config.py` to load configuration from both `.env` and YAML files, process the data (e.g., create lookup maps for styles/types, handle aliases), and provide centralized access to configuration constants.
*   **Advanced Argument Parsing (`handlers/image_gen.py`):**
    *   Implemented a new argument parser (`parse_img_args_prompt_first`) for `/img` and `!` commands.
    *   Supports flags (`--type`/`-t`, `--style`/`-s`, `--ar`/`-a`, `--random`/`-r`) for specifying image generation parameters.
    *   Handles type/style selection by name, alias, relative index (for styles within a type context), and absolute index (`#N` for styles).
    *   Supports random selection markers (`0` or `--random`).
*   **Refined Prompt Helpers (`utils/prompt_helpers.py`):**
    *   Created a dedicated module for prompt construction logic.
    *   `get_style_detail` function now dynamically selects styles based on type mappings defined in `styles.yaml` via `config.py`, replacing hardcoded logic.
    *   Added `generate_random_styled_prompt` and `construct_prompt_with_style` using data loaded from config.
*   **Dedicated API Module (`api/gemini_api.py`):**
    *   Moved all Google Gemini API call logic (image generation, text streaming, single text request) into a separate module.
    *   Improved API error parsing and reporting (`_parse_gemini_finish_reason`).
    *   Added timing logs for API calls.
    *   Included groundwork for prompt enhancement (`enhance_prompt_with_gemini`), although not yet exposed via UI.
*   **Improved Text Formatting (`utils/html_helpers.py`):**
    *   Replaced basic `markdown.markdown` usage with a custom `convert_basic_markdown_to_html` function that handles escaping and converts basic Markdown (bold, italic, code, code blocks) to Telegram-supported HTML more reliably.
*   **Text Generation System Prompt (`/reset`):**
    *   The `/reset` command now specifically manages the system prompt for the *text* model (`CHAT_DATA_KEY_TEXT_SYSTEM_PROMPT`), separate from the image prefix handled by `/prompt`.
*   **Toggle LLM Text Display (`/toggle_llm`):**
    *   Added the `/toggle_llm` command (`handlers/commands.py`) to allow users to control whether the text portion of the Gemini image model's response is included in the image caption (`ui/messages.py`).

### 🏗️ Refactoring & Structure

*   **Modular Codebase:** Migrated from a single `bot.py` file to a multi-directory structure:
    *   `api/`: For external API interactions.
    *   `config/`: For YAML configuration files.
    *   `handlers/`: For specific command, message, and callback handlers.
    *   `ui/`: For message formatting and keyboard generation (preparation for v2.1).
    *   `utils/`: For shared helper functions (auth, cache, HTML, prompts, Telegram interactions).
    *   `config.py`: Central configuration loading and processing.
    *   `bot.py`: Main application setup, handler registration, and execution loop.
*   **Dedicated Utility Modules:** Created specific modules for common tasks like authorization (`utils/auth.py`), image caching (`utils/cache.py`), etc.
*   **Refined Message Sending:** Centralized response sending logic in `ui/messages.py` (`send_image_generation_response`) and `utils/telegram_helpers.py` (`stream_and_update_message`).

### 🗑️ Removed

*   **Legacy Commands (`!!`, `!!!`, `!!!!`):** Removed the multi-exclamation mark commands for translation, programmatic styling, and LLM rephrasing. These functionalities are intended to be replaced or integrated into the new argument parsing system and the upcoming interactive keyboard features.
*   **Legacy Command (`/edit`):** Removed the `/edit` command, which relied on simple last-image tracking. Editing is now primarily handled via text replies to bot images or will be integrated into interactive keyboards.

### 🔧 Fixes

*   Implicitly improved error handling and robustness through modular design and dedicated API/utility functions.
*   Standardized logging setup.
*   Addressed potential issues with Markdown parsing by implementing a custom HTML converter.