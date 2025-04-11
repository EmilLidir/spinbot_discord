# SpinBot for Goodgame Empire 🎰

A Discord bot designed to automate the process of spinning the Lucky Wheel in the browser game Goodgame Empire. It interacts with the game's WebSocket server to perform spins and aggregates the received rewards.

**Disclaimer:** This bot interacts with the game in a way that might violate Goodgame Studios' Terms of Service. Automating gameplay actions can lead to warnings or bans on your game account. Use this bot entirely at your own risk. The developers of this bot are not responsible for any consequences resulting from its use. Furthermore, providing your game account credentials to the bot carries inherent security risks. While this bot is designed not to store passwords persistently, any system handling credentials can be a potential target.

## Features

*   `/spin` command to initiate the spinning process via a Discord Modal.
*   Securely prompts for username and password using a Discord Modal (input is ephemeral).
*   Connects to the Goodgame Empire WebSocket server.
*   Performs the specified number of spins on the Lucky Wheel.
*   Parses reward messages received from the server.
*   Aggregates and summarizes the total rewards received.
*   Displays results in a formatted Discord embed.
*   Uses custom Application-Owned Emojis for a visually appealing reward summary.
*   Includes a `/spintest` command to preview the reward display format without using real spins/tickets.
*   Configurable spin count per session.
*   Cooldown mechanism to prevent command spam.

## Requirements

*   Python 3.8 or higher
*   `discord.py` library (`pip install discord.py`)
*   `websocket-client` library (`pip install websocket-client`)
*   A Discord Bot Token
*   A Goodgame Empire account

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <your-repository-url>
    cd <repository-directory>
    ```
    (Or download the Python script directly).

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    ```bash
    pip install discord.py websocket-client
    ```
    (Ensure you have the correct versions if specific ones are required, though the latest should generally work).

4.  **Create a Discord Bot Application:**
    *   Go to the [Discord Developer Portal](https://discord.com/developers/applications).
    *   Create a New Application.
    *   Go to the "Bot" tab and click "Add Bot".
    *   Enable the `Server Members Intent` and `Message Content Intent` under "Privileged Gateway Intents" (although this specific script *doesn't* currently require them, it's good practice if you extend it).
    *   Copy the **Bot Token** (Keep this secret!). You will need it for configuration.
    *   Go to the "OAuth2" -> "URL Generator" tab. Select the `bot` and `application.commands` scopes. In "Bot Permissions", select necessary permissions like `Send Messages`, `Embed Links`, `Read Message History` (optional but useful), etc. Copy the generated URL and invite the bot to your server.

5.  **Configure Environment Variable:**
    *   The bot requires your Discord Bot Token to be set as an environment variable named `DISCORD_TOKEN`.
    *   You can set this variable in your operating system, or use a `.env` file in the bot's directory (you'll need to install `python-dotenv` via `pip install python-dotenv` and add `from dotenv import load_dotenv; load_dotenv()` at the beginning of the script).
    *   **Example `.env` file:**
        ```dotenv
        DISCORD_TOKEN=YOUR_SUPER_SECRET_BOT_TOKEN_HERE
        ```

6.  **Set Up Custom Emojis:**
    *   This bot uses **Application-Owned Emojis**. You need to upload these in the Discord Developer Portal for *your specific bot application*.
    *   Go to your Application in the [Discord Developer Portal](https://discord.com/developers/applications).
    *   Navigate to the "Emojis" tab.
    *   Upload the corresponding images for the rewards.
    *   **Crucially**, name the emojis **exactly** as they appear as the *values* in the `direct_emoji_map`'s keys within the `SpinModal.on_submit` method (e.g., name the ruby emoji `ruby`, the tools emoji `tools`, the Schildmaid emoji `schildmaid`, etc.).
    *   The current code expects emojis named: `tools`, `gear`, `konstrukte`, `chest`, `dekorationen`, `mehrweller`, `sceatta`, `beatrice`, `ulrich`, `ludwig`, `baumarken`, `ausbaumarken`, `ruby`, `ticket`, `beschuetzer`, `schildmaid`, `scharfschuetzin`, `waldlaeuferin`. Ensure all these are uploaded with the correct names.

## Usage

1.  **Run the Bot:**
    ```bash
    python your_script_name.py
    ```
    (Replace `your_script_name.py` with the actual filename).

2.  **Discord Commands:**
    *   `/spin`: Initiates the process. The bot will respond with a Modal (a pop-up form).
        *   Enter your Goodgame Empire **Username**.
        *   Enter your Goodgame Empire **Password**.
        *   Enter the **Number of Spins** you want to perform.
        *   Click Submit.
        *   The bot will confirm receipt (ephemerally) and then post a status message indicating it's starting. This message will be updated with the results or any errors.
    *   `/spintest`: Displays a test embed showing how all known rewards would be formatted with their corresponding emojis. This is useful for verifying your emoji setup without actually spinning the wheel. The output is ephemeral (only visible to you).

## Important Considerations

*   **Security:** You are providing your game account credentials directly to the bot via Discord's Modal interface. While Modals offer a degree of security over plain text messages, and this script does not intentionally store the password after use, be aware of the risks involved in handling credentials this way. Ensure the machine running the bot is secure.
*   **Terms of Service:** Using bots or scripts to automate gameplay is often against the game's Terms of Service (ToS). Using this bot could lead to disciplinary action against your game account, including temporary or permanent bans. **Use at your own discretion and risk.**
*   **Game Updates:** This bot relies on the specific WebSocket communication protocol used by Goodgame Empire at the time of writing. If Goodgame Studios updates the game's communication methods, login sequence, or message formats, **this bot will likely break** and will require code updates to function again.
*   **Error Handling:** The bot includes error handling for common issues like connection timeouts, invalid input, and WebSocket errors. If spins fail, check the bot's console logs for detailed error messages and tracebacks.

## Troubleshooting

*   **Bot doesn't come online:**
    *   Verify the `DISCORD_TOKEN` environment variable is set correctly and the token is valid.
    *   Check the console for any startup errors (e.g., library import errors, login failures).
*   **Login Fails / No Rewards:**
    *   Double-check your entered username and password.
    *   The game servers might be down or having issues.
    *   Goodgame Studios might have updated the game's login protocol, breaking the bot. Check console logs for connection or handshake errors.
*   **Emojis Don't Display Correctly:**
    *   Ensure you uploaded the emojis as **Application-Owned Emojis** in the Discord Developer Portal (NOT just server emojis).
    *   Verify the emoji **names** in the Developer Portal exactly match the required names (e.g., `tools`, `ruby`, `schildmaid`).
    *   Verify the **Emoji IDs** in the `direct_emoji_map` within the code match the actual IDs shown in the Developer Portal.
    *   **Restart the bot** completely after uploading or renaming emojis in the Developer Portal.
    *   Use the `/spintest` command to check the display.
*   **Modal Error:**
    *   Ensure the bot has necessary permissions in the channel (Send Messages, Embed Links).
    *   There might be temporary Discord API issues.

## License

(Optional) Specify a license, e.g.:
This project is licensed under the MIT License - see the LICENSE.md file for details.
