from AAA3A_utils import Cog, Settings  # isort:skip
from redbot.core import commands, Config, modlog  # isort:skip
from redbot.core.bot import Red  # isort:skip
from redbot.core.i18n import Translator, cog_i18n  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import os

from redbot.core.utils.chat_formatting import box

# Créditos:
# Créditos gerais do repositório.
# Obrigado ao Matt pela ideia do cog!

_: Translator = Translator("Honeypot", __file__)


@cog_i18n(_)
class Honeypot(Cog):
    """Crie um canal no topo do servidor para atrair bots/scammers e notifique/mute/kick/ban them imediatamente!"""

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)

        self.config: Config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571750,
            force_registration=True,
        )
        self.config.register_guild(
            enabled=False,
            action=None,
            logs_channel=None,
            ping_role=None,
            honeypot_channel=None,
            mute_role=None,
            ban_delete_message_days=3,
        )

        _settings: typing.Dict[str, typing.Dict[str, typing.Any]] = {
            "enabled": {
                "converter": bool,
                "description": "Ativar ou desativar o cog.",
            },
            "action": {
                "converter": typing.Literal["mute", "kick", "ban"],
                "description": "A ação a ser tomada quando um bot/scammer é detectado.",
            },
            "logs_channel": {
                "converter": typing.Union[
                    discord.TextChannel, discord.VoiceChannel, discord.Thread
                ],
                "description": "O canal para enviar os logs.",
            },
            "ping_role": {
                "converter": discord.Role,
                "description": "O cargo a ser mencionado quando um bot/scammer é detectado.",
            },
            "mute_role": {
                "converter": discord.Role,
                "description": "O cargo de mudo a ser atribuído aos bots/scammers, se a ação for `mute`.",
            },
            "ban_delete_message_days": {
                "converter": commands.Range[int, 0, 7],
                "description": "O número de dias de mensagens a serem deletadas ao banir um bot/scammer.",
            },
        }
        self.settings: Settings = Settings(
            bot=self.bot,
            cog=self,
            config=self.config,
            group=self.config.GUILD,
            settings=_settings,
            global_path=[],
            use_profiles_system=False,
            can_edit=True,
            commands_group=self.sethoneypot,
        )

    async def cog_load(self) -> None:
        await super().cog_load()
        await self.settings.add_commands()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.guild is None:
            return
        if await self.bot.cog_disabled_in_guild(self, message.guild):
            return
        if message.author.bot:
            return
        config = await self.config.guild(message.guild).all()
        if (
            not config["enabled"]
            or (honeypot_channel_id := config["honeypot_channel"]) is None
            or (logs_channel_id := config["logs_channel"]) is None
            or (logs_channel := message.guild.get_channel(logs_channel_id)) is None
        ):
            return
        if message.channel.id != honeypot_channel_id:
            return
        if (
            message.author.id in self.bot.owner_ids
            or await self.bot.is_mod(message.author)
            or await self.bot.is_admin(message.author)
            or message.author.guild_permissions.manage_guild
            or message.author.top_role >= message.guild.me.top_role
        ):
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        action = config["action"]
        embed: discord.Embed = discord.Embed(
            title=_("Honeypot — Bot/Scammer Detectado!"),
            description=f">>> {message.content}",
            color=discord.Color.red(),
            timestamp=message.created_at,
        )
        embed.set_author(
            name=f"{message.author.display_name} ({message.author.id})",
            icon_url=message.author.display_avatar,
        )
        embed.set_thumbnail(url=message.author.display_avatar)
        failed = None
        if action is not None:
            try:
                if action == "mute":
                    if (mute_role_id := config["mute_role"]) is not None and (
                        mute_role := message.guild.get_role(mute_role_id)
                    ) is not None:
                        await message.author.add_roles(
                            mute_role, reason="Bot/scammer detectado."
                        )
                    else:
                        failed = _(
                            "**Falhou:** O cargo de mudo não está definido ou não existe mais."
                        )
                elif action == "kick":
                    await message.author.kick(reason="Bot/scammer detectado.")
                elif action == "ban":
                    await message.author.ban(
                        reason="Bot/scammer detectado.",
                        delete_message_days=config["ban_delete_message_days"],
                    )
            except discord.HTTPException as e:
                failed = _(
                    "**Falhou:** Ocorreu um erro ao tentar tomar uma ação contra o membro:\n"
                ) + box(str(e), lang="py")
            else:
                await modlog.create_case(
                    self.bot,
                    message.guild,
                    message.created_at,
                    action_type=action,
                    user=message.author,
                    moderator=message.guild.me,
                    reason="Bot/scammer detectado.",
                )
            embed.add_field(
                name=_("Ação:"),
                value=(
                    (
                        _("O membro foi silenciado.")
                        if action == "mute"
                        else (
                            _("O membro foi expulso.")
                            if action == "kick"
                            else _("O membro foi banido.")
                        )
                    )
                    if failed is None
                    else failed
                ),
                inline=False,
            )
        embed.set_footer(text=message.guild.name, icon_url=message.guild.icon)
        await logs_channel.send(
            content=(
                ping_role.mention
                if (ping_role_id := config["ping_role"]) is not None
                and (ping_role := message.guild.get_role(ping_role_id)) is not None
                else None
            ),
            embed=embed,
        )

    @commands.guild_only()
    @commands.guildowner()
    @commands.hybrid_group()
    async def sethoneypot(self, ctx: commands.Context) -> None:
        """Defina as configurações do honeypot. Apenas o proprietário do servidor pode usar este comando por razões de segurança."""
        pass

    @commands.bot_has_guild_permissions(manage_channels=True)
    @sethoneypot.command(aliases=["makechannel"])
    async def createchannel(self, ctx: commands.Context) -> None:
        """Crie o canal honeypot."""
        if (
            honeypot_channel_id := await self.config.guild(ctx.guild).honeypot_channel()
        ) is not None and (
            honeypot_channel := ctx.guild.get_channel(honeypot_channel_id)
        ) is not None:
            raise commands.UserFeedbackCheckFailure(
                _(
                    "O canal honeypot já existe: {honeypot_channel.mention} ({honeypot_channel.id})."
                ).format(honeypot_channel=honeypot_channel)
            )
        honeypot_channel = await ctx.guild.create_text_channel(
            name="honeypot",
            position=0,
            overwrites={
                ctx.guild.me: discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True,
                    manage_channels=True,
                ),
                ctx.guild.default_role: discord.PermissionOverwrite(
                    view_channel=True, read_messages=True, send_messages=True
                ),
            },
            reason=f"Criação do canal honeypot solicitada por {ctx.author.display_name} ({ctx.author.id}).",
        )
        embed = discord.Embed(
            title=_("⚠️ NÃO POSTE AQUI! ⚠️"),
            description=_(
                "Uma ação será imediatamente tomada contra você se você enviar uma mensagem neste canal."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name=_("O que não fazer?"),
            value=_("Não envie mensagens neste canal."),
            inline=False,
        )
        embed.add_field(
            name=_("O que ACONTECERÁ?"),
            value=_("Uma ação será tomada contra você."),
            inline=False,
        )
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon)
        embed.set_image(url="attachment://do_not_post_here.png")
        await honeypot_channel.send(
            content=_("## ⚠️ AVISO ⚠️"),
            embed=embed,
            files=[discord.File(os.path.join(os.path.dirname(__file__), "do_not_post_here.png"))],
        )
        await self.config.guild(ctx.guild).honeypot_channel.set(honeypot_channel.id)
        await ctx.send(
            _(
                "O canal honeypot foi definido como {honeypot_channel.mention} ({honeypot_channel.id}). Você pode agora começar a atrair bots/scammers!\n"
                "Por favor, certifique-se de ativar o cog e definir o canal de logs, a ação a ser tomada, o cargo a ser mencionado (e o cargo de mudo) se você ainda não o fez."
            ).format(honeypot_channel=honeypot_channel)
        )
