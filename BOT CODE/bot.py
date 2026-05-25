import discord
from discord.ext import commands
import time
import re
from datetime import datetime, timedelta
import asyncio

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Dictionary to track user spam
user_messages = {}
user_promotions = {}

# Configuration
SPAM_TIME_WINDOW = 5
SPAM_MESSAGE_COUNT = 5
WARNING_COOLDOWN = 60

def is_staff_member(member):
    """Check if user is staff (immune to all enforcement)"""
    if member == member.guild.owner:
        return True
    
    if member.guild_permissions.administrator or member.guild_permissions.kick_members:
        return True
    
    if member.guild_permissions.manage_messages or member.guild_permissions.manage_guild:
        return True
    
    mod_role_names = ['mod', 'moderator', 'moderators', 'staff', 'admin', 'administrator', 'management', 'team']
    for role in member.roles:
        if role.name.lower() in mod_role_names:
            return True
    
    return False

def contains_promotion(content):
    """Check if message contains promotional content"""
    promotion_patterns = [
        r'(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li|com/invite))/[a-zA-Z0-9]+',
        r'(?i)join my discord',
        r'(?i)join my server',
        r'(?i)looking for members',
        r'(?i)recruiting',
        r'(?i)i give .*script',
        r'(?i)free script',
    ]
    
    for pattern in promotion_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return True, pattern
    
    return False, None

@bot.event
async def on_ready():
    print(f'{bot.user} is online and protecting the server!')
    print(f'Logged in as {bot.user.name}')
    print('=' * 50)
    print('🛡️ PROTECTION MODES ACTIVE:')
    print('1. IMAGE DELETION - Silently deletes ALL images (NO warning/kick)')
    print('2. SPAM DETECTION - Warning → Kick (text messages only)')
    print('3. PROMOTION DETECTION - Warning → Kick (text only)')
    print('=' * 50)
    print('⚠️ ALL images/photos/attachments will be silently deleted!')
    print('=' * 50)

@bot.event
async def on_message(message):
    # Ignore bot messages and DMs
    if message.author.bot or not message.guild:
        await bot.process_commands(message)
        return
    
    # Staff members are completely immune
    if is_staff_member(message.author):
        await bot.process_commands(message)
        return
    
    # ============================================
    # IMAGE DELETION - Delete ALL images silently
    # ============================================
    if message.attachments:
        # Check if any attachment is an image
        for attachment in message.attachments:
            # Check if it's an image file
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.ico')):
                try:
                    # Delete the message silently
                    await message.delete()
                    
                    # Log to console
                    print(f"🗑️ IMAGE DELETED: {message.author.name} deleted image: {attachment.filename}")
                    
                    # Don't process further - message is gone
                    return
                except Exception as e:
                    print(f"Error deleting image: {e}")
        
        # If it has attachments but not images (other files), let it through
        # (or you can also delete them by uncommenting below)
        # await message.delete()
        # return
    
    # ============================================
    # PROMOTION DETECTION (Warning → Kick) - TEXT ONLY
    # ============================================
    is_promo, promo_content = contains_promotion(message.content)
    if is_promo:
        await handle_promotion(message, promo_content)
        return
    
    # ============================================
    # SPAM DETECTION (Warning → Kick) - TEXT ONLY
    # ============================================
    if await is_spamming(message.author.id):
        await handle_spam(message)
        return
    
    await bot.process_commands(message)

async def handle_promotion(message, promo_content):
    """Handle promotional messages - Warning then kick"""
    user_id = message.author.id
    
    if user_id not in user_promotions:
        user_promotions[user_id] = {
            'warning_count': 0,
            'last_warning_time': None
        }
    
    tracker = user_promotions[user_id]
    current_time = time.time()
    
    if tracker['last_warning_time'] and (current_time - tracker['last_warning_time']) < WARNING_COOLDOWN:
        await kick_for_promotion(message, promo_content)
        if user_id in user_promotions:
            del user_promotions[user_id]
    else:
        await warn_for_promotion(message, promo_content)
        tracker['warning_count'] += 1
        tracker['last_warning_time'] = current_time

async def warn_for_promotion(message, promo_content):
    """Send warning for promotional content"""
    try:
        await message.delete()
        
        embed = discord.Embed(
            title="⚠️ PROMOTION WARNING ⚠️",
            description=f"{message.author.mention} **NO PROMOTING ALLOWED!**",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="Next Offense",
            value="⚠️ **You will be IMMEDIATELY KICKED from the server!**",
            inline=False
        )
        
        warning_msg = await message.channel.send(embed=embed)
        
        try:
            await message.author.send(f"⚠️ Warning from {message.guild.name}: No promotions allowed! Next offense = Kick")
        except:
            pass
        
        await asyncio.sleep(10)
        try:
            await warning_msg.delete()
        except:
            pass
        
        print(f"⚠️ PROMOTION WARNING: {message.author.name}")
        
    except Exception as e:
        print(f"Error warning for promotion: {e}")

async def kick_for_promotion(message, promo_content):
    """Kick user for repeated promotional content"""
    try:
        user = message.author
        guild = message.guild
        
        try:
            await message.delete()
        except:
            pass
        
        embed = discord.Embed(
            title="🔨 MEMBER KICKED FOR PROMOTION 🔨",
            description=f"{user.mention} has been kicked for repeated promotional content!",
            color=discord.Color.red()
        )
        
        await message.channel.send(embed=embed)
        
        try:
            await user.send(f"🔨 You have been kicked from {guild.name} for repeated promotions.")
        except:
            pass
        
        await guild.kick(user, reason="Repeated promotion after warning")
        
        if user.id in user_messages:
            del user_messages[user.id]
        if user.id in user_promotions:
            del user_promotions[user.id]
        
        print(f"🔨 KICKED FOR PROMOTION: {user.name}")
        
    except discord.Forbidden:
        await message.channel.send("❌ I don't have permission to kick members!")
    except Exception as e:
        print(f"Error kicking for promotion: {e}")

async def is_spamming(user_id):
    """Check if user is spamming"""
    current_time = time.time()
    
    if user_id not in user_messages:
        user_messages[user_id] = UserTrack(user_id)
    
    tracker = user_messages[user_id]
    tracker.message_times.append(current_time)
    
    cutoff_time = current_time - SPAM_TIME_WINDOW
    tracker.message_times = [msg_time for msg_time in tracker.message_times 
                            if msg_time > cutoff_time]
    
    return len(tracker.message_times) > SPAM_MESSAGE_COUNT

async def handle_spam(message):
    """Handle spammer with warning first, then kick"""
    user_id = message.author.id
    tracker = user_messages[user_id]
    
    current_time = time.time()
    if tracker.last_warning_time and (current_time - tracker.last_warning_time) < WARNING_COOLDOWN:
        await kick_spammer(message)
    else:
        await warn_spammer(message)
        tracker.last_warning_time = current_time

async def warn_spammer(message):
    """Send warning to spammer"""
    try:
        def is_spam_message(msg):
            return msg.author == message.author and (datetime.utcnow() - msg.created_at).seconds <= SPAM_TIME_WINDOW
        
        await message.channel.purge(limit=SPAM_MESSAGE_COUNT + 5, check=is_spam_message)
        
        embed = discord.Embed(
            title="⚠️ SPAM WARNING ⚠️",
            description=f"{message.author.mention}, stop spamming!",
            color=discord.Color.orange()
        )
        embed.add_field(
            name="Next Offense",
            value="Will result in an immediate **KICK** from the server!",
            inline=False
        )
        
        warning_msg = await message.channel.send(embed=embed)
        
        try:
            await message.author.send(f"⚠️ Warning from {message.guild.name}: You have been warned for spamming! Next offense = Kick")
        except:
            pass
        
        await asyncio.sleep(10)
        try:
            await warning_msg.delete()
        except:
            pass
        
        print(f"⚠️ SPAM WARNING: {message.author.name}")
        
    except Exception as e:
        print(f"Error warning spammer: {e}")

async def kick_spammer(message):
    """Kick spammer"""
    try:
        user = message.author
        guild = message.guild
        
        def is_recent(msg):
            return msg.author == user and (datetime.utcnow() - msg.created_at).seconds <= 30
        
        try:
            await message.channel.purge(limit=50, check=is_recent)
        except:
            pass
        
        embed = discord.Embed(
            title="🔨 MEMBER KICKED FOR SPAM 🔨",
            description=f"{user.mention} has been kicked for spamming!",
            color=discord.Color.red()
        )
        
        await message.channel.send(embed=embed)
        
        try:
            await user.send(f"🔨 You have been kicked from {guild.name} for spamming after receiving a warning.")
        except:
            pass
        
        await guild.kick(user, reason="Spamming after warning")
        
        if user.id in user_messages:
            del user_messages[user.id]
        
        print(f"🔨 KICKED FOR SPAM: {user.name}")
        
    except discord.Forbidden:
        await message.channel.send("❌ I don't have permission to kick members!")
    except Exception as e:
        print(f"Error kicking spammer: {e}")

class UserTrack:
    def __init__(self, user_id):
        self.user_id = user_id
        self.message_times = []
        self.warning_count = 0
        self.last_warning_time = None
        self.is_kicked = False

# Admin Commands
@bot.command(name='settings')
@commands.has_permissions(administrator=True)
async def view_settings(ctx):
    """View all protection settings"""
    embed = discord.Embed(
        title="🛡️ Server Protection Settings",
        color=discord.Color.blue()
    )
    embed.add_field(name="📷 IMAGE DELETION", value="✅ ACTIVE - ALL images silently deleted (NO warning/kick)", inline=False)
    embed.add_field(name="💬 SPAM Protection", value=f"{SPAM_MESSAGE_COUNT} msgs / {SPAM_TIME_WINDOW} sec → Warning → Kick", inline=False)
    embed.add_field(name="📢 PROMOTION Protection", value="✅ Warning → Kick", inline=False)
    embed.add_field(name="👥 Monitored Users", value="Regular Members ONLY", inline=False)
    embed.add_field(name="👑 Immune Users", value="Staff, Admins, Owner", inline=False)
    
    await ctx.send(embed=embed)

@bot.command(name='test')
@commands.has_permissions(administrator=True)
async def test_protection(ctx):
    """Test the protection system"""
    embed = discord.Embed(
        title="🛡️ Protection System Active",
        description="The bot is protecting the server!",
        color=discord.Color.green()
    )
    embed.add_field(
        name="📷 IMAGES",
        value="✅ ALL images will be silently deleted\n❌ NO warning or kick",
        inline=False
    )
    embed.add_field(
        name="💬 SPAM",
        value="⚠️ Warning on first offense\n🔨 Kick on second offense",
        inline=False
    )
    embed.add_field(
        name="📢 PROMOTION",
        value="⚠️ Warning on first offense\n🔨 Kick on second offense",
        inline=False
    )
    await ctx.send(embed=embed)

# ============================================
# TOKEN CONFIGURATION
# ============================================

import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except:
    pass

TOKEN = os.getenv('DISCORD_TOKEN')

if TOKEN and TOKEN != 'MTUwODQ5OTI5MDk2Njg1MTcyNw.GINIMH.AWJAZzNUTEErSV7OZbVW6XpcNm1fmeJuDMk0ag':
    print("Starting bot...")
    bot.run(TOKEN)
else:
    print("=" * 50)
    print("ERROR: Bot token not found!")
    print("Please set DISCORD_TOKEN environment variable")
    print("=" * 50)
