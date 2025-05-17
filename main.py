#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import discord
from discord import app_commands
import asyncio
import os
import websocket # websocket-client
import time
import re
import json
from collections import defaultdict
import traceback
from typing import Dict, Tuple, List

# Selenium imports
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
GGE_RECAPTCHA_V3_SITE_KEY = "6Lc7w34oAAAAAFKhfmln41m96VQm4MNqEdpCYm-k" 
GGE_RECAPTCHA_ACTION = "submit"
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID")


# --- Logging ---
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] [%(name)s:%(funcName)s] %(message)s',
    handlers=[
        logging.FileHandler("spinbot_final.log", encoding='utf-8'), # Changed log file name
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("SpinBotApp")

def log(message): # Uses the global 'logger'
    logger.info(message)

# --- Reward Formatting and Emoji Mapping (from your SpinBot) ---
def format_rewards_field_value(rewards: Dict[str, int]) -> str:
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


def parse_reward_message(msg, rewards: defaultdict):
    # ... (Your existing parse_reward_message implementation - KEEP AS IS) ...
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


# --- Selenium Function to Get reCAPTCHA Token (from your working test script) ---
def get_gge_recaptcha_token_for_spinbot(quiet=False): # Added "for_spinbot" to distinguish if needed
    log_prefix = "SpinBotRCT:" # Use a distinct prefix for these logs
    log(f"{log_prefix} Versuche, einen GGE reCAPTCHA Token mit Selenium zu erhalten...")
    driver = None
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=800,600") 
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox") 
        options.add_argument("--disable-dev-shm-usage") 
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            driver = webdriver.Chrome(options=options) 
        except WebDriverException as e_init_driver:
            log(f"{log_prefix} ❌ ChromeDriver Initialisierungsfehler: {e_init_driver}")
            log(f"{log_prefix} Stellen Sie sicher, dass chromedriver.exe im PATH oder im Skriptverzeichnis ist und zur Chrome-Version passt.")
            return None
        log(f"{log_prefix} ChromeDriver initialisiert.")
        
        driver.get(GGE_LOGIN_URL_FOR_RCT)
        wait = WebDriverWait(driver, 45, poll_frequency=0.1) 

        log(f"{log_prefix} Warte auf Spiel-iFrame (iframe#game)...")
        iframe_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe#game')))
        driver.switch_to.frame(iframe_element)
        log(f"{log_prefix} Zum Spiel-iFrame gewechselt. Warte auf reCAPTCHA Badge (.grecaptcha-badge)...")

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.grecaptcha-badge')))
        log(f"{log_prefix} reCAPTCHA Badge gefunden.")
        time.sleep(2.5)

        log(f"{log_prefix} Führe grecaptcha.execute-Skript aus...")
        script_to_execute = f"""
            return new Promise((resolve, reject) => {{
                if (typeof window.grecaptcha === 'undefined' || typeof window.grecaptcha.ready === 'undefined') {{
                    let err_msg = 'grecaptcha object not ready or not defined!'; console.error('[JS] ' + err_msg); reject(err_msg); return;
                }}
                window.grecaptcha.ready(() => {{
                    console.log('[JS] grecaptcha ist bereit. Führe execute aus...');
                    try {{
                        window.grecaptcha.execute('{GGE_RECAPTCHA_V3_SITE_KEY}', {{ action: '{GGE_RECAPTCHA_ACTION}' }})
                            .then(token => {{ console.log('[JS] Token erhalten:', token ? token.substring(0,20) + '...' : 'null'); resolve(token); }},
                             err => {{ console.error('[JS] grecaptcha.execute promise (inline) rejected:', err); reject(err ? err.toString() : "Promise rejected");}})
                           .catch(err => {{ console.error('[JS] grecaptcha.execute .catch(err):', err); reject(err ? err.toString() : "Promise caught");}});
                    }} catch (e) {{ console.error('[JS] Fehler bei window.grecaptcha.execute:', e); reject(e.toString()); }}
                }});
            }});
        """
        recaptcha_token = driver.execute_script(script_to_execute)
        
        if recaptcha_token:
            log(f"{log_prefix} ✅ reCAPTCHA Token erhalten: {recaptcha_token}") 
            return recaptcha_token
        else:
            log(f"{log_prefix} ❌ Konnte reCAPTCHA Token nicht abrufen.")
            if driver: driver.save_screenshot("rct_token_null_spinbot.png")
            return None
    except SeleniumTimeoutException as e_timeout: log(f"{log_prefix} Selenium Timeout: {e_timeout}")
    except WebDriverException as e_wd: log(f"{log_prefix} WebDriver Fehler: {e_wd}")
    except Exception as e: log(f"{log_prefix} Allgemeiner Fehler beim Abrufen des reCAPTCHA Tokens: {e}", exc_info=True)
    finally:
        if driver: driver.quit()
        log(f"{log_prefix} Selenium Browser für reCAPTCHA geschlossen.")
    return None


# --- Modified spin_lucky_wheel ---
def spin_lucky_wheel(username, password, spins, rct_token): # Accepts rct_token
    rewards = defaultdict(int); ws = None; connect_timeout = 20.0
    login_wait_time = 3.0 # Time to wait after sending login command with RCT
    receive_timeout_per_spin = 15.0; spin_send_delay = 0.35 
    log_prefix = f"SpinBot ({username}):" # Consistent logging prefix

    try:
        log(f"{log_prefix} Versuche Verbindung (Timeout: {connect_timeout}s)")
        ws = websocket.create_connection(GGE_WEBSOCKET_URL, timeout=connect_timeout)
        log(f"{log_prefix} ✅ WebSocket-Verbindung erfolgreich hergestellt!")
        log(f"{log_prefix} Sende Login-Sequenz mit reCAPTCHA Token...")

        # Initial handshake (same as your new GGE logs showed before lli)
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>"); time.sleep(0.15)
        ws.send(f"<msg t='sys'><body action='login' r='0'><login z='{GGE_GAME_WORLD}'><nick><![CDATA[]]></nick><pword><![CDATA[1133015%de%0]]></pword></login></body></msg>"); time.sleep(0.15) 
        ws.send(f"%xt%{GGE_GAME_WORLD}%vln%1%{{\"NOM\":\"{username}\"}}%"); time.sleep(0.15)
        
        # Construct and send the NEW login command with RCT
        login_payload = {
            "CONM": 297, "RTM": 54, "ID": 0, "PL": 1, 
            "NOM": username, "PW": password, "LT": None, "LANG": "de", 
            "DID": "0", "AID": "1728606031093813874", # From your RCT login log
            "KID": "", "REF": "https://empire.goodgamestudios.com", # From your RCT login log
            "GCI": "", "SID": 9, "PLFID": 1, "RCT": rct_token
        }
        login_command_with_rct = f"%xt%{GGE_GAME_WORLD}%lli%1%{json.dumps(login_payload)}%"
        
        log_login_cmd = login_command_with_rct
        if len(log_login_cmd) > 200 : log_login_cmd = login_command_with_rct[:100] + "...(RCT INKLUSIVE)..." + login_command_with_rct[-50:]
        log(f"{log_prefix} Sende Login Befehl: {log_login_cmd}")
        ws.send(login_command_with_rct)
        
        log(f"{log_prefix} 🔐 Anmeldeversuch mit RCT gesendet.")
        log(f"{log_prefix} ⏳ Warte {login_wait_time}s nach Login-Versuch auf Bestätigung...")
        
        login_confirmed = False
        login_check_start_time = time.time()
        received_after_login_cmd_snippets = []
        
        # Loop to catch the login confirmation message
        ws.settimeout(0.5) # Short timeout for individual recv attempts in loop
        while time.time() - login_check_start_time < login_wait_time + 2.0: # Wait a bit longer than login_wait_time
            if not ws.connected:
                log(f"{log_prefix} ❌ Verbindung während Login-Bestätigung verloren.")
                break
            try:
                msg = ws.recv()
                if isinstance(msg, bytes): msg = msg.decode("utf-8", errors="ignore")
                received_after_login_cmd_snippets.append(msg[:150])
                if "%xt%lli%1%0%" in msg:
                    log(f"{log_prefix} ✅ Login-Bestätigung (%xt%lli%1%0%) erhalten!")
                    login_confirmed = True
                    break
                elif "%xt%lli%1%409%" in msg: # Handle potential conflict
                    log(f"{log_prefix} ❌ Login-Antwort mit Konflikt (Code 409) erhalten: {msg[:150]}. Breche ab.")
                    raise ConnectionError("Login Konflikt (409) vom Server erhalten.")
                # Add other GGE error codes from lli if you know them
            except websocket.WebSocketTimeoutException:
                continue # No message in 0.5s, continue loop if overall time not up
            except ConnectionError: raise # Re-raise specific ConnectionError
            except Exception as e_recv_login:
                log(f"{log_prefix} Fehler beim Empfangen der Login-Bestätigung: {e_recv_login}")
                break # Stop trying on other errors
        
        if received_after_login_cmd_snippets:
            log(f"{log_prefix} Nachrichten nach Login-Befehl (Snippets): {received_after_login_cmd_snippets}")

        if not login_confirmed:
            log(f"{log_prefix} ❌ Login-Bestätigung (%xt%lli%1%0%) nicht innerhalb der Zeit erhalten. Breche Spins ab.")
            raise ConnectionError("Login zu GGE mit RCT fehlgeschlagen (keine %xt%lli%1%0% Bestätigung).")

        # Discard messages after successful login confirmation
        log(f"{log_prefix} Login erfolgreich bestätigt. Verwerfe weitere Nachrichten für ~1 Sekunde...")
        discard_start_time = time.time()
        try:
            ws.settimeout(0.1) 
            discard_count = 0
            while time.time() - discard_start_time < 1.0: 
                if not ws.connected: break
                ws.recv(); discard_count+=1
            log(f"{log_prefix} {discard_count} Nachrichten nach Login verworfen.")
        except websocket.WebSocketTimeoutException: pass
        except Exception as discard_err: log(f"{log_prefix} ⚠️ Fehler beim Verwerfen von Nachrichten nach Login: {discard_err}")
        
        ws.settimeout(receive_timeout_per_spin) # Reset timeout for spins

        log(f"{log_prefix} 🚀 Beginne mit {spins} Glücksrad-Spins...")
        for i in range(spins):
            # ... (Rest of your spin loop logic from the original SpinBot - KEEP AS IS) ...
            current_spin = i + 1; time.sleep(spin_send_delay); spin_command = "%xt%EmpireEx_2%lws%1%{\"LWET\":1}%"
            try: ws.send(spin_command)
            except Exception as send_err: log(f"{log_prefix} ❌ Fehler Senden Spin {current_spin}: {send_err}."); traceback.print_exc(); break
            spin_reward_found = False; search_start_time = time.time()
            while time.time() - search_start_time < receive_timeout_per_spin:
                try:
                    remaining_time = max(0.1, receive_timeout_per_spin - (time.time() - search_start_time)); ws.settimeout(remaining_time)
                    msg = ws.recv();
                    if isinstance(msg, bytes): msg = msg.decode("utf-8", errors="ignore")
                    if msg.startswith("%xt%lws%1%0%"):
                        log(f"{log_prefix} 🎯 [{current_spin}/{spins}] Belohnung: {msg[:150]}...")
                        parse_reward_message(msg, rewards); spin_reward_found = True; break
                except (websocket.WebSocketTimeoutException, TimeoutError):
                    if not (time.time() - search_start_time < receive_timeout_per_spin): log(f"{log_prefix} ⏰ [{current_spin}/{spins}] Timeout ({receive_timeout_per_spin}s) für Belohnung.")
                    break
                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as conn_err: log(f"{log_prefix} ❌ [{current_spin}/{spins}] Verbindung geschlossen: {conn_err}."); raise conn_err # Re-raise to stop all
                except Exception as recv_err: log(f"{log_prefix} ⚠️ [{current_spin}/{spins}] Fehler Empfang/Prüfung: {recv_err}"); traceback.print_exc(); break # Break this spin's recv loop
            if not spin_reward_found: log(f"{log_prefix} 🤷 [{current_spin}/{spins}] Keine passende Belohnungsnachricht ({receive_timeout_per_spin}s).")
        log(f"{log_prefix} ✅ Alle {spins} angeforderten Spins versucht.")
    except ConnectionError as e_conn: log(f"{log_prefix} ❌ {e_conn}"); raise 
    except websocket.WebSocketTimeoutException as e: log(f"{log_prefix} ❌ Connection Timeout ({connect_timeout}s): {e}"); raise ConnectionError("GGE Connection Timeout") from e
    except websocket.WebSocketBadStatusException as e: log(f"{log_prefix} ❌ WS Handshake Failed (Status {e.status_code})"); raise ConnectionError("GGE WS Handshake Failed") from e
    except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e: log(f"{log_prefix} ❌ WS unerwartet geschlossen: {e}"); raise ConnectionError(f"GGE WS unerwartet geschlossen: {e}") from e
    except Exception as e: log(f"{log_prefix} ❌ Schwerwiegender Fehler: {e}"); traceback.print_exc(); raise e
    finally:
        if ws and ws.connected: log(f"{log_prefix} 🔌 Schließe WebSocket."); ws.close()
    log(f"{log_prefix} Gesammelte Belohnungen: {dict(rewards)}")
    return dict(rewards)


class SpinModal(discord.ui.Modal, title="🎰 SpinBot Eingabe"):
    # ... (SpinModal definition as before, it calls asyncio.to_thread with the new spin_lucky_wheel args) ...
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
        embed = discord.Embed(title="🎰 SpinBot startet!", description=f"Versuche Login für `{username}` und `{spins}` Spin(s)...\n*Selenium startet Browser für reCAPTCHA.* ", color=discord.Color.orange())
        embed.set_footer(text="Bitte warten..."); status_message = await interaction.followup.send(embed=embed, wait=True)
        
        try:
            log(f"SpinBot: Fordere reCAPTCHA Token für '{username}' an...")
            rct_token = await asyncio.to_thread(get_gge_recaptcha_token_for_spinbot) # Call Selenium part
            if not rct_token:
                log(f"SpinBot: ❌ Konnte keinen reCAPTCHA Token für '{username}' erhalten.")
                embed_err = discord.Embed(title="❌ Fehler: reCAPTCHA Token!", description=f"Konnte keinen reCAPTCHA Token für GGE Login erhalten.\nVersuch für `{username}` abgebrochen.", color=discord.Color.red())
                await status_message.edit(embed=embed_err); return

            log(f"SpinBot: reCAPTCHA Token für '{username}' erhalten. Starte spin_lucky_wheel...")
            await status_message.edit(embed=discord.Embed(title="🎰 SpinBot: GGE Login...", description=f"Login zu GGE für `{username}` mit reCAPTCHA Token...\n`{spins}` Spin(s) werden vorbereitet.", color=discord.Color.blue()))
            
            rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins, rct_token) # Pass rct_token
            
            embed_done = discord.Embed(title="✅ Spins Abgeschlossen!", description=f"Alle `{spins}` Spins für `{username}` ausgeführt.", color=discord.Color.green())
            if rewards: embed_done.add_field(name=" Erhaltene Belohnungen", value=format_rewards_field_value(rewards), inline=False)
            else: embed_done.add_field(name=" Erhaltene Belohnungen", value="Keine Belohnungen erkannt oder Prozess vorzeitig beendet.", inline=False); embed_done.color = discord.Color.gold()
            await status_message.edit(embed=embed_done)

        except ConnectionError as e_conn:
            log(f"SpinBot: Verbindungs-/Loginfehler für {username}: {e_conn}"); traceback.print_exc()
            embed_err = discord.Embed(title="❌ Login- oder Verbindungsfehler!", description=f"Problem beim Login oder der Verbindung zu GGE für `{username}`.\nFehler: `{e_conn}`\nAnmeldedaten prüfen oder später erneut versuchen.", color=discord.Color.red())
            await status_message.edit(embed=embed_err)
        except Exception as e:
            log(f"SpinBot: Fehler bei Ausführung von spin_lucky_wheel für {username}: {e}"); traceback.print_exc()
            embed_err = discord.Embed(title="❌ Fehler bei Spin-Ausführung!", description=f"Problem bei Verarbeitung der Spins für `{username}`.\nGründe: Falsche Login-Daten, Serverprobleme, Netzwerkunterbrechung.\nDetails im Bot-Konsolenlog prüfen.", color=discord.Color.red())
            await status_message.edit(embed=embed_err)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log(f"Fehler in SpinModal Interaktion: {error}"); traceback.print_exc()
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func('Oops! Formularfehler.', ephemeral=True)

class SpinBotClient(discord.Client):
    # ... (Same as before) ...
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
async def spin_slash_command(interaction: discord.Interaction): 
    log(f"Befehl /spin von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.send_modal(SpinModal())

@bot_instance.tree.command(name="spintest", description="Zeigt eine Testausgabe aller bekannten Belohnungen mit Emojis an.")
async def spintest_slash_command(interaction: discord.Interaction):
    # ... (Same as before) ...
    log(f"Befehl /spintest von Benutzer {interaction.user} (ID: {interaction.user.id}) erhalten.")
    await interaction.response.defer(ephemeral=True)
    test_rewards = { "Werkzeuge": 3000, "Ausrüstung/Edelsteine": 2, "Konstrukte": 1, "Kisten": 3, "Dekorationen": 1, "Mehrweller": 1, "Sceattas": 610, "Beatrice-Geschenke": 5, "Ulrich-Geschenke": 7, "Ludwig-Geschenke": 6, "Baumarken": 672, "Ausbaumarken": 6592, "Rubine": 100000, "Lose": 120, "Beschützer des Nordens": 126000, "Schildmaid": 300000, "Walküren-Scharfschützin": 114000, "Walküren-Waldläuferin": 197500 }
    try:
        reward_lines = format_rewards_field_value(test_rewards)
        embed_test = discord.Embed(title="🧪 SpinBot Testausgabe", description="Vorschau der Belohnungsanzeige:", color=discord.Color.blue())
        embed_test.add_field(name=" Test Belohnungen", value=reward_lines, inline=False)
        await interaction.followup.send(embed=embed_test, ephemeral=True)
    except Exception as e: log(f"Fehler bei Testausgabe: {e}"); traceback.print_exc(); await interaction.followup.send("❌ Fehler bei Testausgabe.", ephemeral=True)


@bot_instance.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    # ... (Same as before) ...
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
            bot_instance.run(TOKEN, log_handler=None) 
        except discord.LoginFailure: log("❌ FATAL: Login zu Discord fehlgeschlagen. Token korrekt?")
        except Exception as e: log(f"❌ FATAL: Bot beendet durch Fehler: {e}"); traceback.print_exc()