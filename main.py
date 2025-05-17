#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
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

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.common.exceptions import WebDriverException, TimeoutException as SeleniumTimeoutException

# --- Configuration ---
TOKEN = os.getenv("DISCORD_TOKEN")
GGE_LOGIN_URL_FOR_RCT = "https://empire.goodgamestudios.com/" 
GGE_WEBSOCKET_URL = "wss://ep-live-de1-game.goodgamestudios.com/"
GGE_GAME_WORLD = "EmpireEx_2"
GGE_RECAPTCHA_V3_SITE_KEY = "6Lc7w34oAAAAFKfhm1n41m96VQm4MNqEdpCYm-k" 
GGE_RECAPTCHA_ACTION = "submit"
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID") # For faster command syncing during testing

# --- Logging Setup (MOVED TO THE TOP) ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s] %(message)s',
    handlers=[
        logging.FileHandler("spinbot_recaptcha.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Main logger for the application
logger = logging.getLogger("SpinBotApp")
# Specific logger for reCAPTCHA part if desired, or just use the main logger
logger_rct = logging.getLogger("SpinBotRCT") # This will inherit SpinBotApp's settings if not configured separately

def log(message): # Uses the global 'logger'
    logger.info(message)

# --- Reward Formatting and Emoji Mapping ---
def format_rewards_field_value(rewards: Dict[str, int]) -> str:
    # ... (implementation as before) ...
    if not rewards: return "Keine Belohnungen verfügbar."
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
    def get_reward_sort_key(item: Tuple[str, int]): key, _ = item; priority = sort_priority.get(key, DEFAULT_PRIORITY); return (priority, key)
    try: sorted_rewards = sorted(rewards.items(), key=get_reward_sort_key)
    except Exception as e: log(f"Fehler beim Sortieren: {e}"); sorted_rewards = sorted(rewards.items())
    reward_lines_list = []
    for rk, rv in sorted_rewards:
        es = direct_emoji_map.get(rk)
        if es: reward_lines_list.append(f"{es} {rv:,}")
        else:
            if not rk.startswith("Unbekannt_"): log(f"ℹ️ Kein Emoji für '{rk}'.")
            reward_lines_list.append(f"**{rk}**: {rv:,}")
    return "\n".join(reward_lines_list) if reward_lines_list else "Nichts Nennenswertes gewonnen."


def parse_reward_message(msg, rewards: defaultdict):
    # ... (implementation as before) ...
    try:
        match = re.search(r"%xt%lws%1%0%(.*)%", msg)
        if not match:
            if msg.startswith("%xt%"): pass
            return
        json_str = match.group(1); data = json.loads(json_str)
        if "R" not in data or not isinstance(data["R"], list): log(f"ℹ️ Keine 'R' Liste in JSON: {data}"); return
        for item in data["R"]:
            if not isinstance(item, list) or len(item) < 2: log(f"  ⚠️ Ungültiges Item-Format: {item}"); continue
            reward_type = item[0]; reward_data = item[1]; amount = 0; reward_name = None
            try:
                if reward_type == "U":
                    if isinstance(reward_data, list) and len(reward_data) == 2: unit_id, amount = reward_data; truppen_namen = { 215: "Schildmaid", 238: "Walküren-Scharfschützin", 227: "Beschützer des Nordens", 216: "Walküren-Waldläuferin" }; reward_name = truppen_namen.get(unit_id, f"UnbekannteEinheit_{unit_id}")
                    else: log(f"  ⚠️ Ungültiges 'U' Format: {reward_data}")
                elif reward_type == "RI": amount = 1; reward_name = "Ausrüstung/Edelsteine"
                elif reward_type == "CI": amount = 1; reward_name = "Konstrukte"
                elif reward_type == "LM":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ausbaumarken"
                    else: log(f"  ⚠️ Ungültiges 'LM' Format: {reward_data}")
                elif reward_type == "LT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Baumarken"
                    else: log(f"  ⚠️ Ungültiges 'LT' Format: {reward_data}")
                elif reward_type == "STP":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Sceattas"
                    else: log(f"  ⚠️ Ungültiges 'STP' Format: {reward_data}")
                elif reward_type == "SLWT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Lose"
                    else: amount = 1; log(f"  ⚠️ Ungültiges 'SLWT' Format, nehme 1: {reward_data}"); reward_name = "Lose"
                elif reward_type == "LB":
                    if isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]; reward_name = "Kisten"
                    elif isinstance(reward_data, int): amount = reward_data; reward_name = "Kisten"
                    else: amount = 1; log(f"  ⚠️ Ungewöhnliches 'LB' Format, nehme 1: {reward_data}"); reward_name = "Kisten"
                elif reward_type == "UE": amount = 1; reward_name = "Mehrweller"
                elif reward_type == "C2":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Rubine"
                    else: log(f"  ⚠️ Ungültiges 'C2' Format: {reward_data}")
                elif reward_type == "FKT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ludwig-Geschenke"
                    else: log(f"  ⚠️ Ungültiges 'FKT' Format: {reward_data}")
                elif reward_type == "PTK":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Beatrice-Geschenke"
                    else: log(f"  ⚠️ Ungültiges 'PTK' Format: {reward_data}")
                elif reward_type == "KTK":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ulrich-Geschenke"
                    else: log(f"  ⚠️ Ungültiges 'KTK' Format: {reward_data}")
                elif reward_type == "D": amount = 1; reward_name = "Dekorationen"
                else:
                    if isinstance(reward_data, int): amount = reward_data
                    elif isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]
                    else: amount = 1
                    reward_name = f"Unbekannt_{reward_type}"; log(f"  -> Unbekannter Typ: {reward_type}, Daten: {reward_data}. Gezählt als '{reward_name}'.")
                if reward_name and amount > 0: rewards[reward_name] += amount
            except Exception as e_inner: log(f"  ❌ Fehler bei Item {item}: {e_inner}"); traceback.print_exc(limit=1)
    except json.JSONDecodeError as e: log(f"❌ JSON-Parse Fehler '{json_str}': {e}")
    except Exception as e: log(f"❌ Unerwarteter Parse-Fehler '{msg[:100]}...': {e}"); traceback.print_exc()

def get_gge_recaptcha_token_for_spinbot(quiet=True):
    # ... (implementation as before, using logger_rct or just logger) ...
    # Ensure logger_rct (or logger) is used consistently inside this function.
    # For simplicity, I'll use the global 'logger' here.
    logger.info("Versuche, einen GGE reCAPTCHA Token mit Selenium zu erhalten...")
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=800,600");options.add_argument("--disable-gpu");options.add_argument("--no-sandbox");options.add_argument("--disable-dev-shm-usage")
        options.add_experimental_option("excludeSwitches", ["enable-automation"]);options.add_experimental_option("useAutomationExtension", False)
        options.add_argument('--disable-blink-features=AutomationControlled');options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        try: driver = webdriver.Chrome(options=options)
        except WebDriverException as e_init: logger.error(f"ChromeDriver Init Fehler: {e_init}"); return None
        logger.info("ChromeDriver initialisiert.")
        driver.get(GGE_LOGIN_URL_FOR_RCT); wait = WebDriverWait(driver, 45, poll_frequency=0.1) 
        logger.info("Warte auf Spiel-iFrame (iframe#game)...")
        iframe_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe#game'))); driver.switch_to.frame(iframe_element)
        logger.info("Zum Spiel-iFrame gewechselt. Warte auf reCAPTCHA Badge...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.grecaptcha-badge'))); logger.info("reCAPTCHA Badge gefunden.")
        time.sleep(2.5); logger.info("Führe grecaptcha.execute-Skript aus...")
        script_to_execute = f"""return new Promise((resolve, reject) => {{ if (typeof window.grecaptcha === 'undefined' || typeof window.grecaptcha.ready === 'undefined') {{ let err_msg = 'grecaptcha object not ready!'; console.error('[JS] ' + err_msg); reject(err_msg); return; }} window.grecaptcha.ready(() => {{ console.log('[JS] grecaptcha bereit. Führe execute aus...'); try {{ window.grecaptcha.execute('{GGE_RECAPTCHA_V3_SITE_KEY}', {{ action: '{GGE_RECAPTCHA_ACTION}' }}).then(token => {{ console.log('[JS] Token:', token ? token.substring(0,20) + '...' : 'null'); resolve(token); }}, err => {{ console.error('[JS] grecaptcha.execute promise rejected:', err); reject(err ? err.toString() : "Promise rejected");}}).catch(err => {{ console.error('[JS] grecaptcha.execute .catch(err):', err); reject(err ? err.toString() : "Promise caught");}});}} catch (e) {{ console.error('[JS] Fehler bei window.grecaptcha.execute:', e); reject(e.toString()); }} }});}});"""
        recaptcha_token = driver.execute_script(script_to_execute)
        if recaptcha_token: logger.info(f"✅ reCAPTCHA Token: {recaptcha_token}"); return recaptcha_token
        else: logger.error("❌ Konnte reCAPTCHA Token nicht abrufen."); return None
    except SeleniumTimeoutException as e_timeout: logger.error(f"Selenium Timeout: {e_timeout}")
    except WebDriverException as e_wd: logger.error(f"WebDriver Fehler: {e_wd}")
    except Exception as e: logger.error(f"Allgemeiner Fehler beim reCAPTCHA Token Abruf: {e}", exc_info=True)
    finally:
        if driver: driver.quit()
        logger.info("Selenium Browser für reCAPTCHA geschlossen.")
    return None

def spin_lucky_wheel(username, password, spins, rct_token):
    # ... (implementation as before, using the global 'log' function or 'logger.info') ...
    rewards = defaultdict(int); ws = None; connect_timeout = 20.0; login_wait_time = 3.0 ; receive_timeout_per_spin = 15.0; spin_send_delay = 0.35; log_prefix = f"SpinBot ({username}):"
    try:
        log(f"{log_prefix} Versuche Verbindung (Timeout: {connect_timeout}s)")
        ws = websocket.create_connection(GGE_WEBSOCKET_URL, timeout=connect_timeout); log(f"{log_prefix} ✅ WS verbunden!")
        log(f"{log_prefix} Sende Login-Sequenz mit RCT...")
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>"); time.sleep(0.15)
        ws.send(f"<msg t='sys'><body action='login' r='0'><login z='{GGE_GAME_WORLD}'><nick><![CDATA[]]></nick><pword><![CDATA[1133015%de%0]]></pword></login></body></msg>"); time.sleep(0.15)
        ws.send(f"%xt%{GGE_GAME_WORLD}%vln%1%{{\"NOM\":\"{username}\"}}%"); time.sleep(0.15)
        login_payload = { "CONM": 297, "RTM": 54, "ID": 0, "PL": 1, "NOM": username, "PW": password, "LT": None, "LANG": "de", "DID": "0", "AID": "1728606031093813874", "KID": "", "REF": "https://empire.goodgamestudios.com", "GCI": "", "SID": 9, "PLFID": 1, "RCT": rct_token }
        login_command_with_rct = f"%xt%{GGE_GAME_WORLD}%lli%1%{json.dumps(login_payload)}"
        ws.send(login_command_with_rct); log(f"{log_prefix} 🔐 Anmeldeversuch gesendet."); log(f"{log_prefix} ⏳ Warte {login_wait_time}s..."); time.sleep(login_wait_time)
        login_confirmed = False; login_check_start_time = time.time(); received_after_login_cmd = []
        try:
            ws.settimeout(0.2)
            while time.time() - login_check_start_time < 5.0:
                if not ws.connected: break
                try:
                    msg = ws.recv()
                    if isinstance(msg, bytes): msg = msg.decode("utf-8", errors="ignore")
                    received_after_login_cmd.append(msg[:150])
                    if "%xt%lli%1%0%" in msg: log(f"{log_prefix} ✅ Login-Bestätigung!"); login_confirmed = True; break
                    elif "%xt%lli%1%409%" in msg: log(f"{log_prefix} ❌ Login-Konflikt (409): {msg}."); raise ConnectionError("Login Konflikt (409)")
                except websocket.WebSocketTimeoutException: continue
                except Exception as e_recv: log(f"{log_prefix} Fehler Empfang Login-Bestätigung: {e_recv}"); break
        finally: ws.settimeout(receive_timeout_per_spin);
        if received_after_login_cmd: log(f"{log_prefix} Nachrichten nach Login: {received_after_login_cmd}")
        if not login_confirmed: raise ConnectionError("Login mit RCT fehlgeschlagen (keine %xt%lli%1%0% Bestätigung).")
        try:
            ws.settimeout(0.1); log(f"{log_prefix} Verwerfe Nachrichten nach Login..."); discard_count = 0
            for _ in range(30): 
                if not ws.connected: break
                msg = ws.recv(); discard_count += 1; time.sleep(0.05)
            log(f"{log_prefix} {discard_count} Nachrichten verworfen.")
        except (websocket.WebSocketTimeoutException, TimeoutError): pass
        except Exception as e_disc: log(f"{log_prefix} ⚠️ Fehler Verwerfen nach Login: {e_disc}")
        ws.settimeout(receive_timeout_per_spin)
        log(f"{log_prefix} 🚀 Beginne mit {spins} Spins...")
        for i in range(spins):
            current_spin = i + 1; time.sleep(spin_send_delay); spin_cmd = "%xt%EmpireEx_2%lws%1%{\"LWET\":1}%"
            try: ws.send(spin_cmd)
            except Exception as e_send: log(f"{log_prefix} ❌ Fehler Senden Spin {current_spin}: {e_send}."); traceback.print_exc(); break
            reward_found = False; search_start = time.time()
            while time.time() - search_start < receive_timeout_per_spin:
                try:
                    rem_t = max(0.1, receive_timeout_per_spin-(time.time()-search_start)); ws.settimeout(rem_t); msg = ws.recv()
                    if isinstance(msg, bytes): msg = msg.decode("utf-8", errors="ignore")
                    if msg.startswith("%xt%lws%1%0%"): log(f"{log_prefix} 🎯 [{current_spin}/{spins}] Belohnung: {msg[:150]}..."); parse_reward_message(msg, rewards); reward_found = True; break
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    if not (time.time() - search_start < receive_timeout_per_spin): log(f"{log_prefix} ⏰ [{current_spin}/{spins}] Timeout ({receive_timeout_per_spin}s).")
                    break
                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e_conn_recv: log(f"{log_prefix} ❌ [{current_spin}/{spins}] Verbindung zu: {e_conn_recv}."); raise e_conn_recv
                except Exception as e_recv_spin: log(f"{log_prefix} ⚠️ [{current_spin}/{spins}] Fehler Empfang: {e_recv_spin}"); traceback.print_exc(); break
            if not reward_found: log(f"{log_prefix} 🤷 [{current_spin}/{spins}] Keine Belohnungsnachricht ({receive_timeout_per_spin}s).")
        log(f"{log_prefix} ✅ Alle {spins} Spins versucht.")
    except ConnectionError as e_conn_main: log(f"{log_prefix} ❌ {e_conn_main}"); raise
    except websocket.WebSocketTimeoutException as e_to: log(f"{log_prefix} ❌ Timeout ({connect_timeout}s): {e_to}"); raise ConnectionError("GGE Connection Timeout") from e_to
    except websocket.WebSocketBadStatusException as e_stat: log(f"{log_prefix} ❌ WS Handshake Failed (Status {e_stat.status_code})"); raise ConnectionError("GGE WS Handshake Failed") from e_stat
    except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e_closed: log(f"{log_prefix} ❌ WS unerwartet geschlossen: {e_closed}"); raise ConnectionError(f"GGE WS unerwartet geschlossen: {e_closed}") from e_closed
    except Exception as e_fatal: log(f"{log_prefix} ❌ Schwerwiegender Fehler: {e_fatal}"); traceback.print_exc(); raise e_fatal
    finally:
        if ws and ws.connected: log(f"{log_prefix} 🔌 Schließe WebSocket."); ws.close()
    log(f"{log_prefix} Gesammelte Belohnungen: {dict(rewards)}")
    return dict(rewards)

class SpinModal(discord.ui.Modal, title="🎰 SpinBot Eingabe"):
    # ... (implementation as before) ...
    def __init__(self):
        super().__init__(timeout=300)
        self.username = discord.ui.TextInput(label="Benutzername", placeholder="GGE Benutzernamen eingeben...", required=True, style=discord.TextStyle.short, max_length=50)
        self.password = discord.ui.TextInput(label="Passwort", placeholder="Passwort eingeben...", style=discord.TextStyle.short, required=True, max_length=50)
        self.spins = discord.ui.TextInput(label="Anzahl der Spins", placeholder="Wie oft soll gedreht werden? (1-1000)", style=discord.TextStyle.short, required=True, max_length=4)
        self.add_item(self.username); self.add_item(self.password); self.add_item(self.spins)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username.value; password = self.password.value
        try: spins = int(self.spins.value);
        except ValueError: await interaction.response.send_message("❌ Ungültige Anzahl (1-1000).", ephemeral=True); return
        if not (1 <= spins <= 1000): await interaction.response.send_message("❌ Ungültige Anzahl (1-1000).",ephemeral=True); return
        await interaction.response.send_message("🔒 Verarbeite... Starte reCAPTCHA & GGE Login...", ephemeral=True)
        embed = discord.Embed(title="🎰 SpinBot startet!", description=f"Login für `{username}` & `{spins}` Spin(s)...\n*Selenium startet Browser für reCAPTCHA.* ", color=discord.Color.orange())
        embed.set_footer(text="Bitte warten..."); status_message = await interaction.followup.send(embed=embed, wait=True)
        try:
            log(f"SpinBot: Fordere reCAPTCHA Token für '{username}' an...")
            rct_token = await asyncio.to_thread(get_gge_recaptcha_token_for_spinbot)
            if not rct_token:
                log(f"SpinBot: ❌ Kein reCAPTCHA Token für '{username}'.")
                embed_err = discord.Embed(title="❌ Fehler: reCAPTCHA Token!", description=f"Konnte keinen reCAPTCHA Token erhalten.\nVersuch für `{username}` abgebrochen.", color=discord.Color.red())
                await status_message.edit(embed=embed_err); return
            log(f"SpinBot: reCAPTCHA Token für '{username}' erhalten. Starte spin_lucky_wheel...")
            await status_message.edit(embed=discord.Embed(title="🎰 SpinBot: GGE Login...", description=f"Login zu GGE für `{username}` mit reCAPTCHA...\n`{spins}` Spin(s) werden vorbereitet.", color=discord.Color.blue()))
            rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins, rct_token)
            embed_done = discord.Embed(title="✅ Spins Abgeschlossen!", description=f"Alle `{spins}` Spins für `{username}` ausgeführt.", color=discord.Color.green())
            if rewards: embed_done.add_field(name=" Erhaltene Belohnungen", value=format_rewards_field_value(rewards), inline=False)
            else: embed_done.add_field(name=" Erhaltene Belohnungen", value="Keine Belohnungen erkannt.", inline=False); embed_done.color = discord.Color.gold()
            await status_message.edit(embed=embed_done)
        except ConnectionError as e_conn:
            log(f"SpinBot: Verbindungs-/Loginfehler für {username}: {e_conn}"); traceback.print_exc()
            embed_err = discord.Embed(title="❌ Login-/Verbindungsfehler!", description=f"Problem bei Login/Verbindung zu GGE für `{username}`.\nFehler: `{e_conn}`\nAnmeldedaten prüfen / später versuchen.", color=discord.Color.red())
            await status_message.edit(embed=embed_err)
        except Exception as e:
            log(f"SpinBot: Fehler bei spin_lucky_wheel für {username}: {e}"); traceback.print_exc()
            embed_err = discord.Embed(title="❌ Fehler bei Spin-Ausführung!", description=f"Problem bei Verarbeitung der Spins für `{username}`.", color=discord.Color.red())
            await status_message.edit(embed=embed_err)
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log(f"Fehler in SpinModal Interaktion: {error}"); traceback.print_exc()
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func('Oops! Formularfehler.', ephemeral=True)

class SpinBotClient(discord.Client):
    def __init__(self): intents = discord.Intents.default(); super().__init__(intents=intents); self.tree = app_commands.CommandTree(self)
    async def setup_hook(self):
        log("🔌 setup_hook..."); log("   Synchronisiere Slash-Befehle...")
        try: 
            guild_obj = discord.Object(id=int(TEST_GUILD_ID)) if TEST_GUILD_ID and TEST_GUILD_ID.isdigit() else None
            if guild_obj: self.tree.copy_global_to(guild=guild_obj); await self.tree.sync(guild=guild_obj); log(f"✅ Slash-Befehle mit Test-Server {TEST_GUILD_ID} synchronisiert.")
            else: await self.tree.sync(); log("✅ Slash-Befehle global synchronisiert.")
        except Exception as e: log(f"   ❌ Fehler Synchronisieren in setup_hook: {e}"); traceback.print_exc()
        log("✅ setup_hook abgeschlossen.")
    async def on_ready(self): print(f"✅ Bot online als {self.user} (ID: {self.user.id})\n✅ Bereit für Befehle...")

bot_instance = SpinBotClient()

@bot_instance.tree.command(name="spin", description="Startet das Drehen am Glücksrad für Goodgame Empire.")
@app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
async def spin_slash_command(interaction: discord.Interaction): # Renamed to avoid conflict
    log(f"Befehl /spin von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.send_modal(SpinModal())

@bot_instance.tree.command(name="spintest", description="Zeigt eine Testausgabe aller bekannten Belohnungen mit Emojis an.")
async def spintest_slash_command(interaction: discord.Interaction): # Renamed
    log(f"Befehl /spintest von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.defer(ephemeral=True)
    test_rewards = { "Werkzeuge": 3000, "Ausrüstung/Edelsteine": 2, "Konstrukte": 1, "Kisten": 3, "Dekorationen": 1, "Mehrweller": 1, "Sceattas": 610, "Beatrice-Geschenke": 5, "Ulrich-Geschenke": 7, "Ludwig-Geschenke": 6, "Baumarken": 672, "Ausbaumarken": 6592, "Rubine": 100000, "Lose": 120, "Beschützer des Nordens": 126000, "Schildmaid": 300000, "Walküren-Scharfschützin": 114000, "Walküren-Waldläuferin": 197500 }
    try:
        reward_lines = format_rewards_field_value(test_rewards)
        embed_test = discord.Embed(title="🧪 SpinBot Testausgabe", description="Vorschau der Belohnungsanzeige:", color=discord.Color.blue())
        embed_test.add_field(name=" Test Belohnungen", value=reward_lines, inline=False)
        await interaction.followup.send(embed=embed_test, ephemeral=True)
    except Exception as e: log(f"Fehler bei Testausgabe: {e}"); traceback.print_exc(); await interaction.followup.send("❌ Fehler bei Testausgabe.", ephemeral=True)

# Error handler needs to be attached to the command group if using one, or to specific command
# For bot.tree.command, the error handler is usually a global one or attached via command.on_error
# Let's make a general error handler for app commands for now.
@bot_instance.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CommandOnCooldown): 
        await interaction.response.send_message(f"⏳ Cooldown aktiv. Bitte warte {error.retry_after:.2f} weitere Sekunden.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("Du hast nicht die nötigen Berechtigungen für diesen Befehl.", ephemeral=True)
    else: 
        log(f"Unbehandelter Fehler in App-Befehl ({interaction.command.name if interaction.command else 'N/A'}): {error} (Typ: {type(error)})"); traceback.print_exc()
        if not interaction.response.is_done():
            await interaction.response.send_message("Ein unerwarteter Fehler ist aufgetreten.", ephemeral=True)
        else:
            await interaction.followup.send("Ein unerwarteter Fehler ist aufgetreten.", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN: 
        print("❌ FATAL: DISCORD_TOKEN Umgebungsvariable nicht gesetzt!"); 
        log("❌ FATAL: DISCORD_TOKEN Umgebungsvariable nicht gesetzt!")
        exit(1)
    else:
        log("Starte SpinBot...")
        try:
            # Pass log_handler=None to use our configured logging for discord.py internal logs too
            bot_instance.run(TOKEN, log_handler=None) 
        except discord.LoginFailure: log("❌ FATAL: Login zu Discord fehlgeschlagen. Token korrekt?")
        except Exception as e: log(f"❌ FATAL: Bot beendet durch Fehler: {e}"); traceback.print_exc()