import discord
from discord import app_commands
import asyncio
import os
import websocket
import time
import json
import re
from collections import defaultdict

# Bot-Token aus Umgebungsvariablen
TOKEN = os.getenv("DISCORD_TOKEN")

# Mapping
troop_ids = {
    215: "Schildmaid",
    238: "Walküren-Scharfschützin",
    227: "Beschützer des Nordens",
    216: "Walküren-Waldläuferin"
}

gift_map = {
    "FKT": "Geschenke Ludwig",
    "PTK": "Geschenk Beatrice",
    "KTK": "Geschenke Ulrich"
}

reward_counter = defaultdict(int)  # 🧮 Alle Belohnungen werden hier gezählt

class SpinModal(discord.ui.Modal, title="🎰 SpinBot Eingabe"):
    def __init__(self):
        super().__init__()

        self.username = discord.ui.TextInput(
            label="Benutzername",
            placeholder="Gib deinen Empire-Benutzernamen ein...",
            required=True
        )
        self.password = discord.ui.TextInput(
            label="Passwort",
            placeholder="Gib dein Passwort ein (keiner kann dein Passwort sehen)...",
            style=discord.TextStyle.short,
            required=True
        )
        self.spins = discord.ui.TextInput(
            label="Anzahl der Spins",
            placeholder="Wie oft soll das Rad gedreht werden?",
            style=discord.TextStyle.short,
            required=True
        )

        self.add_item(self.username)
        self.add_item(self.password)
        self.add_item(self.spins)

    async def on_submit(self, interaction: discord.Interaction):
        username = self.username.value
        password = self.password.value
        spins = int(self.spins.value)

        await interaction.response.send_message("🔒 Deine Eingaben wurden verarbeitet!", ephemeral=True)

        embed = discord.Embed(
            title="🎰 SpinBot gestartet!",
            description=f"Starte `{spins}` Spins für `{username}`...",
            color=discord.Color.green()
        )
        embed.set_footer(text="Bitte warten, bis alle Spins abgeschlossen sind...")
        await interaction.followup.send(embed=embed)

        await asyncio.to_thread(spin_lucky_wheel, username, password, spins, interaction)

        embed_done = discord.Embed(
            title="✅ Spins abgeschlossen!",
            description=f"Alle `{spins}` Spins für `{username}` wurden erfolgreich ausgeführt!",
            color=discord.Color.blue()
        )
        await interaction.followup.send(embed=embed_done)


class SpinBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        await self.tree.sync()
        print(f"✅ Bot ist online als {self.user}")

bot = SpinBot()

def log(message):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def parse_reward_message(msg):
    if "%xt%lws%" not in msg:
        return

    try:
        json_str = re.search(r"%xt%lws%1%0%(.*)%", msg).group(1)
        data = json.loads(json_str)

        if "R" in data:
            for reward in data["R"]:
                r_type = reward[0]
                r_value = reward[1]

                if r_type == "U":
                    item_id, amount = r_value
                    if item_id in troop_ids:
                        reward_counter[troop_ids[item_id]] += amount
                    else:
                        reward_counter["Werkzeuge"] += amount
                elif r_type == "RI":
                    reward_counter["Ausrüstung"] += 1
                elif r_type == "CI":
                    reward_counter["Konstrukte"] += 1
                elif r_type == "LM":
                    reward_counter["Ausbaumarken"] += r_value
                elif r_type == "STP":
                    reward_counter["Sceattas"] += r_value
                elif r_type == "LB":
                    reward_counter["Kisten"] += r_value[1]
                elif r_type == "UE":
                    reward_counter["Mehrweller"] += r_value
                elif r_type == "C2":
                    reward_counter["Rubine"] += r_value
                elif r_type == "D":
                    reward_counter["Dekorationen"] += r_value[1]
                elif r_type in gift_map:
                    reward_counter[gift_map[r_type]] += r_value

    except Exception as e:
        log(f"⚠️ Fehler beim Parsen der Message: {e}")

def spin_lucky_wheel(username, password, spins, interaction):
    try:
        ws = websocket.WebSocket()
        ws.connect("wss://ep-live-de1-game.goodgamestudios.com/")
        log("✅ Verbindung hergestellt!")

        # Schritt 1: Version check
        ws.send("<msg t='sys'><body action='verChk' r='0'><ver v='166' /></body></msg>")
        time.sleep(0.1)

        # Schritt 2: Verbindungs-Handshake
        ws.send("<msg t='sys'><body action='login' r='0'><login z='EmpireEx_2'><nick><![CDATA[]]></nick><pword><![CDATA[1119057%de%0]]></pword></login></body></msg>")
        time.sleep(0.1)

        # Schritt 3: Vor-Login mit Username
        ws.send(f"%xt%EmpireEx_2%vln%1%{{\"NOM\":\"{username}\"}}%")
        time.sleep(0.1)

        # Schritt 4: Login mit Passwort
        login_befehl = f"%xt%EmpireEx_2%lli%1%{{\"CONM\":491,\"RTM\":74,\"ID\":0,\"PL\":1,\"NOM\":\"{username}\" ,\"PW\":\"{password}\",\"LT\":null,\"LANG\":\"de\",\"DID\":\"0\",\"AID\":\"1735403904264644306\",\"KID\":\"\",\"REF\":\"https://empire-html5.goodgamestudios.com\",\"GCI\":\"\",\"SID\":9,\"PLFID\":1}}%"
        ws.send(login_befehl)
        time.sleep(0.2)

        log("🔐 Erfolgreich eingeloggt! Starte Spins...")

        for i in range(spins):
            log(f"🎰 Spin {i+1}/{spins}")
            ws.send("%xt%EmpireEx_2%lws%1%{\"LWET\":1}%")
            msg = ws.recv()
            parse_reward_message(msg)

        log("✅ Alle Spins abgeschlossen!")
        ws.close()

        # Ergebnis an Discord senden
        asyncio.run(send_summary(interaction))

    except Exception as e:
        log(f"❌ Fehler beim Spin-Prozess: {e}")

async def send_summary(interaction):
    summary_lines = []
    for name, count in reward_counter.items():
        summary_lines.append(f"**{name}:** `{count}`")

    summary_text = "\n".join(summary_lines) if summary_lines else "Keine Belohnungen erkannt."

    embed = discord.Embed(
        title="🎁 Zusammenfassung deiner Belohnungen",
        description=summary_text,
        color=discord.Color.gold()
    )
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="spin", description="Starte das Glücksrad-Drehen!")
async def spin(interaction: discord.Interaction):
    await interaction.response.send_modal(SpinModal())

bot.run(TOKEN)
