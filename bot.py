import discord
from discord import app_commands
from discord.ext import commands
import sqlite3
import asyncio
import random
import os
import datetime
import threading
import time
from flask import Flask
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# ✅ Enable Bot Intents
intents = discord.Intents.default()
intents.message_content = True  # Required to process messages

bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ Database Setup
conn = sqlite3.connect("swearjar.db")
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS swear_counts (
        user_id INTEGER PRIMARY KEY,
        count INTEGER DEFAULT 0,
        coins INTEGER DEFAULT 100,
        warnings INTEGER DEFAULT 0,
        last_daily TIMESTAMP
    )
""")

# ✅ Additional table for tracking shop item purchases
c.execute("""
    CREATE TABLE IF NOT EXISTS shop_purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        price_paid INTEGER NOT NULL,
        purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

# Create table for positive words
c.execute("""
    CREATE TABLE IF NOT EXISTS positive_words (
        word TEXT PRIMARY KEY,
        reward INTEGER NOT NULL
    )
""")

conn.commit()

c.execute("CREATE TABLE IF NOT EXISTS swear_words (word TEXT PRIMARY KEY)")
c.execute("CREATE TABLE IF NOT EXISTS warning_messages (message TEXT PRIMARY KEY)")
c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")

# Create tables for new features
c.execute("""
    CREATE TABLE IF NOT EXISTS moderation_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS nsfw_words (
        word TEXT PRIMARY KEY
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS gif_filters (
        filter TEXT PRIMARY KEY
    )
""")

# ✅ Create shop items table and inventory table
c.execute("""
    CREATE TABLE IF NOT EXISTS shop_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        emoji TEXT NOT NULL,
        price INTEGER NOT NULL,
        description TEXT,
        role_id TEXT
    )
""")

c.execute("""
    CREATE TABLE IF NOT EXISTS user_inventory (
        user_id INTEGER,
        item_id INTEGER,
        quantity INTEGER DEFAULT 1,
        PRIMARY KEY (user_id, item_id)
    )
""")

# ✅ Add default shop items if none exist
c.execute("SELECT COUNT(*) FROM shop_items")
if c.fetchone()[0] == 0:
    default_items = [
        ("VIP Status", "👑", 500, "Special VIP role with unique color", None),
        ("Mute Token", "🔇", 300, "Mute someone for 5 minutes", None),
        ("Get Out of Jail", "🔑", 200, "Remove a warning from your record", None),
        ("Swear Pass", "🎟️", 150, "One-time pass to swear without penalty", None),
        ("Money Bag", "💰", 100, "Get 50 bonus coins", None)
    ]
    c.executemany("INSERT INTO shop_items (name, emoji, price, description, role_id) VALUES (?, ?, ?, ?, ?)", default_items)

conn.commit()

# ✅ Slash Command `/balance`
@bot.tree.command(name="balance", description="Check your remaining coins.")
async def balance(interaction: discord.Interaction):
    c.execute("SELECT coins FROM swear_counts WHERE user_id = ?", (interaction.user.id,))
    result = c.fetchone()
    coins = result[0] if result else 100

    # Get the currency emoji from settings, default to 💰
    c.execute("SELECT value FROM settings WHERE key = 'currency_emoji'")
    currency_emoji = c.fetchone()
    currency_emoji = currency_emoji[0] if currency_emoji else "💰"

    await interaction.response.send_message(f"{currency_emoji} You have `{coins}` coins left!")

# ✅ Slash Command `/daily`
@bot.tree.command(name="daily", description="Collect your daily coins reward.")
async def daily(interaction: discord.Interaction):
    user_id = interaction.user.id

    # Check if user exists, if not create entry
    c.execute("SELECT last_daily, coins FROM swear_counts WHERE user_id = ?", (user_id,))
    result = c.fetchone()

    now = datetime.datetime.now()

    if not result:
        # New user, give them coins and set timestamp
        c.execute("INSERT INTO swear_counts (user_id, coins, last_daily) VALUES (?, ?, ?)", 
                 (user_id, 100, now.isoformat()))
        conn.commit()
        await interaction.response.send_message("🎉 Welcome! You received your first 100 coins!")
        return

    last_daily_str, current_coins = result

    # If last_daily is None or if it's been more than 24 hours since last claim
    if not last_daily_str:
        last_daily = None
    else:
        try:
            last_daily = datetime.datetime.fromisoformat(last_daily_str)
        except (ValueError, TypeError):
            last_daily = None

    if not last_daily or (now - last_daily).total_seconds() >= 86400:  # 24 hours in seconds
        # User can claim daily reward
        reward = random.randint(50, 150)
        new_coins = current_coins + reward

        c.execute("UPDATE swear_counts SET coins = ?, last_daily = ? WHERE user_id = ?",
                 (new_coins, now.isoformat(), user_id))
        conn.commit()

        # Get the currency emoji from settings, default to 💰
        c.execute("SELECT value FROM settings WHERE key = 'currency_emoji'")
        currency_emoji = c.fetchone()
        currency_emoji = currency_emoji[0] if currency_emoji else "💰"

        await interaction.response.send_message(f"🎁 You claimed your daily reward of {reward} coins! You now have {new_coins} {currency_emoji}.")
    else:
        # Calculate time remaining until next claim
        next_claim = last_daily + datetime.timedelta(days=1)
        time_left = next_claim - now
        hours, remainder = divmod(time_left.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        await interaction.response.send_message(
            f"⏰ You already claimed your daily reward! Try again in {hours}h {minutes}m.",
            ephemeral=True
        )

# ✅ Slash Command `/set_currency <n>`
@bot.tree.command(name="set_currency", description="Set the currency name (e.g. gold, tokens).")
async def set_currency(interaction: discord.Interaction, name: str):
    c.execute("REPLACE INTO settings (key, value) VALUES ('currency', ?)", (name,))
    conn.commit()
    await interaction.response.send_message(f"💰 Currency name set to `{name}`!")

# ✅ Slash Command `/set_currency_emoji`
@bot.tree.command(name="set_currency_emoji", description="Set the emoji used for currency.")
@app_commands.describe(emoji="The emoji to use as currency symbol")
async def set_currency_emoji(interaction: discord.Interaction, emoji: str):
    # Basic check to ensure it's likely an emoji
    if len(emoji.strip()) != 1 and not emoji.startswith('<:'):
        await interaction.response.send_message("⚠️ Please provide a valid emoji!", ephemeral=True)
        return

    c.execute("REPLACE INTO settings (key, value) VALUES ('currency_emoji', ?)", (emoji,))
    conn.commit()
    await interaction.response.send_message(f"✅ Currency emoji set to {emoji}!")

# ✅ Slash Command `/shop`
@bot.tree.command(name="shop", description="View available items in the shop.")
async def shop(interaction: discord.Interaction):
    c.execute("SELECT id, name, emoji, price, description FROM shop_items ORDER BY price")
    items = c.fetchall()

    if not items:
        await interaction.response.send_message("🏪 The shop is currently empty!", ephemeral=True)
        return

    # Get user's coins
    c.execute("SELECT coins FROM swear_counts WHERE user_id = ?", (interaction.user.id,))
    result = c.fetchone()
    user_coins = result[0] if result else 100

    # Create an embed for the shop
    embed = discord.Embed(title="🏪 Shop", description="Buy items with your coins!", color=0x00FF00)
    embed.set_footer(text=f"You have {user_coins} coins")

    for item_id, name, emoji, price, description in items:
        embed.add_field(
            name=f"{emoji} {name} - {price} coins",
            value=f"ID: `{item_id}` | {description}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/buy`
@bot.tree.command(name="buy", description="Buy an item from the shop.")
@app_commands.describe(item_id="The ID of the item you want to buy")
async def buy(interaction: discord.Interaction, item_id: int):
    # Get the item details
    c.execute("SELECT name, emoji, price, description, role_id FROM shop_items WHERE id = ?", (item_id,))
    item = c.fetchone()

    if not item:
        await interaction.response.send_message("❌ Item not found!", ephemeral=True)
        return

    name, emoji, price, description, role_id = item

    # Check if user has enough coins
    c.execute("SELECT coins FROM swear_counts WHERE user_id = ?", (interaction.user.id,))
    result = c.fetchone()
    user_coins = result[0] if result else 100

    if user_coins < price:
        await interaction.response.send_message(f"❌ You don't have enough coins! You need {price - user_coins} more.", ephemeral=True)
        return

    # Process special items
    if name == "Money Bag":
        # Give 50 bonus coins
        bonus = 50
        new_coins = user_coins - price + bonus
        c.execute("UPDATE swear_counts SET coins = ? WHERE user_id = ?", (new_coins, interaction.user.id))
        conn.commit()
        await interaction.response.send_message(f"🎉 You bought a {emoji} {name} and received {bonus} bonus coins! You now have {new_coins} coins.")
        return

    elif name == "Get Out of Jail":
        # Remove a warning
        c.execute("SELECT warnings FROM swear_counts WHERE user_id = ?", (interaction.user.id,))
        current_warnings = c.fetchone()

        if not current_warnings or current_warnings[0] <= 0:
            await interaction.response.send_message("❌ You don't have any warnings to remove!", ephemeral=True)
            return

        new_warnings = current_warnings[0] - 1
        new_coins = user_coins - price

        c.execute("UPDATE swear_counts SET warnings = ?, coins = ? WHERE user_id = ?", 
                 (new_warnings, new_coins, interaction.user.id))
        conn.commit()

        await interaction.response.send_message(f"🎉 You bought {emoji} {name} and removed 1 warning! You now have {new_warnings} warnings and {new_coins} coins.")
        return

    # For all other items, add to inventory
    new_coins = user_coins - price
    c.execute("UPDATE swear_counts SET coins = ? WHERE user_id = ?", (new_coins, interaction.user.id))

    # Add to user's inventory
    c.execute("SELECT quantity FROM user_inventory WHERE user_id = ? AND item_id = ?", 
             (interaction.user.id, item_id))
    inventory_item = c.fetchone()

    if inventory_item:
        new_quantity = inventory_item[0] + 1
        c.execute("UPDATE user_inventory SET quantity = ? WHERE user_id = ? AND item_id = ?",
                 (new_quantity, interaction.user.id, item_id))
    else:
        c.execute("INSERT INTO user_inventory (user_id, item_id, quantity) VALUES (?, ?, 1)", 
                 (interaction.user.id, item_id))

    # Track the purchase for statistics
    c.execute("INSERT INTO shop_purchases (user_id, item_id, price_paid) VALUES (?, ?, ?)",
             (interaction.user.id, item_id, price))

    conn.commit()

    # If item gives a role
    if role_id:
        try:
            role = interaction.guild.get_role(int(role_id))
            if role:
                await interaction.user.add_roles(role)
                role_msg = f" and received the {role.name} role!"
            else:
                role_msg = " but the role couldn't be found."
        except Exception as e:
            print(f"Error adding role: {e}")
            role_msg = " but there was an error giving you the role."
    else:
        role_msg = "!"

    await interaction.response.send_message(f"🎉 You bought {emoji} {name}{role_msg} You now have {new_coins} coins.")

# ✅ Slash Command `/inventory`
@bot.tree.command(name="inventory", description="View your inventory.")
async def inventory(interaction: discord.Interaction):
    c.execute("""
        SELECT s.id, s.name, s.emoji, s.description, u.quantity
        FROM user_inventory u
        JOIN shop_items s ON u.item_id = s.id
        WHERE u.user_id = ?
    """, (interaction.user.id,))

    items = c.fetchall()

    if not items:
        await interaction.response.send_message("📦 Your inventory is empty!", ephemeral=True)
        return

    embed = discord.Embed(title="📦 Your Inventory", color=0x9B59B6)

    for item_id, name, emoji, description, quantity in items:
        embed.add_field(
            name=f"{emoji} {name} (x{quantity})",
            value=f"ID: `{item_id}` | {description}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/use`
@bot.tree.command(name="use", description="Use an item from your inventory.")
@app_commands.describe(
    item_id="The ID of the item you want to use",
    target="The user to target with this item (if applicable)"
)
async def use_item(interaction: discord.Interaction, item_id: int, target: discord.Member = None):
    # Check if user has the item
    c.execute("""
        SELECT ui.quantity, si.name, si.emoji, si.description
        FROM user_inventory ui
        JOIN shop_items si ON ui.item_id = si.id
        WHERE ui.user_id = ? AND ui.item_id = ?
    """, (interaction.user.id, item_id))

    item = c.fetchone()

    if not item or item[0] <= 0:
        await interaction.response.send_message("❌ You don't have this item in your inventory!", ephemeral=True)
        return

    quantity, name, emoji, description = item

    # Process specific items
    if name == "Mute Token":
        if not target:
            await interaction.response.send_message("❌ You need to specify a user to mute!", ephemeral=True)
            return

        # Create or get muted role
        muted_role = discord.utils.get(interaction.guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await interaction.guild.create_role(name="Muted")
                for channel in interaction.guild.channels:
                    await channel.set_permissions(muted_role, send_messages=False)
            except Exception as e:
                await interaction.response.send_message(f"❌ Error creating muted role: {e}", ephemeral=True)
                return

        # Apply mute
        try:
            await target.add_roles(muted_role)
            await interaction.response.send_message(f"🔇 {interaction.user.mention} used a Mute Token on {target.mention}! They have been muted for 5 minutes.")

            # Remove one item from inventory
            new_quantity = quantity - 1
            if new_quantity > 0:
                c.execute("UPDATE user_inventory SET quantity = ? WHERE user_id = ? AND item_id = ?",
                         (new_quantity, interaction.user.id, item_id))
            else:
                c.execute("DELETE FROM user_inventory WHERE user_id = ? AND item_id = ?",
                         (interaction.user.id, item_id))
            conn.commit()

            # Unmute after 5 minutes
            await asyncio.sleep(300)  # 5 minutes
            await target.remove_roles(muted_role)
        except Exception as e:
            await interaction.response.send_message(f"❌ Error muting user: {e}", ephemeral=True)

    elif name == "Swear Pass":
        # Add a swear pass to the user
        c.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", 
                 (f"swear_pass_{interaction.user.id}", "true"))
        conn.commit()

        # Remove one item from inventory
        new_quantity = quantity - 1
        if new_quantity > 0:
            c.execute("UPDATE user_inventory SET quantity = ? WHERE user_id = ? AND item_id = ?",
                     (new_quantity, interaction.user.id, item_id))
        else:
            c.execute("DELETE FROM user_inventory WHERE user_id = ? AND item_id = ?",
                     (interaction.user.id, item_id))
        conn.commit()

        await interaction.response.send_message(f"🎟️ You used a Swear Pass! Your next swear word will not be penalized.")

    else:
        # Generic response for other items
        await interaction.response.send_message(f"⚠️ Item '{name}' doesn't have a specific action implemented yet.")

# ✅ Slash Command `/add_shop_item`
@bot.tree.command(name="add_shop_item", description="Add a new item to the shop.")
@app_commands.describe(
    name="The name of the item",
    emoji="An emoji to represent the item",
    price="The price in coins",
    description="A description of what the item does",
    role_id="Optional: The role ID to give when item is purchased"
)
async def add_shop_item(interaction: discord.Interaction, name: str, emoji: str, price: int, description: str, role_id: str = None):
    # Check if admin (simple check - can be expanded)
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to add shop items!", ephemeral=True)
        return

    # Basic validation
    if price <= 0:
        await interaction.response.send_message("❌ Price must be positive!", ephemeral=True)
        return

    # Add the item to the shop
    c.execute("""
        INSERT INTO shop_items (name, emoji, price, description, role_id) 
        VALUES (?, ?, ?, ?, ?)
    """, (name, emoji, price, description, role_id))
    
    conn.commit()
    item_id = c.lastrowid  # Get the ID of the newly inserted item

    await interaction.response.send_message(f"✅ Added **{emoji} {name}** to the shop with ID `{item_id}`!")

# ✅ Slash Command `/remove_shop_item`
@bot.tree.command(name="remove_shop_item", description="Remove an item from the shop.")
@app_commands.describe(item_id="The ID of the item to remove")
async def remove_shop_item(interaction: discord.Interaction, item_id: int):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to remove shop items!", ephemeral=True)
        return

    # Get the item details
    c.execute("SELECT name, emoji FROM shop_items WHERE id = ?", (item_id,))
    item = c.fetchone()

    if not item:
        await interaction.response.send_message("❌ Item not found!", ephemeral=True)
        return

    name, emoji = item

    # Show confirmation UI
    view = ConfirmRemovalView(item_id, name, emoji)
    await interaction.response.send_message(
        f"⚠️ Are you sure you want to remove **{emoji} {name}** from the shop?",
        view=view
    )

# Confirmation view for item removal
class ConfirmRemovalView(discord.ui.View):
    def __init__(self, item_id, name, emoji):
        super().__init__(timeout=60)
        self.item_id = item_id
        self.name = name
        self.emoji = emoji

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Delete the item
        c.execute("DELETE FROM shop_items WHERE id = ?", (self.item_id,))
        conn.commit()

        await interaction.response.edit_message(
            content=f"✅ **{self.emoji} {self.name}** has been removed from the shop.",
            view=None
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content=f"❌ Removal of **{self.emoji} {self.name}** cancelled.",
            view=None
        )

# ✅ Slash Command `/update_shop_item`
@bot.tree.command(name="update_shop_item", description="Update an existing shop item.")
@app_commands.describe(
    item_id="The ID of the item to update",
    name="New name (leave blank to keep current)",
    emoji="New emoji (leave blank to keep current)",
    price="New price (set to 0 to keep current)",
    description="New description (leave blank to keep current)",
    role_id="New role ID (leave blank to keep current)"
)
async def update_shop_item(interaction: discord.Interaction, item_id: int, name: str = None, emoji: str = None, 
                          price: int = 0, description: str = None, role_id: str = None):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to update shop items!", ephemeral=True)
        return

    # Get current item data
    c.execute("SELECT name, emoji, price, description, role_id FROM shop_items WHERE id = ?", (item_id,))
    item = c.fetchone()

    if not item:
        await interaction.response.send_message("❌ Item not found!", ephemeral=True)
        return

    current_name, current_emoji, current_price, current_description, current_role_id = item

    # Use provided values or fall back to current values
    new_name = name if name is not None else current_name
    new_emoji = emoji if emoji is not None else current_emoji
    new_price = price if price > 0 else current_price
    new_description = description if description is not None else current_description
    new_role_id = role_id if role_id is not None else current_role_id

    # Update the item
    c.execute("""
        UPDATE shop_items 
        SET name = ?, emoji = ?, price = ?, description = ?, role_id = ?
        WHERE id = ?
    """, (new_name, new_emoji, new_price, new_description, new_role_id, item_id))
    
    conn.commit()

    await interaction.response.send_message(f"✅ Updated shop item **{new_emoji} {new_name}**!")

# ✅ Slash Command `/shop_manager`
@bot.tree.command(name="shop_manager", description="Manage shop items in a more detailed view.")
async def shop_manager(interaction: discord.Interaction):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to access the shop manager!", ephemeral=True)
        return

    # Get all items
    c.execute("""
        SELECT id, name, emoji, price, description, role_id 
        FROM shop_items 
        ORDER BY price DESC
    """)
    
    items = c.fetchall()

    if not items:
        await interaction.response.send_message("🏪 The shop is currently empty! Add items with `/add_shop_item`.")
        return

    # Create an embed for the shop manager
    embed = discord.Embed(
        title="🏪 Shop Manager", 
        description="View and manage shop items. Use `/add_shop_item`, `/update_shop_item`, or `/remove_shop_item` to make changes.",
        color=0xFF5500
    )

    for item_id, name, emoji, price, description, role_id in items:
        role_text = f"Gives role ID: `{role_id}`" if role_id else "No role reward"
        embed.add_field(
            name=f"ID {item_id}: {emoji} {name} - {price} coins",
            value=f"{description}\n{role_text}",
            inline=False
        )

    embed.set_footer(text="Use the commands mentioned in the description to manage items.")
    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/give_coins`
@bot.tree.command(name="give_coins", description="Give coins to a user (admin only).")
@app_commands.describe(
    user="The user to give coins to",
    amount="The amount of coins to give"
)
async def give_coins(interaction: discord.Interaction, user: discord.Member, amount: int):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to give coins!", ephemeral=True)
        return

    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be positive!", ephemeral=True)
        return

    # Check if user exists in the database
    c.execute("SELECT coins FROM swear_counts WHERE user_id = ?", (user.id,))
    result = c.fetchone()

    if result:
        current_coins = result[0]
        new_amount = current_coins + amount
        c.execute("UPDATE swear_counts SET coins = ? WHERE user_id = ?", (new_amount, user.id))
    else:
        new_amount = 100 + amount
        c.execute("INSERT INTO swear_counts (user_id, coins) VALUES (?, ?)", (user.id, new_amount))

    conn.commit()

    await interaction.response.send_message(f"✅ Gave {amount} coins to {user.mention}! They now have {new_amount} coins.")

# ✅ Bot Ready Event
@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')
    
    # Set bot start time for uptime tracking
    bot.start_time = datetime.datetime.now()
    
    # Load custom moderation reactions from database
    global MILD_REACTION, MODERATE_REACTION, SEVERE_REACTION, MUTED_REACTION
    
    c.execute("SELECT key, value FROM moderation_settings WHERE key = 'mild_reaction'")
    result = c.fetchone()
    if result:
        MILD_REACTION = result[1]
        
    c.execute("SELECT key, value FROM moderation_settings WHERE key = 'moderate_reaction'")
    result = c.fetchone()
    if result:
        MODERATE_REACTION = result[1]
        
    c.execute("SELECT key, value FROM moderation_settings WHERE key = 'severe_reaction'")
    result = c.fetchone()
    if result:
        SEVERE_REACTION = result[1]
        
    c.execute("SELECT key, value FROM moderation_settings WHERE key = 'muted_reaction'")
    result = c.fetchone()
    if result:
        MUTED_REACTION = result[1]
    
    try:
        await bot.tree.sync()
        print(f"✅ Successfully synced slash commands.")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# ✅ Load Swear Words & Settings
def load_swear_words():
    c.execute("SELECT word FROM swear_words")
    return {row[0] for row in c.fetchall()} | {"sorry", "fuck", "damn"}

# ✅ Load Positive Words
def load_positive_words():
    c.execute("SELECT word, reward FROM positive_words")
    return {row[0]: row[1] for row in c.fetchall()} or {"thanks": 5, "awesome": 5, "great": 5}

# ✅ Moderation Level Emojis
# These are Unicode emojis that work across all Discord clients
# Level 1: Mild warning (first offense)
MILD_REACTION = "😠"  # Angry face
# Level 2: Moderate warning (second offense or low coins)
MODERATE_REACTION = "😡"  # Very angry face
# Level 3: Severe warning (near mute threshold)
SEVERE_REACTION = "🤬"  # Face with symbols on mouth
# Level 4: Muted (3+ warnings)
MUTED_REACTION = "🔇"  # Muted speaker
# Positive reaction (for good behavior)
POSITIVE_REACTION = "😊"  # Smiling face with smiling eyes
# Very positive reaction (for consistent good behavior)
VERY_POSITIVE_REACTION = "🌟"  # Glowing star

SWEAR_WORDS = load_swear_words()
POSITIVE_WORDS = load_positive_words()

# Get user's moderation level (1-4) based on warning count and behavior
async def get_user_moderation_level(user_id):
    c.execute("SELECT warnings, count FROM swear_counts WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    
    if not result:
        return 1  # Default level for new users
    
    warnings, swear_count = result
    
    if warnings >= 2:  # About to be muted
        return 3
    elif warnings == 1 or swear_count >= 5:  # Second warning or frequent offender
        return 2
    else:
        return 1  # First-time or infrequent offender

# ✅ Message Event Handler
@bot.event
async def on_message(message):
    # Ignore messages from the bot itself
    if message.author == bot.user:
        return

    # Check if message contains swear words
    content = message.content.lower()
    swear_detected = False
    nsfw_detected = False
    gif_detected = False

    # Check for swear words
    for word in SWEAR_WORDS:
        if word.lower() in content.split():
            swear_detected = True
            break
            
    # Check for NSFW words
    c.execute("SELECT word FROM nsfw_words")
    nsfw_words = {row[0] for row in c.fetchall()}
    
    for word in nsfw_words:
        if word.lower() in content.split():
            nsfw_detected = True
            break
            
    # Check for GIFs
    if message.content.lower().startswith("gif:") or "tenor.com" in message.content.lower() or "giphy.com" in message.content.lower():
        # Get filtered GIF terms
        c.execute("SELECT filter FROM gif_filters")
        gif_filters = {row[0] for row in c.fetchall()}
        
        if gif_filters:  # Only run filter check if there are terms to filter
            for filter_term in gif_filters:
                if filter_term.lower() in message.content.lower():
                    gif_detected = True
                    break
    
    # Handle GIF filter violations
    if gif_detected:
        user_id = message.author.id
        await message.delete()
        await message.channel.send(f"⚠️ {message.author.mention} posted a GIF with filtered content and it was removed.")
        
        # Apply warning
        c.execute("SELECT warnings FROM swear_counts WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if result:
            warnings = result[0] + 1
            c.execute("UPDATE swear_counts SET warnings = ? WHERE user_id = ?", (warnings, user_id))
        else:
            warnings = 1
            c.execute("INSERT INTO swear_counts (user_id, count, coins, warnings) VALUES (?, 0, 100, ?)", (user_id, warnings))
        
        conn.commit()
        await message.channel.send(f"⚠️ {message.author.mention} received a warning ({warnings}/3) for posting a filtered GIF.")
    
    # Handle NSFW content
    if nsfw_detected:
        user_id = message.author.id
        await message.delete()
        await message.channel.send(f"🔞 {message.author.mention} posted NSFW content and it was removed.")
        
        # Apply warning
        c.execute("SELECT warnings FROM swear_counts WHERE user_id = ?", (user_id,))
        result = c.fetchone()
        
        if result:
            warnings = result[0] + 1
            c.execute("UPDATE swear_counts SET warnings = ? WHERE user_id = ?", (warnings, user_id))
        else:
            warnings = 1
            c.execute("INSERT INTO swear_counts (user_id, count, coins, warnings) VALUES (?, 0, 100, ?)", (user_id, warnings))
        
        conn.commit()
        await message.channel.send(f"⚠️ {message.author.mention} received a warning ({warnings}/3) for posting NSFW content.")

    if swear_detected:
        user_id = message.author.id

        # Check if user has a swear pass
        c.execute("SELECT value FROM settings WHERE key = ?", (f"swear_pass_{user_id}",))
        has_pass = c.fetchone()

        if has_pass and has_pass[0] == "true":
            # Use up the swear pass
            c.execute("DELETE FROM settings WHERE key = ?", (f"swear_pass_{user_id}",))
            conn.commit()

            await message.add_reaction("🎟️")
            await message.channel.send(f"🎟️ {message.author.mention} used a Swear Pass! No penalty this time.")
            return

        # Get user's current stats
        c.execute("SELECT count, coins, warnings FROM swear_counts WHERE user_id = ?", (user_id,))
        result = c.fetchone()

        # Determine moderation level for appropriate reaction
        moderation_level = await get_user_moderation_level(user_id)
        
        # Add reaction based on moderation level
        if moderation_level == 1:
            await message.add_reaction(MILD_REACTION)
        elif moderation_level == 2:
            await message.add_reaction(MODERATE_REACTION)
        elif moderation_level == 3:
            await message.add_reaction(SEVERE_REACTION)
        # Level 4 is applied when user is actually muted

        if result:
            count, coins, warnings = result
            new_count = count + 1
            new_coins = max(0, coins - 10)  # Deduct 10 coins, but don't go below 0

            # Check if out of coins
            if new_coins <= 0:
                new_warnings = warnings + 1
                await message.channel.send(f"⚠️ {message.author.mention} is out of coins and received a warning! ({new_warnings}/3)")

                # Check for 3 warnings = mute
                if new_warnings >= 3:
                    # Create or get muted role
                    muted_role = discord.utils.get(message.guild.roles, name="Muted")
                    if not muted_role:
                        try:
                            muted_role = await message.guild.create_role(name="Muted")
                            for channel in message.guild.channels:
                                await channel.set_permissions(muted_role, send_messages=False)
                        except Exception as e:
                            print(f"Error creating muted role: {e}")

                    try:
                        await message.author.add_roles(muted_role)
                        # Add muted reaction
                        await message.add_reaction(MUTED_REACTION)
                        await message.channel.send(f"🔇 {message.author.mention} reached 3 warnings and has been muted for 10 minutes!")

                        # Reset warnings
                        new_warnings = 0

                        # Unmute after 10 minutes
                        await asyncio.sleep(600)  # 10 minutes
                        await message.author.remove_roles(muted_role)
                    except Exception as e:
                        print(f"Error muting user: {e}")
            else:
                new_warnings = warnings

                # Get the currency emoji from settings, default to 💰
                c.execute("SELECT value FROM settings WHERE key = 'currency_emoji'")
                currency_emoji = c.fetchone()
                currency_emoji = currency_emoji[0] if currency_emoji else "💰"

                # Choose emoji based on warning level for the message
                warning_emoji = SEVERE_REACTION
                if new_warnings == 0:
                    warning_emoji = MILD_REACTION
                elif new_warnings == 1:
                    warning_emoji = MODERATE_REACTION
                    
                await message.channel.send(f"{warning_emoji} {message.author.mention} swore and lost 10 coins! {currency_emoji} {new_coins} remaining.")

            c.execute("UPDATE swear_counts SET count = ?, coins = ?, warnings = ? WHERE user_id = ?",
                     (new_count, new_coins, new_warnings, user_id))
        else:
            # First time swearing, create entry with penalty
            c.execute("INSERT INTO swear_counts (user_id, count, coins) VALUES (?, 1, 90)", (user_id,))
            await message.channel.send(f"{MILD_REACTION} {message.author.mention} swore for the first time and lost 10 coins! 💰 90 remaining.")

        conn.commit()

    # Check for positive words
    for word, reward in POSITIVE_WORDS.items():
        if word in content:
            user_id = message.author.id
            c.execute("SELECT coins FROM swear_counts WHERE user_id = ?", (user_id,))
            result = c.fetchone()
            
            # Get the currency emoji from settings, default to 💰
            c.execute("SELECT value FROM settings WHERE key = 'currency_emoji'")
            currency_emoji = c.fetchone()
            currency_emoji = currency_emoji[0] if currency_emoji else "💰"
            
            # Determine which positive reaction to use
            # Check if the user has a streak of positive behavior
            c.execute("SELECT COUNT(*) FROM swear_counts WHERE user_id = ? AND count <= 2", (user_id,))
            low_offense_count = c.fetchone()[0]
            
            if low_offense_count > 0:
                # Regular positive user
                await message.add_reaction(POSITIVE_REACTION)
                positive_emoji = POSITIVE_REACTION
            else:
                # Very positive user with minimal offenses
                await message.add_reaction(VERY_POSITIVE_REACTION)
                positive_emoji = VERY_POSITIVE_REACTION
            
            if result:
                current_coins = result[0]
                new_coins = current_coins + reward
                c.execute("UPDATE swear_counts SET coins = ? WHERE user_id = ?", (new_coins, user_id))
                conn.commit()
                await message.channel.send(f"{positive_emoji} {message.author.mention} used a positive word and earned {reward} coins! {currency_emoji} {new_coins} remaining.")
            else:
                # First positive word, create entry with reward
                c.execute("INSERT INTO swear_counts (user_id, coins) VALUES (?, ?)", (user_id, 100 + reward))
                conn.commit()
                await message.channel.send(f"{positive_emoji} {message.author.mention} used a positive word and earned {reward} coins! {currency_emoji} {100 + reward} remaining.")

    # Process commands
    await bot.process_commands(message)

# ✅ Slash Command `/addswear`
@bot.tree.command(name="addswear", description="Add a new swear word to the list.")
@app_commands.describe(word="The word you want to add to the swear list")
async def addswear(interaction: discord.Interaction, word: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to add swear words!", ephemeral=True)
        return
        
    c.execute("INSERT INTO swear_words (word) VALUES (?)", (word.lower(),))
    conn.commit()
    SWEAR_WORDS.add(word.lower())
    await interaction.response.send_message(f"✅ Added `{word}` to the swear list!")

# ✅ Slash Command `/removeswear`
@bot.tree.command(name="removeswear", description="Remove a word from the swear list.")
@app_commands.describe(word="The word you want to remove")
async def removeswear(interaction: discord.Interaction, word: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to remove swear words!", ephemeral=True)
        return
        
    c.execute("DELETE FROM swear_words WHERE word = ?", (word.lower(),))
    conn.commit()
    SWEAR_WORDS.discard(word.lower())
    await interaction.response.send_message(f"✅ Removed `{word}` from the swear list!")

# ✅ Slash Command `/addpositive`
@bot.tree.command(name="addpositive", description="Add a new positive word to reward users.")
@app_commands.describe(
    word="The positive word or phrase to add",
    reward="Coins to reward when used (default: 5)"
)
async def addpositive(interaction: discord.Interaction, word: str, reward: int = 5):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to add positive words!", ephemeral=True)
        return
        
    if reward <= 0:
        await interaction.response.send_message("❌ Reward must be positive!", ephemeral=True)
        return
        
    c.execute("INSERT OR REPLACE INTO positive_words (word, reward) VALUES (?, ?)", (word.lower(), reward))
    conn.commit()
    POSITIVE_WORDS[word.lower()] = reward
    await interaction.response.send_message(f"✅ Added `{word}` as a positive word with {reward} coins reward!")

# ✅ Slash Command `/removepositive`
@bot.tree.command(name="removepositive", description="Remove a word from the positive words list.")
@app_commands.describe(word="The word you want to remove")
async def removepositive(interaction: discord.Interaction, word: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to remove positive words!", ephemeral=True)
        return
        
    c.execute("DELETE FROM positive_words WHERE word = ?", (word.lower(),))
    conn.commit()
    POSITIVE_WORDS.pop(word.lower(), None)
    await interaction.response.send_message(f"✅ Removed `{word}` from the positive words list!")

# ✅ Slash Command `/positive_words_list`
@bot.tree.command(name="positive_words_list", description="View all positive words and their rewards.")
async def positive_words_list(interaction: discord.Interaction):
    c.execute("SELECT word, reward FROM positive_words")
    words = c.fetchall()
    
    if not words:
        await interaction.response.send_message("📋 No positive words have been added yet!")
        return
        
    embed = discord.Embed(title="✨ Positive Words List", description="Words that earn coins when used:", color=0x00FFFF)
    
    for word, reward in words:
        embed.add_field(name=word, value=f"Reward: {reward} coins", inline=True)
        
    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/leaderboard`
@bot.tree.command(name="leaderboard", description="View the swear jar leaderboard.")
async def leaderboard(interaction: discord.Interaction):
    c.execute("SELECT user_id, count FROM swear_counts ORDER BY count DESC LIMIT 10")
    swearers = c.fetchall()
    
    if not swearers:
        await interaction.response.send_message("📊 No swear counts recorded yet!")
        return
        
    embed = discord.Embed(title="🤬 Swear Jar Leaderboard", description="Top swearers:", color=0xFF0000)
    
    for i, (user_id, count) in enumerate(swearers, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"User {user_id}"
            
        embed.add_field(name=f"{i}. {name}", value=f"{count} swears", inline=False)
        
    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/richest`
@bot.tree.command(name="richest", description="View the users with the most coins.")
async def richest(interaction: discord.Interaction):
    c.execute("SELECT user_id, coins FROM swear_counts ORDER BY coins DESC LIMIT 10")
    rich_users = c.fetchall()
    
    if not rich_users:
        await interaction.response.send_message("📊 No users have any coins yet!")
        return
        
    # Get the currency name from settings, default to "coins"
    c.execute("SELECT value FROM settings WHERE key = 'currency'")
    currency_name = c.fetchone()
    currency_name = currency_name[0] if currency_name else "coins"
    
    # Get the emoji from settings
    c.execute("SELECT value FROM settings WHERE key = 'currency_emoji'")
    currency_emoji = c.fetchone()
    currency_emoji = currency_emoji[0] if currency_emoji else "💰"
    
    embed = discord.Embed(
        title=f"{currency_emoji} Richest Users", 
        description=f"Users with the most {currency_name}:", 
        color=0xFFD700
    )
    
    for i, (user_id, coins) in enumerate(rich_users, 1):
        try:
            user = await bot.fetch_user(user_id)
            name = user.display_name
        except:
            name = f"User {user_id}"
            
        embed.add_field(name=f"{i}. {name}", value=f"{coins} {currency_name}", inline=False)
        
    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/banned_words`
@bot.tree.command(name="banned_words", description="View all banned words.")
async def banned_words(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    
    c.execute("SELECT word FROM swear_words")
    db_words = c.fetchall()
    all_words = [row[0] for row in db_words]
    all_words.extend(["sorry", "fuck", "damn"])  # Add default words
    all_words = list(set(all_words))  # Remove duplicates
    
    if not all_words:
        await interaction.followup.send("📋 No words are banned yet!")
        return
        
    embed = discord.Embed(title="🚫 Banned Words", description="Words that trigger the swear jar:", color=0xFF0000)
    
    # Split words into chunks to avoid hitting field limits
    chunk_size = 10
    word_chunks = [all_words[i:i + chunk_size] for i in range(0, len(all_words), chunk_size)]
    
    for i, chunk in enumerate(word_chunks, 1):
        embed.add_field(name=f"Words {i}", value="`" + "`, `".join(chunk) + "`", inline=False)
        
    await interaction.followup.send(embed=embed, ephemeral=True)
    
# ✅ Slash Command `/moderation_levels`
@bot.tree.command(name="moderation_levels", description="View information about moderation levels and their reactions.")
async def moderation_levels(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📊 Moderation Levels", 
        description="The bot uses different reactions based on user behavior:", 
        color=0x00FFFF
    )
    
    embed.add_field(
        name=f"Level 1: Mild {MILD_REACTION}", 
        value="First offenses or infrequent rule violations", 
        inline=False
    )
    
    embed.add_field(
        name=f"Level 2: Moderate {MODERATE_REACTION}", 
        value="Second warning or frequent offender (5+ swears)", 
        inline=False
    )
    
    embed.add_field(
        name=f"Level 3: Severe {SEVERE_REACTION}", 
        value="User with 2+ warnings, on the verge of being muted", 
        inline=False
    )
    
    embed.add_field(
        name=f"Level 4: Muted {MUTED_REACTION}", 
        value="User who has reached 3 warnings and is muted", 
        inline=False
    )
    
    embed.add_field(
        name=f"Positive: {POSITIVE_REACTION}", 
        value="Using positive words earns coins and this reaction", 
        inline=False
    )
    
    embed.add_field(
        name=f"Very Positive: {VERY_POSITIVE_REACTION}", 
        value="Consistent positive behavior with minimal offenses", 
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)
    
# ✅ Slash Command `/add_nsfw_word`
@bot.tree.command(name="add_nsfw_word", description="Add a new NSFW word to the filter list.")
@app_commands.describe(word="The NSFW word you want to filter")
async def add_nsfw_word(interaction: discord.Interaction, word: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to add NSFW words!", ephemeral=True)
        return
        
    c.execute("INSERT OR IGNORE INTO nsfw_words (word) VALUES (?)", (word.lower(),))
    conn.commit()
    await interaction.response.send_message(f"✅ Added `{word}` to the NSFW filter list!", ephemeral=True)

# ✅ Slash Command `/remove_nsfw_word`
@bot.tree.command(name="remove_nsfw_word", description="Remove a word from the NSFW filter list.")
@app_commands.describe(word="The NSFW word you want to remove from filtering")
async def remove_nsfw_word(interaction: discord.Interaction, word: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to remove NSFW words!", ephemeral=True)
        return
        
    c.execute("DELETE FROM nsfw_words WHERE word = ?", (word.lower(),))
    conn.commit()
    await interaction.response.send_message(f"✅ Removed `{word}` from the NSFW filter list!", ephemeral=True)

# ✅ Slash Command `/nsfw_words_list`
@bot.tree.command(name="nsfw_words_list", description="View all filtered NSFW words.")
async def nsfw_words_list(interaction: discord.Interaction):
    # Check if admin to view the list
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to view NSFW words!", ephemeral=True)
        return
        
    c.execute("SELECT word FROM nsfw_words")
    words = c.fetchall()
    
    if not words:
        await interaction.response.send_message("📋 No NSFW words have been added to the filter yet!", ephemeral=True)
        return
        
    embed = discord.Embed(title="🔞 NSFW Filter List", description="Words that trigger content removal:", color=0xFF0000)
    
    # Split words into chunks to avoid hitting field limits
    chunk_size = 10
    word_chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]
    
    for i, chunk in enumerate(word_chunks, 1):
        words_text = "`, `".join([row[0] for row in chunk])
        embed.add_field(name=f"Words {i}", value=f"`{words_text}`", inline=False)
        
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ✅ Slash Command `/add_gif_filter`
@bot.tree.command(name="add_gif_filter", description="Add a new term to the GIF filter list.")
@app_commands.describe(filter_term="The term to filter in GIFs (e.g., 'nsfw', 'violence')")
async def add_gif_filter(interaction: discord.Interaction, filter_term: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to add GIF filters!", ephemeral=True)
        return
        
    c.execute("INSERT OR IGNORE INTO gif_filters (filter) VALUES (?)", (filter_term.lower(),))
    conn.commit()
    await interaction.response.send_message(f"✅ Added `{filter_term}` to the GIF filter list!", ephemeral=True)

# ✅ Slash Command `/remove_gif_filter`
@bot.tree.command(name="remove_gif_filter", description="Remove a term from the GIF filter list.")
@app_commands.describe(filter_term="The term to remove from GIF filtering")
async def remove_gif_filter(interaction: discord.Interaction, filter_term: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to remove GIF filters!", ephemeral=True)
        return
        
    c.execute("DELETE FROM gif_filters WHERE filter = ?", (filter_term.lower(),))
    conn.commit()
    await interaction.response.send_message(f"✅ Removed `{filter_term}` from the GIF filter list!", ephemeral=True)

# ✅ Slash Command `/gif_filters_list`
@bot.tree.command(name="gif_filters_list", description="View all filtered GIF terms.")
async def gif_filters_list(interaction: discord.Interaction):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to view GIF filters!", ephemeral=True)
        return
        
    c.execute("SELECT filter FROM gif_filters")
    filters = c.fetchall()
    
    if not filters:
        await interaction.response.send_message("📋 No GIF filter terms have been added yet!", ephemeral=True)
        return
        
    embed = discord.Embed(title="🎬 GIF Filter List", description="Terms that trigger GIF removal:", color=0xFF5733)
    
    # List all filter terms
    filters_text = "`, `".join([row[0] for row in filters])
    embed.add_field(name="Filtered Terms", value=f"`{filters_text}`", inline=False)
        
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ✅ Slash Command `/add_warning_message`
@bot.tree.command(name="add_warning_message", description="Add a custom warning message for rule violations.")
@app_commands.describe(message="The warning message to display to users")
async def add_warning_message(interaction: discord.Interaction, message: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to add warning messages!", ephemeral=True)
        return
        
    c.execute("INSERT OR IGNORE INTO warning_messages (message) VALUES (?)", (message,))
    conn.commit()
    await interaction.response.send_message(f"✅ Added warning message: `{message}`", ephemeral=True)

# ✅ Slash Command `/remove_warning_message`
@bot.tree.command(name="remove_warning_message", description="Remove a custom warning message.")
@app_commands.describe(message="The exact warning message to remove")
async def remove_warning_message(interaction: discord.Interaction, message: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to remove warning messages!", ephemeral=True)
        return
        
    c.execute("DELETE FROM warning_messages WHERE message = ?", (message,))
    conn.commit()
    await interaction.response.send_message(f"✅ Removed warning message: `{message}`", ephemeral=True)

# ✅ Slash Command `/warning_messages_list`
@bot.tree.command(name="warning_messages_list", description="View all custom warning messages.")
async def warning_messages_list(interaction: discord.Interaction):
    c.execute("SELECT message FROM warning_messages")
    messages = c.fetchall()
    
    if not messages:
        await interaction.response.send_message("📋 No custom warning messages have been added yet!")
        return
        
    embed = discord.Embed(title="⚠️ Warning Messages", description="Custom messages used for rule violations:", color=0xFFA500)
    
    for i, (message,) in enumerate(messages, 1):
        embed.add_field(name=f"Message {i}", value=message, inline=False)
        
    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/set_moderation_reaction`
@bot.tree.command(name="set_moderation_reaction", description="Set custom reaction emoji for a moderation level.")
@app_commands.describe(
    level="The moderation level (1-4)",
    emoji="The emoji to use for this level"
)
async def set_moderation_reaction(interaction: discord.Interaction, level: int, emoji: str):
    # Check if admin
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You need administrator permissions to set moderation reactions!", ephemeral=True)
        return
        
    # Validate level
    if level < 1 or level > 4:
        await interaction.response.send_message("❌ Level must be between 1 and 4!", ephemeral=True)
        return
        
    # Map level to settings key
    key_map = {
        1: "mild_reaction",
        2: "moderate_reaction",
        3: "severe_reaction",
        4: "muted_reaction"
    }
    
    c.execute("REPLACE INTO moderation_settings (key, value) VALUES (?, ?)", (key_map[level], emoji))
    conn.commit()
    
    # Update global variables to take effect immediately
    if level == 1:
        global MILD_REACTION
        MILD_REACTION = emoji
    elif level == 2:
        global MODERATE_REACTION
        MODERATE_REACTION = emoji
    elif level == 3:
        global SEVERE_REACTION
        SEVERE_REACTION = emoji
    elif level == 4:
        global MUTED_REACTION
        MUTED_REACTION = emoji
    
    await interaction.response.send_message(f"✅ Set level {level} moderation reaction to {emoji}")

# ✅ Slash Command `/ping`
@bot.tree.command(name="ping", description="Check if the bot is online and responding")
async def ping(interaction: discord.Interaction):
    # Calculate bot latency
    latency = round(bot.latency * 1000)  # Convert to ms
    
    # Get bot uptime
    current_time = datetime.datetime.now()
    uptime = current_time - bot.start_time if hasattr(bot, 'start_time') else datetime.timedelta(seconds=0)
    
    # Format uptime nicely
    days, remainder = divmod(int(uptime.total_seconds()), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m {seconds}s"
    
    embed = discord.Embed(
        title="🔔 Bot Status", 
        description="The bot is online and operational!", 
        color=0x00FF00
    )
    
    embed.add_field(name="Ping", value=f"{latency}ms", inline=True)
    embed.add_field(name="Uptime", value=uptime_str, inline=True)
    embed.add_field(name="Commands", value=f"{len(bot.tree.get_commands())} loaded", inline=True)
    
    await interaction.response.send_message(embed=embed)

# ✅ Slash Command `/help`
@bot.tree.command(name="help", description="Display information about the bot's commands and features.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Swear Jar Bot Help", 
        description="This bot monitors chat for swear words and maintains an economy system with reactions that indicate moderation levels.", 
        color=0x5865F2
    )
    
    # User commands
    user_commands = """
`/balance` - Check your current coin balance
`/daily` - Claim your daily reward coins
`/shop` - View items available for purchase
`/buy` - Purchase items from the shop
`/inventory` - View your purchased items
`/use_item` - Use an item from your inventory
`/leaderboard` - View top swearers
`/richest` - View users with most coins
`/moderation_levels` - View info about reaction system
`/ping` - Check if bot is online and get status
"""
    embed.add_field(name="📝 User Commands", value=user_commands, inline=False)
    
    # Admin commands
    admin_commands = """
`/addswear` - Add a word to the swear list
`/removeswear` - Remove a word from the swear list
`/banned_words` - View all banned words
`/addpositive` - Add a positive word with reward
`/removepositive` - Remove a positive word
`/positive_words_list` - View all positive words
`/set_currency` - Set currency name
`/set_currency_emoji` - Set currency emoji
`/give_coins` - Give coins to a user
"""
    embed.add_field(name="⚙️ Admin Commands", value=admin_commands, inline=False)
    
    # Shop commands
    shop_commands = """
`/add_shop_item` - Add an item to the shop
`/remove_shop_item` - Remove an item from the shop 
`/update_shop_item` - Update an existing shop item
`/shop_manager` - View and manage shop items
"""
    embed.add_field(name="🛒 Shop Management", value=shop_commands, inline=False)
    
    # Reaction system
    reaction_info = f"""
This bot now features an animated emoji reaction system that visually indicates moderation levels:

{MILD_REACTION} **Level 1:** First offense
{MODERATE_REACTION} **Level 2:** Second offense or frequent offender
{SEVERE_REACTION} **Level 3:** Near mute threshold
{MUTED_REACTION} **Level 4:** Muted user
{POSITIVE_REACTION} **Positive:** Reward for positive words
{VERY_POSITIVE_REACTION} **Very Positive:** Consistent good behavior

Use `/moderation_levels` for more details
"""
    embed.add_field(name="⚠️ Reaction System", value=reaction_info, inline=False)
    
    await interaction.response.send_message(embed=embed)

for _ in range(20):
    print("Hello World it is me")
    time.sleep(30)

# Create a simple web server to keep Replit happy
app = Flask(__name__)

@app.route('/')
def home():
    return "Discord Swear Jar Bot is running!"

def keep_alive():
    # Start the web server in a separate thread
    server_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False))
    server_thread.daemon = True
    server_thread.start()
    print("✅ Web server started on port 5000")

# ✅ Keep the server alive and start the bot
if __name__ == "__main__":
    keep_alive()
    bot.run(BOT_TOKEN)