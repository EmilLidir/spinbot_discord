#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
from discord import app_commands
import asyncio
import os
import websocket # Ensure 'websocket-client' library is installed (`pip install websocket-client`)
import time
import re
import json
from collections import defaultdict
import traceback # For better error logging

# --- Configuration ---
# Retrieve the bot token from environment variables for security
TOKEN = os.getenv("DISCORD_TOKEN")

# --- Discord UI Modal for Input ---
class SpinModal(discord.ui.Modal, title="🎰 SpinBot Eingabe"):
    """A Discord Modal (form) to collect user credentials and spin count."""
    def __init__(self):
        super().__init__(timeout=300) # 5-minute timeout for the modal

        self.username = discord.ui.TextInput(
            label="Benutzername",
            placeholder="Gib deinen Empire-Benutzernamen ein...",
            required=True,
            style=discord.TextStyle.short,
            max_length=50
        )
        self.password = discord.ui.TextInput(
            label="Passwort",
            placeholder="Gib dein Passwort ein...",
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        self.spins = discord.ui.TextInput(
            label="Anzahl der Spins",
            placeholder="Wie oft soll das Rad gedreht werden?",
            style=discord.TextStyle.short,
            required=True,
            max_length=4 # Limit max spins input length
        )

        self.add_item(self.username)
        self.add_item(self.password)
        self.add_item(self.spins)

    async def on_submit(self, interaction: discord.Interaction):
        """Handles the modal submission."""
        username = self.username.value
        password = self.password.value

        # Validate spins input
        try:
            spins = int(self.spins.value)
            if not (1 <= spins <= 1000): # Example range limit
                raise ValueError("Spin count out of range.")
        except ValueError:
            await interaction.response.send_message(
                "❌ Ungültige Anzahl an Spins. Bitte gib eine Zahl (z.B. zwischen 1 und 1000) ein.",
                ephemeral=True
            )
            return

        # Send initial confirmations
        await interaction.response.send_message("🔒 Deine Eingaben wurden sicher verarbeitet! Starte Spins...", ephemeral=True)

        embed = discord.Embed(
            title="🎰 SpinBot wird gestartet!",
            description=f"Initialisiere `{spins}` Spin(s) für den Benutzer `{username}`...\n"
                        f"*Dies kann einen Moment dauern.*",
            color=discord.Color.orange()
        )
        embed.set_footer(text="Bitte habe Geduld, bis alle Spins abgeschlossen sind.")
        # Use followup as response was already sent (ephemeral)
        status_message = await interaction.followup.send(embed=embed, wait=True)

        # --- Run the blocking WebSocket task in a separate thread ---
        try:
            rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins)

            # --- Process results ---
            embed_done = discord.Embed(
                title="✅ Spins Abgeschlossen!",
                description=f"Alle `{spins}` Spins für `{username}` wurden ausgeführt.",
                color=discord.Color.green()
            )

            if rewards:
                # --- START: Emoji Enhancement Logic (Using Application Emojis) ---

                # 1. Define the mapping from reward key (string) to emoji name (string)
                #    Make sure these keys EXACTLY match the keys generated in parse_reward_message
                #    Make sure the emoji names EXACTLY match the names you gave them in Discord Developer Portal -> Emojis
                emoji_map = {
                    "Schildmaid": "schildmaid",
                    "Beschützer des Nordens": "beschuetzer",
                    "Walküren-Scharfschützin": "scharfschuetzin",
                    "Walküren-Waldläuferin": "waldlaeuferin",
                    "Konstrukte": "konstrukte",
                    "Mehrweller": "mehrweller",
                    "Ulrich-Geschenke": "ulrich",
                    "Beatrice-Geschenke": "beatrice",
                    "Ludwig-Geschenke": "ludwig",
                    "Baumarken": "baumarken",
                    "Ausbaumarken": "ausbaumarken",
                    "Dekorationen": "dekorationen",
                    "Lose": "ticket",
                    "Rubine": "ruby", 
                    "Kisten": "chest",
                    "Werkzeuge": "tools",
                    "Sceattas": "sceatta",
                    "Ausrüstung/Edelsteine": "gear",
                }

                reward_lines_list = []
                # 2. Get the list of ALL emojis the bot client can see/use
                #    This includes its own application-owned emojis.
                client_emojis = interaction.client.emojis

                # 3. Iterate through sorted rewards and format lines
                for reward_key, reward_value in sorted(rewards.items()):
                    emoji_str = "" # Default: no emoji prefix
                    if reward_key in emoji_map:
                        emoji_name = emoji_map[reward_key]
                        # Find the emoji object by name within all accessible emojis
                        # This will find your application-owned emojis if the names match.
                        found_emoji = discord.utils.get(client_emojis, name=emoji_name)
                        if found_emoji:
                            # If found, use it! It automatically converts to <:name:id> string
                            emoji_str = f"{found_emoji} " # Add space after emoji
                        else:
                             # Optional: Log if an expected application emoji wasn't found
                             # This helps debug if you mistyped a name in the map or the portal
                             log(f"⚠️ Warnung: Anwendungs-Emoji '{emoji_name}' nicht gefunden für Belohnung '{reward_key}'.")

                    # Format the line: Use emoji if found, otherwise just the key
                    # Use f-string for number formatting with comma separators
                    reward_lines_list.append(f"{emoji_str}**{reward_key}**: {reward_value:,}")

                reward_lines = "\n".join(reward_lines_list)
                # --- END: Emoji Enhancement Logic ---

                embed_done.add_field(name="🎁 Erhaltene Belohnungen", value=reward_lines, inline=False)
            else:
                embed_done.add_field(name="🎁 Erhaltene Belohnungen", value="Keine Belohnungen erkannt oder Prozess vorzeitig beendet.", inline=False)
                embed_done.color = discord.Color.gold() # Indicate potentially incomplete run

            await status_message.edit(embed=embed_done) # Edit the original status message

        except Exception as e:
            # --- Handle errors during the spin process ---
            print(f"Error during spin_lucky_wheel execution for {username}: {e}") # Log to console
            traceback.print_exc() # Print full traceback to console

            embed_error = discord.Embed(
                title="❌ Fehler beim Ausführen der Spins!",
                description=f"Ein Problem ist während der Verarbeitung der Spins für `{username}` aufgetreten.\n"
                            f"Mögliche Gründe: Falsche Login-Daten, Serverprobleme, Netzwerkunterbrechung.\n"
                            f"Bitte überprüfe die Konsolenlogs des Bots für Details.",
                color=discord.Color.red()
            )
            await status_message.edit(embed=embed_error) # Edit status message to show error

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handles errors originating from the modal interaction itself."""
        print(f"Error in SpinModal interaction: {error}")
        traceback.print_exc()
        # Use followup because the interaction might already be responded to or deferred
        if interaction.response.is_done():
             await interaction.followup.send('Hoppla! Etwas ist beim Öffnen des Formulars schiefgelaufen.', ephemeral=True)
        else:
             await interaction.response.send_message('Hoppla! Etwas ist beim Öffnen des Formulars schiefgelaufen.', ephemeral=True)

# --- Discord Bot Class ---
class SpinBot(discord.Client):
    """The main Discord bot client."""
    def __init__(self):
        # Define necessary intents
        intents = discord.Intents.default()
        # No special intents needed for slash commands + reading client emojis
        intents.message_content = False

        super().__init__(intents=intents)
        # Command Tree for slash commands
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Syncs slash commands when the bot is ready."""
        await self.tree.sync()
        print(f"✅ Slash-Befehle synchronisiert.")

    async def on_ready(self):
        """Called when the bot successfully connects to Discord."""
        print(f"✅ Bot ist online als {self.user} (ID: {self.user.id})")
        print(f"✅ Eigene Emojis: {[e.name for e in self.emojis]}") # Log loaded application emojis
        print(f"✅ Bereit und wartet auf Befehle...")


# --- Helper Functions ---
def log(message):
    """Simple timestamped logging to console."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def parse_reward_message(msg, rewards):
    """Parses the specific reward message format from the game server."""
    try:
        # Target the specific message format for lucky wheel spins
        match = re.search(r"%xt%lws%1%0%(.*)%", msg)
        if not match:
            # Optional: Log other %xt% messages if needed for debugging, but keep it minimal
            if msg.startswith("%xt%"):
                 log(f"ℹ️ Ignoriere Nachricht (passt nicht zum Belohnungsformat %xt%lws%1%0%...): {msg[:80]}...")
            return

        log(f"🎯 Potentielle Glücksrad-Belohnungsnachricht gefunden: {msg[:100]}...")
        json_str = match.group(1)
        data = json.loads(json_str)

        # Structure expected: {"R":[["TYPE", DATA], ["TYPE", DATA], ...], ...other keys...}
        if "R" not in data or not isinstance(data["R"], list):
            log(f"ℹ️ Keine gültige 'R' (Rewards) Liste im geparsten JSON gefunden: {data}")
            return

        log(f"✨ Verarbeite Belohnungen aus JSON: {data['R']}")

        for item in data["R"]:
            if not isinstance(item, list) or len(item) < 2:
                log(f"  ⚠️ Überspringe ungültiges Belohnungsitem-Format: {item}")
                continue

            reward_type = item[0]    # e.g., "U", "RI", "STP"
            reward_data = item[1]    # e.g., [215, 1500] or 100 or 1

            # --- Reward Type Handling (using defaultdict automatically initializes keys to 0) ---
            amount = 0
            reward_name = None

            try:
                if reward_type == "U": # Truppen oder Werkzeuge
                    if isinstance(reward_data, list) and len(reward_data) == 2:
                        unit_id, amount = reward_data
                        truppen_namen = {
                            215: "Schildmaid", 238: "Walküren-Scharfschützin",
                            227: "Beschützer des Nordens", 216: "Walküren-Waldläuferin"
                        }
                        if unit_id in truppen_namen:
                            reward_name = truppen_namen[unit_id]
                        else: # Assume Werkzeuge if ID not in troop map
                            reward_name = "Werkzeuge"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'U': {reward_data}")

                elif reward_type == "RI": # Ausrüstung oder Edelsteine
                    amount = 1 # Usually just one item
                    reward_name = "Ausrüstung/Edelsteine"

                elif reward_type == "CI": # Konstrukt
                    amount = 1
                    reward_name = "Konstrukte"

                elif reward_type == "LM": # Ausbaumarken
                    if isinstance(reward_data, int): amount = reward_data
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'LM': {reward_data}")
                    reward_name = "Ausbaumarken"

                elif reward_type == "STP": # Sceattas (Event Währung?)
                    if isinstance(reward_data, int): amount = reward_data
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'STP': {reward_data}")
                    reward_name = "Sceattas"

                elif reward_type == "SLWT": # Ticket
                     if isinstance(reward_data, int): amount = reward_data
                     else: log(f"  ⚠️ Ungültiges Format für Typ 'SLWT': {reward_data}")
                     reward_name = "Lose"

                elif reward_type == "LB": # Kisten
                    # Sometimes format is ["LB", [box_id, amount]], sometimes just amount?
                    if isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int):
                         amount = reward_data[1]
                    elif isinstance(reward_data, int): # Fallback if just amount is given
                         amount = reward_data
                    else: # Default to 1 if format is unexpected
                         amount = 1
                         log(f"  ⚠️ Ungewöhnliches Format für Typ 'LB', nehme Menge 1 an: {reward_data}")
                    reward_name = "Kisten"

                elif reward_type == "UE": # Mehrweller
                    amount = 1
                    reward_name = "Mehrweller"

                elif reward_type == "C2": # Rubine
                    if isinstance(reward_data, int): amount = reward_data
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'C2': {reward_data}")
                    reward_name = "Rubine"

                elif reward_type == "FKT": # Ludwig-Geschenke
                    if isinstance(reward_data, int): amount = reward_data
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'FKT': {reward_data}")
                    reward_name = "Ludwig-Geschenke"

                elif reward_type == "PTK": # Beatrice-Geschenke
                    if isinstance(reward_data, int): amount = reward_data
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'PTK': {reward_data}")
                    reward_name = "Beatrice-Geschenke"

                elif reward_type == "KTK": # Ulrich-Geschenke
                    if isinstance(reward_data, int): amount = reward_data
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'KTK': {reward_data}")
                    reward_name = "Ulrich-Geschenke"

                elif reward_type == "D": # Dekorationen
                    amount = 1
                    reward_name = "Dekorationen"

                else: # Handle unknown types
                    # Try to guess amount
                    if isinstance(reward_data, int): amount = reward_data
                    elif isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]
                    else: amount = 1 # Default to 1 if unsure
                    reward_name = f"Unbekannt_{reward_type}"
                    log(f"  -> Unbekannter Belohnungstyp: {reward_type} mit Daten {reward_data}. Gezählt als '{reward_name}'.")

                # Add to rewards if valid name and amount found
                if reward_name and amount > 0:
                    rewards[reward_name] += amount
                    log(f"  -> Belohnung: {amount:,}x {reward_name}")

            except Exception as parse_inner_err:
                log(f"  ❌ Fehler beim Verarbeiten des Items {item}: {parse_inner_err}")
                traceback.print_exc(limit=1) # Log traceback for this specific item error


    except json.JSONDecodeError as e:
        log(f"❌ Fehler beim JSON-Parsen des extrahierten Strings '{json_str}': {e}")
    except Exception as e:
        log(f"❌ Unerwarteter Fehler beim Parsen der Nachricht '{msg[:100]}...': {e}")
        traceback.print_exc()


# --- Core WebSocket Logic (Robust Receive Loop Method) ---
def spin_lucky_wheel(username, password, spins):
    """Connects, logs in, performs spins, and waits specifically for reward messages."""
    rewards = defaultdict(int)
    ws = None

    # --- Timeouts and Delays ---
    connect_timeout = 20.0
    login_wait_time = 5.0 # Still wait a bit after login seems successful
    # Timeout *per spin* to wait for the specific reward message
    receive_timeout_per_spin = 15.0 # seconds (Increase if rewards sometimes take longer)
    spin_send_delay = 0.3 # Small delay before sending next spin command

    try:
        log(f"Versuche Verbindung herzustellen (Timeout: {connect_timeout}s)")
        ws = websocket.create_connection(
            "wss://ep-live-de1-game.goodgamestudios.com/", # Consider making this configurable
            timeout=connect_timeout,
            # Add origin header, sometimes needed
            header={"Origin": "https://empire-html5.goodgamestudios.com"}
        )
        log("✅ WebSocket-Verbindung erfolgreich hergestellt!")

        # --- Login Sequence ---
        log("Sende Login-Sequenz...")
        # Version Check - Important! Might need updating if game changes significantly
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>")
        time.sleep(0.1)
        # Initial login zone message
        ws.send("<msg t='sys'><body action='login' r='0'><login z='EmpireEx_2'><nick><![CDATA[]]></nick><pword><![CDATA[1119057%de%0]]></pword></login></body></msg>")
        time.sleep(0.1)
        # Send username (validation?)
        ws.send(f"%xt%EmpireEx_2%vln%1%{{\"NOM\":\"{username}\"}}%")
        time.sleep(0.1)
        # Main login command with credentials
        login_payload = {
            "CONM": 491, "RTM": 74, "ID": 0, "PL": 1, "NOM": username, "PW": password,
            "LT": None, "LANG": "de", "DID": "0", "AID": "1735403904264644306", "KID": "",
            "REF": "https://empire-html5.goodgamestudios.com", "GCI": "", "SID": 9, "PLFID": 1
        }
        login_command = f"%xt%EmpireEx_2%lli%1%{json.dumps(login_payload)}%"
        ws.send(login_command)
        log(f"🔐 Anmeldeversuch für '{username}' gesendet.")

        # --- Wait after login attempt ---
        # Ideally, we'd wait for a specific success message like %xt%l%l%...
        # but a simple wait is less prone to breaking if that message changes format.
        log(f"⏳ Warte {login_wait_time} Sekunden nach dem Login-Versuch...")
        time.sleep(login_wait_time)

        # Optional: Clear any messages received during the login wait
        try:
            ws.settimeout(0.1) # Short timeout for clearing buffer
            while True:
                msg = ws.recv()
                # log(f"  (Verwerfe Nachricht nach Login: {msg[:60]}...)") # Uncomment for debug
        except (websocket.WebSocketTimeoutException, TimeoutError):
            pass # Expected timeout when buffer is empty
        except Exception as discard_err:
            log(f"⚠️ Fehler beim Verwerfen alter Nachrichten nach Login: {discard_err}")
        finally:
             ws.settimeout(receive_timeout_per_spin) # Restore main timeout


        log("🚀 Beginne mit den Glücksrad-Spins...")

        # --- Spin Loop ---
        for i in range(spins):
            current_spin = i + 1
            log(f"🎰 [{current_spin}/{spins}] Bereite Spin vor...")
            time.sleep(spin_send_delay) # Small delay before sending command

            # --- Send Spin Command ---
            spin_command = "%xt%EmpireEx_2%lws%1%{\"LWET\":1}%" # lws = Lucky Wheel Spin? LWET=1 might mean 'use ticket'
            try:
                ws.send(spin_command)
                log(f"-> Befehl für Spin {current_spin} gesendet.")
            except Exception as send_err:
                log(f"❌ Fehler beim Senden des Spin-Befehls {current_spin}: {send_err}. Breche ab.")
                traceback.print_exc()
                break # Stop all spins if sending fails

            # --- Wait Specifically for the Reward Message ---
            spin_reward_found = False
            search_start_time = time.time()
            log(f"👂 [{current_spin}/{spins}] Warte auf Belohnungsnachricht (max {receive_timeout_per_spin}s)...")

            while time.time() - search_start_time < receive_timeout_per_spin:
                try:
                    # Calculate remaining time for this specific recv attempt
                    remaining_time = max(0.1, receive_timeout_per_spin - (time.time() - search_start_time))
                    ws.settimeout(remaining_time) # Dynamically set timeout

                    msg = ws.recv()
                    if isinstance(msg, bytes):
                        msg = msg.decode("utf-8", errors="ignore")

                    # *** THE CRITICAL CHECK: Look for the specific reward message format ***
                    if msg.startswith("%xt%lws%1%0%"):
                        log(f"🎯 [{current_spin}/{spins}] Passende Belohnungsnachricht gefunden!")
                        parse_reward_message(msg, rewards) # Parse the found message
                        spin_reward_found = True
                        break # Found the reward, exit inner 'while' loop, proceed to next spin
                    else:
                        # Log other game messages briefly to see what's happening
                        if msg.startswith("%xt%"): # Only log game-related %xt% messages
                             log(f"🌀 [{current_spin}/{spins}] Ignoriere Nachricht: {msg[:80]}...")
                        # else: log(f"🌀 [{current_spin}/{spins}] Ignoriere Non-XT Nachricht.")

                except (websocket.WebSocketTimeoutException, TimeoutError):
                    # This means ws.recv() timed out waiting for *any* message within remaining_time
                    # Check if the overall spin timeout has been exceeded by the outer loop condition
                    if not (time.time() - search_start_time < receive_timeout_per_spin):
                         log(f"⏰ [{current_spin}/{spins}] Timeout ({receive_timeout_per_spin}s) erreicht beim Warten auf Belohnungsnachricht.")
                    # If recv timed out but outer loop time isn't up, the outer loop just continues waiting
                    break # Exit inner loop on timeout, outer loop condition handles overall timeout

                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as conn_err:
                    log(f"❌ [{current_spin}/{spins}] Verbindung geschlossen beim Warten auf Belohnung: {conn_err}. Breche ab.")
                    raise conn_err # Re-raise to break outer loop and signal failure

                except Exception as recv_err:
                    log(f"⚠️ [{current_spin}/{spins}] Fehler beim Empfangen/Prüfen der Nachricht: {recv_err}")
                    traceback.print_exc()
                    # Optionally break inner loop here too, or let it retry the receive
                    break # Safer to break inner loop on unexpected errors

            # --- After the inner receive loop for this spin ---
            if not spin_reward_found:
                 # This happens if the inner loop exited due to timeout or error without finding '%xt%lws%1%0%'
                 log(f"🤷 [{current_spin}/{spins}] Keine passende Belohnungsnachricht innerhalb von {receive_timeout_per_spin}s gefunden oder Fehler beim Empfang.")
                 # Decide whether to continue to the next spin or stop. Continuing might be okay.

        log("✅ Alle angeforderten Spins wurden versucht.")

    # --- Exception Handling for the whole process ---
    except websocket.WebSocketTimeoutException as e:
        log(f"❌ Timeout ({connect_timeout}s) beim Herstellen der WebSocket-Verbindung. Server nicht erreichbar? {e}")
        raise ConnectionError("Connection Timeout") from e # Raise specific error for modal
    except websocket.WebSocketBadStatusException as e:
         log(f"❌ Fehler beim WebSocket Handshake (Bad Status): {e.status_code} {e.resp_body}. URL korrekt? Origin benötigt? Login Server down?")
         raise ConnectionError("WebSocket Handshake Failed") from e # Raise specific error for modal
    except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e:
         log(f"❌ WebSocket-Verbindung war geschlossen oder wurde während des Prozesses unerwartet beendet. {e}")
         # Don't necessarily raise, might have partial results. The modal will show what was collected.
    except Exception as e:
        log(f"❌ Schwerwiegender Fehler im spin_lucky_wheel Prozess: {e}")
        traceback.print_exc()
        raise e # Re-raise critical errors to be caught by the modal's handler
    finally:
        # --- Ensure the WebSocket is closed cleanly ---
        if ws and ws.connected:
            log("🔌 Schließe WebSocket-Verbindung.")
            try:
                # Send logout? Optional, closing might be enough
                # ws.send("%xt%EmpireEx_2%logout%1%{}%")
                # time.sleep(0.2)
                ws.close()
            except Exception as close_err:
                log(f"⚠️ Fehler beim Schließen der WebSocket-Verbindung: {close_err}")
        elif ws:
            log("ℹ️ WebSocket-Verbindung war bereits geschlossen.")
        else:
            log("ℹ️ Keine WebSocket-Verbindung zum Schließen vorhanden.")

    log(f"Gesammelte Belohnungen: {dict(rewards)}") # Log final rewards to console
    return dict(rewards) # Return the collected rewards


# --- Bot Instance and Command Definition ---
bot = SpinBot()

@bot.tree.command(name="spin", description="Startet das Glücksrad-Drehen für Goodgame Empire.")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id) # Cooldown: 1 use per 60 sec per user
async def spin(interaction: discord.Interaction):
    """Slash command handler to initiate the spin process by showing the modal."""
    log(f"Befehl /spin von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    # Show the modal to the user to collect credentials
    await interaction.response.send_modal(SpinModal())

@spin.error
async def on_spin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for the /spin command, like cooldowns."""
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(
            f"⏳ Dieser Befehl hat einen Cooldown. Bitte warte noch {error.retry_after:.2f} Sekunden.",
            ephemeral=True
        )
    else:
        # Log other errors originating from the command itself (not the modal's on_submit)
        log(f"Unhandled error in /spin command processing: {error}")
        traceback.print_exc()
        # Use followup if original interaction response was already sent (e.g., deferred)
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func(
            "Ein unerwarteter Fehler ist beim Verarbeiten des Befehls aufgetreten.",
            ephemeral=True
        )

# --- Bot Execution ---
if __name__ == "__main__":
    if not TOKEN:
        print("❌ FATAL: DISCORD_TOKEN Umgebungsvariable nicht gesetzt!")
        print("Bitte setze die Umgebungsvariable 'DISCORD_TOKEN' mit deinem Discord Bot Token.")
        exit(1) # Exit if token is missing
    else:
        log("Starte SpinBot...")
        try:
            # Run the bot asynchronously
            bot.run(TOKEN)
        except discord.LoginFailure:
            log("❌ FATAL: Login zum Discord fehlgeschlagen. Ist der Token korrekt?")
        except Exception as e:
            log(f"❌ FATAL: Ein unerwarteter Fehler hat den Bot beendet: {e}")
            traceback.print_exc()