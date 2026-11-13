import os
import re
import json
import asyncio
import logging
import unicodedata
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands

TOKEN = "MTU2ODE4ODcyNDkzNDg3MzE3OA.GuqPoD.DE2Ae44nglylOcTpD3HXUI5qyNBMxcEtXZpwTk"
DATA_FILE = "DeaTh_system_data.json"
PREFIX = "!"
MEMBER_ROLE_NAME = "DeaTh"
TICKET_CATEGORY_NAME = "tickets"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("death")

intents = discord.Intents.default()
intents.guilds = intents.members = intents.messages = True
intents.message_content = intents.voice_states = True

data = {
    "staff_roles": {}, "ticket_rooms": {}, "protected_words": {},
    "channel_states": {}, "welcome_channels": {}, "welcome_texts": {},
    "locket_channels": {}, "logs": {}, "mute_staff_roles": {},
    "prison_roles": {}, "muted_roles": {}, "voice_mutes": {}, "chat_mutes": {},
    "bot_status": {"value": "online"},
    "staff_permissions": {}, "prison_channels": {}, "prison_saved_roles": {},
    "image_roles": {}, "server_lock_states": {}
}

LOG_NAMES = {
    "messages": "الرسائل",
    "roles": "الرولات",
    "channels": "الرومات",
    "nickname": "الأسماء",
    "server": "السيرفر",
    "admin": "الإدارة",
}


def load_data():
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for key in data:
            if isinstance(saved.get(key), dict):
                data[key] = saved[key]
    except (OSError, json.JSONDecodeError):
        log.exception("تعذر تحميل ملف البيانات")


def save_data():
    try:
        with open(DATA_FILE + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(DATA_FILE + ".tmp", DATA_FILE)
    except OSError:
        log.exception("تعذر حفظ ملف البيانات")


def is_owner(member):
    return bool(getattr(member, "guild", None) and member.guild.owner_id == member.id)


def is_staff(member):
    if member.guild_permissions.administrator or is_owner(member):
        return True
    ids = data["staff_roles"].get(str(member.guild.id), [])
    return any(str(r.id) in ids for r in member.roles)


def actor_above(actor, target):
    return actor.id == actor.guild.owner_id or actor.top_role > target.top_role


def bot_can_manage_role(guild, role):
    return bool(guild.me and guild.me.guild_permissions.manage_roles and role < guild.me.top_role)


PERMISSION_NAMES = {
    "kick": "الطرد", "mute": "الميوت", "ban": "الباند",
    "clear": "مسح الرسائل", "add_role": "إضافة رتب", "remove_role": "سحب رتب",
    "channels": "إدارة الرومات", "server": "قفل وفتح السيرفر",
    "voice": "إدارة الفويس", "prison": "السجن", "timeout": "التايم أوت",
    "nickname": "تغيير الأسماء", "images": "إدارة الصور", "words": "الكلمات المحظورة"
}

PERMISSION_ALIASES = {
    "kick": "kick", "طرد": "kick", "kick_members": "kick",
    "mute": "mute", "ميوت": "mute", "ميوت": "mute",
    "ban": "ban", "باند": "ban", "حظر": "ban",
    "clear": "clear", "مسح": "clear", "purge": "clear",
    "add": "add_role", "add_role": "add_role", "اضافة": "add_role", "إضافة": "add_role", "اضافه": "add_role",
    "remove": "remove_role", "remove_role": "remove_role", "سحب": "remove_role", "حذف": "remove_role",
    "channels": "channels", "rooms": "channels", "رومات": "channels", "روم": "channels",
    "server": "server", "السيرفر": "server", "قفل_السيرفر": "server",
    "voice": "voice", "فويس": "voice", "صوت": "voice",
    "prison": "prison", "سجن": "prison",
    "timeout": "timeout", "تايم": "timeout", "تايم_اوت": "timeout",
    "nickname": "nickname", "nick": "nickname", "اسماء": "nickname", "الأسماء": "nickname",
    "images": "images", "صور": "images", "الصور": "images",
    "words": "words", "كلمات": "words"
}


def member_has_permission(member, permission):
    if is_owner(member) or member.guild_permissions.administrator:
        return True
    guild_key = str(member.guild.id)
    permission_map = data.get("staff_permissions", {}).get(guild_key, {})
    # Keep existing staff-role behavior until the owner starts configuring granular permissions.
    if not permission_map:
        return is_staff(member)
    allowed_role_ids = permission_map.get(permission, [])
    return any(str(role.id) in allowed_role_ids for role in member.roles)


async def staff_check(ctx, permission=None):
    allowed = member_has_permission(ctx.author, permission) if permission else is_staff(ctx.author)
    if not allowed:
        label = PERMISSION_NAMES.get(permission, "استخدام هذا الأمر") if permission else "استخدام هذا الأمر"
        await ctx.reply(f"ما عندك صلاحية {label}.", mention_author=False)
        return False
    return True


async def owner_check(ctx):
    if not is_owner(ctx.author):
        await ctx.reply("هذا الأمر خاص بمالك السيرفر.", mention_author=False)
        return False
    return True


LOG_KIND_MAP = {
    "messages": "messages",
    "roles": "roles",
    "channels": "channels",
    "nickname": "nickname",
    "server": "server",
    "admin": "admin",
    "moderation": "admin",
    "members": "server",
    "voice": "server",
}

LOG_KIND_ALIASES = {
    "الرسائل": "messages", "رسائل": "messages", "message": "messages",
    "الرولات": "roles", "الرول": "roles", "roles": "roles", "role": "roles",
    "الرومات": "channels", "الروم": "channels", "channels": "channels", "channel": "channels",
    "الأسماء": "nickname", "الاسماء": "nickname", "الأسماء المستعارة": "nickname",
    "الاسم": "nickname", "nick": "nickname", "nickname": "nickname",
    "السيرفر": "server", "server": "server",
    "الاداره": "admin", "الإدارة": "admin", "الادارة": "admin",
    "admin": "admin", "moderation": "admin",
}


def normalize_log_kind(value):
    key = str(value).strip().casefold()
    return LOG_KIND_ALIASES.get(key, LOG_KIND_MAP.get(key, key))


def log_settings(guild):
    settings = data["logs"].setdefault(
        str(guild.id), {"all": None, "types": {}}
    )

    # Migrate old log destinations into the current organized sections.
    old_types = settings.setdefault("types", {})
    migrated = {}
    for old_kind, channel_id in old_types.items():
        new_kind = normalize_log_kind(old_kind)
        if new_kind in LOG_NAMES and channel_id and new_kind not in migrated:
            migrated[new_kind] = channel_id
    settings["types"] = migrated

    return settings


async def send_log(guild, kind, title, description, color=0x5865F2):
    kind = normalize_log_kind(kind)
    settings = log_settings(guild)
    ids = []
    if settings.get("types", {}).get(kind):
        ids.append(int(settings["types"][kind]))

    for cid in dict.fromkeys(ids):
        channel = guild.get_channel(cid)
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title=title[:256],
                description=description[:4000],
                color=color,
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"DeaTh System | {guild.name}")
            try:
                await channel.send(embed=embed)
            except discord.HTTPException:
                log.exception("فشل إرسال اللوق")


async def audit_executor(guild, action, target_id=None):
    await asyncio.sleep(0.8)
    try:
        async for entry in guild.audit_logs(limit=10, action=action):
            age = (discord.utils.utcnow() - entry.created_at).total_seconds()
            if age > 8:
                break
            if target_id is None or getattr(entry.target, "id", None) == target_id:
                return entry.user, entry.reason
    except (discord.Forbidden, discord.HTTPException):
        log.exception("تعذر قراءة Audit Log")
    return None, None


def channel_state(channel):
    gd = data["channel_states"].setdefault(str(channel.guild.id), {})
    return gd.setdefault(str(channel.id), {"closed": False, "hidden": False})


def save_channel_state(channel, closed=None, hidden=None):
    state = channel_state(channel)
    if closed is not None:
        state["closed"] = closed
    if hidden is not None:
        state["hidden"] = hidden
    save_data()


async def apply_channel_state(channel):
    state = channel_state(channel)
    ow = channel.overwrites_for(channel.guild.default_role)

    if state["hidden"]:
        ow.view_channel = False
    elif ow.view_channel is False:
        ow.view_channel = None

    if isinstance(channel, discord.TextChannel):
        ow.send_messages = False if state["closed"] else None
    elif isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        ow.connect = False if state["closed"] else None

    await channel.set_permissions(
        channel.guild.default_role,
        overwrite=ow,
        reason="DeaTh channel controls"
    )


async def hierarchy_check(ctx, member):
    if member.id in (ctx.author.id, ctx.guild.owner_id):
        await ctx.reply("ما تقدر تنفذ الأمر على هذا العضو.", mention_author=False)
        return False

    if not is_owner(ctx.author) and not actor_above(ctx.author, member):
        await ctx.reply("لازم تكون رتبتك أعلى من رتبة العضو المستهدف.", mention_author=False)
        return False

    if not ctx.guild.me or member.top_role >= ctx.guild.me.top_role:
        await ctx.reply("رتبة البوت لازم تكون أعلى من رتبة العضو المستهدف.", mention_author=False)
        return False

    return True


# ---------- Role search ----------

def role_search_key(value):
    value = normalize_text(str(value).strip())
    return "".join(char for char in value if char.isalnum())


def find_role_matches(guild, query):
    query = str(query).strip()
    if not query:
        return []

    mention = re.fullmatch(r"<@&(\d+)>|(\d+)", query)
    if mention:
        role = guild.get_role(int(mention.group(1) or mention.group(2)))
        return [role] if role else []

    wanted = role_search_key(query)
    if not wanted:
        return []

    roles = [role for role in guild.roles if not role.is_default()]

    exact = [
        role for role in roles
        if role_search_key(role.name) == wanted
    ]
    if exact:
        return exact

    return [
        role for role in roles
        if role_search_key(role.name).startswith(wanted)
    ]


def find_role(guild, query):
    matches = find_role_matches(guild, query)
    return matches[0] if len(matches) == 1 else None


def role_check(ctx, role):
    if role is None:
        return False, "هذا الرول غير موجود."
    if role.is_default() or role.managed:
        return False, "ما تقدر تعدل هذا الرول."
    if not ctx.guild.me.guild_permissions.manage_roles:
        return False, "البوت يحتاج Manage Roles."
    if role >= ctx.guild.me.top_role:
        return False, "لازم رتبة البوت تكون أعلى من الرول."
    if not is_owner(ctx.author) and role >= ctx.author.top_role:
        return False, "لازم رتبتك تكون أعلى من الرول."
    return True, None


async def get_members(guild):
    try:
        await guild.chunk(cache=True)
    except (discord.Forbidden, discord.HTTPException):
        pass
    return list(guild.members)


async def configure_prison_access(guild):
    role_id = data.get("prison_roles", {}).get(str(guild.id))
    channel_id = data.get("prison_channels", {}).get(str(guild.id))
    role = guild.get_role(int(role_id)) if role_id else None
    prison_channel = guild.get_channel(int(channel_id)) if channel_id else None
    if role is None or not isinstance(prison_channel, discord.TextChannel):
        return False

    for channel in guild.channels:
        try:
            ow = channel.overwrites_for(role)
            ow.view_channel = False
            ow.send_messages = False
            ow.read_message_history = False
            ow.add_reactions = False
            ow.attach_files = False
            ow.embed_links = False
            ow.send_messages_in_threads = False
            ow.create_public_threads = False
            ow.create_private_threads = False
            ow.use_external_emojis = False
            ow.use_external_stickers = False
            ow.mention_everyone = False
            ow.send_tts_messages = False
            ow.manage_messages = False
            ow.manage_threads = False
            ow.manage_channels = False
            ow.manage_webhooks = False
            ow.connect = False
            ow.speak = False
            if channel.id == prison_channel.id:
                ow.view_channel = True
                ow.send_messages = True
                ow.read_message_history = True
            await channel.set_permissions(role, overwrite=ow, reason="Configure prison access")
        except discord.HTTPException:
            log.exception("تعذر ضبط صلاحيات روم السجن: %s", channel.id)
    return True


# ---------- Protected words ----------

ARABIC_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي",
    "ؤ": "و", "ئ": "ي", "ة": "ه", "ـ": "", "۰": "0", "۱": "1",
    "۲": "2", "۳": "3", "٤": "4", "٥": "5", "٦": "6", "٧": "7",
    "٨": "8", "٩": "9"
})

LOOKALIKE_MAP = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "і": "i", "ј": "j", "Α": "a", "Β": "b", "Ε": "e",
    "Ι": "i", "Κ": "k", "Μ": "m", "Ν": "n", "Ο": "o", "Ρ": "p",
    "Τ": "t", "Χ": "x"
})


def normalize_text(value):
    value = unicodedata.normalize("NFKC", value).translate(ARABIC_MAP).translate(LOOKALIKE_MAP).casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r"(.)\1{2,}", r"\1\1", value)
    return value


def compact_text(value):
    value = normalize_text(value)
    value = "".join(c for c in value if c.isalnum())
    return re.sub(r"(.)\1+", r"\1", value)


def contains_protected_word(content, words):
    normalized = normalize_text(content)
    compact = compact_text(content)

    for word in words:
        nw = normalize_text(str(word))
        cw = compact_text(str(word))

        if not nw or not cw:
            continue

        pattern = r"(?<![a-z0-9\u0600-\u06ff])" + re.escape(nw) + r"(?![a-z0-9\u0600-\u06ff])"

        if re.search(pattern, normalized) or cw in compact:
            return str(word)

    return None


async def filter_message(message):
    if not message.guild or message.author.bot or is_staff(message.author):
        return False

    words = data["protected_words"].get(str(message.guild.id), [])
    matched = contains_protected_word(message.content or "", words)

    if not matched:
        return False

    try:
        await message.delete()
        await message.channel.send(
            f"{message.author.mention} هذه الكلمة غير مسموح بها هنا.",
            delete_after=5,
            allowed_mentions=discord.AllowedMentions(users=True)
        )
    except discord.HTTPException:
        log.exception("تعذر حذف رسالة مخالفة")

    return True


# ---------- Message logging cache ----------

MESSAGE_CACHE_LIMIT = 10000
message_cache = {}


def message_snapshot(message):
    attachments = [
        {
            "filename": attachment.filename,
            "url": attachment.url
        }
        for attachment in message.attachments
    ]

    return {
        "guild_id": message.guild.id if message.guild else None,
        "channel_id": message.channel.id,
        "channel_name": getattr(message.channel, "name", "غير معروف"),
        "author_id": message.author.id,
        "author_name": str(message.author),
        "author_mention": message.author.mention,
        "message_id": message.id,
        "content": message.content or "",
        "attachments": attachments
    }


def cache_message(message):
    if not message.guild or message.author.bot:
        return

    message_cache[message.id] = message_snapshot(message)

    if len(message_cache) > MESSAGE_CACHE_LIMIT:
        oldest_keys = list(message_cache.keys())[:1000]
        for key in oldest_keys:
            message_cache.pop(key, None)


def message_snapshot_text(snapshot):
    if not snapshot:
        return "محتوى الرسالة غير متاح؛ ربما لم تكن محفوظة في ذاكرة البوت."

    content = snapshot.get("content") or "لا يوجد نص"
    attachments = snapshot.get("attachments", [])

    lines = [
        f"العضو: {snapshot.get('author_mention', snapshot.get('author_name', 'غير معروف'))}",
        f"الروم: <#{snapshot.get('channel_id')}>",
        f"محتوى الرسالة:\n{content[:2200]}"
    ]

    if attachments:
        lines.append("المرفقات:")
        for attachment in attachments[:5]:
            lines.append(f"{attachment.get('filename', 'ملف')}: {attachment.get('url', '')}")

    lines.append(f"معرّف الرسالة: `{snapshot.get('message_id', 'غير معروف')}`")
    return "\n".join(lines)


# ---------- Persistent tickets ----------

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="إغلاق التذكرة", style=discord.ButtonStyle.danger, custom_id="zeth_ticket_close")
    async def close_ticket(self, interaction, button):
        ch = interaction.channel

        if not isinstance(ch, discord.TextChannel) or not ch.topic or not ch.topic.startswith("zeth_ticket_owner:"):
            return await interaction.response.send_message("هذه ليست قناة تذكرة.", ephemeral=True)

        owner_id = int(ch.topic.split(":", 1)[1])

        if interaction.user.id != owner_id and not is_staff(interaction.user):
            return await interaction.response.send_message("الإغلاق لصاحب التذكرة أو الإدارة فقط.", ephemeral=True)

        await interaction.response.send_message("سيتم حذف التذكرة بعد 5 ثوانٍ.")
        await asyncio.sleep(5)

        try:
            await ch.delete(reason=f"Ticket closed by {interaction.user}")
        except discord.HTTPException:
            pass


class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="فتح تذكرة", style=discord.ButtonStyle.primary, custom_id="zeth_ticket_open")
    async def open_ticket(self, interaction, button):
        guild, member = interaction.guild, interaction.user

        if guild is None or not isinstance(member, discord.Member):
            return await interaction.response.send_message("استخدم الزر داخل السيرفر.", ephemeral=True)

        for ch in guild.text_channels:
            if ch.topic == f"zeth_ticket_owner:{member.id}":
                return await interaction.response.send_message(f"عندك تذكرة مفتوحة: {ch.mention}", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        category = discord.utils.get(guild.categories, name=TICKET_CATEGORY_NAME)
        if category is None:
            category = await guild.create_category(TICKET_CATEGORY_NAME)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True
            )
        }

        for rid in data["staff_roles"].get(str(guild.id), []):
            role = guild.get_role(int(rid))
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )

        safe = re.sub(r"[^a-z0-9-]", "-", member.name.lower()).strip("-") or "member"

        try:
            ticket = await guild.create_text_channel(
                f"ticket-{safe[:70]}",
                category=category,
                topic=f"zeth_ticket_owner:{member.id}",
                overwrites=overwrites,
                reason=f"Ticket by {member}"
            )

            embed = discord.Embed(
                title="الدعم الفني",
                description=f"أهلًا {member.mention}.\nاكتب طلبك هنا وسيساعدك فريق الإدارة.",
                color=0x5865F2
            )

            await ticket.send(embed=embed, view=TicketCloseView())
            await interaction.followup.send(f"تم إنشاء تذكرتك: {ticket.mention}", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("ما أقدر أنشئ التذكرة. تأكد من صلاحياتي.", ephemeral=True)


# ---------- Owner panel ----------

class OwnerMemberModal(discord.ui.Modal, title="البحث عن عضو"):
    member_id = discord.ui.TextInput(
        label="منشن العضو أو ID",
        placeholder="@member أو 123456789",
        max_length=40
    )

    def __init__(self, guild_id):
        super().__init__()
        self.guild_id = guild_id

    async def on_submit(self, interaction):
        guild = bot.get_guild(self.guild_id)

        if guild is None or interaction.user.id != guild.owner_id:
            return await interaction.response.send_message("غير مصرح لك.", ephemeral=True)

        match = re.fullmatch(r"<@!?(\d+)>|(\d+)", str(self.member_id).strip())

        if not match:
            return await interaction.response.send_message("اكتب منشن عضو أو ID صحيح.", ephemeral=True)

        uid = int(match.group(1) or match.group(2))
        member = guild.get_member(uid)

        if member is None:
            try:
                member = await guild.fetch_member(uid)
            except discord.HTTPException:
                return await interaction.response.send_message("العضو غير موجود.", ephemeral=True)

        await interaction.response.send_message(
            embed=member_embed(member),
            view=MemberControlView(guild.id, member.id),
            ephemeral=True
        )


def member_embed(member):
    roles = [r.mention for r in reversed(member.roles) if not r.is_default()]

    e = discord.Embed(title="ملف العضو", color=0x5865F2)
    e.add_field(name="العضو", value=f"{member.mention}\n`{member}`", inline=True)
    e.add_field(name="ID", value=f"`{member.id}`", inline=True)
    e.add_field(
        name="انضم",
        value=discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "غير معروف",
        inline=True
    )
    e.add_field(name="الرولات", value="، ".join(roles)[:1000] or "لا يوجد", inline=False)
    return e


class MemberRoleModal(discord.ui.Modal, title="إعطاء أو سحب رتبة"):
    role_id = discord.ui.TextInput(label="منشن الرول أو ID أو اسمه", max_length=100)

    def __init__(self, guild_id, member_id):
        super().__init__()
        self.guild_id, self.member_id = guild_id, member_id

    async def on_submit(self, interaction):
        guild = bot.get_guild(self.guild_id)

        if guild is None or interaction.user.id != guild.owner_id:
            return await interaction.response.send_message("غير مصرح لك.", ephemeral=True)

        member = guild.get_member(self.member_id)
        matches = find_role_matches(guild, str(self.role_id))

        if member is None:
            return await interaction.response.send_message("العضو غير موجود.", ephemeral=True)

        if not matches:
            return await interaction.response.send_message("هذا الرول غير موجود.", ephemeral=True)

        if len(matches) > 1:
            names = "\n".join(f"- {role.name}" for role in matches[:10])
            return await interaction.response.send_message(
                f"الاسم يطابق أكثر من رول. اكتب الاسم بشكل أوضح:\n{names}",
                ephemeral=True
            )

        role = matches[0]

        if role.is_default() or role.managed or not bot_can_manage_role(guild, role):
            return await interaction.response.send_message(
                "البوت لا يستطيع تعديل هذا الرول؛ تحقق من الترتيب والصلاحيات.",
                ephemeral=True
            )

        try:
            if role in member.roles:
                await member.remove_roles(role, reason=f"Owner panel by {interaction.user}")
                msg = "تم سحب الرتبة."
            else:
                await member.add_roles(role, reason=f"Owner panel by {interaction.user}")
                msg = "تم إعطاء الرتبة."

            await interaction.response.send_message(msg, ephemeral=True)

            await send_log(
                guild,
                "roles",
                "تعديل رتبة من لوحة الأونر",
                f"المنفذ: {interaction.user.mention}\nالعضو: {member.mention}\nالرول: {role.mention}"
            )

        except discord.HTTPException:
            await interaction.response.send_message("تعذر تعديل الرتبة.", ephemeral=True)


class ConfirmActionView(discord.ui.View):
    def __init__(self, owner_id, guild_id, member_id, action):
        super().__init__(timeout=45)
        self.owner_id, self.guild_id, self.member_id, self.action = owner_id, guild_id, member_id, action

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("هذه اللوحة خاصة بمالك السيرفر.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="تأكيد", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        guild = bot.get_guild(self.guild_id)
        member = guild.get_member(self.member_id) if guild else None

        if guild is None or member is None:
            return await interaction.response.edit_message(
                content="العضو أو السيرفر غير متاح.",
                embed=None,
                view=None
            )

        if member.id == guild.owner_id or not guild.me or member.top_role >= guild.me.top_role:
            return await interaction.response.edit_message(
                content="لا يمكن للبوت تنفيذ الإجراء بسبب ترتيب الرتب.",
                embed=None,
                view=None
            )

        try:
            if self.action == "kick":
                await member.kick(reason=f"Owner panel by {interaction.user}")
                text = "تم طرد العضو."
            else:
                await member.ban(reason=f"Owner panel by {interaction.user}")
                text = "تم حظر العضو."

            await interaction.response.edit_message(content=text, embed=None, view=None)

            await send_log(
                guild,
                "moderation",
                text,
                f"المنفذ: {interaction.user.mention}\nالعضو: `{member}`"
            )

        except discord.HTTPException:
            await interaction.response.edit_message(
                content="تعذر تنفيذ الإجراء.",
                embed=None,
                view=None
            )

    @discord.ui.button(label="إلغاء", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        await interaction.response.edit_message(content="تم إلغاء الإجراء.", embed=None, view=None)


class MemberControlView(discord.ui.View):
    def __init__(self, guild_id, member_id):
        super().__init__(timeout=300)
        self.guild_id, self.member_id = guild_id, member_id

    async def get_target(self, interaction):
        guild = bot.get_guild(self.guild_id)

        if guild is None or interaction.user.id != guild.owner_id:
            await interaction.response.send_message("هذه اللوحة خاصة بمالك السيرفر.", ephemeral=True)
            return None, None

        member = guild.get_member(self.member_id)

        if member is None:
            await interaction.response.send_message("العضو لم يعد موجودًا في السيرفر.", ephemeral=True)
            return None, None

        return guild, member

    @discord.ui.button(label="تحديث المعلومات", style=discord.ButtonStyle.secondary, row=0)
    async def refresh(self, interaction, button):
        guild, member = await self.get_target(interaction)
        if member:
            await interaction.response.edit_message(embed=member_embed(member), view=self)

    @discord.ui.button(label="إعطاء / سحب رول", style=discord.ButtonStyle.primary, row=0)
    async def role(self, interaction, button):
        guild, member = await self.get_target(interaction)
        if member:
            await interaction.response.send_modal(MemberRoleModal(guild.id, member.id))

    @discord.ui.button(label="طرد", style=discord.ButtonStyle.danger, row=1)
    async def kick(self, interaction, button):
        guild, member = await self.get_target(interaction)
        if member:
            await interaction.response.send_message(
                "تأكيد طرد هذا العضو؟",
                view=ConfirmActionView(guild.owner_id, guild.id, member.id, "kick"),
                ephemeral=True
            )

    @discord.ui.button(label="باند", style=discord.ButtonStyle.danger, row=1)
    async def ban(self, interaction, button):
        guild, member = await self.get_target(interaction)
        if member:
            await interaction.response.send_message(
                "تأكيد حظر هذا العضو؟",
                view=ConfirmActionView(guild.owner_id, guild.id, member.id, "ban"),
                ephemeral=True
            )

    @discord.ui.button(label="Timeout 10 دقائق", style=discord.ButtonStyle.secondary, row=2)
    async def apply_timeout(self, interaction, button):
        guild, member = await self.get_target(interaction)

        if not member:
            return

        if member.id == guild.owner_id or not guild.me or member.top_role >= guild.me.top_role:
            return await interaction.response.send_message(
                "لا يمكن تطبيق Timeout بسبب ترتيب الرتب.",
                ephemeral=True
            )

        try:
            await member.timeout(
                discord.utils.utcnow() + timedelta(minutes=10),
                reason=f"Owner panel by {interaction.user}"
            )
            await interaction.response.send_message("تم تطبيق Timeout لمدة 10 دقائق.", ephemeral=True)

        except discord.HTTPException:
            await interaction.response.send_message("تعذر تطبيق Timeout.", ephemeral=True)


class OwnerPanelView(discord.ui.View):
    def __init__(self, owner_id, guild_id):
        super().__init__(timeout=600)
        self.owner_id, self.guild_id = owner_id, guild_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("هذه اللوحة ليست لك.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="الأعضاء", style=discord.ButtonStyle.primary, row=0)
    async def members(self, interaction, button):
        await interaction.response.send_modal(OwnerMemberModal(self.guild_id))

    @discord.ui.button(label="الرولات", style=discord.ButtonStyle.primary, row=0)
    async def roles(self, interaction, button):
        guild = bot.get_guild(self.guild_id)

        if guild is None:
            return await interaction.response.send_message("السيرفر غير متاح.", ephemeral=True)

        roles = [r for r in reversed(guild.roles) if not r.is_default()]
        desc = "\n".join(f"{r.mention} — `{r.id}`" for r in roles[:35]) or "لا توجد رولات."

        await interaction.response.send_message(
            embed=discord.Embed(title="رولات السيرفر", description=desc, color=0x5865F2),
            ephemeral=True
        )

    @discord.ui.button(label="الرومات", style=discord.ButtonStyle.secondary, row=0)
    async def channels(self, interaction, button):
        guild = bot.get_guild(self.guild_id)

        if guild is None:
            return await interaction.response.send_message("السيرفر غير متاح.", ephemeral=True)

        embed = discord.Embed(
            title="إحصائيات الرومات",
            description=f"كتابية: `{len(guild.text_channels)}`\nصوتية: `{len(guild.voice_channels)}`",
            color=0x5865F2
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="اللوق", style=discord.ButtonStyle.secondary, row=1)
    async def logs(self, interaction, button):
        guild = bot.get_guild(self.guild_id)

        if guild is None:
            return await interaction.response.send_message("السيرفر غير متاح.", ephemeral=True)

        settings = log_settings(guild)
        lines = []
        for key, label in LOG_NAMES.items():
            cid = settings.get("types", {}).get(key)
            target = guild.get_channel(int(cid)) if cid else None
            lines.append(f"{label}: {target.mention if target else 'غير محدد'}")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @discord.ui.button(label="تحديث اللوحة", style=discord.ButtonStyle.success, row=1)
    async def update(self, interaction, button):
        guild = bot.get_guild(self.guild_id)

        if guild is None:
            return await interaction.response.send_message("السيرفر غير متاح.", ephemeral=True)

        await interaction.response.edit_message(embed=owner_panel_embed(guild), view=self)


def owner_panel_embed(guild):
    e = discord.Embed(
        title="ZeTh Control Center",
        description="لوحة التحكم الخاصة بمالك السيرفر.\nاختر القسم المطلوب من الأزرار.",
        color=0x5865F2
    )
    e.add_field(name="السيرفر", value=guild.name, inline=True)
    e.add_field(name="الأعضاء", value=str(guild.member_count or len(guild.members)), inline=True)
    e.add_field(name="الرومات", value=str(len(guild.channels)), inline=True)
    e.set_footer(text="Owner Only • ZeTh System")
    return e


# ---------- Bot lifecycle ----------

class ZeThBot(commands.Bot):
    async def setup_hook(self):
        load_data()
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())

        try:
            synced = await self.tree.sync()
            log.info("تمت مزامنة %s أمرًا", len(synced))
        except discord.HTTPException:
            log.exception("فشلت مزامنة أوامر Slash")


bot = ZeThBot(
    command_prefix=PREFIX,
    intents=intents,
    help_command=None,
    case_insensitive=True
)



# ---------- Events ----------

async def schedule_voice_unmute(guild_id, member_id, expires_at):
    key = f"{guild_id}:{member_id}"
    tasks = getattr(bot, "_voice_mute_tasks", {})
    old = tasks.get(key)

    if old and not old.done():
        old.cancel()

    async def runner():
        delay = max(0, float(expires_at) - discord.utils.utcnow().timestamp())
        await asyncio.sleep(delay)

        guild = bot.get_guild(guild_id)
        member = guild.get_member(member_id) if guild else None

        try:
            if member and member.voice and member.voice.mute:
                await member.edit(mute=False, reason="انتهاء مدة الميوت التلقائي")
                await send_log(guild, "moderation", "انتهاء ميوت تلقائي", f"العضو: {member.mention}")

        except discord.HTTPException:
            log.exception("فشل فك الميوت التلقائي")

        finally:
            data["voice_mutes"].pop(key, None)
            save_data()

            if tasks.get(key) is asyncio.current_task():
                tasks.pop(key, None)

    bot._voice_mute_tasks = tasks
    tasks[key] = asyncio.create_task(runner())


@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id)

    status_name = data.get("bot_status", {}).get("value", "online")
    status_value = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible,
    }.get(status_name, discord.Status.online)
    await bot.change_presence(status=status_value)

    for key, expires_at in list(data["voice_mutes"].items()):
        try:
            guild_id, member_id = map(int, key.split(":", 1))
            await schedule_voice_unmute(guild_id, member_id, float(expires_at))
        except (ValueError, TypeError):
            data["voice_mutes"].pop(key, None)

    for key, expires_at in list(data.get("chat_mutes", {}).items()):
        try:
            guild_id, member_id = map(int, key.split(":", 1))
            await schedule_chat_unmute(guild_id, member_id, float(expires_at))
        except (ValueError, TypeError):
            data["chat_mutes"].pop(key, None)

    save_data()


@bot.event
async def on_member_join(member):
    if member.bot:
        return

    key = str(member.guild.id)
    cid = data["welcome_channels"].get(key)
    msg = data["welcome_texts"].get(key, "حياك الله نورت السيرفر")

    if cid:
        ch = member.guild.get_channel(int(cid))
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(
                    f"{msg[:1800]}\n{member.mention}",
                    allowed_mentions=discord.AllowedMentions(users=True)
                )
            except discord.HTTPException:
                pass

    role = discord.utils.get(member.guild.roles, name=MEMBER_ROLE_NAME)

    if role is None:
        try:
            role = await member.guild.create_role(
                name=MEMBER_ROLE_NAME,
                reason="Default ZeTh member role"
            )
        except discord.HTTPException:
            role = None

    if role and role not in member.roles and bot_can_manage_role(member.guild, role):
        try:
            await member.add_roles(role, reason="Automatic member role")
        except discord.HTTPException:
            pass

    await send_log(
        member.guild,
        "members",
        "دخول عضو",
        f"العضو: {member.mention}\nID: `{member.id}`",
        0x2ECC71
    )


@bot.event
async def on_member_remove(member):
    await send_log(
        member.guild,
        "members",
        "خروج عضو",
        f"العضو: `{member}`\nID: `{member.id}`",
        0xE67E22
    )


# تسجيل حذف الرسائل حتى لو لم تكن موجودة في كاش Discord
@bot.event
async def on_raw_message_delete(payload):
    if payload.guild_id is None:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    snapshot = message_cache.pop(payload.message_id, None)

    if snapshot is None and payload.cached_message is not None:
        snapshot = message_snapshot(payload.cached_message)

    if snapshot is None:
        channel = guild.get_channel(payload.channel_id)
        channel_name = channel.mention if channel else f"`{payload.channel_id}`"

        description = (
            f"الروم: {channel_name}\n"
            f"محتوى الرسالة غير متاح؛ لم تكن الرسالة محفوظة في ذاكرة البوت.\n"
            f"معرّف الرسالة: `{payload.message_id}`"
        )
    else:
        description = message_snapshot_text(snapshot)

    await send_log(
        guild,
        "messages",
        "حذف رسالة",
        description,
        0xE74C3C
    )


# تسجيل تعديل الرسائل مع المحتوى السابق والجديد
@bot.event
async def on_raw_message_edit(payload):
    if payload.guild_id is None:
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    before_snapshot = message_cache.get(payload.message_id)

    if before_snapshot is None and payload.cached_message is not None:
        before_snapshot = message_snapshot(payload.cached_message)

    channel = guild.get_channel(payload.channel_id)

    if channel is None:
        return

    try:
        after = await channel.fetch_message(payload.message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return

    if after.author.bot:
        return

    after_snapshot = message_snapshot(after)
    cache_message(after)

    before_content = before_snapshot.get("content", "") if before_snapshot else None
    after_content = after_snapshot.get("content", "")

    if before_content == after_content:
        return

    if await filter_message(after):
        return

    before_text = before_content if before_content else "فارغ أو غير متاح"
    after_text = after_content if after_content else "فارغ"

    description = (
        f"العضو: {after.author.mention}\n"
        f"الروم: {after.channel.mention}\n"
        f"قبل التعديل:\n{before_text[:1500]}\n\n"
        f"بعد التعديل:\n{after_text[:1500]}\n"
        f"معرّف الرسالة: `{after.id}`"
    )

    await send_log(
        guild,
        "messages",
        "تعديل رسالة",
        description,
        0xF1C40F
    )


@bot.event
async def on_member_update(before, after):
    if before.nick != after.nick:
        await send_log(
            after.guild,
            "nickname",
            "تغيير اسم عضو",
            f"العضو: {after.mention}\nقبل: {before.nick or before.name}\nبعد: {after.nick or after.name}"
        )

    added = [r for r in after.roles if r not in before.roles and not r.is_default()]
    removed = [r for r in before.roles if r not in after.roles and not r.is_default()]

    if added or removed:
        executor, reason = await audit_executor(
            after.guild,
            discord.AuditLogAction.member_role_update,
            after.id
        )

        for role in added:
            await send_log(
                after.guild,
                "roles",
                "إعطاء رتبة",
                f"من: {executor.mention if executor else 'غير معروف'}\n"
                f"إلى: {after.mention}\n"
                f"الرول: {role.mention}\n"
                f"السبب: {reason or 'غير محدد'}"
            )

        for role in removed:
            await send_log(
                after.guild,
                "roles",
                "سحب رتبة",
                f"العضو: {after.mention}\n"
                f"الرتبة المسحوبة: {role.mention}\n"
                f"بواسطة: {executor.mention if executor else 'غير معروف'}\n"
                f"السبب: {reason or 'غير محدد'}"
            )



@bot.event
async def on_guild_role_create(role):
    user, reason = await audit_executor(role.guild, discord.AuditLogAction.role_create, role.id)

    await send_log(
        role.guild,
        "roles",
        "إنشاء رتبة",
        f"{role.mention}\nبواسطة: {user.mention if user else 'غير معروف'}\nالسبب: {reason or 'غير محدد'}"
    )


@bot.event
async def on_guild_role_delete(role):
    user, reason = await audit_executor(role.guild, discord.AuditLogAction.role_delete, role.id)

    await send_log(
        role.guild,
        "roles",
        "حذف رتبة",
        f"{role.name}\nبواسطة: {user.mention if user else 'غير معروف'}\nالسبب: {reason or 'غير محدد'}"
    )


@bot.event
async def on_guild_role_update(before, after):
    changes = []

    if before.name != after.name:
        changes.append(f"الاسم: {before.name} ← {after.name}")

    if before.color != after.color:
        changes.append(f"اللون: {before.color} ← {after.color}")

    if changes:
        await send_log(after.guild, "roles", "تعديل رتبة", f"{after.mention}\n" + "\n".join(changes))


@bot.event
async def on_guild_channel_create(channel):
    user, reason = await audit_executor(
        channel.guild,
        discord.AuditLogAction.channel_create,
        channel.id
    )

    await send_log(
        channel.guild,
        "channels",
        "إنشاء روم",
        f"{channel.mention}\nبواسطة: {user.mention if user else 'غير معروف'}\nالسبب: {reason or 'غير محدد'}"
    )


@bot.event
async def on_guild_channel_delete(channel):
    user, reason = await audit_executor(
        channel.guild,
        discord.AuditLogAction.channel_delete,
        channel.id
    )

    await send_log(
        channel.guild,
        "channels",
        "حذف روم",
        f"{channel.name}\nبواسطة: {user.mention if user else 'غير معروف'}\nالسبب: {reason or 'غير محدد'}"
    )


@bot.event
async def on_guild_channel_update(before, after):
    changes = []

    if before.name != after.name:
        changes.append(f"الاسم: {before.name} ← {after.name}")

    if getattr(before, "topic", None) != getattr(after, "topic", None):
        changes.append("تم تعديل وصف الروم.")

    if changes:
        await send_log(after.guild, "channels", "تعديل روم", f"{after.mention}\n" + "\n".join(changes))



@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel != after.channel:
        old = before.channel.mention if before.channel else "خارج الفويس"
        new = after.channel.mention if after.channel else "خارج الفويس"

        await send_log(
            member.guild,
            "voice",
            "تغيير قناة صوتية",
            f"{member.mention}\nمن: {old}\nإلى: {new}"
        )

    if before.mute != after.mute:
        await send_log(
            member.guild,
            "voice",
            "تغيير Mute صوتي",
            f"العضو: {member.mention}\nالحالة: {'مكتوم' if after.mute else 'مفتوح'}"
        )


@bot.event
async def on_guild_update(before, after):
    changes = []

    if before.name != after.name:
        changes.append(f"الاسم: {before.name} ← {after.name}")

    if before.icon != after.icon:
        changes.append("تم تغيير صورة السيرفر.")

    if changes:
        await send_log(after, "server", "تعديل السيرفر", "\n".join(changes))



@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    muted_role_id = data.get("muted_roles", {}).get(str(message.guild.id))
    if muted_role_id and any(str(role.id) == str(muted_role_id) for role in message.author.roles):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        return

    # حفظ الرسالة وتسجيلها قبل تطبيق الفلاتر أو حذفها
    cache_message(message)

    await send_log(
        message.guild,
        "messages",
        "رسالة جديدة",
        message_snapshot_text(message_snapshot(message)),
        0x3498DB
    )

    locket_id = data["locket_channels"].get(str(message.guild.id))

    if locket_id and message.channel.id == int(locket_id) and not is_staff(message.author):
        image_role_id = data.get("image_roles", {}).get(str(message.guild.id))
        has_image_role = bool(image_role_id and any(str(r.id) == str(image_role_id) for r in message.author.roles))
        has_image = any(
            (attachment.content_type or "").startswith("image/")
            or attachment.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))
            for attachment in message.attachments
        )

        if not has_image_role or not has_image:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention} هذا الروم مخصص للصور ولأصحاب رتبة الصور فقط.",
                    delete_after=5,
                    allowed_mentions=discord.AllowedMentions(users=True)
                )
            except discord.HTTPException:
                log.exception("تعذر تطبيق إعداد روم الصور")

            return

    if await filter_message(message):
        return

    if is_owner(message.author):
        content = message.content.strip()
        first = content.split(maxsplit=1)[0].lower() if content else ""

        if first and not content.startswith(PREFIX) and first in bot.all_commands:
            message.content = PREFIX + content

    await bot.process_commands(message)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, (commands.CommandNotFound, commands.CheckFailure)):
        return

    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(f"ناقصك إدخال: `{error.param.name}`", mention_author=False)

    elif isinstance(error, commands.BadArgument):
        await ctx.reply("المدخل غير صحيح، تأكد من منشن العضو أو الرول.", mention_author=False)

    elif isinstance(error, commands.MissingPermissions):
        await ctx.reply("ما عندك الصلاحية المطلوبة.", mention_author=False)

    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.reply("البوت يحتاج صلاحية إضافية.", mention_author=False)

    else:
        log.exception("خطأ أمر", exc_info=error)
        await ctx.reply("صار خطأ أثناء تنفيذ الأمر.", mention_author=False)


# ---------- Help ----------

class HelpSelect(discord.ui.Select):
    def __init__(self):
        opts = [
            discord.SelectOption(label="الأساسية", value="main"),
            discord.SelectOption(label="الإعدادات", value="settings"),
            discord.SelectOption(label="الحماية", value="security")
        ]

        super().__init__(
            placeholder="اختر قسم الأوامر",
            min_values=1,
            max_values=1,
            options=opts
        )

    async def callback(self, interaction):
        pages = {
            "main": (
                "الأوامر الأساسية",
                "**الرومات**\n"
                "`!close` أو `!قفل` قفل الكتابة\n"
                "`!open` فتح الروم\n"
                "`!hide` إخفاء الروم\n"
                "`!unhide` أو `!show` إظهار الروم\n"
                "`!lockvc` و`!unlockvc` قفل/فتح فويس\n"
                "`!lockallvc` و`!unlockallvc` قفل/فتح كل الفويسات\n"
                "`!kickvoice تأكيد` إخراج جميع الأعضاء من الفويس\n"
                "`!addroom <اسم>` إنشاء روم كتابي\n"
                "`!addroom voice <اسم>` إنشاء روم صوتي\n"
                "`!delroom #روم` حذف روم\n"
                "`!lockserver تأكيد` و`!openserver` قفل/فتح الرومات الكتابية والصوتية\n"
                "`!roleallremove @رول تأكيد` سحب رتبة من الجميع\n"
                "`!slowmode [ثواني]` تحديد بطء الشات\n"
                "`!مسح [عدد]` حذف الرسائل\n\n"
                "**الإدارة**\n"
                "`!برا @عضو` طرد\n"
                "`!تل @عضو` سحب الرولات عدا ZeTh\n"
                "`!تف` أو `!بنعالي` أو `!ban` باند\n"
                "`!mute @عضو [دقائق]` منع الكتابة بالشات واللوكت (بدون مدة = دائم)\n"
                "`!unmute @عضو` فك الميوت\n"
                "`!timeout @عضو [دقائق]` تايم أوت ديسكورد\n"
                "`!untime @عضو` فك التايم أوت\n"
                "`!prison @عضو` سجن\n"
                "`!unprison @عضو` فك السجن\n"
                "`!unban ID` فك الباند\n\n"
                "**الرولات**\n"
                "`!رول @عضو @رول` إعطاء/سحب\n"
                "`!رول @عضو اسم الرول` إعطاء/سحب باستخدام الاسم أو بدايته\n"
                "`!رول @رول_قديم @رول_جديد` توزيع حسب رول\n"
                "`!roleall @رول` إعطاء للجميع"
            ),
            "settings": (
                "الإعدادات",
                "`!set welcome #روم` روم الترحيب\n"
                "`!set welcome text <النص>` نص الترحيب\n"
                "`!set Locket #روم` تحديد روم الصور\n"
                "`!set images role @رول` تحديد رتبة السماح بنشر الصور\n"
                "`!set prison room #روم` تحديد روم السجن الذي يستطيع السجين الكتابة فيه\n"
                "`!set log messages #روم` تحديد روم لوق الرسائل\n"
                "`!set log roles #روم` تحديد روم لوق الرولات\n"
                "`!set log channels #روم` تحديد روم لوق الرومات\n"
                "`!set log nickname #روم` تحديد روم لوق الأسماء\n"
                "`!set log server #روم` تحديد روم لوق السيرفر\n"
                "`!set log admin #روم` تحديد روم لوق الإدارة\n"
                "`!set log reset` إعادة ضبط إعدادات اللوق\n"
                "`!status online` حالة البوت متصل\n"
                "`!status idle` حالة البوت خامل\n"
                "`!status dnd` حالة البوت مشغول\n"
                "`!status invisible` إخفاء حالة البوت\n"
                "`!activity <النص>` تغيير النشاط الظاهر للبوت\n"
                "`!set mute role @رول` تحديد الرول الذي يحصل عليه العضو عند الميوت\n"
                "`!set prison role @رول` رول السجن\n"
                "`!set prison room #روم` روم السجن المسموح للسجين بالكتابة فيه\n"
                "`!logs` عرض إعدادات اللوق\n"
                "`/set ticket room` لوحة التكت\n"
                "`/set staff role` إضافة رتبة إدارة\n"
                "`!setpermission @رول kick` منح صلاحية لرتبة\n"
                "الصلاحيات: kick, mute, ban, clear, add_role, remove_role, channels, server, voice, prison, timeout, nickname, images, words\n"
                "`!removepermission @رول kick` سحب صلاحية من رتبة\n"
                "`!permissions` عرض توزيع الصلاحيات"
            ),
            "security": (
                "الحماية",
                "`!set bad word <كلمة>` إضافة كلمة ممنوعة\n"
                "`!set bad word remove <كلمة>` حذف كلمة\n"
                "`!words` عرض الكلمات الممنوعة\n"
                "فلتر الكلمات يفحص الرسائل وتعديلاتها ويطبّع التشكيل والتطويل والرموز."
            )
        }

        title, desc = pages[self.values[0]]

        await interaction.response.edit_message(
            embed=discord.Embed(
                title=f"ZeTh System | {title}",
                description=desc,
                color=0x5865F2
            ),
            view=self.view
        )


class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(HelpSelect())


@bot.command(name="help", aliases=["مساعدة", "اوامر"])
async def help_command(ctx):
    await ctx.reply(
        embed=discord.Embed(
            title="ZeTh System",
            description="اختر القسم من القائمة لعرض الأوامر.",
            color=0x5865F2
        ),
        view=HelpView(),
        mention_author=False
    )


# ---------- Channel commands ----------

@bot.command(name="close", aliases=["قفل", "lock"])
async def close_channel(ctx):
    if not await staff_check(ctx, "channels"):
        return

    if not isinstance(ctx.channel, discord.TextChannel):
        return

    save_channel_state(ctx.channel, closed=True)

    try:
        await apply_channel_state(ctx.channel)
        await ctx.reply("تم قفل الروم.", mention_author=False)
    except discord.Forbidden:
        await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)


@bot.command(name="open", aliases=["unlock"])
async def open_channel(ctx):
    if not await staff_check(ctx, "channels"):
        return

    if not isinstance(ctx.channel, discord.TextChannel):
        return

    save_channel_state(ctx.channel, closed=False)
    await apply_channel_state(ctx.channel)
    await ctx.reply("تم فتح الروم.", mention_author=False)


@bot.command(name="hide")
async def hide_channel(ctx):
    if not await staff_check(ctx, "channels"):
        return

    if not isinstance(ctx.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
        return

    save_channel_state(ctx.channel, hidden=True)
    await apply_channel_state(ctx.channel)
    await ctx.reply("تم إخفاء الروم.", mention_author=False)


@bot.command(name="unhide", aliases=["show"])
async def unhide_channel(ctx):
    if not await staff_check(ctx, "channels"):
        return

    if not isinstance(ctx.channel, (discord.TextChannel, discord.VoiceChannel, discord.StageChannel)):
        return

    save_channel_state(ctx.channel, hidden=False)
    await apply_channel_state(ctx.channel)
    await ctx.reply("تم إظهار الروم.", mention_author=False)


async def voice_lock(ctx, channel, locked):
    if not await staff_check(ctx, "voice"):
        return

    if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
        return await ctx.reply("حدد رومًا صوتيًا صحيحًا.", mention_author=False)

    ow = channel.overwrites_for(ctx.guild.default_role)
    ow.connect = False if locked else None

    try:
        await channel.set_permissions(
            ctx.guild.default_role,
            overwrite=ow,
            reason=f"Voice control by {ctx.author}"
        )
        await ctx.reply("تم قفل الفويس." if locked else "تم فتح الفويس.", mention_author=False)

    except discord.Forbidden:
        await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)


@bot.command(name="lockvc")
async def lock_vc(ctx, channel: discord.VoiceChannel = None):
    target = channel or (ctx.author.voice.channel if ctx.author.voice else None)
    await voice_lock(ctx, target, True)


@bot.command(name="unlockvc")
async def unlock_vc(ctx, channel: discord.VoiceChannel = None):
    target = channel or (ctx.author.voice.channel if ctx.author.voice else None)
    await voice_lock(ctx, target, False)


async def all_voice(ctx, locked):
    if not await staff_check(ctx, "voice"):
        return

    ok = failed = 0

    for ch in ctx.guild.voice_channels + ctx.guild.stage_channels:
        try:
            ow = ch.overwrites_for(ctx.guild.default_role)
            ow.connect = False if locked else None

            await ch.set_permissions(
                ctx.guild.default_role,
                overwrite=ow,
                reason=f"Bulk voice control by {ctx.author}"
            )
            ok += 1

        except discord.HTTPException:
            failed += 1

    await ctx.reply(
        f"تم {'قفل' if locked else 'فتح'} {ok} روم صوتي.\nفشل: `{failed}`",
        mention_author=False
    )


@bot.command(name="lockallvc")
async def lock_all_vc(ctx):
    await all_voice(ctx, True)


@bot.command(name="unlockallvc")
async def unlock_all_vc(ctx):
    await all_voice(ctx, False)


@bot.command(name="slowmode", aliases=["slow"])
async def slowmode(ctx, seconds: int = 5):
    if not await staff_check(ctx, "channels"):
        return

    if not isinstance(ctx.channel, discord.TextChannel):
        return

    if not 0 <= seconds <= 21600:
        return await ctx.reply("حدد مدة من 0 إلى 21600 ثانية.", mention_author=False)

    try:
        await ctx.channel.edit(
            slowmode_delay=seconds,
            reason=f"Slowmode by {ctx.author}"
        )
        await ctx.reply(f"تم ضبط Slowmode على {seconds} ثانية.", mention_author=False)

    except discord.Forbidden:
        await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)


@bot.command(name="مسح", aliases=["clear", "purge"])
async def clear_messages(ctx, amount: int = 30):
    if not await staff_check(ctx, "clear"):
        return

    if not ctx.author.guild_permissions.manage_messages and not is_owner(ctx.author):
        return await ctx.reply("تحتاج Manage Messages.", mention_author=False)

    if not ctx.guild.me.guild_permissions.manage_messages:
        return await ctx.reply("البوت يحتاج Manage Messages.", mention_author=False)

    if not 1 <= amount <= 100:
        return await ctx.reply("حدد عددًا من 1 إلى 100.", mention_author=False)

    try:
        deleted = await ctx.channel.purge(limit=amount + 1, bulk=True)
        count = len(deleted) - (1 if ctx.message in deleted else 0)

        msg = await ctx.send(f"تم حذف {count} رسالة.")
        await msg.delete(delay=3)

    except discord.HTTPException:
        await ctx.reply("تعذر حذف الرسائل.", mention_author=False)


# ---------- Moderation ----------

async def strip_member_roles(ctx, member):
    if not await staff_check(ctx, "remove_role") or not await hierarchy_check(ctx, member):
        return

    if not ctx.guild.me.guild_permissions.manage_roles:
        return await ctx.reply("البوت يحتاج Manage Roles.", mention_author=False)

    protected = discord.utils.get(ctx.guild.roles, name=MEMBER_ROLE_NAME)

    removable = [
        r for r in member.roles
        if not r.is_default() and r != protected and not r.managed and r < ctx.guild.me.top_role
    ]

    skipped = [
        r.name for r in member.roles
        if not r.is_default() and r != protected and (r.managed or r >= ctx.guild.me.top_role)
    ]

    if not removable:
        return await ctx.reply("ما عند العضو رولات قابلة للسحب.", mention_author=False)

    try:
        await member.remove_roles(*removable, reason=f"Role strip by {ctx.author}")
    except discord.HTTPException:
        return await ctx.reply("تعذر سحب الرولات.", mention_author=False)

    names = ", ".join(r.name for r in removable)

    await ctx.reply(
        f"تم سحب رولات {member.mention}: {names}\nتم استثناء ZeTh."
        + (f"\nتم تخطي: {', '.join(skipped)}" if skipped else ""),
        mention_author=False
    )

    await send_log(
        ctx.guild,
        "moderation",
        "سحب رولات",
        f"المنفذ: {ctx.author.mention}\nالعضو: {member.mention}\nالرولات: {names}"
    )


@bot.command(name="تل")
async def strip_roles(ctx, member: discord.Member):
    await strip_member_roles(ctx, member)


@bot.command(name="برا")
async def kick_or_strip(ctx, *, args=""):
    if args.casefold().startswith("رولاتك"):
        try:
            member = await commands.MemberConverter().convert(
                ctx,
                args[len("رولاتك"):].strip()
            )
        except commands.BadArgument:
            return await ctx.reply("استخدم: `!برا رولاتك @عضو`", mention_author=False)

        return await strip_member_roles(ctx, member)

    parts = args.split(maxsplit=1)

    if not parts:
        return await ctx.reply("استخدم: `!برا @عضو [السبب]`", mention_author=False)

    try:
        member = await commands.MemberConverter().convert(ctx, parts[0])
    except commands.BadArgument:
        return await ctx.reply("العضو غير موجود.", mention_author=False)

    reason = parts[1] if len(parts) > 1 else "بدون سبب"

    if not await staff_check(ctx, "kick"):
        return
    if not await hierarchy_check(ctx, member):
        return

    if not ctx.guild.me.guild_permissions.kick_members:
        return await ctx.reply("البوت يحتاج Kick Members.", mention_author=False)

    try:
        await member.kick(reason=f"{ctx.author}: {reason}")
        await ctx.reply(f"تم طرد {member}.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "طرد عضو",
            f"المنفذ: {ctx.author.mention}\nالعضو: {member}\nالسبب: {reason}"
        )

    except discord.HTTPException:
        await ctx.reply("تعذر طرد العضو.", mention_author=False)


async def do_ban(ctx, member, reason):
    if not await staff_check(ctx, "ban") or not await hierarchy_check(ctx, member):
        return

    if not ctx.guild.me.guild_permissions.ban_members:
        return await ctx.reply("البوت يحتاج Ban Members.", mention_author=False)

    try:
        await member.ban(reason=f"{ctx.author}: {reason}")
        await ctx.reply(f"تم حظر {member}.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "حظر عضو",
            f"المنفذ: {ctx.author.mention}\nالعضو: {member}\nالسبب: {reason}"
        )

    except discord.HTTPException:
        await ctx.reply("تعذر حظر العضو.", mention_author=False)


@bot.command(name="ban", aliases=["تف", "بنعالي"])
async def ban_member(ctx, member: discord.Member, *, reason="بدون سبب"):
    await do_ban(ctx, member, reason)


@bot.command(name="kick", aliases=["طرد"])
async def kick_member(ctx, member: discord.Member, *, reason="بدون سبب"):
    if not await staff_check(ctx, "kick") or not await hierarchy_check(ctx, member):
        return

    if not ctx.guild.me.guild_permissions.kick_members:
        return await ctx.reply("البوت يحتاج Kick Members.", mention_author=False)

    try:
        await member.kick(reason=f"{ctx.author}: {reason}")
        await ctx.reply(f"تم طرد {member}.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "طرد عضو",
            f"المنفذ: {ctx.author.mention}\nالعضو: {member}\nالسبب: {reason}"
        )

    except discord.HTTPException:
        await ctx.reply("تعذر طرد العضو.", mention_author=False)


async def mute_permission(ctx):
    return await staff_check(ctx, "mute")


async def mute_hierarchy_check(ctx, member):
    if member.id in (ctx.author.id, ctx.guild.owner_id):
        await ctx.reply("ما تقدر تنفذ الأمر على هذا العضو.", mention_author=False)
        return False

    if not ctx.guild.me or member.top_role >= ctx.guild.me.top_role:
        await ctx.reply("رتبة البوت لازم تكون أعلى من رتبة العضو.", mention_author=False)
        return False

    return True


async def configure_chat_mute_role(guild, role):
    if not bot_can_manage_role(guild, role):
        raise discord.Forbidden(response=None, message="Muted role is above bot")

    for channel in guild.text_channels:
        try:
            ow = channel.overwrites_for(role)
            ow.send_messages = False
            ow.send_messages_in_threads = False
            ow.create_public_threads = False
            ow.create_private_threads = False
            ow.add_reactions = False
            await channel.set_permissions(role, overwrite=ow, reason="Configure chat mute role")
        except (discord.Forbidden, discord.HTTPException):
            log.warning("تعذر ضبط صلاحيات الميوت في الروم %s", channel.id)


async def get_muted_role(guild):
    rid = data["muted_roles"].get(str(guild.id))
    role = guild.get_role(int(rid)) if rid else None

    if role is None:
        role = discord.utils.get(guild.roles, name="Muted")

    if role is None:
        role = await guild.create_role(name="Muted", reason="Chat mute role")

    await configure_chat_mute_role(guild, role)
    data["muted_roles"][str(guild.id)] = str(role.id)
    save_data()
    return role

async def schedule_chat_unmute(guild_id, member_id, expires_at):
    key = f"{guild_id}:{member_id}"
    tasks = getattr(bot, "_chat_mute_tasks", {})
    old = tasks.get(key)
    if old and not old.done():
        old.cancel()

    async def runner():
        try:
            delay = max(0, float(expires_at) - discord.utils.utcnow().timestamp())
            await asyncio.sleep(delay)
            guild = bot.get_guild(guild_id)
            member = guild.get_member(member_id) if guild else None
            role_id = data["muted_roles"].get(str(guild_id))
            role = guild.get_role(int(role_id)) if guild and role_id else None
            if member and role and role in member.roles:
                await member.remove_roles(role, reason="انتهاء مدة الميوت الكتابي")
                await send_log(guild, "moderation", "انتهاء الميوت الكتابي", f"العضو: {member.mention}")
        except discord.HTTPException:
            log.exception("فشل فك الميوت الكتابي تلقائيًا")
        finally:
            data["chat_mutes"].pop(key, None)
            save_data()
            if tasks.get(key) is asyncio.current_task():
                tasks.pop(key, None)

    bot._chat_mute_tasks = tasks
    tasks[key] = asyncio.create_task(runner())


async def do_chat_mute(ctx, member, minutes, reason, mute):
    if not await mute_permission(ctx):
        return
    if not await mute_hierarchy_check(ctx, member):
        return

    try:
        role = await get_muted_role(ctx.guild)
        key = f"{ctx.guild.id}:{member.id}"
        tasks = getattr(bot, "_chat_mute_tasks", {})

        if mute:
            if role not in member.roles:
                await member.add_roles(role, reason=f"Chat muted by {ctx.author}: {reason}")

            old_task = tasks.pop(key, None)
            if old_task and not old_task.done():
                old_task.cancel()

            if minutes is None:
                data["chat_mutes"].pop(key, None)
                duration_text = "حتى فكّه يدويًا"
            else:
                expires_at = discord.utils.utcnow().timestamp() + minutes * 60
                data["chat_mutes"][key] = expires_at
                await schedule_chat_unmute(ctx.guild.id, member.id, expires_at)
                duration_text = f"لمدة {minutes} دقيقة"

            save_data()
            await ctx.reply(f"تم ميوت {member.mention} كتابيًا {duration_text}.", mention_author=False)
            await send_log(ctx.guild, "moderation", "ميوت كتابي", f"المنفذ: {ctx.author.mention}\nالعضو: {member.mention}\nالمدة: {duration_text}\nالسبب: {reason}")
        else:
            if role in member.roles:
                await member.remove_roles(role, reason=f"Chat unmuted by {ctx.author}")
            data["chat_mutes"].pop(key, None)
            task = tasks.pop(key, None)
            if task and not task.done():
                task.cancel()
            save_data()
            await ctx.reply(f"تم فك الميوت عن {member.mention}.", mention_author=False)
            await send_log(ctx.guild, "moderation", "فك الميوت الكتابي", f"المنفذ: {ctx.author.mention}\nالعضو: {member.mention}")
    except discord.Forbidden:
        await ctx.reply("تأكد أن رتبة البوت أعلى من رتبة الميوت والعضو.", mention_author=False)
    except discord.HTTPException:
        await ctx.reply("تعذر تطبيق الميوت الكتابي.", mention_author=False)


@bot.command(name="mute", aliases=["m", "اص", "ميوت"])
async def mute_member(ctx, member: discord.Member, minutes: int = None, *, reason="بدون سبب"):
    if minutes is not None and not 1 <= minutes <= 40320:
        return await ctx.reply("حدد مدة بين دقيقة و40320 دقيقة.", mention_author=False)
    await do_chat_mute(ctx, member, minutes, reason, True)

@bot.command(name="unmute", aliases=["um", "تكلم"])
async def unmute_member(ctx, member: discord.Member):
    await do_chat_mute(ctx, member, 1, "فك الميوت", False)


@bot.command(name="timeout", aliases=["t", "time", "تايم"])
async def timeout_member(ctx, member: discord.Member, minutes: int = 10, *, reason="بدون سبب"):
    if not await staff_check(ctx, "timeout") or not await hierarchy_check(ctx, member):
        return

    if not 1 <= minutes <= 40320:
        return await ctx.reply("حدد مدة بين دقيقة و40320 دقيقة.", mention_author=False)

    try:
        await member.timeout(
            discord.utils.utcnow() + timedelta(minutes=minutes),
            reason=f"{ctx.author}: {reason}"
        )

        await ctx.reply(
            f"تم تطبيق Timeout على {member.mention} لمدة {minutes} دقيقة.",
            mention_author=False
        )

        await send_log(
            ctx.guild,
            "moderation",
            "Timeout عضو",
            f"المنفذ: {ctx.author.mention}\n"
            f"العضو: {member.mention}\n"
            f"المدة: {minutes} دقيقة\n"
            f"السبب: {reason}"
        )

    except discord.HTTPException:
        await ctx.reply("تعذر تطبيق Timeout.", mention_author=False)


@bot.command(name="untime", aliases=["ut"])
async def untimeout_member(ctx, member: discord.Member):
    if not await staff_check(ctx, "timeout") or not await hierarchy_check(ctx, member):
        return

    try:
        await member.timeout(None, reason=f"Timeout removed by {ctx.author}")
        await ctx.reply(f"تم فك Timeout عن {member.mention}.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "فك Timeout",
            f"المنفذ: {ctx.author.mention}\nالعضو: {member.mention}"
        )

    except discord.HTTPException:
        await ctx.reply("تعذر فك Timeout.", mention_author=False)


@bot.command(name="prison", aliases=["سجن"])
async def prison_member(ctx, member: discord.Member, *, reason="بدون سبب"):
    if not await staff_check(ctx, "prison") or not await hierarchy_check(ctx, member):
        return

    rid = data["prison_roles"].get(str(ctx.guild.id))
    role = ctx.guild.get_role(int(rid)) if rid else None

    if role is None:
        return await ctx.reply("رول السجن غير محدد. استخدم `!set prison role @رول`.", mention_author=False)

    if not bot_can_manage_role(ctx.guild, role):
        return await ctx.reply("رتبة البوت لازم تكون أعلى من رول السجن.", mention_author=False)

    prison_channel_id = data.get("prison_channels", {}).get(str(ctx.guild.id))
    prison_channel = ctx.guild.get_channel(int(prison_channel_id)) if prison_channel_id else None
    if not isinstance(prison_channel, discord.TextChannel):
        return await ctx.reply("حدد روم السجن أولًا باستخدام `!set prison room #روم`.", mention_author=False)

    if not await configure_prison_access(ctx.guild):
        return await ctx.reply("إعدادات السجن غير مكتملة. حدد رول السجن وروم السجن.", mention_author=False)

    try:
        saved_roles = [str(r.id) for r in member.roles if not r.is_default() and not r.managed and r != role]
        data.setdefault("prison_saved_roles", {})[f"{ctx.guild.id}:{member.id}"] = saved_roles
        removable = [r for r in member.roles if not r.is_default() and not r.managed and r != role and r < ctx.guild.me.top_role]
        if removable:
            await member.remove_roles(*removable, reason=f"Prison role isolation by {ctx.author}")
        await member.add_roles(role, reason=f"{ctx.author}: {reason}")
        await ctx.reply(f"تم سجن {member.mention} في {prison_channel.mention}.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "سجن عضو",
            f"المنفذ: {ctx.author.mention}\nالعضو: {member.mention}\nالسبب: {reason}"
        )

    except discord.HTTPException:
        saved_ids = data.setdefault("prison_saved_roles", {}).pop(f"{ctx.guild.id}:{member.id}", [])
        restore = [ctx.guild.get_role(int(rid)) for rid in saved_ids]
        restore = [r for r in restore if r and bot_can_manage_role(ctx.guild, r) and r not in member.roles]
        if restore:
            try:
                await member.add_roles(*restore, reason="Restore roles after failed prison action")
            except discord.HTTPException:
                log.exception("تعذر استعادة رتب العضو بعد فشل السجن")
        save_data()
        await ctx.reply("تعذر سجن العضو؛ تمت محاولة استعادة رتبته السابقة.", mention_author=False)


@bot.command(name="unprison", aliases=["unpison", "فك"])
async def unprison_member(ctx, member: discord.Member):
    if not await staff_check(ctx, "prison") or not await hierarchy_check(ctx, member):
        return

    rid = data["prison_roles"].get(str(ctx.guild.id))
    role = ctx.guild.get_role(int(rid)) if rid else None

    if role is None:
        return await ctx.reply("رول السجن غير محدد.", mention_author=False)

    if not bot_can_manage_role(ctx.guild, role):
        return await ctx.reply("رتبة البوت لازم تكون أعلى من رول السجن.", mention_author=False)

    try:
        await member.remove_roles(role, reason=f"Unprison by {ctx.author}")
        saved_key = f"{ctx.guild.id}:{member.id}"
        saved_ids = data.setdefault("prison_saved_roles", {}).pop(saved_key, [])
        restore = []
        for saved_id in saved_ids:
            saved_role = ctx.guild.get_role(int(saved_id))
            if saved_role and bot_can_manage_role(ctx.guild, saved_role) and saved_role not in member.roles:
                restore.append(saved_role)
        if restore:
            await member.add_roles(*restore, reason=f"Restore roles after prison by {ctx.author}")
        save_data()
        await ctx.reply(f"تم فك السجن عن {member.mention}.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "فك سجن عضو",
            f"المنفذ: {ctx.author.mention}\nالعضو: {member.mention}"
        )

    except discord.HTTPException:
        await ctx.reply("تعذر فك السجن.", mention_author=False)


@bot.command(name="unban")
async def unban_member(ctx, user_id: int, *, reason="بدون سبب"):
    if not await staff_check(ctx, "ban"):
        return

    if not ctx.guild.me.guild_permissions.ban_members:
        return await ctx.reply("البوت يحتاج Ban Members.", mention_author=False)

    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")

        await ctx.reply(f"تم فك الحظر عن `{user}`.", mention_author=False)

        await send_log(
            ctx.guild,
            "moderation",
            "فك حظر عضو",
            f"المنفذ: {ctx.author.mention}\nالمستخدم: `{user}`\nالسبب: {reason}"
        )

    except discord.NotFound:
        await ctx.reply("هذا المستخدم غير محظور.", mention_author=False)

    except discord.HTTPException:
        await ctx.reply("تعذر فك الحظر.", mention_author=False)


@bot.command(name="نك", aliases=["nick", "nickname"])
async def change_nick(ctx, member: discord.Member, *, nickname: str):
    if not await staff_check(ctx, "nickname"):
        return

    if not is_owner(ctx.author) and not actor_above(ctx.author, member):
        return await ctx.reply("لازم رتبتك أعلى من رتبة العضو.", mention_author=False)

    if member.id == ctx.guild.owner_id or member.top_role >= ctx.guild.me.top_role:
        return await ctx.reply(
            "البوت لا يستطيع تغيير نك هذا العضو بسبب ترتيب الرتب.",
            mention_author=False
        )

    if not 1 <= len(nickname.strip()) <= 32:
        return await ctx.reply("النك لازم يكون بين 1 و32 حرفًا.", mention_author=False)

    try:
        await member.edit(nick=nickname.strip(), reason=f"Nickname by {ctx.author}")
        await ctx.reply("تم تغيير النك.", mention_author=False)

    except discord.HTTPException:
        await ctx.reply("تعذر تغيير النك.", mention_author=False)


# ---------- Roles ----------

async def actor_can_edit(ctx, member):
    return is_owner(ctx.author) or ctx.author.top_role > member.top_role


@bot.command(name="رول", aliases=["role", "ر", "r"])
async def toggle_role(ctx, *, targets=None):
    if not targets:
        return await ctx.reply(
            "الاستخدام:\n"
            "`!رول @عضو @رول`\n"
            "`!رول @عضو اسم الرول`\n"
            "`!رول @رول_مصدر @رول_جديد`",
            mention_author=False
        )

    role_ids = re.findall(r"<@&(\d+)>", targets)
    member_ids = re.findall(r"<@!?(\d+)>", targets)
    parts = targets.split()

    # وضع توزيع الرول القديم إلى الرول الجديد
    if len(role_ids) == 2 and len(parts) == 2 and not member_ids:
        src, dst = [ctx.guild.get_role(int(x)) for x in role_ids]

        if not src or not dst:
            return await ctx.reply("هذا الرول غير موجود.", mention_author=False)

        for role in (src, dst):
            ok, err = role_check(ctx, role)
            if not ok:
                return await ctx.reply(err, mention_author=False)

        if not await staff_check(ctx, "add_role") or not await staff_check(ctx, "remove_role"):
            return
        success = skipped = failed = 0

        await ctx.reply("بدأ توزيع الرول...", mention_author=False)

        async with ctx.typing():
            for member in await get_members(ctx.guild):
                if src not in member.roles:
                    continue

                if dst in member.roles or not await actor_can_edit(ctx, member):
                    skipped += 1
                    continue

                try:
                    await member.add_roles(dst, reason=f"Role distribution by {ctx.author}")
                    success += 1
                except discord.HTTPException:
                    failed += 1

        await ctx.send(
            f"انتهى التوزيع.\nنجح: `{success}` | تخطي: `{skipped}` | فشل: `{failed}`"
        )
        return

    # وضع إعطاء أو سحب رول من عضو
    member_match = re.match(r"^\s*<@!?(\d+)>\s+(.+)$", targets)

    if member_match:
        member_id = int(member_match.group(1))
        role_query = member_match.group(2).strip()

        member = ctx.guild.get_member(member_id)

        if not member:
            return await ctx.reply("هذا العضو غير موجود.", mention_author=False)

        matches = find_role_matches(ctx.guild, role_query)

        if not matches:
            return await ctx.reply("ما حصلت رول بهذا الاسم أو البداية التي كتبتها.", mention_author=False)

        if len(matches) > 1:
            names = "\n".join(f"- {role.name}" for role in matches[:10])

            return await ctx.reply(
                f"البداية تطابق أكثر من رول. حدد الاسم بشكل أوضح:\n{names}",
                mention_author=False
            )

        role = matches[0]
        needed_permission = "remove_role" if role in member.roles else "add_role"
        if not await staff_check(ctx, needed_permission):
            return

        ok, err = role_check(ctx, role)

        if not ok:
            return await ctx.reply(err, mention_author=False)

        if not await actor_can_edit(ctx, member):
            return await ctx.reply("لازم رتبتك أعلى من رتبة العضو.", mention_author=False)

        try:
            if role in member.roles:
                await member.remove_roles(role, reason=f"Role toggle by {ctx.author}")
                text = f"تم سحب {role.mention} من {member.mention}."
            else:
                await member.add_roles(role, reason=f"Role toggle by {ctx.author}")
                text = f"تم إعطاء {role.mention} إلى {member.mention}."

            await ctx.reply(text, mention_author=False)

        except discord.HTTPException:
            await ctx.reply("تعذر تعديل الرول.", mention_author=False)

        return

    await ctx.reply(
        "الاستخدام غير صحيح.\n"
        "استخدم `!رول @عضو @رول` أو `!رول @عضو اسم الرول` "
        "أو منشن رولين للتوزيع.",
        mention_author=False
    )


@bot.command(name="roleall")
async def role_all(ctx, *, query=None):
    if not await staff_check(ctx, "add_role"): 
        return

    matches = find_role_matches(ctx.guild, query) if query else []

    if not matches:
        return await ctx.reply("هذا الرول غير موجود.", mention_author=False)

    if len(matches) > 1:
        names = "\n".join(f"- {role.name}" for role in matches[:10])
        return await ctx.reply(f"الاسم يطابق أكثر من رول:\n{names}", mention_author=False)

    role = matches[0]
    ok, err = role_check(ctx, role)

    if not ok:
        return await ctx.reply(err or "هذا الرول غير موجود.", mention_author=False)

    success = skipped = failed = 0

    await ctx.reply("بدأ إعطاء الرول للأعضاء...", mention_author=False)

    async with ctx.typing():
        for member in await get_members(ctx.guild):
            if role in member.roles or not await actor_can_edit(ctx, member):
                skipped += 1
                continue

            try:
                await member.add_roles(role, reason=f"Role all by {ctx.author}")
                success += 1
            except discord.HTTPException:
                failed += 1

    await ctx.send(
        f"انتهى التوزيع.\nنجح: `{success}` | تخطي: `{skipped}` | فشل: `{failed}`"
    )


# ---------- Extended server administration ----------

@bot.command(name="addroom", aliases=["اضافة_روم", "اضافهروم"])
async def add_room(ctx, *, name):
    if not await staff_check(ctx, "channels"):
        return
    if not ctx.guild.me.guild_permissions.manage_channels:
        return await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)

    parts = name.strip().split(maxsplit=1)
    channel_type = "text"
    if len(parts) == 2 and parts[0].casefold() in ("voice", "فويس", "صوت"):
        channel_type, name = "voice", parts[1]
    name = re.sub(r"\s+", "-", name.strip().lower())[:90]
    if not name:
        return await ctx.reply("اكتب اسم الروم.", mention_author=False)
    try:
        if channel_type == "voice":
            channel = await ctx.guild.create_voice_channel(name, reason=f"Room created by {ctx.author}")
        else:
            channel = await ctx.guild.create_text_channel(name, reason=f"Room created by {ctx.author}")
        await ctx.reply(f"تم إنشاء الروم {channel.mention}.", mention_author=False)
    except discord.HTTPException:
        await ctx.reply("تعذر إنشاء الروم.", mention_author=False)


@bot.command(name="delroom", aliases=["حذف_روم"])
async def delete_room(ctx, *, channel_query):
    if not await staff_check(ctx, "channels"):
        return
    if not ctx.guild.me.guild_permissions.manage_channels:
        return await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)
    try:
        channel = await commands.GuildChannelConverter().convert(ctx, channel_query)
    except commands.BadArgument:
        return await ctx.reply("حدد رومًا صحيحًا بالمنشن أو الاسم.", mention_author=False)
    try:
        await ctx.reply(f"سيتم حذف {channel.name} خلال 3 ثوانٍ.", mention_author=False)
        await asyncio.sleep(3)
        await channel.delete(reason=f"Room deleted by {ctx.author}")
    except discord.HTTPException:
        await ctx.reply("تعذر حذف الروم.", mention_author=False)


@bot.command(name="kickvoice", aliases=["طرد_الفويس", "فصل_الفويس"])
async def kick_all_voice(ctx, confirmation=None):
    if not await staff_check(ctx, "voice"):
        return
    if str(confirmation).casefold() not in ("confirm", "تأكيد", "تاكيد"):
        return await ctx.reply("لتأكيد إخراج جميع الموجودين بالفويس اكتب: `!kickvoice تأكيد`.", mention_author=False)
    if not ctx.guild.me.guild_permissions.move_members:
        return await ctx.reply("البوت يحتاج Move Members.", mention_author=False)
    members = [m for vc in ctx.guild.voice_channels + ctx.guild.stage_channels for m in list(vc.members)]
    done = failed = 0
    for member in members:
        try:
            await member.move_to(None, reason=f"Disconnect all voice by {ctx.author}")
            done += 1
        except discord.HTTPException:
            failed += 1
    await ctx.reply(f"تم إخراج {done} عضو من الفويس. تعذر: {failed}.", mention_author=False)


@bot.command(name="lockserver", aliases=["قفل_السيرفر", "قفل_الكل"])
async def lock_server(ctx, confirmation=None):
    if not await staff_check(ctx, "server"):
        return
    if str(confirmation).casefold() not in ("confirm", "تأكيد", "تاكيد"):
        return await ctx.reply("لتأكيد قفل الكتابة والفويس في الرومات اكتب: `!lockserver تأكيد`.", mention_author=False)
    if not ctx.guild.me.guild_permissions.manage_channels:
        return await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)

    progress = await ctx.reply("جاري قفل الرومات...", mention_author=False)
    key = str(ctx.guild.id)
    states = data.setdefault("server_lock_states", {}).setdefault(key, {})
    changed = failed = 0
    channels = list(ctx.guild.text_channels) + list(ctx.guild.voice_channels) + list(ctx.guild.stage_channels)
    for channel in channels:
        try:
            ow = channel.overwrites_for(ctx.guild.default_role)
            channel_state = states.setdefault(str(channel.id), {})
            if isinstance(channel, discord.TextChannel):
                channel_state.setdefault("send_messages", ow.send_messages)
                ow.send_messages = False
            else:
                channel_state.setdefault("connect", ow.connect)
                ow.connect = False
            await channel.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"Server locked by {ctx.author}")
            changed += 1
        except discord.HTTPException:
            failed += 1
    save_data()
    await progress.edit(content=f"تم قفل {changed} روم كتابي وصوتي. تعذر: {failed}.")


@bot.command(name="openserver", aliases=["فتح_السيرفر", "فتح_الكل"])
async def unlock_server(ctx):
    if not await staff_check(ctx, "server"):
        return
    if not ctx.guild.me.guild_permissions.manage_channels:
        return await ctx.reply("البوت يحتاج Manage Channels.", mention_author=False)
    key = str(ctx.guild.id)
    states = data.setdefault("server_lock_states", {}).get(key, {})
    restored = failed = 0
    remaining = {}
    for channel_id, saved in list(states.items()):
        channel = ctx.guild.get_channel(int(channel_id))
        if channel is None:
            continue
        try:
            ow = channel.overwrites_for(ctx.guild.default_role)
            if isinstance(saved, dict):
                if "send_messages" in saved:
                    ow.send_messages = saved["send_messages"]
                if "connect" in saved:
                    ow.connect = saved["connect"]
            else:
                ow.send_messages = saved
            await channel.set_permissions(ctx.guild.default_role, overwrite=ow, reason=f"Server unlocked by {ctx.author}")
            restored += 1
        except discord.HTTPException:
            failed += 1
            remaining[channel_id] = saved
    if remaining:
        data.setdefault("server_lock_states", {})[key] = remaining
    else:
        data.setdefault("server_lock_states", {}).pop(key, None)
    save_data()
    await ctx.reply(f"تم فتح {restored} روم كتابي وصوتي. تعذر: {failed}.", mention_author=False)


@bot.command(name="roleallremove", aliases=["سحب_رتبة_الكل", "removeallrole"])
async def remove_role_all(ctx, *, query=None):
    if not await staff_check(ctx, "remove_role"):
        return
    if not query or not re.search(r"(?:^|\s)(?:confirm|تأكيد|تاكيد)$", query, re.IGNORECASE):
        return await ctx.reply("لتأكيد سحب الرتبة من الجميع اكتب: `!roleallremove @رول تأكيد`.", mention_author=False)
    query = re.sub(r"\s+(?:confirm|تأكيد|تاكيد)$", "", query, flags=re.IGNORECASE).strip()
    matches = find_role_matches(ctx.guild, query) if query else []
    if len(matches) != 1:
        return await ctx.reply("حدد رولًا واحدًا صحيحًا بالمنشن أو الاسم.", mention_author=False)
    role = matches[0]
    ok, err = role_check(ctx, role)
    if not ok:
        return await ctx.reply(err, mention_author=False)
    success = skipped = failed = 0
    await ctx.reply(f"بدأ سحب {role.mention} من الأعضاء...", mention_author=False)
    async with ctx.typing():
        for member in await get_members(ctx.guild):
            if role not in member.roles:
                continue
            if member.id == ctx.guild.owner_id or member.top_role >= ctx.guild.me.top_role:
                skipped += 1
                continue
            try:
                await member.remove_roles(role, reason=f"Bulk role removal by {ctx.author}")
                success += 1
            except discord.HTTPException:
                failed += 1
    await ctx.send(f"انتهى السحب. نجح: {success} | تخطي: {skipped} | فشل: {failed}")


@bot.command(name="permissions", aliases=["الصلاحيات", "صلاحيات"])
async def show_permissions(ctx):
    if not await owner_check(ctx):
        return
    mapping = data.get("staff_permissions", {}).get(str(ctx.guild.id), {})
    lines = ["صلاحيات الرتب"]
    for key, label in PERMISSION_NAMES.items():
        ids = mapping.get(key, [])
        roles = [ctx.guild.get_role(int(rid)) for rid in ids]
        roles = [r.mention for r in roles if r]
        lines.append(f"{label}: {', '.join(roles) if roles else 'غير محدد'}")
    await ctx.reply("\n".join(lines), mention_author=False)


@bot.command(name="setpermission", aliases=["صلاحية", "تعيين_صلاحية"])
async def set_permission(ctx, role: discord.Role, permission: str):
    if not await owner_check(ctx):
        return
    key = PERMISSION_ALIASES.get(permission.strip().casefold())
    if not key:
        return await ctx.reply("الصلاحية غير معروفة. استخدم `!permissions` لمعرفة الأقسام المتاحة.", mention_author=False)
    ok, err = role_check(ctx, role)
    if not ok:
        return await ctx.reply(err, mention_author=False)
    roles = data.setdefault("staff_permissions", {}).setdefault(str(ctx.guild.id), {}).setdefault(key, [])
    if str(role.id) not in roles:
        roles.append(str(role.id))
    save_data()
    await ctx.reply(f"تم منح {role.mention} صلاحية {PERMISSION_NAMES[key]}.", mention_author=False)


@bot.command(name="removepermission", aliases=["حذف_صلاحية", "ازالة_صلاحية"])
async def remove_permission(ctx, role: discord.Role, permission: str):
    if not await owner_check(ctx):
        return
    key = PERMISSION_ALIASES.get(permission.strip().casefold())
    if not key:
        return await ctx.reply("الصلاحية غير معروفة.", mention_author=False)
    mapping = data.setdefault("staff_permissions", {}).setdefault(str(ctx.guild.id), {})
    mapping[key] = [rid for rid in mapping.get(key, []) if rid != str(role.id)]
    save_data()
    await ctx.reply(f"تم سحب صلاحية {PERMISSION_NAMES[key]} من {role.mention}.", mention_author=False)


# ---------- Words, owner commands ----------

@bot.command(name="words", aliases=["كلمات"])
async def list_words(ctx):
    if not await staff_check(ctx, "words"):
        return

    words = data["protected_words"].get(str(ctx.guild.id), [])

    await ctx.reply(
        "الكلمات المحظورة\n" + ("\n".join(words[:50]) if words else "ما فيه كلمات محظورة."),
        mention_author=False
    )


@bot.command(name="status", aliases=["حالة", "حاله"])
@commands.guild_only()
async def set_bot_status(ctx, status: str):
    if not await owner_check(ctx):
        return

    aliases = {
        "online": "online", "متصل": "online", "اونلاين": "online",
        "idle": "idle", "خامل": "idle", "بعيد": "idle",
        "dnd": "dnd", "busy": "dnd", "مشغول": "dnd", "عدم_الازعاج": "dnd",
        "invisible": "invisible", "offline": "invisible", "مخفي": "invisible", "غير_متصل": "invisible",
    }
    value = aliases.get(status.strip().casefold())
    if value is None:
        return await ctx.reply(
            "الحالات المتاحة: `online` أو `idle` أو `dnd` أو `invisible`.",
            mention_author=False
        )

    data.setdefault("bot_status", {})["value"] = value
    save_data()
    discord_status = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible,
    }[value]
    await bot.change_presence(status=discord_status)
    await ctx.reply(f"تم تغيير حالة البوت إلى `{value}`.", mention_author=False)


@bot.command(name="activity")
@commands.guild_only()
async def set_activity(ctx, *, text):
    if not await owner_check(ctx):
        return

    await bot.change_presence(activity=discord.Game(name=text[:128]))
    await ctx.reply("تم تغيير حالة البوت.", mention_author=False)


@bot.command(name="botavatar")
@commands.guild_only()
async def set_avatar(ctx):
    if not await owner_check(ctx):
        return

    if not ctx.message.attachments:
        return await ctx.reply("أرفق صورة مع الأمر.", mention_author=False)

    att = ctx.message.attachments[0]

    if att.content_type and not att.content_type.startswith("image/"):
        return await ctx.reply("المرفق ليس صورة.", mention_author=False)

    try:
        await bot.user.edit(avatar=await att.read())
        await ctx.reply("تم تغيير صورة البوت.", mention_author=False)

    except discord.HTTPException:
        await ctx.reply("تعذر تغيير صورة البوت.", mention_author=False)


@bot.command(name="say")
async def owner_say(ctx, *, text):
    if not await owner_check(ctx):
        return

    await ctx.send(text[:2000], allowed_mentions=discord.AllowedMentions.none())


@bot.tree.command(name="say", description="إرسال رسالة باسم البوت للمالك فقط")
@app_commands.describe(text="النص")
async def slash_say(interaction, text: str):
    if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message(
            "هذا الأمر خاص بمالك السيرفر.",
            ephemeral=True
        )

    await interaction.response.send_message(
        text[:2000],
        allowed_mentions=discord.AllowedMentions.none()
    )


@bot.tree.command(name="control", description="فتح لوحة تحكم ZeTh الخاصة بالأونر")
async def control_panel(interaction):
    if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message(
            "هذا الأمر خاص بمالك السيرفر.",
            ephemeral=True
        )

    try:
        await interaction.user.send(
            embed=owner_panel_embed(interaction.guild),
            view=OwnerPanelView(interaction.user.id, interaction.guild.id)
        )
        await interaction.response.send_message("أرسلت لوحة التحكم إلى الخاص.", ephemeral=True)

    except discord.Forbidden:
        await interaction.response.send_message(
            "افتح الخاص من إعدادات السيرفر حتى أرسل اللوحة.",
            ephemeral=True
        )


# ---------- Prefix settings ----------

@commands.group(name="set", aliases=["ضبط"], invoke_without_command=True)
async def set_group(ctx):
    await ctx.reply("هذا الأمر غير متوفر.", mention_author=False)

@set_group.command(name="welcome", aliases=["ترحيب"])
async def set_welcome(ctx, target: str, *, value=None):
    if not await owner_check(ctx):
        return

    key = str(ctx.guild.id)

    if target.casefold() in ("text", "نص", "message", "رسالة"):
        if not value:
            return await ctx.reply("اكتب نص الترحيب.", mention_author=False)

        data["welcome_texts"][key] = value[:1900]

    else:
        try:
            channel = await commands.TextChannelConverter().convert(ctx, target)
        except commands.BadArgument:
            return await ctx.reply("حدد رومًا صحيحًا.", mention_author=False)

        data["welcome_channels"][key] = channel.id

    save_data()
    await ctx.reply("تم حفظ إعداد الترحيب.", mention_author=False)


@set_group.command(name="locket", aliases=["لوكت", "صور"])
async def set_locket(ctx, channel: discord.TextChannel):
    if not await owner_check(ctx):
        return

    data["locket_channels"][str(ctx.guild.id)] = channel.id
    image_role_id = data.get("image_roles", {}).get(str(ctx.guild.id))
    image_role = ctx.guild.get_role(int(image_role_id)) if image_role_id else None
    try:
        everyone = channel.overwrites_for(ctx.guild.default_role)
        everyone.attach_files = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=everyone, reason="Image room restrictions")
        if image_role:
            role_overwrite = channel.overwrites_for(image_role)
            role_overwrite.attach_files = True
            role_overwrite.embed_links = True
            await channel.set_permissions(image_role, overwrite=role_overwrite, reason="Image posting role")
    except discord.HTTPException:
        return await ctx.reply("تم حفظ الروم لكن تعذر ضبط صلاحيات المرفقات.", mention_author=False)
    save_data()

    await ctx.reply(f"تم تحديد روم الصور: {channel.mention}.", mention_author=False)


@set_group.group(name="log", aliases=["logs"], invoke_without_command=True)
async def set_log(ctx, target=None, channel: discord.TextChannel = None):
    if not await owner_check(ctx):
        return

    if not target:
        return await ctx.reply("هذا الأمر غير متوفر.", mention_author=False)

    key = normalize_log_kind(target)
    if key not in LOG_NAMES:
        return await ctx.reply("قسم اللوق غير معروف.", mention_author=False)

    if channel is None:
        return await ctx.reply("حدد رومًا للقسم.", mention_author=False)

    settings = log_settings(ctx.guild)
    settings.setdefault("types", {})[key] = channel.id
    save_data()
    await ctx.reply(
        f"تم تحديد لوق {LOG_NAMES[key]} في {channel.mention}.",
        mention_author=False
    )

@set_log.command(name="reset")
async def reset_logs(ctx):
    if not await owner_check(ctx):
        return

    data["logs"].pop(str(ctx.guild.id), None)
    save_data()

    await ctx.reply("تمت إعادة ضبط اللوق.", mention_author=False)


@bot.command(name="logs")
async def show_logs(ctx):
    if not await owner_check(ctx):
        return

    settings = log_settings(ctx.guild)
    lines = [
        "إعدادات لوقات DeaTh",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "الأقسام",
        ""
    ]

    for key, label in LOG_NAMES.items():
        cid = settings.get("types", {}).get(key)
        channel = ctx.guild.get_channel(int(cid)) if cid else None
        lines.extend([
            label,
            f"الروم: {channel.mention if channel else 'غير محدد'}",
            ""
        ])

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    await ctx.reply("\n".join(lines), mention_author=False)


@set_group.command(name="permission", aliases=["صلاحية"])
async def set_permission_nested(ctx, role: discord.Role, permission: str):
    await set_permission(ctx, role, permission)


@set_group.command(name="removepermission", aliases=["حذف_صلاحية"])
async def remove_permission_nested(ctx, role: discord.Role, permission: str):
    await remove_permission(ctx, role, permission)


@set_group.group(name="bad", invoke_without_command=True)
async def set_bad(ctx):
    await ctx.reply("هذا الأمر غير متوفر.", mention_author=False)


@set_bad.group(name="word", invoke_without_command=True)
async def set_bad_word(ctx, *, word=None):
    if not await staff_check(ctx, "words"):
        return

    if not word:
        return await ctx.reply("هذا الأمر غير متوفر.", mention_author=False)

    word = word.strip()

    if not compact_text(word):
        return await ctx.reply("الكلمة غير صالحة.", mention_author=False)

    words = data["protected_words"].setdefault(str(ctx.guild.id), [])

    if compact_text(word) not in [compact_text(w) for w in words]:
        words.append(word)

    save_data()
    await ctx.reply("تمت إضافة الكلمة.", mention_author=False)


@set_bad_word.command(name="remove", aliases=["حذف", "ازالة"])
async def remove_bad_word(ctx, *, word):
    if not await staff_check(ctx, "words"):
        return

    key = str(ctx.guild.id)
    wanted = compact_text(word)

    data["protected_words"][key] = [
        w for w in data["protected_words"].get(key, [])
        if compact_text(w) != wanted
    ]

    save_data()
    await ctx.reply("تم حذف الكلمة.", mention_author=False)


@set_group.group(name="mute", invoke_without_command=True)
async def set_mute(ctx):
    await ctx.reply("هذا الأمر غير متوفر.", mention_author=False)


@set_mute.command(name="role")
async def set_mute_role(ctx, role: discord.Role):
    if not await owner_check(ctx):
        return

    if role.is_default() or role.managed:
        return await ctx.reply("هذا الرول غير صالح.", mention_author=False)

    data["muted_roles"][str(ctx.guild.id)] = str(role.id)
    try:
        await configure_chat_mute_role(ctx.guild, role)
    except discord.Forbidden:
        return await ctx.reply("رتبة الميوت أعلى من رتبة البوت.", mention_author=False)
    save_data()

    await ctx.reply(f"تم ضبط رول الميوت الكتابي: {role.mention} على كل الرومات ومنها Locket.", mention_author=False)


@set_group.group(name="images", invoke_without_command=True)
async def set_images(ctx):
    await ctx.reply("استخدم `!set images role @رول` لتحديد رتبة الصور.", mention_author=False)


@set_images.command(name="role", aliases=["رول"])
async def set_images_role(ctx, role: discord.Role):
    if not await owner_check(ctx):
        return
    ok, err = role_check(ctx, role)
    if not ok:
        return await ctx.reply(err, mention_author=False)
    data.setdefault("image_roles", {})[str(ctx.guild.id)] = str(role.id)
    save_data()
    channel_id = data.get("locket_channels", {}).get(str(ctx.guild.id))
    channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
    if isinstance(channel, discord.TextChannel):
        ow = channel.overwrites_for(role)
        ow.attach_files = True
        ow.embed_links = True
        await channel.set_permissions(role, overwrite=ow, reason="Image posting role")
    await ctx.reply(f"تم تحديد رتبة الصور: {role.mention}.", mention_author=False)


@set_group.group(name="prison", invoke_without_command=True)
async def set_prison(ctx):
    await ctx.reply("هذا الأمر غير متوفر.", mention_author=False)


@set_prison.command(name="room", aliases=["channel", "روم"])
async def set_prison_room(ctx, channel: discord.TextChannel):
    if not await owner_check(ctx):
        return
    data.setdefault("prison_channels", {})[str(ctx.guild.id)] = str(channel.id)
    save_data()
    configured = await configure_prison_access(ctx.guild)
    note = " وتم ضبط صلاحيات الرول." if configured else " حدد رول السجن أيضًا حتى يضبط البوت صلاحياته."
    await ctx.reply(f"تم تحديد روم السجن: {channel.mention}.{note}", mention_author=False)


@set_prison.command(name="role")
async def set_prison_role(ctx, role: discord.Role):
    if not await owner_check(ctx):
        return

    ok, err = role_check(ctx, role)

    if not ok:
        return await ctx.reply(err, mention_author=False)
    dangerous_prison_permissions = (
        "administrator", "manage_guild", "manage_channels", "manage_roles",
        "manage_webhooks", "manage_messages", "manage_threads", "kick_members",
        "ban_members", "moderate_members", "mute_members", "deafen_members", "move_members"
    )
    if any(getattr(role.permissions, name, False) for name in dangerous_prison_permissions):
        return await ctx.reply("رول السجن يحتوي صلاحيات إدارية. استخدم رولًا عاديًا بدون صلاحيات إدارة.", mention_author=False)

    data["prison_roles"][str(ctx.guild.id)] = str(role.id)
    save_data()
    configured = await configure_prison_access(ctx.guild)
    note = " وتم ضبط الروم بحيث لا يرى السجين إلا روم السجن." if configured else " حدد روم السجن باستخدام `!set prison room #روم`."
    await ctx.reply(f"تم تحديد رول السجن: {role.mention}.{note}", mention_author=False)


bot.add_command(set_group)


# ---------- Slash settings ----------

set_slash = app_commands.Group(name="set", description="إعدادات ZeTh")
ticket_slash = app_commands.Group(name="ticket", description="إعدادات التكت")
staff_slash = app_commands.Group(name="staff", description="إعدادات الإدارة")


@ticket_slash.command(name="room", description="تحديد روم لوحة التكت")
async def set_ticket_room(interaction, channel: discord.TextChannel):
    if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message(
            "هذا الإعداد خاص بمالك السيرفر.",
            ephemeral=True
        )

    guild = interaction.guild

    try:
        ow = channel.overwrites_for(guild.default_role)
        ow.view_channel = True
        ow.send_messages = False

        await channel.set_permissions(
            guild.default_role,
            overwrite=ow,
            reason="Ticket panel"
        )

        data["ticket_rooms"][str(guild.id)] = channel.id
        save_data()

        embed = discord.Embed(
            title="الدعم الفني",
            description="اضغط الزر لفتح تذكرة خاصة.",
            color=0x5865F2
        )

        await channel.send(embed=embed, view=TicketPanelView())

        await interaction.response.send_message(
            f"تم إعداد لوحة التكت في {channel.mention}.",
            ephemeral=True
        )

    except discord.HTTPException:
        await interaction.response.send_message("تعذر إعداد روم التكت.", ephemeral=True)


@staff_slash.command(name="role", description="إضافة رتبة للإدارة")
async def set_staff_role(interaction, role: discord.Role):
    if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message(
            "هذا الإعداد خاص بمالك السيرفر.",
            ephemeral=True
        )

    if role.is_default() or role.managed:
        return await interaction.response.send_message("هذا الرول غير صالح.", ephemeral=True)

    roles = data["staff_roles"].setdefault(str(interaction.guild.id), [])

    if str(role.id) not in roles:
        roles.append(str(role.id))

    save_data()

    await interaction.response.send_message(
        f"تمت إضافة رتبة الإدارة: {role.mention}.",
        ephemeral=True
    )


@staff_slash.command(name="remove", description="حذف رتبة من الإدارة")
async def remove_staff_role(interaction, role: discord.Role):
    if not interaction.guild or interaction.user.id != interaction.guild.owner_id:
        return await interaction.response.send_message(
            "هذا الإعداد خاص بمالك السيرفر.",
            ephemeral=True
        )

    roles = data["staff_roles"].setdefault(str(interaction.guild.id), [])

    data["staff_roles"][str(interaction.guild.id)] = [
        x for x in roles if x != str(role.id)
    ]

    save_data()

    await interaction.response.send_message(
        f"تم حذف رتبة الإدارة: {role.mention}.",
        ephemeral=True
    )


set_slash.add_command(ticket_slash)
set_slash.add_command(staff_slash)
bot.tree.add_command(set_slash)


# ---------- Start bot ----------

async def main():
    token = TOKEN

    if not token:
        raise RuntimeError("ضع توكن البوت في متغير TOKEN.")

    async with bot:
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
