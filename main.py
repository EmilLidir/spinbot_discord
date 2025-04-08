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
            placeholder="Gib dein Passwort (sicher) ein...",
            style=discord.TextStyle.short, # CORRECTED: Use short style for password
            required=True,
            max_length=50
        )
        self.spins = discord.ui.TextInput(
            label="Anzahl der Spins",
            placeholder="Wie oft soll das Rad gedreht werden? (Zahl)",
            style=discord.TextStyle.short,
            required=True,
            max_length=4 # Limit max spins input length
        )

        self.add_item(self.username)
        self.add_item(self.password)
        self.add_item(self.spins)

    # --- on_submit and on_error methods remain the same ---
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
        await interaction.response.send_message("🔒 Deine Eingaben wurden sicher verarbeitet! Starte den Prozess...", ephemeral=True)

        embed = discord.Embed(
            title="🎰 SpinBot wird gestartet!",
            description=f"Initialisiere `{spins}` Spin(s) für den Benutzer `{username}`...\n"
                        f"*Dies kann einen Moment dauern, besonders der Login.*",
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
                description=f"Alle `{spins}` angeforderten Spins für `{username}` wurden ausgeführt.",
                color=discord.Color.green()
            )

            if rewards:
                reward_lines = "\n".join([f"**{k}**: {v:,}" for k, v in sorted(rewards.items())]) # Sort and format numbers
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
        intents.message_content = False # Not needed for slash commands usually

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
        print(f"✅ Bereit und wartet auf Befehle...")


# --- Helper Functions ---
def log(message):
    """Simple timestamped logging to console."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def parse_reward_message(msg, rewards):
    """Parses the specific reward message format from the game server."""
    try:
        # Regex to find the specific reward message format and extract the JSON part
        # %xt%<extension>%<command>%<room_id>%<data_type>%<json_payload>%
        match = re.search(r"%xt%lws%1%0%(.*)%", msg)
        if not match:
            # Avoid logging every single non-matching message if many are expected
            # Only log potentially relevant game messages that start similarly
            if msg.startswith("%xt%"):
                 log(f"ℹ️ Ignoriere Nachricht (passt nicht zum Belohnungsformat %xt%lws%1%0%...): {msg[:80]}...")
            return # Not the message format we are looking for

        log(f"🎯 Potentielle Belohnungsnachricht gefunden: {msg[:100]}...")
        json_str = match.group(1)
        data = json.loads(json_str)

        # Check if the expected reward data structure is present
        if "R" not in data or not isinstance(data["R"], list):
            log(f"ℹ️ Keine gültige 'R' (Rewards) Liste im geparsten JSON gefunden: {data}")
            return # No reward array or wrong format in this specific message

        log(f"✨ Verarbeite Belohnungen aus JSON: {data['R']}")

        for item in data["R"]:
            # Basic validation of item structure
            if not isinstance(item, list) or len(item) < 2:
                log(f"  ⚠️ Überspringe ungültiges Belohnungsitem-Format: {item}")
                continue

            reward_type = item[0]
            reward_data = item[1]

            # --- Reward Type Handling ---
            # (Using .get for safer dictionary lookups)
            if reward_type == "U": # Truppen oder Werkzeuge
                unit_id, amount = reward_data
                truppen_namen = {
                    215: "Schildmaid", 238: "Walküren-Scharfschützin",
                    227: "Beschützer des Nordens", 216: "Walküren-Waldläuferin"
                }
                if unit_id in truppen_namen:
                    reward_name = truppen_namen[unit_id]
                    rewards[reward_name] += amount
                    log(f"  -> Belohnung: {amount:,}x {reward_name}")
                else: # Werkzeuge (assuming other U types are tools)
                    rewards["Werkzeuge"] += amount
                    log(f"  -> Belohnung: {amount:,}x Werkzeuge (ID: {unit_id})")

            elif reward_type == "RI": # Ausrüstung oder Edelsteine
                 amount = 1 # Usually count is 1 for these items
                 rewards["Ausrüstung/Edelsteine"] += amount # Combine for simplicity
                 log(f"  -> Belohnung: {amount:,}x Ausrüstung/Edelsteine")

            elif reward_type == "CI": # Konstrukt
                amount = 1
                rewards["Konstrukte"] += amount
                log(f"  -> Belohnung: {amount:,}x Konstrukte")

            elif reward_type == "LM": # Ausbaumarken
                amount = reward_data
                rewards["Ausbaumarken"] += amount
                log(f"  -> Belohnung: {amount:,}x Ausbaumarken")

            elif reward_type == "STP": # Sceattas (Special Currency)
                amount = reward_data
                rewards["Sceattas"] += amount
                log(f"  -> Belohnung: {amount:,}x Sceattas")

            elif reward_type == "LB": # Kisten (Loot Boxes)
                 # reward_data might be [box_type_id, amount]
                 amount = reward_data[1] if isinstance(reward_data, list) and len(reward_data) > 1 else 1
                 rewards["Kisten"] += amount
                 log(f"  -> Belohnung: {amount:,}x Kisten")

            elif reward_type == "UE": # Mehrweller (Unit Enchantment?)
                 amount = 1 # Assuming always 1
                 rewards["Mehrweller"] += amount
                 log(f"  -> Belohnung: {amount:,}x Mehrweller")

            elif reward_type == "C2": # Rubine (Premium Currency)
                 amount = reward_data
                 rewards["Rubine"] += amount
                 log(f"  -> Belohnung: {amount:,}x Rubine")

            elif reward_type == "FKT": # Ludwig-Geschenke (Event Item?)
                 amount = reward_data
                 rewards["Ludwig-Geschenke"] += amount
                 log(f"  -> Belohnung: {amount:,}x Ludwig-Geschenke")

            elif reward_type == "PTK": # Beatrice-Geschenke (Event Item?)
                 amount = reward_data
                 rewards["Beatrice-Geschenke"] += amount
                 log(f"  -> Belohnung: {amount:,}x Beatrice-Geschenke")

            elif reward_type == "KTK": # Ulrich-Geschenke (Event Item?)
                 amount = reward_data
                 rewards["Ulrich-Geschenke"] += amount
                 log(f"  -> Belohnung: {amount:,}x Ulrich-Geschenke")

            elif reward_type == "D": # Dekorationen
                 amount = 1 # Assuming always 1
                 rewards["Dekorationen"] += amount
                 log(f"  -> Belohnung: {amount:,}x Dekorationen")

            else:
                 # Handle unknown types gracefully
                 amount = 1 # Default amount if structure is unknown
                 if isinstance(reward_data, (int, float)):
                     amount = reward_data
                 elif isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], (int, float)):
                     amount = reward_data[1] # Guess amount might be second element

                 reward_key = f"Unbekannt_{reward_type}"
                 rewards[reward_key] += amount
                 log(f"  -> Unbekannter Belohnungstyp: {reward_type} mit Daten {reward_data}. Gezählt als '{reward_key}'.")

    except json.JSONDecodeError as e:
        log(f"❌ Fehler beim JSON-Parsen des extrahierten Strings '{json_str}': {e}")
    except Exception as e:
        log(f"❌ Unerwarteter Fehler beim Parsen der Nachricht '{msg[:100]}...': {e}")
        traceback.print_exc() # Log full traceback for unexpected parsing errors


# --- Keep SpinModal, SpinBot, log, and the *detailed* parse_reward_message from the full code ---
# Ensure parse_reward_message still has the check:
# match = re.search(r"%xt%lws%1%0%(.*)%", msg)
# if not match:
#     # Log ignored message (optional)
#     return
# ... rest of parsing logic ...

# --- Core WebSocket Logic (Robust Receive Loop Method) ---
def spin_lucky_wheel(username, password, spins):
    """Connects, logs in, performs spins, and waits specifically for reward messages."""
    rewards = defaultdict(int)
    ws = None

    # --- Timeouts and Delays ---
    connect_timeout = 20.0
    login_wait_time = 5.0 # Still wait a bit after login seems successful
    # Timeout *per spin* to wait for the specific reward message
    # Increase this if rewards sometimes take longer to arrive
    receive_timeout_per_spin = 15.0 # seconds
    spin_send_delay = 0.3 # Small delay before sending next spin command

    try:
        log(f"Versuche Verbindung herzustellen (Timeout: {connect_timeout}s)")
        ws = websocket.create_connection(
            "wss://ep-live-de1-game.goodgamestudios.com/",
            timeout=connect_timeout
        )
        log("✅ WebSocket-Verbindung erfolgreich hergestellt!")

        # --- Login Sequence (Keep as before) ---
        log("Sende Login-Sequenz...")
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>")
        time.sleep(0.1)
        ws.send("<msg t='sys'><body action='login' r='0'><login z='EmpireEx_2'><nick><![CDATA[]]></nick><pword><![CDATA[1119057%de%0]]></pword></login></body></msg>")
        time.sleep(0.1)
        ws.send(f"%xt%EmpireEx_2%vln%1%{{\"NOM\":\"{username}\"}}%")
        time.sleep(0.1)
        login_payload = {
            "CONM": 491, "RTM": 74, "ID": 0, "PL": 1, "NOM": username, "PW": password,
            "LT": None, "LANG": "de", "DID": "0", "AID": "1735403904264644306", "KID": "",
            "REF": "https://empire-html5.goodgamestudios.com", "GCI": "", "SID": 9, "PLFID": 1
        }
        login_command = f"%xt%EmpireEx_2%lli%1%{json.dumps(login_payload)}%"
        ws.send(login_command)
        log(f"🔐 Anmeldeversuch für '{username}' gesendet.")

        log(f"⏳ Warte {login_wait_time} Sekunden nach dem Login-Versuch...")
        time.sleep(login_wait_time)

        # Optional: Clear buffer after login wait
        try:
            ws.settimeout(0.1)
            while True: msg = ws.recv()
        except (websocket.WebSocketTimeoutException, TimeoutError): pass # Expected
        except Exception as discard_err: log(f"⚠️ Fehler beim Verwerfen alter Nachrichten: {discard_err}")

        # Set the main timeout for receive operations within the loop
        # This will be adjusted dynamically per recv call based on remaining time
        # ws.settimeout(receive_timeout_per_spin) # Set a base timeout

        log("🚀 Beginne mit den Glücksrad-Spins...")

        # --- Spin Loop ---
        for i in range(spins):
            current_spin = i + 1
            log(f"🎰 [{current_spin}/{spins}] Bereite Spin vor...")
            time.sleep(spin_send_delay) # Small delay before sending command

            # --- Send Spin Command ---
            spin_command = "%xt%EmpireEx_2%lws%1%{\"LWET\":1}%"
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
                    # Calculate remaining time for this attempt
                    remaining_time = max(0.1, receive_timeout_per_spin - (time.time() - search_start_time))
                    ws.settimeout(remaining_time) # Set timeout for this specific recv

                    msg = ws.recv()
                    if isinstance(msg, bytes):
                        msg = msg.decode("utf-8", errors="ignore")

                    # *** THE CRITICAL CHECK ***
                    # Check if it's the specific reward message format we want
                    if msg.startswith("%xt%lws%1%0%"):
                        log(f"🎯 [{current_spin}/{spins}] Passende Belohnungsnachricht gefunden!")
                        parse_reward_message(msg, rewards) # Parse the found message
                        spin_reward_found = True
                        break # Found the reward, exit inner 'while' loop and go to next spin
                    else:
                        # Log other messages briefly to see what's being ignored
                        if msg.startswith("%xt%"): # Only log game-related messages
                             log(f"🌀 [{current_spin}/{spins}] Ignoriere Nachricht: {msg[:80]}...")
                        # else: log(f"🌀 [{current_spin}/{spins}] Ignoriere unspezifische Nachricht.")

                except (websocket.WebSocketTimeoutException, TimeoutError):
                    # This means ws.recv() timed out waiting for *any* message within remaining_time
                    # Check if the overall spin timeout has been exceeded by the outer loop condition
                    if not (time.time() - search_start_time < receive_timeout_per_spin):
                         log(f"⏰ [{current_spin}/{spins}] Timeout ({receive_timeout_per_spin}s) erreicht beim Warten auf Belohnungsnachricht.")
                    # else: # Timeout on recv, but overall time not expired yet, loop continues
                    #    log(f"-> Kurzer Timeout bei recv(), versuche erneut...")
                    # Break inner loop on timeout either way, handled below
                    break

                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as conn_err:
                    log(f"❌ [{current_spin}/{spins}] Verbindung geschlossen beim Warten auf Belohnung: {conn_err}. Breche ab.")
                    raise conn_err # Re-raise to break outer loop and stop everything

                except Exception as recv_err:
                    log(f"⚠️ [{current_spin}/{spins}] Fehler beim Empfangen/Prüfen: {recv_err}")
                    traceback.print_exc()
                    # Optionally break inner loop here too, or let it retry
                    break # Safer to break inner loop on unexpected errors

            # --- After the inner receive loop for this spin ---
            if not spin_reward_found:
                 # This happens if the inner loop exited due to timeout or error without finding the reward msg
                 log(f"🤷 [{current_spin}/{spins}] Keine passende Belohnungsnachricht innerhalb von {receive_timeout_per_spin}s gefunden oder Fehler beim Empfang.")
                 # Decide if you want to stop all spins here or just continue with the next
                 # continue # Continue to next spin is usually desired

        log("✅ Alle angeforderten Spins wurden versucht.")

    # --- Exception Handling (keep the detailed blocks from previous full code) ---
    except websocket.WebSocketTimeoutException as e:
        log(f"❌ Timeout ({connect_timeout}s) beim Herstellen der WebSocket-Verbindung. Server nicht erreichbar? {e}")
        raise ConnectionError("Connection Timeout") from e
    except websocket.WebSocketBadStatusException as e:
         log(f"❌ Fehler beim WebSocket Handshake (Bad Status): {e.status_code} {e.resp_body}. URL korrekt? Origin benötigt?")
         raise ConnectionError("WebSocket Handshake Failed") from e
    except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e:
         log(f"❌ WebSocket-Verbindung war geschlossen oder wurde während des Prozesses unerwartet beendet. {e}")
         # Let it return potentially partial rewards
    except Exception as e:
        log(f"❌ Schwerwiegender Fehler im spin_lucky_wheel Prozess: {e}")
        traceback.print_exc()
        raise e # Re-raise critical errors
    finally:
        # --- Ensure the WebSocket is closed cleanly ---
        if ws and ws.connected:
            log("🔌 Schließe WebSocket-Verbindung.")
            try: ws.close()
            except Exception as close_err: log(f"⚠️ Fehler beim Schließen der WebSocket-Verbindung: {close_err}")
        elif ws: log("ℹ️ WebSocket-Verbindung war bereits geschlossen.")
        else: log("ℹ️ Keine WebSocket-Verbindung zum Schließen vorhanden.")

    log(f"Gesammelte Belohnungen: {dict(rewards)}")
    return dict(rewards)

# --- Ensure the rest of the bot code (SpinModal, SpinBot, @bot.tree.command, bot.run) is integrated with this function ---


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
        log(f"Unhandled error in /spin command: {error}")
        traceback.print_exc()
        await interaction.response.send_message(
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
            # Consider adding proper signal handling for graceful shutdown if needed
            bot.run(TOKEN)
        except discord.LoginFailure:
            log("❌ FATAL: Login zum Discord fehlgeschlagen. Ist der Token korrekt?")
        except Exception as e:
            log(f"❌ FATAL: Ein unerwarteter Fehler hat den Bot beendet: {e}")
            traceback.print_exc()