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
TOKEN = os.getenv("DISCORD_TOKEN")

# --- Helper Functions ---
def log(message):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

# --- Discord UI Modal for Input ---
class SpinModal(discord.ui.Modal, title="🎰 SpinBot Eingabe"):
    def __init__(self):
        super().__init__(timeout=300)
        self.username = discord.ui.TextInput(label="Benutzername", placeholder="Gib deinen Empire-Benutzernamen ein...", required=True, style=discord.TextStyle.short, max_length=50)
        self.password = discord.ui.TextInput(label="Passwort", placeholder="Gib dein Passwort ein...", style=discord.TextStyle.short, required=True, max_length=50)
        self.spins = discord.ui.TextInput(label="Anzahl der Spins", placeholder="Wie oft soll das Rad gedreht werden?", style=discord.TextStyle.short, required=True, max_length=4)
        self.add_item(self.username)
        self.add_item(self.password)
        self.add_item(self.spins)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username.value
        password = self.password.value
        try:
            spins = int(self.spins.value)
            if not (1 <= spins <= 1000): raise ValueError("Spin count out of range.")
        except ValueError:
            await interaction.response.send_message("❌ Ungültige Anzahl an Spins. Bitte gib eine Zahl (z.B. zwischen 1 und 1000) ein.", ephemeral=True); return

        await interaction.response.send_message("🔒 Deine Eingaben wurden sicher verarbeitet! Starte Spins...", ephemeral=True)
        embed = discord.Embed(title="🎰 SpinBot wird gestartet!", description=f"Initialisiere `{spins}` Spin(s) für den Benutzer `{username}`...\n*Dies kann einen Moment dauern.*", color=discord.Color.orange())
        embed.set_footer(text="Bitte habe Geduld, bis alle Spins abgeschlossen sind.")
        status_message = await interaction.followup.send(embed=embed, wait=True)

        try:
            rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins)
            embed_done = discord.Embed(title="✅ Spins Abgeschlossen!", description=f"Alle `{spins}` Spins für `{username}` wurden ausgeführt.", color=discord.Color.green())

            if rewards:
                emoji_map = { "Schildmaid": "schildmaid", "Beschützer des Nordens": "beschuetzer", "Walküren-Scharfschützin": "scharfschuetzin", "Walküren-Waldläuferin": "waldlaeuferin", "Konstrukte": "konstrukte", "Mehrweller": "mehrweller", "Ulrich-Geschenke": "ulrich", "Beatrice-Geschenke": "beatrice", "Ludwig-Geschenke": "ludwig", "Baumarken": "baumarken", "Ausbaumarken": "ausbaumarken", "Dekorationen": "dekorationen", "Lose": "ticket", "Rubine": "ruby", "Kisten": "chest", "Werkzeuge": "tools", "Sceattas": "sceatta", "Ausrüstung/Edelsteine": "gear" }
                reward_lines_list = []
                # --- MODIFIED: Use client.emojis directly and filter it ---
                all_client_emojis = interaction.client.emojis
                bot_app_id = interaction.client.user.id

                # Filter the main list to get potential app emojis
                possible_app_emojis = [emoji for emoji in all_client_emojis if getattr(emoji, 'application_id', None) == bot_app_id]
                log(f"ℹ️ In on_submit: Found {len(possible_app_emojis)} potential app emojis by filtering client.emojis.")

                # Iterate through sorted rewards
                for reward_key, reward_value in sorted(rewards.items()):
                    found_emoji_obj = None # Use a different name to avoid confusion
                    if reward_key in emoji_map:
                        emoji_name = emoji_map[reward_key]
                        # Search within the filtered list
                        found_emoji_obj = discord.utils.get(possible_app_emojis, name=emoji_name)

                    # --- FORMATTING LOGIC ---
                    if found_emoji_obj:
                        reward_lines_list.append(f"{found_emoji_obj} {reward_value:,}")
                    else:
                        # Fallback to **NAME**: COUNT
                        if reward_key in emoji_map: # Log only if it was mapped but not found in the filtered list
                             log(f"ℹ️ Anwendungs-Emoji '{emoji_map[reward_key]}' für '{reward_key}' nicht in gefilterter Liste gefunden. Zeige Namen an.")
                        reward_lines_list.append(f"**{reward_key}**: {reward_value:,}")

                reward_lines = "\n".join(reward_lines_list)
                embed_done.add_field(name="🎁 Erhaltene Belohnungen", value=reward_lines, inline=False)
            else:
                embed_done.add_field(name="🎁 Erhaltene Belohnungen", value="Keine Belohnungen erkannt oder Prozess vorzeitig beendet.", inline=False)
                embed_done.color = discord.Color.gold()

            await status_message.edit(embed=embed_done)
        except Exception as e:
            print(f"Error during spin_lucky_wheel execution for {username}: {e}"); traceback.print_exc()
            embed_error = discord.Embed(title="❌ Fehler beim Ausführen der Spins!", description=f"Ein Problem ist während der Verarbeitung der Spins für `{username}` aufgetreten.\n M\u00f6gliche Gr\u00fcnde: Falsche Login-Daten, Serverprobleme, Netzwerkunterbrechung.\n Bitte \u00fcberpr\u00fcfe die Konsolenlogs des Bots f\u00fcr Details.", color=discord.Color.red())
            await status_message.edit(embed=embed_error)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        print(f"Error in SpinModal interaction: {error}"); traceback.print_exc()
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func('Hoppla! Etwas ist beim Öffnen des Formulars schiefgelaufen.', ephemeral=True)

# --- Discord Bot Class (Simplified setup_hook) ---
class SpinBot(discord.Client):
    """The main Discord bot client."""
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        # Removed self.app_emojis instance variable

    async def setup_hook(self):
        """Syncs commands before the bot is ready."""
        log("🔌 Running setup_hook...")
        # Removed the application_info fetching logic
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
        # Log the general emoji cache content - this *should* include app emojis when ready
        print(f"✅ Gesamt-Emojis im Client-Cache (self.emojis): {[e.name for e in self.emojis]}")
        print(f"✅ Bereit und wartet auf Befehle...")


def parse_reward_message(msg, rewards):
    """Parses the specific reward message format from the game server."""
    try:
        match = re.search(r"%xt%lws%1%0%(.*)%", msg)
        if not match:
            if msg.startswith("%xt%"): pass # Keep logs cleaner
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
            try: # Simplified Reward Type Handling
                if reward_type == "U":
                    if isinstance(reward_data, list) and len(reward_data) == 2: unit_id, amount = reward_data; truppen_namen = { 215: "Schildmaid", 238: "Walküren-Scharfschützin", 227: "Beschützer des Nordens", 216: "Walküren-Waldläuferin" }; reward_name = truppen_namen.get(unit_id, "Werkzeuge")
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'U': {reward_data}")
                elif reward_type == "RI": amount = 1; reward_name = "Ausrüstung/Edelsteine"
                elif reward_type == "CI": amount = 1; reward_name = "Konstrukte"
                elif reward_type == "LM":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ausbaumarken"
                    else: log(f"  ⚠️ Ungültiges Format für Typ 'LM': {reward_data}")
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
                else: # Handle unknown types
                    if isinstance(reward_data, int): amount = reward_data
                    elif isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]
                    else: amount = 1
                    reward_name = f"Unbekannt_{reward_type}"; log(f"  -> Unbekannter Belohnungstyp: {reward_type} mit Daten {reward_data}. Gezählt als '{reward_name}'.")
                if reward_name and amount > 0: rewards[reward_name] += amount
            except Exception as parse_inner_err: log(f"  ❌ Fehler beim Verarbeiten des Items {item}: {parse_inner_err}"); traceback.print_exc(limit=1)
    except json.JSONDecodeError as e: log(f"❌ Fehler beim JSON-Parsen des extrahierten Strings '{json_str}': {e}")
    except Exception as e: log(f"❌ Unerwarteter Fehler beim Parsen der Nachricht '{msg[:100]}...': {e}"); traceback.print_exc()


# --- Core WebSocket Logic (Reverted Login Command Construction) ---
def spin_lucky_wheel(username, password, spins):
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
        try: # Clear buffer
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
                    if msg.startswith("%xt%lws%1%0%"): log(f"🎯 [{current_spin}/{spins}] Passende Belohnungsnachricht gefunden!"); parse_reward_message(msg, rewards); spin_reward_found = True; break
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

# --- Bot Instance and Command Definition ---
bot = SpinBot()

@bot.tree.command(name="spin", description="Startet das Glücksrad-Drehen für Goodgame Empire.")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def spin(interaction: discord.Interaction):
    log(f"Befehl /spin von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.send_modal(SpinModal())

@spin.error
async def on_spin_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown): await interaction.response.send_message(f"⏳ Cooldown aktiv. Bitte warte noch {error.retry_after:.2f} Sekunden.", ephemeral=True)
    else: log(f"Unhandled error in /spin command processing: {error}"); traceback.print_exc(); resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message; await resp_func("Ein unerwarteter Fehler ist aufgetreten.", ephemeral=True)

# --- Bot Execution ---
if __name__ == "__main__":
    if not TOKEN: print("❌ FATAL: DISCORD_TOKEN Umgebungsvariable nicht gesetzt!"); exit(1)
    else:
        log("Starte SpinBot...")
        try: bot.run(TOKEN)
        except discord.LoginFailure: log("❌ FATAL: Login zum Discord fehlgeschlagen. Token korrekt?")
        except Exception as e: log(f"❌ FATAL: Bot beendet durch Fehler: {e}"); traceback.print_exc()