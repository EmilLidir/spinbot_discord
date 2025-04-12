#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import discord
from discord import app_commands
import asyncio
import os
import websocket
import time
import re
import json
from collections import defaultdict
import traceback
from typing import Dict, Tuple, List

TOKEN = os.getenv("DISCORD_TOKEN")

def log(message):
    """Simple timestamped logging to console."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def format_rewards_field_value(rewards: Dict[str, int]) -> str:
    """
    Formats the rewards dictionary into a string for the Discord embed field,
    applying emoji mapping and custom sorting.
    """
    if not rewards:
        return "No rewards available."

    direct_emoji_map = {
                    "Werkzeuge": "<:tools:1359522120509554922>",
                    "Ausrüstung/Edelsteine": "<:gear:1359518850713911488>",
                    "Konstrukte": "<:konstrukte:1359518720531235047>",
                    "Kisten": "<:chest:1359518414154104974>",
                    "Dekorationen": "<:dekorationen:1359518108900917359>",
                    "Mehrweller": "<:mehrweller:1359517882064699483>",
                    "Sceattas": "<:sceatta:1359517377066438747>",
                    "Beatrice-Geschenke": "<:beatrice:1359517272640721170>",
                    "Ulrich-Geschenke": "<:ulrich:1359516848474820789>",
                    "Ludwig-Geschenke": "<:ludwig:1359516694716092416>",
                    "Baumarken": "<:baumarken:1359516243463373030>",
                    "Ausbaumarken": "<:ausbaumarken:1359516063477268622>",
                    "Rubine": "<:ruby:1359515929951731812>",
                    "Lose": "<:ticket:1359508197429219501>",
                    "Beschützer des Nordens": "<:beschuetzer:1359481568430915765>",
                    "Schildmaid": "<:schildmaid:1359479372041683015>",
                    "Walküren-Scharfschützin": "<:scharfschuetzin:1359477765421793422>",
                    "Walküren-Waldläuferin": "<:waldlaeuferin:1359477735856013576>"
                }

    sort_priority = {
        "Schildmaid": 0, "Walküren-Scharfschützin": 0, "Beschützer des Nordens": 0, "Walküren-Waldläuferin": 0,
        "Lose": 1,
        "Rubine": 2,
        "Ludwig-Geschenke": 3, "Ulrich-Geschenke": 4, "Beatrice-Geschenke": 5, "Ausbaumarken": 6, "Baumarken": 7, "Sceattas": 8,
    }
    DEFAULT_PRIORITY = 99

    def get_reward_sort_key(item: Tuple[str, int]):
        key, _ = item
        priority = sort_priority.get(key, DEFAULT_PRIORITY)
        return (priority, key)

    try:
        sorted_rewards = sorted(rewards.items(), key=get_reward_sort_key)
    except Exception as e:
        log(f"Fehler beim Sortieren der Belohnungen: {e}")
        sorted_rewards = sorted(rewards.items())

    reward_lines_list = []
    for reward_key, reward_value in sorted_rewards:
        emoji_string = direct_emoji_map.get(reward_key)
        if emoji_string:
            reward_lines_list.append(f"{emoji_string} {reward_value:,}")
        else:
            if not reward_key.startswith("Unbekannt_"):
                 log(f"ℹ️ Kein direkter Emoji-String für '{reward_key}' in der Map gefunden. Zeige Namen an.")
            reward_lines_list.append(f"**{reward_key}**: {reward_value:,}")

    return "\n".join(reward_lines_list)

class SpinModal(discord.ui.Modal, title="🎰 SpinBot Input"):
    """A Discord Modal (form) to collect user credentials and spin count."""
    def __init__(self):
        super().__init__(timeout=300)
        self.username = discord.ui.TextInput(label="Username", placeholder="Enter your Empire username...", required=True, style=discord.TextStyle.short, max_length=50)
        self.password = discord.ui.TextInput(label="Password", placeholder="Enter your password...", style=discord.TextStyle.short, required=True, max_length=50)
        self.spins = discord.ui.TextInput(label="Number of Spins", placeholder="How many times should the wheel be spun?", style=discord.TextStyle.short, required=True, max_length=4)
        self.add_item(self.username)
        self.add_item(self.password)
        self.add_item(self.spins)

    async def on_submit(self, interaction: discord.Interaction):
        """Handles the modal submission."""
        username = self.username.value
        password = self.password.value
        try:
            spins = int(self.spins.value)
            if not (1 <= spins <= 1000): raise ValueError("Spin count out of range.")
        except ValueError:
            await interaction.response.send_message("❌ Invalid number of spins. Please enter a number (e.g., between 1 and 1000).", ephemeral=True); return

        await interaction.response.send_message("🔒 Your input has been processed securely! Starting spins...", ephemeral=True)
        embed = discord.Embed(title="🎰 SpinBot is starting!", description=f"Initializing `{spins}` spin(s) for user `{username}`...\n*This may take a moment.*", color=discord.Color.orange())
        embed.set_footer(text="Please be patient until all spins are completed.")
        status_message = await interaction.followup.send(embed=embed, wait=True)

        try:
            rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins)
            embed_done = discord.Embed(title="✅ Spins Completed!", description=f"All `{spins}` spins for `{username}` have been executed.", color=discord.Color.green())

            if rewards:
                reward_lines = format_rewards_field_value(rewards)
                embed_done.add_field(name=" Received Rewards", value=reward_lines, inline=False)
            else:
                embed_done.add_field(name=" Received Rewards", value="No rewards detected or process ended prematurely.", inline=False)
                embed_done.color = discord.Color.gold()

            await status_message.edit(embed=embed_done)
        except Exception as e:
            print(f"Error during spin_lucky_wheel execution for {username}: {e}"); traceback.print_exc()
            embed_error = discord.Embed(title="❌ Error Executing Spins!", description=f"A problem occurred while processing spins for `{username}`.\nPossible reasons: Incorrect login details, server issues, network interruption.\nPlease check the bot's console logs for details.", color=discord.Color.red())
            await status_message.edit(embed=embed_error)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        """Handles errors originating from the modal interaction itself."""
        print(f"Error in SpinModal interaction: {error}"); traceback.print_exc()
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func('Oops! Something went wrong while opening the form.', ephemeral=True)

class SpinBot(discord.Client):
    """The main Discord bot client."""
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Syncs commands before the bot is ready."""
        log("🔌 Running setup_hook...")
        log("   Syncing slash commands...")
        try:
            await self.tree.sync()
            log("✅ Slash-Befehle synchronisiert.")
        except Exception as e:
            log(f"   ❌ Error syncing commands in setup_hook: {e}")
            traceback.print_exc()
        log("✅ setup_hook complete.")

    async def on_ready(self):
        """Called when the bot successfully connects to Discord."""
        print(f"✅ Bot ist online als {self.user} (ID: {self.user.id})")
        print(f"✅ Bereit und wartet auf Befehle...")


def parse_reward_message(msg, rewards):
    """Parses the specific reward message format from the game server."""
    try:
        match = re.search(r"%xt%lws%1%0%(.*)%", msg)
        if not match:
            if msg.startswith("%xt%"): pass
            return
        json_str = match.group(1)
        data = json.loads(json_str)
        if "R" not in data or not isinstance(data["R"], list):
            log(f"ℹ️ Keine gültige 'R' (Rewards) Liste im geparsten JSON gefunden: {data}")
            return
        for item in data["R"]:
            if not isinstance(item, list) or len(item) < 2:
                log(f"  ⚠️ Überspringe ungültiges Belohnungsitem-Format: {item}")
                continue
            reward_type = item[0]; reward_data = item[1]; amount = 0; reward_name = None
            try:
                if reward_type == "U":
                    if isinstance(reward_data, list) and len(reward_data) == 2: unit_id, amount = reward_data; truppen_namen = { 215: "Schildmaid", 238: "Walküren-Scharfschützin", 227: "Beschützer des Nordens", 216: "Walküren-Waldläuferin" }; reward_name = truppen_namen.get(unit_id, "Werkzeuge")
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'U': {reward_data}")
                elif reward_type == "RI": amount = 1; reward_name = "Ausrüstung/Edelsteine"
                elif reward_type == "CI": amount = 1; reward_name = "Konstrukte"
                elif reward_type == "LM":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ausbaumarken"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'LM': {reward_data}")
                elif reward_type == "LT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Baumarken"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'LT': {reward_data}")
                elif reward_type == "STP":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Sceattas"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'STP': {reward_data}")
                elif reward_type == "SLWT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Lose"
                    else: amount = 1; log(f"  ⚠️ Ungültiges/Kein Mengenformat für Typ 'SLWT', nehme 1 an: {reward_data}"); reward_name = "Lose"
                elif reward_type == "LB":
                    if isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]; reward_name = "Kisten"
                    elif isinstance(reward_data, int): amount = reward_data; reward_name = "Kisten"
                    else: amount = 1; log(f"  ⚠️ Ungewöhnliches Format für Typ 'LB', nehme Menge 1 an: {reward_data}"); reward_name = "Kisten"
                elif reward_type == "UE": amount = 1; reward_name = "Mehrweller"
                elif reward_type == "C2":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Rubine"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'C2': {reward_data}")
                elif reward_type == "FKT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ludwig-Geschenke"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'FKT': {reward_data}")
                elif reward_type == "PTK":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Beatrice-Geschenke"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'PTK': {reward_data}")
                elif reward_type == "KTK":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ulrich-Geschenke"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'KTK': {reward_data}")
                elif reward_type == "D": amount = 1; reward_name = "Dekorationen"
                else:
                    if isinstance(reward_data, int): amount = reward_data
                    elif isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]
                    else: amount = 1
                    reward_name = f"Unbekannt_{reward_type}"; log(f"  -> Unbekannter Belohnungstyp: {reward_type} mit Daten {reward_data}. Gezählt als '{reward_name}'.")
                if reward_name and amount > 0: rewards[reward_name] += amount
            except Exception as parse_inner_err: log(f"  ❌ Fehler beim Verarbeiten des Items {item}: {parse_inner_err}"); traceback.print_exc(limit=1)
    except json.JSONDecodeError as e: log(f"❌ Fehler beim JSON-Parsen des extrahierten Strings '{json_str}': {e}")
    except Exception as e: log(f"❌ Unerwarteter Fehler beim Parsen der Nachricht '{msg[:100]}...': {e}"); traceback.print_exc()


def spin_lucky_wheel(username, password, spins):
    """Connects, logs in, performs spins, and waits specifically for reward messages."""
    rewards = defaultdict(int); ws = None; connect_timeout = 20.0; login_wait_time = 5.0; receive_timeout_per_spin = 15.0; spin_send_delay = 0.3
    try:
        log(f"Versuche Verbindung herzustellen (Timeout: {connect_timeout}s)")
        ws = websocket.create_connection("wss://ep-live-de1-game.goodgamestudios.com/", timeout=connect_timeout)
        log("✅ WebSocket-Verbindung erfolgreich hergestellt!")
        log("Sende Login-Sequenz...")
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>"); time.sleep(0.1)
        ws.send("<msg t='sys'><body action='login' r='0'><login z='EmpireEx_2'><nick><![CDATA[]]></nick><pword><![CDATA[1119057%de%0]]></pword></login></body></msg>"); time.sleep(0.1)
        ws.send(f"%xt%EmpireEx_2%vln%1%{{\"NOM\":\"{username}\"}}%"); time.sleep(0.1)
        login_command = f"%xt%EmpireEx_2%lli%1%{{\"CONM\":491,\"RTM\":74,\"ID\":0,\"PL\":1,\"NOM\":\"{username}\",\"PW\":\"{password}\",\"LT\":null,\"LANG\":\"de\",\"DID\":\"0\",\"AID\":\"1735403904264644306\",\"KID\":\"\",\"REF\":\"https://empire-html5.goodgamestudios.com\",\"GCI\":\"\",\"SID\":9,\"PLFID\":1}}%"
        ws.send(login_command); log(f"🔐 Anmeldeversuch für '{username}' gesendet.")
        log(f"⏳ Warte {login_wait_time} Sekunden nach dem Login-Versuch..."); time.sleep(login_wait_time)
        try:
            ws.settimeout(0.1);
            while True: msg = ws.recv()
        except (websocket.WebSocketTimeoutException, TimeoutError): pass
        except Exception as discard_err: log(f"⚠️ Fehler beim Verwerfen alter Nachrichten nach Login: {discard_err}")
        ws.settimeout(receive_timeout_per_spin)
        log("🚀 Beginne mit den Glücksrad-Spins...")
        for i in range(spins):
            current_spin = i + 1; time.sleep(spin_send_delay)
            spin_command = "%xt%EmpireEx_2%lws%1%{\"LWET\":1}%"
            try: ws.send(spin_command)
            except Exception as send_err: log(f"❌ Fehler beim Senden des Spin-Befehls {current_spin}: {send_err}. Breche ab."); traceback.print_exc(); break
            spin_reward_found = False; search_start_time = time.time()
            while time.time() - search_start_time < receive_timeout_per_spin:
                try:
                    remaining_time = max(0.1, receive_timeout_per_spin - (time.time() - search_start_time)); ws.settimeout(remaining_time)
                    msg = ws.recv();
                    if isinstance(msg, bytes): msg = msg.decode("utf-8", errors="ignore")
                    # --- MODIFIED LOGIC ---
                    if msg.startswith("%xt%lws%1%0%"):
                        log(f"🎯 [{current_spin}/{spins}] Passende Belohnungsnachricht gefunden: {msg}")
                        parse_reward_message(msg, rewards)
                        spin_reward_found = True
                        break
                    # --- END MODIFIED LOGIC ---
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    if not (time.time() - search_start_time < receive_timeout_per_spin): log(f"⏰ [{current_spin}/{spins}] Timeout ({receive_timeout_per_spin}s) erreicht beim Warten auf Belohnungsnachricht.")
                    break
                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as conn_err: log(f"❌ [{current_spin}/{spins}] Verbindung geschlossen: {conn_err}. Breche ab."); raise conn_err
                except Exception as recv_err: log(f"⚠️ [{current_spin}/{spins}] Fehler beim Empfangen/Prüfen: {recv_err}"); traceback.print_exc(); break
            if not spin_reward_found: log(f"🤷 [{current_spin}/{spins}] Keine passende Belohnungsnachricht gefunden ({receive_timeout_per_spin}s).")
        log("✅ Alle angeforderten Spins wurden versucht.")
    except websocket.WebSocketTimeoutException as e: log(f"❌ Connection Timeout ({connect_timeout}s): {e}"); raise ConnectionError("Connection Timeout") from e
    except websocket.WebSocketBadStatusException as e: log(f"❌ WebSocket Handshake Failed (Bad Status {e.status_code}): {e.resp_body}"); raise ConnectionError("WebSocket Handshake Failed") from e
    except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e: log(f"❌ WebSocket Connection Closed Unexpectedly: {e}")
    except Exception as e: log(f"❌ Schwerwiegender Fehler im spin_lucky_wheel: {e}"); traceback.print_exc(); raise e
    finally:
        if ws and ws.connected: log("🔌 Schließe WebSocket-Verbindung."); ws.close()
    log(f"Gesammelte Belohnungen: {dict(rewards)}")
    return dict(rewards)

bot = SpinBot()

@bot.tree.command(name="spin", description="Starts spinning the Lucky Wheel for Goodgame Empire.")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def spin(interaction: discord.Interaction):
    """Slash command handler to initiate the spin process by showing the modal."""
    log(f"Befehl /spin von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.send_modal(SpinModal())

@bot.tree.command(name="spintest", description="Displays a test output of all known rewards with emojis.")
async def spintest(interaction: discord.Interaction):
    """Displays a test embed with sample rewards and emojis."""
    log(f"Befehl /spintest von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.defer(ephemeral=True)

    test_rewards = { "Werkzeuge": 3000, "Ausrüstung/Edelsteine": 2, "Konstrukte": 1, "Kisten": 3, "Dekorationen": 1, "Mehrweller": 1, "Sceattas": 610, "Beatrice-Geschenke": 5, "Ulrich-Geschenke": 7, "Ludwig-Geschenke": 6, "Baumarken": 672, "Ausbaumarken": 6592, "Rubine": 100000, "Lose": 120, "Beschützer des Nordens": 126000, "Schildmaid": 300000, "Walküren-Scharfschützin": 114000, "Walküren-Waldläuferin": 197500 }

    try:
        reward_lines = format_rewards_field_value(test_rewards)
        embed_test = discord.Embed(title="🧪 SpinBot Test Output", description="This is a preview of how the rewards will be displayed:", color=discord.Color.blue())
        embed_test.add_field(name=" Test Rewards", value=reward_lines, inline=False)
        await interaction.followup.send(embed=embed_test, ephemeral=True)
    except Exception as e:
        log(f"Fehler beim Erstellen der Testausgabe: {e}")
        traceback.print_exc()
        await interaction.followup.send("❌ Error generating test output.", ephemeral=True)

@spin.error
async def on_spin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for the /spin command, like cooldowns."""
    if isinstance(error, app_commands.CommandOnCooldown): await interaction.response.send_message(f"⏳ Cooldown active. Please wait {error.retry_after:.2f} more seconds.", ephemeral=True)
    else: log(f"Unhandled error in /spin command processing: {error}"); traceback.print_exc(); resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message; await resp_func("An unexpected error occurred.", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN: print("❌ FATAL: DISCORD_TOKEN Umgebungsvariable nicht gesetzt!"); exit(1)
    else:
        log("Starte SpinBot...")
        try: bot.run(TOKEN)
        except discord.LoginFailure: log("❌ FATAL: Login zum Discord fehlgeschlagen. Token korrekt?")
        except Exception as e: log(f"❌ FATAL: Bot beendet durch Fehler: {e}"); traceback.print_exc()