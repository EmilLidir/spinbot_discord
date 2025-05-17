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
import logging

# --- Selenium Imports ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService # For explicit chromedriver path
from webdriver_manager.chrome import ChromeDriverManager # Optional: for auto-managing chromedriver
from selenium.common.exceptions import WebDriverException, TimeoutException as SeleniumTimeoutException

# --- Bot Configuration ---
TOKEN = os.getenv("DISCORD_TOKEN")

# --- GGE Configuration ---
GGE_LOGIN_URL_FOR_RCT = "https://empire.goodgamestudios.com/"
GGE_WEBSOCKET_URL = "wss://ep-live-de1-game.goodgamestudios.com/"
GGE_GAME_WORLD = "EmpireEx_2" # Used in various game commands
GGE_RECAPTCHA_V3_SITE_KEY = "6Lc7w34oAAAAAFKhfmln41m96VQm4MNqEdpCYm-k"
GGE_RECAPTCHA_ACTION = "submit"
GGE_AID = "1728606031093813874" # From new login script
GGE_STATIC_PWORD_PART = "1133015%de%0" # From new login script

# --- Logging Setup ---
#logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] (%(module)s.%(funcName)s) %(message)s')
#logger = logging.getLogger("SpinBot")
# More advanced logging setup for Discord bot context
logger = logging.getLogger('discord.spinbot')
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] (%(name)s) %(message)s'))
logger.addHandler(handler)


def format_rewards_field_value(rewards: Dict[str, int]) -> str:
    """Formats the rewards dictionary into a string for the Discord embed field,
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
        "Lose": 1, "Rubine": 2,
        "Ludwig-Geschenke": 3, "Ulrich-Geschenke": 4, "Beatrice-Geschenke": 5,
        "Ausbaumarken": 6, "Baumarken": 7, "Sceattas": 8,
    }
    DEFAULT_PRIORITY = 99

    def get_reward_sort_key(item: Tuple[str, int]):
        key, _ = item
        priority = sort_priority.get(key, DEFAULT_PRIORITY)
        return (priority, key)

    try:
        sorted_rewards = sorted(rewards.items(), key=get_reward_sort_key)
    except Exception as e:
        logger.error(f"Error sorting rewards: {e}")
        sorted_rewards = sorted(rewards.items())

    reward_lines_list = []
    for reward_key, reward_value in sorted_rewards:
        emoji_string = direct_emoji_map.get(reward_key)
        if emoji_string:
            reward_lines_list.append(f"{emoji_string} {reward_value:,}")
        else:
            if not reward_key.startswith("Unbekannt_"):
                logger.info(f"ℹ️ No direct emoji string for '{reward_key}' in map. Displaying name.")
            reward_lines_list.append(f"**{reward_key}**: {reward_value:,}")

    return "\n".join(reward_lines_list)

# --- Selenium Function to Get reCAPTCHA Token (Adapted) ---
def get_gge_recaptcha_token(user_id_for_logging: str = "System", quiet: bool = False):
    logger.info(f"[{user_id_for_logging}] Attempting to get GGE reCAPTCHA token with Selenium...")
    driver = None
    # Optional: Define path to your ChromeDriver if not in PATH
    # CHROMEDRIVER_PATH = "/path/to/your/chromedriver" # Example
    try:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=800,600")
        options.add_argument("--headless") # Run headless for server environment
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36") # Keep User-Agent somewhat up-to-date

        try:
            driver = webdriver.Chrome(
            service=ChromeService(ChromeDriverManager().install()),
            options=options
        )
            
        except WebDriverException as e_init_driver:
            logger.error(f"[{user_id_for_logging}] ChromeDriver could not be initialized: {e_init_driver}")
            logger.error(f"[{user_id_for_logging}] Ensure ChromeDriver is in PATH, matches Chrome version, or path is correctly specified.")
            return None
        logger.info(f"[{user_id_for_logging}] ChromeDriver initialized.")

        driver.get(GGE_LOGIN_URL_FOR_RCT)
        wait = WebDriverWait(driver, 45, poll_frequency=0.1)

        logger.info(f"[{user_id_for_logging}] Waiting for game iframe (iframe#game)...")
        iframe_element = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'iframe#game')))
        driver.switch_to.frame(iframe_element)
        logger.info(f"[{user_id_for_logging}] Switched to game iframe. Waiting for reCAPTCHA badge (.grecaptcha-badge)...")

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.grecaptcha-badge')))
        logger.info(f"[{user_id_for_logging}] reCAPTCHA badge found.")

        logger.info(f"[{user_id_for_logging}] Waiting 2 additional seconds for potential initialization...")
        time.sleep(2.0)

        logger.info(f"[{user_id_for_logging}] Executing grecaptcha.execute script...")
        script_to_execute = f"""
            return new Promise((resolve, reject) => {{
                if (typeof window.grecaptcha === 'undefined' || typeof window.grecaptcha.ready === 'undefined') {{
                    let err_msg = 'grecaptcha object not ready or not defined!';
                    console.error('[JS] ' + err_msg);
                    reject(err_msg);
                    return;
                }}
                window.grecaptcha.ready(() => {{
                    console.log('[JS] grecaptcha is ready. Executing execute...');
                    try {{
                        window.grecaptcha.execute('{GGE_RECAPTCHA_V3_SITE_KEY}', {{ action: '{GGE_RECAPTCHA_ACTION}' }})
                            .then(token => {{
                                console.log('[JS] Token received from execute:', token ? token.substring(0,10) + '...' : 'null');
                                resolve(token);
                             }},
                             err => {{
                                 console.error('[JS] grecaptcha.execute promise (inline) rejected:', err);
                                 reject(err ? err.toString() : "Promise rejected with no error");
                             }}
                            )
                           .catch(err => {{
                                console.error('[JS] grecaptcha.execute .catch(err) triggered:', err);
                               reject(err ? err.toString() : "Promise caught with no error");
                            }});
                    }} catch (e) {{
                        console.error('[JS] Error during direct call of grecaptcha.execute:', e);
                        reject(e.toString());
                    }}
                }});
            }});
        """
        recaptcha_token = driver.execute_script(script_to_execute)

        if recaptcha_token:
            logger.info(f"[{user_id_for_logging}] ✅ Successfully obtained reCAPTCHA token: {recaptcha_token[:20]}...")
            return recaptcha_token
        else:
            logger.error(f"[{user_id_for_logging}] ❌ Failed to retrieve reCAPTCHA token (execute returned null/undefined).")
            return None

    except SeleniumTimeoutException as e_timeout:
        logger.error(f"[{user_id_for_logging}] Selenium Timeout while waiting for an element: {e_timeout}")
        if driver: driver.save_screenshot(f"selenium_timeout_{user_id_for_logging}.png")
        if not quiet: traceback.print_exc()
        return None
    except WebDriverException as e_wd:
        logger.error(f"[{user_id_for_logging}] WebDriver error during initialization or execution: {e_wd}")
        if not quiet: traceback.print_exc()
        return None
    except Exception as e:
        logger.error(f"[{user_id_for_logging}] General error while obtaining reCAPTCHA token: {e}")
        if not quiet: traceback.print_exc()
        return None
    finally:
        if driver:
            driver.quit()
        logger.info(f"[{user_id_for_logging}] Selenium browser for reCAPTCHA closed.")

# --- GGE Login Worker with reCAPTCHA (Adapted) ---
def gge_login_sync_worker_with_rct(username, password, rct_token, user_id_for_logging="User"):
    ws = None
    connect_timeout = 20.0
    login_confirmation_timeout = 15.0 # Increased slightly
    individual_recv_timeout = 0.5

    try:
        logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) GGE Login for '{username}'...")
        ws = websocket.create_connection(GGE_WEBSOCKET_URL, timeout=connect_timeout)
        logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) ✅ WebSocket connection established!")

        try:
            ws.settimeout(2.0)
            initial_msg = ws.recv()
            logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) Initial message from GGE: {initial_msg[:100]}")
        except websocket.WebSocketTimeoutException:
            logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) No initial message from GGE within 2s.")
        except Exception as e_init_recv:
            logger.warning(f"[{user_id_for_logging}] (SyncWorker-RCT) Error receiving initial message: {e_init_recv}")

        ws.settimeout(connect_timeout) # Reset to default

        logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) Sending login sequence...")
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>")
        ws.send(f"<msg t='sys'><body action='login' r='0'><login z='{GGE_GAME_WORLD}'><nick><![CDATA[]]></nick><pword><![CDATA[{GGE_STATIC_PWORD_PART}]]></pword></login></body></msg>")
        ws.send(f"%xt%{GGE_GAME_WORLD}%vln%1%{{\"NOM\":\"{username}\"}}%")

        login_payload = {
            "CONM": 297, "RTM": 54, "ID": 0, "PL": 1,
            "NOM": username, "PW": password, "LT": None, "LANG": "de",
            "DID": "0", "AID": GGE_AID, "KID": "",
            "REF": "https://empire.goodgamestudios.com", "GCI": "",
            "SID": 9, "PLFID": 1, "RCT": rct_token
        }
        login_command = f"%xt%{GGE_GAME_WORLD}%lli%1%{json.dumps(login_payload)}%"
        logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) Sending login command (sensitive parts like PW, RCT omitted from this log line for security if they were printed).")
        # logger.debug(f"[{user_id_for_logging}] (SyncWorker-RCT) Full Login Command: {login_command}") # For debugging only
        ws.send(login_command)
        login_command_sent_time = time.time()

        time.sleep(0.5) # Small delay to allow server to process
        if not ws.connected:
            logger.error(f"[{user_id_for_logging}] (SyncWorker-RCT) GGE WS connection lost immediately after sending login command."); return None

        logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) Waiting for login confirmation (%xt%lli%1%0%)...")
        confirmation_found = False
        login_related_messages_snippets = []

        while (time.time() - login_command_sent_time) < login_confirmation_timeout:
            if not ws.connected:
                logger.warning(f"[{user_id_for_logging}] (SyncWorker-RCT) WS disconnected while waiting for login confirmation.")
                break
            ws.settimeout(individual_recv_timeout)
            try:
                raw_msg = ws.recv()
            except websocket.WebSocketTimeoutException:
                continue
            except Exception as e_inner_recv:
                logger.error(f"[{user_id_for_logging}] (SyncWorker-RCT) Inner recv error: {e_inner_recv}")
                break

            msg_str = raw_msg.decode('utf-8', errors='ignore') if isinstance(raw_msg, bytes) else str(raw_msg)
            login_related_messages_snippets.append(msg_str[:200])

            if f"%xt%{GGE_GAME_WORLD}%lli%1%0%" in msg_str or "%xt%lli%1%0%" in msg_str: # Handle potential world prefix
                logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) ✅ Login confirmation (%xt%...%lli%1%0%) received!")
                confirmation_found = True
                break
        
        if login_related_messages_snippets:
             logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) Message snippets during login confirmation wait: {login_related_messages_snippets}")

        if confirmation_found:
            logger.info(f"[{user_id_for_logging}] (SyncWorker-RCT) Login confirmed. Discarding further messages for 1 second...")
            discard_start_time = time.time()
            try:
                ws.settimeout(0.1)
                while time.time() - discard_start_time < 1.0:
                    if not ws.connected: break
                    ws.recv()
            except websocket.WebSocketTimeoutException: pass
            except Exception as e_discard: logger.warning(f"[{user_id_for_logging}] (SyncWorker-RCT) Error discarding messages post-login: {e_discard}")
            
            ws.settimeout(connect_timeout) # Reset to a reasonable default for subsequent operations
            return ws
        else:
            logger.error(f"[{user_id_for_logging}] (SyncWorker-RCT) Login confirmation (%xt%...%lli%1%0%) NOT received within {login_confirmation_timeout}s.")
            if ws.connected: ws.close()
            return None

    except websocket.WebSocketException as e_ws: # Catch specific websocket errors
        logger.error(f"[{user_id_for_logging}] (SyncWorker-RCT) WebSocket GGE Login Error: {e_ws}", exc_info=True)
    except Exception as e_main:
        logger.error(f"[{user_id_for_logging}] (SyncWorker-RCT) Unexpected GGE Login Error: {e_main}", exc_info=True)

    if ws and ws.connected:
        try: ws.close()
        except: pass
    return None

def parse_reward_message(msg: str, rewards: defaultdict):
    """Parses the specific reward message format from the game server."""
    try:
        match = re.search(r"%xt%lws%1%0%(.*)%", msg) # Original regex seems fine
        if not match:
            if msg.startswith("%xt%"): # Non-reward xt message
                pass # logger.debug(f"Non-reward xt message: {msg[:60]}")
            return
        json_str = match.group(1)
        data = json.loads(json_str)

        if "R" not in data or not isinstance(data["R"], list):
            logger.info(f"ℹ️ No valid 'R' (Rewards) list in parsed JSON: {data}")
            return

        for item in data["R"]:
            if not isinstance(item, list) or len(item) < 2:
                logger.warning(f"  ⚠️ Skipping invalid reward item format: {item}")
                continue
            reward_type = item[0]
            reward_data = item[1]
            amount = 0
            reward_name = None
            try:
                if reward_type == "U":
                    if isinstance(reward_data, list) and len(reward_data) == 2:
                        unit_id, amount = reward_data
                        truppen_namen = { 215: "Schildmaid", 238: "Walküren-Scharfschützin", 227: "Beschützer des Nordens", 216: "Walküren-Waldläuferin" }
                        reward_name = truppen_namen.get(unit_id, "Werkzeuge") # Default to Werkzeuge if unknown unit
                    else: logger.warning(f"  ⚠️ Invalid format for type 'U': {reward_data}")
                elif reward_type == "RI": amount = 1; reward_name = "Ausrüstung/Edelsteine"
                elif reward_type == "CI": amount = 1; reward_name = "Konstrukte"
                elif reward_type == "LM":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ausbaumarken"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'LM': {reward_data}")
                elif reward_type == "LT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Baumarken"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'LT': {reward_data}")
                elif reward_type == "STP":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Sceattas"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'STP': {reward_data}")
                elif reward_type == "SLWT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Lose"
                    else: amount = 1; logger.warning(f"  ⚠️ Invalid/No quantity for 'SLWT', assuming 1: {reward_data}"); reward_name = "Lose"
                elif reward_type == "LB":
                    if isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]; reward_name = "Kisten"
                    elif isinstance(reward_data, int): amount = reward_data; reward_name = "Kisten"
                    else: amount = 1; logger.warning(f"  ⚠️ Unusual format for 'LB', assuming quantity 1: {reward_data}"); reward_name = "Kisten"
                elif reward_type == "UE": amount = 1; reward_name = "Mehrweller"
                elif reward_type == "C2":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Rubine"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'C2': {reward_data}")
                elif reward_type == "FKT":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ludwig-Geschenke"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'FKT': {reward_data}")
                elif reward_type == "PTK":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Beatrice-Geschenke"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'PTK': {reward_data}")
                elif reward_type == "KTK":
                    if isinstance(reward_data, int): amount = reward_data; reward_name = "Ulrich-Geschenke"
                    else: logger.warning(f"  ⚠️ Invalid format for type 'KTK': {reward_data}")
                elif reward_type == "D": amount = 1; reward_name = "Dekorationen"
                else:
                    if isinstance(reward_data, int): amount = reward_data
                    elif isinstance(reward_data, list) and len(reward_data) > 1 and isinstance(reward_data[1], int): amount = reward_data[1]
                    else: amount = 1
                    reward_name = f"Unbekannt_{reward_type}"
                    logger.info(f"  -> Unknown reward type: {reward_type} with data {reward_data}. Counted as '{reward_name}'.")

                if reward_name and amount > 0:
                    rewards[reward_name] += amount
            except Exception as parse_inner_err:
                logger.error(f"  ❌ Error processing item {item}: {parse_inner_err}", exc_info=True)
    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parsing error for extracted string '{json_str}': {e}")
    except Exception as e:
        logger.error(f"❌ Unexpected error parsing message '{msg[:100]}...': {e}", exc_info=True)


def spin_lucky_wheel(username, password, spins, user_id_for_logging="User"):
    """Connects via reCAPTCHA, logs in, performs spins, and waits for reward messages."""
    rewards = defaultdict(int)
    ws = None
    receive_timeout_per_spin = 15.0
    spin_send_delay = 0.3 # Small delay between sending spin commands

    logger.info(f"[{user_id_for_logging}] Starting spin_lucky_wheel for {username} with {spins} spins.")

    try:
        # Step 1: Get reCAPTCHA token
        logger.info(f"[{user_id_for_logging}] Attempting to obtain reCAPTCHA token for {username}...")
        rct_token = get_gge_recaptcha_token(user_id_for_logging=user_id_for_logging, quiet=False)
        if not rct_token:
            logger.error(f"[{user_id_for_logging}] Failed to obtain reCAPTCHA token for {username}. Aborting spins.")
            raise ConnectionError("Failed to obtain reCAPTCHA token. Check bot logs and Selenium/ChromeDriver setup.")

        # Step 2: Login with reCAPTCHA token
        logger.info(f"[{user_id_for_logging}] Attempting GGE login for {username} using reCAPTCHA token...")
        ws = gge_login_sync_worker_with_rct(username, password, rct_token, user_id_for_logging=user_id_for_logging)
        if not ws or not ws.connected:
            logger.error(f"[{user_id_for_logging}] GGE login failed for {username} after obtaining reCAPTCHA token. Aborting spins.")
            raise ConnectionError("GGE login failed. Check credentials or game server status. Token might have expired or been invalid.")

        logger.info(f"[{user_id_for_logging}] ✅ GGE Login successful for {username}. Proceeding with spins.")
        ws.settimeout(receive_timeout_per_spin) # Set timeout for spin reward messages

        # Step 3: Perform spins
        logger.info(f"[{user_id_for_logging}] 🚀 Starting {spins} lucky wheel spins for {username}...")
        for i in range(spins):
            current_spin = i + 1
            if not ws.connected:
                logger.warning(f"[{user_id_for_logging}] [{current_spin}/{spins}] WebSocket disconnected before sending spin command. Aborting.")
                break
            
            time.sleep(spin_send_delay)
            spin_command = f"%xt%{GGE_GAME_WORLD}%lws%1%{{\"LWET\":1}}%" # LWET:1 seems to be the spin type
            
            try:
                ws.send(spin_command)
                # logger.debug(f"[{user_id_for_logging}] [{current_spin}/{spins}] Sent spin command.")
            except Exception as send_err:
                logger.error(f"[{user_id_for_logging}] ❌ Error sending spin command {current_spin} for {username}: {send_err}. Aborting further spins.", exc_info=True)
                break

            spin_reward_found = False
            search_start_time = time.time()
            
            while time.time() - search_start_time < receive_timeout_per_spin:
                if not ws.connected:
                    logger.warning(f"[{user_id_for_logging}] [{current_spin}/{spins}] WebSocket disconnected while waiting for reward. Aborting.")
                    break # Break from inner while
                
                try:
                    # Dynamic timeout for recv
                    remaining_time = max(0.1, receive_timeout_per_spin - (time.time() - search_start_time))
                    ws.settimeout(remaining_time)
                    msg_bytes = ws.recv()
                    msg = msg_bytes.decode("utf-8", errors="ignore")
                    
                    # Check for the specific reward message structure
                    if msg.startswith(f"%xt%{GGE_GAME_WORLD}%lws%1%0%") or msg.startswith("%xt%lws%1%0%"): # Handle potential world prefix in lws response
                        logger.info(f"[{user_id_for_logging}] 🎯 [{current_spin}/{spins}] Matched reward message: {msg[:100]}...")
                        parse_reward_message(msg, rewards)
                        spin_reward_found = True
                        break # Break from inner while, proceed to next spin
                    # else:
                        # logger.debug(f"[{user_id_for_logging}] [{current_spin}/{spins}] Received non-reward msg: {msg[:60]}")
                        
                except websocket.WebSocketTimeoutException:
                    # This timeout is per recv attempt within the larger spin_reward_found loop
                    if not (time.time() - search_start_time < receive_timeout_per_spin): # Check if overall spin timeout is also exceeded
                        logger.warning(f"[{user_id_for_logging}] ⏰ [{current_spin}/{spins}] Timeout ({receive_timeout_per_spin}s) reached waiting for reward message for spin {current_spin}.")
                    break # Break from inner while (recv loop)
                except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as conn_err:
                    logger.error(f"[{user_id_for_logging}] ❌ [{current_spin}/{spins}] Connection closed during spin {current_spin}: {conn_err}. Aborting.", exc_info=True)
                    raise conn_err # Re-raise to be caught by outer try-except
                except Exception as recv_err:
                    logger.warning(f"[{user_id_for_logging}] ⚠️ [{current_spin}/{spins}] Error receiving/processing message for spin {current_spin}: {recv_err}", exc_info=True)
                    break # Break from inner while
            
            if not ws.connected: # Check again if disconnected during the receive loop
                break # Break from outer for loop (spins)

            if not spin_reward_found:
                logger.warning(f"[{user_id_for_logging}] 🤷 [{current_spin}/{spins}] No specific reward message found for spin {current_spin} within {receive_timeout_per_spin}s timeout.")
        
        logger.info(f"[{user_id_for_logging}] ✅ All {spins} requested spins attempted for {username}.")

    except ConnectionError as e: # Custom error from RCT/login phases
        logger.error(f"[{user_id_for_logging}] Connection or Login Error for {username}: {e}", exc_info=True)
        raise # Re-raise to be handled by the modal's on_submit
    except (websocket.WebSocketConnectionClosedException, BrokenPipeError) as e:
        logger.error(f"[{user_id_for_logging}] WebSocket Connection Closed Unexpectedly for {username}: {e}", exc_info=True)
        # Don't re-raise as a generic Exception, let the caller handle it if needed or finish
    except Exception as e:
        logger.error(f"[{user_id_for_logging}] ❌ Major error in spin_lucky_wheel for {username}: {e}", exc_info=True)
        raise # Re-raise to be handled by the modal's on_submit
    finally:
        if ws and ws.connected:
            logger.info(f"[{user_id_for_logging}] 🔌 Closing WebSocket connection for {username}.")
            try: ws.close()
            except Exception as e_close: logger.error(f"[{user_id_for_logging}] Error closing WebSocket: {e_close}")
        logger.info(f"[{user_id_for_logging}] Collected rewards for {username}: {dict(rewards)}")
    return dict(rewards)


class SpinModal(discord.ui.Modal, title="🎰 SpinBot Input"):
    """A Discord Modal (form) to collect user credentials and spin count."""
    def __init__(self): # Corrected init
        super().__init__(timeout=300) # 5 minutes timeout for modal
        self.username_input = discord.ui.TextInput(label="Username", placeholder="Enter your Empire username...", required=True, style=discord.TextStyle.short, max_length=50)
        self.password_input = discord.ui.TextInput(label="Password", placeholder="Enter your password...", style=discord.TextStyle.short, required=True, max_length=50)
        self.spins_input = discord.ui.TextInput(label="Number of Spins", placeholder="How many times? (1-1000)", style=discord.TextStyle.short, required=True, max_length=4)
        self.add_item(self.username_input)
        self.add_item(self.password_input)
        self.add_item(self.spins_input)

    async def on_submit(self, interaction: discord.Interaction):
        """Handles the modal submission."""
        username = self.username_input.value
        password = self.password_input.value
        spins_value = self.spins_input.value
        user_id_for_logging = f"{interaction.user.name} ({interaction.user.id})"

        try:
            spins = int(spins_value)
            if not (1 <= spins <= 10000): # Max 1000 spins, adjust if needed
                raise ValueError("Spin count out of range.")
        except ValueError:
            await interaction.response.send_message("❌ Invalid number of spins. Please enter a number between 1 and 1000.", ephemeral=True)
            return

        await interaction.response.send_message(f"🔒 Input received for {username}. Starting {spins} spin(s)...\n*This may take a while, especially the first time (reCAPTCHA). Please be patient.*", ephemeral=True)
        
        embed = discord.Embed(title="🎰 SpinBot is working...", description=f"Initializing {spins} spin(s) for user {username}...\n*This may take a moment, including reCAPTCHA solving.*", color=discord.Color.orange())
        embed.set_footer(text="Please be patient until all spins are completed.")
        status_message = await interaction.followup.send(embed=embed, wait=True) # Send as non-ephemeral

        try:
            # Run the blocking spin_lucky_wheel in a separate thread
            rewards = await asyncio.to_thread(spin_lucky_wheel, username, password, spins, user_id_for_logging)
            
            embed_done = discord.Embed(title="✅ Spins Completed!", description=f"All {spins} spin attempts for {username} have been processed.", color=discord.Color.green())
            if rewards:
                reward_lines = format_rewards_field_value(rewards)
                embed_done.add_field(name="Received Rewards", value=reward_lines, inline=False)
            else:
                embed_done.add_field(name="Received Rewards", value="No rewards detected or process ended prematurely. Check bot logs.", inline=False)
                embed_done.color = discord.Color.gold() # Gold if no rewards but process finished
            await status_message.edit(embed=embed_done)

        except ConnectionError as e: # Catch specific ConnectionError from spin_lucky_wheel for RCT/login issues
            logger.error(f"Error during spin_lucky_wheel (Connection/Login) for {username} by {user_id_for_logging}: {e}", exc_info=True)
            embed_error = discord.Embed(title="❌ Error During Login/Connection!", description=f"A problem occurred while trying to log in or connect for {username}.\n**Reason:** {e}\n\nPlease check the bot's console logs for details. This could be due to incorrect login, reCAPTCHA issues, or game server problems.", color=discord.Color.red())
            await status_message.edit(embed=embed_error)
        except (WebDriverException, SeleniumTimeoutException) as e_selenium: # Catch Selenium specific errors
            logger.error(f"Selenium error during spin_lucky_wheel for {username} by {user_id_for_logging}: {e_selenium}", exc_info=True)
            embed_error = discord.Embed(title="❌ Error with Automated Browser!", description=f"A problem occurred with the automated browser task (reCAPTCHA) for {username}.\n**Details:** {type(e_selenium).__name__}. Check bot logs.\nThis might be a temporary issue or a problem with the bot's setup (ChromeDriver).", color=discord.Color.red())
            await status_message.edit(embed=embed_error)
        except Exception as e:
            logger.error(f"Error during spin_lucky_wheel execution for {username} by {user_id_for_logging}: {e}", exc_info=True)
            embed_error = discord.Embed(title="❌ Error Executing Spins!", description=f"An unexpected problem occurred while processing spins for {username}.\nPossible reasons: Incorrect login details, game server issues, network interruption, or an internal bot error.\nPlease check the bot's console logs for detailed technical information.", color=discord.Color.red())
            await status_message.edit(embed=embed_error)

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logger.error(f"Error in SpinModal interaction: {error}", exc_info=True)
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func('Oops! Something went wrong while opening or handling the form.', ephemeral=True)


class SpinBotClient(discord.Client): # Renamed to avoid conflict with module name
    """The main Discord bot client."""
    def __init__(self): # Corrected init
        intents = discord.Intents.default()
        # intents.message_content = False # Not strictly needed for slash commands only
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        logger.info("🔌 Running setup_hook...")
        logger.info("   Syncing slash commands...")
        try:
            # self.tree.copy_global_to(guild=discord.Object(id=YOUR_GUILD_ID)) # Optional: Sync to one guild for faster updates
            await self.tree.sync() # Sync globally
            logger.info("✅ Global slash commands synchronized.")
        except Exception as e:
            logger.error(f"   ❌ Error syncing commands in setup_hook: {e}", exc_info=True)
        logger.info("✅ setup_hook complete.")

    async def on_ready(self):
        logger.info(f"✅ Bot is online as {self.user} (ID: {self.user.id})")
        logger.info(f"✅ Ready and waiting for commands...")

client = SpinBotClient() # Use the renamed class

@client.tree.command(name="spin", description="Starts spinning the Lucky Wheel for Goodgame Empire.")
@app_commands.checks.cooldown(1, 90.0, key=lambda i: i.user.id) # Increased cooldown slightly due to Selenium
async def spin_command_handler(interaction: discord.Interaction): # Renamed to avoid conflict
    """Slash command handler to initiate the spin process by showing the modal."""
    logger.info(f"Command /spin received from user {interaction.user.name} (ID: {interaction.user.id}).")
    await interaction.response.send_modal(SpinModal())

@client.tree.command(name="spintest", description="Displays a test output of all known rewards with emojis.")
async def spintest_command_handler(interaction: discord.Interaction): # Renamed
    """Displays a test embed with sample rewards and emojis."""
    logger.info(f"Command /spintest received from user {interaction.user.name} (ID: {interaction.user.id}).")
    await interaction.response.defer(ephemeral=True)

    test_rewards = {
        "Werkzeuge": 3000, "Ausrüstung/Edelsteine": 2, "Konstrukte": 1, "Kisten": 3, "Dekorationen": 1,
        "Mehrweller": 1, "Sceattas": 610, "Beatrice-Geschenke": 5, "Ulrich-Geschenke": 7,
        "Ludwig-Geschenke": 6, "Baumarken": 672, "Ausbaumarken": 6592, "Rubine": 100000, "Lose": 120,
        "Beschützer des Nordens": 126000, "Schildmaid": 300000, "Walküren-Scharfschützin": 114000,
        "Walküren-Waldläuferin": 197500
    }

    try:
        reward_lines = format_rewards_field_value(test_rewards)
        embed_test = discord.Embed(title="🧪 SpinBot Test Output", description="This is a preview of how the rewards will be displayed:", color=discord.Color.blue())
        embed_test.add_field(name="Test Rewards", value=reward_lines, inline=False)
        await interaction.followup.send(embed=embed_test, ephemeral=True)
    except Exception as e:
        logger.error(f"Error generating test output: {e}", exc_info=True)
        await interaction.followup.send("❌ Error generating test output.", ephemeral=True)

@spin_command_handler.error # Attach to the renamed command handler
async def on_spin_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Handles errors specifically for the /spin command, like cooldowns."""
    if isinstance(error, app_commands.CommandOnCooldown):
        await interaction.response.send_message(f"⏳ Cooldown active for you. Please wait {error.retry_after:.2f} more seconds.", ephemeral=True)
    elif isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("🚫 You do not have permission to use this command.", ephemeral=True)
    else:
        logger.error(f"Unhandled error in /spin command processing: {error}", exc_info=True)
        resp_func = interaction.followup.send if interaction.response.is_done() else interaction.response.send_message
        await resp_func("An unexpected error occurred while processing the command.", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        logger.critical("❌ FATAL: DISCORD_TOKEN environment variable not set!")
        exit(1)
    else:
        logger.info("Starting SpinBot with reCAPTCHA support...")
        try:
            client.run(TOKEN, log_handler=None) # Using custom logger setup
        except discord.LoginFailure:
            logger.critical("❌ FATAL: Login to Discord failed. Is the token correct?")
        except Exception as e:
            logger.critical(f"❌ FATAL: Bot terminated due to an error: {e}", exc_info=True)
