from AAA3A_utils import Cog, Loop, CogsUtils, Menu  # isort:skip
from redbot.core import commands, Config  # isort:skip
from redbot.core.bot import Red  # isort:skip
from redbot.core.i18n import Translator, cog_i18n  # isort:skip
import discord  # isort:skip
import typing  # isort:skip

import datetime
import io
from copy import deepcopy

from redbot.core.utils.chat_formatting import humanize_list, pagify

# Créditos:
# Créditos gerais do repositório.
# Agradecimentos a Obi-Wan3 pela ideia do cog e pelas strings de algumas mensagens (https://github.com/Obi-Wan3/OB13-Cogs/tree/main/temprole)!

_: Translator = Translator("TempRoles", __file__)

DurationConverter: commands.converter.TimedeltaConverter = commands.converter.TimedeltaConverter(
    minimum=datetime.timedelta(minutes=1),
    maximum=None,
    allowed_units=None,
    default_unit="days",
)


class OptionalDurationConverter(commands.Converter):
    async def convert(
        self, ctx: commands.Context, argument: str
    ) -> typing.Optional[datetime.timedelta]:
        if argument.lower() == "none":
            return None
        return await DurationConverter.convert(ctx, argument=argument)


@cog_i18n(_)
class TempRoles(Cog):
    """Um cog para atribuir funções temporárias aos usuários, expirando após um determinado período!"""

    __authors__: typing.List[str] = ["AAA3A", "Obi-Wan3"]

    def __init__(self, bot: Red) -> None:
        super().__init__(bot=bot)

        self.config: Config = Config.get_conf(
            self,
            identifier=205192943327321000143939875896557571750,
            force_registration=True,
        )
        self.config.register_member(temp_roles={})
        self.config.register_guild(
            logs_channel=None,
            allowed_self_temp_roles={},
            joining_temp_roles={},
            auto_temp_roles={},
            user_roles={},
            allowed_personal_role_id=None,
        )

    async def cog_load(self) -> None:
        await super().cog_load()
        self.loops.append(
            Loop(
                cog=self,
                name="Verificar TempRoles",
                function=self.temp_roles_loop,
                seconds=30,
            )
        )

    async def red_delete_data_for_user(
        self,
        *,
        requester: typing.Literal["discord_deleted_user", "owner", "user", "user_strict"],
        user_id: int,
    ) -> None:
        """Excluir funções temporárias apenas nos dados do cog para o usuário."""
        if requester not in ("discord_deleted_user", "owner", "user", "user_strict"):
            return
        if requester not in ("discord_deleted_user", "owner"):
            return
        member_group = self.config._get_base_group(self.config.MEMBER)
        async with member_group.all() as members_data:
            _members_data = deepcopy(members_data)
            for guild in _members_data:
                if str(user_id) in _members_data[guild]:
                    del members_data[guild][str(user_id)]
                if not members_data[guild]:
                    del members_data[guild]

    async def red_get_data_for_user(self, *, user_id: int) -> typing.Dict[str, io.BytesIO]:
        """Obter todos os dados sobre o usuário."""
        data = {
            Config.GLOBAL: {},
            Config.USER: {},
            Config.MEMBER: {},
            Config.ROLE: {},
            Config.CHANNEL: {},
            Config.GUILD: {},
        }

        members_data = await self.config.all_members()
        for guild in members_data:
            if user_id in members_data[guild]:
                data[Config.MEMBER][guild] = members_data[guild][user_id]

        _data = deepcopy(data)
        for key, value in _data.items():
            if not value:
                del data[key]
        if not data:
            return {}
        file = io.BytesIO(str(data).encode(encoding="utf-8"))
        return {f"{self.qualified_name}.json": file}

    async def temp_roles_loop(self, utc_now: datetime.datetime = None) -> bool:
        if utc_now is None:
            utc_now = datetime.datetime.now(tz=datetime.timezone.utc)
        executed = False
        member_group = self.config._get_base_group(self.config.MEMBER)
        async with member_group.all() as members_data:
            _members_data = deepcopy(members_data)
            for guild_id in _members_data:
                if (guild := self.bot.get_guild(int(guild_id))) is None:
                    continue
                for member_id in _members_data[guild_id]:
                    if (member := guild.get_member(int(member_id))) is None:
                        del members_data[guild_id][member_id]
                        continue
                    for temp_role_id, expires_times in _members_data[guild_id][member_id][
                        "temp_roles"
                    ].items():
                        if datetime.datetime.fromtimestamp(
                            expires_times, tz=datetime.timezone.utc
                        ) <= utc_now.replace(microsecond=0):
                            executed = True
                            if (temp_role := guild.get_role(int(temp_role_id))) is not None:
                                try:
                                    await member.remove_roles(
                                        temp_role, reason="Função Temporária automaticamente desassociada."
                                    )
                                except discord.HTTPException as e:
                                    self.logger.error(
                                        f"Erro ao remover a Função Temporária {temp_role.name} ({temp_role.id}) de {member} ({member.id}) em {guild.name} ({guild.id}).",
                                        exc_info=e,
                                    )
                                else:
                                    if (
                                        (
                                            logs_channel_id := await self.config.guild(
                                                guild
                                            ).logs_channel()
                                        )
                                        is not None
                                        and (logs_channel := guild.get_channel(logs_channel_id))
                                        is not None
                                        and logs_channel.permissions_for(guild.me).embed_links
                                    ):
                                        await logs_channel.send(
                                            embed=discord.Embed(
                                                title=_("Funções Temporárias"),
                                                description=_(
                                                    "A Função Temporária {temp_role.mention} ({temp_role.id}) foi automaticamente desassociada de {member.mention} ({member.id})."
                                                ).format(temp_role=temp_role, member=member),
                                                color=await self.bot.get_embed_color(logs_channel),
                                            )
                                        )
                            del members_data[guild_id][member_id]["temp_roles"][temp_role_id]
                    if not members_data[guild_id][member_id]["temp_roles"]:
                        del members_data[guild_id][member_id]
                if not members_data[guild_id]:
                    del members_data[guild_id]
        return executed

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        joining_temp_roles = {
            role: duration
            for role_id, duration in (
                await self.config.guild(member.guild).joining_temp_roles()
            ).items()
            if (role := member.guild.get_role(int(role_id))) is not None
        }
        for role, duration in joining_temp_roles.items():
            try:
                end_time = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
                    seconds=duration
                )
            except OverflowError:
                continue
            end_time = end_time.replace(second=0 if end_time.second < 30 else 30)
            duration_string = CogsUtils.get_interval_string(duration)
            try:
                await member.add_roles(
                    role,
                    reason=f"Função Temporária atribuída ao novo membro, expira em {duration_string}.",
                )
            except discord.HTTPException as e:
                self.logger.error(
                    f"Erro ao atribuir a Função Temporária de Entrada {role.name} ({role.id}) a {member} ({member.id}) em {member.guild.name} ({member.guild.id}).",
                    exc_info=e,
                )
            else:
                member_temp_roles = await self.config.member(member).temp_roles()
                end_time = datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(
                    seconds=duration
                )
                member_temp_roles[str(role.id)] = int(end_time.replace(microsecond=0).timestamp())
                await self.config.member(member).temp_roles.set(member_temp_roles)
                if (
                    (logs_channel_id := await self.config.guild(member.guild).logs_channel())
                    is not None
                    and (logs_channel := member.guild.get_channel(logs_channel_id)) is not None
                    and logs_channel.permissions_for(member.guild.me).embed_links
                ):
                    await logs_channel.send(
                        embed=discord.Embed(
                            title=_("Funções Temporárias de Entrada"),
                            description=_(
                                "A Função Temporária de Entrada {role.mention} ({role.id}) foi atribuída a {member.mention} ({member.id}). Expira em {duration_string}."
                            ).format(role=role, member=member, duration_string=duration_string),
                            color=await self.bot.get_embed_color(logs_channel),
                        )
                    )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles == after.roles:
            return
        if len(before.roles) > len(after.roles):
            removed_roles = set(before.roles) - set(after.roles)
            for role in removed_roles:
                if str(role.id) in await self.config.member(after).temp_roles():
                    member_temp_roles = await self.config.member(after).temp_roles()
                    del member_temp_roles[str(role.id)]
                    await self.config.member(after).temp_roles.set(member_temp_roles)
        elif len(before.roles) < len(after.roles):
            added_roles = set(after.roles) - set(before.roles)
            for role in added_roles:
                if str(role.id) in await self.config.guild(after.guild).auto_temp_roles():
                    auto_temp_roles = await self.config.guild(after.guild).auto_temp_roles()
                    duration = datetime.timedelta(seconds=auto_temp_roles[str(role.id)])
                    try:
                        end_time = datetime.datetime.now(tz=datetime.timezone.utc) + duration
                    except OverflowError:
                        continue
                    end_time = end_time.replace(second=0 if end_time.second < 30 else 30)
                    duration_string = CogsUtils.get_interval_string(duration)
                    member_temp_roles = await self.config.member(after).temp_roles()
                    end_time = datetime.datetime.now(tz=datetime.timezone.utc) + duration
                    member_temp_roles[str(role.id)] = int(
                        end_time.replace(microsecond=0).timestamp()
                    )
                    await self.config.member(after).temp_roles.set(member_temp_roles)
                    if (
                        (logs_channel_id := await self.config.guild(after.guild).logs_channel())
                        is not None
                        and (logs_channel := after.guild.get_channel(logs_channel_id)) is not None
                        and logs_channel.permissions_for(after.guild.me).embed_links
                    ):
                        await logs_channel.send(
                            embed=discord.Embed(
                                title=_("Funções Temporárias Automáticas"),
                                description=_(
                                    "A Função Temporária Automática {role.mention} ({role.id}) foi atribuída a {member.mention} ({member.id}). Expira em {duration_string}."
                                ).format(role=role, member=after, duration_string=duration_string),
                                color=await self.bot.get_embed_color(logs_channel),
                            )
                        )

    @commands.guild_only()
    @commands.bot_has_permissions(manage_roles=True)
    @commands.hybrid_group(aliases=["temprole"])
    async def temproles(self, ctx: commands.Context) -> None:
        """Atribuir funções temporárias aos usuários, expirando após um determinado tempo."""
        pass

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command(aliases=["add", "+", "adicionar"])
    async def assign(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        duration: DurationConverter,
    ) -> None:
        """Atribuir/Adicionar uma Função Temporária a um membro, por um período especificado."""
        member_temp_roles = await self.config.member(member).temp_roles()
        if str(role.id) in member_temp_roles:
            # raise commands.UserFeedbackCheckFailure(
            #     _("Esta função já é uma Função Temporária deste membro.")
            # )
            if not ctx.assume_yes:
                if not await CogsUtils.ConfirmationAsk(
                    ctx,
                    content=_(
                        "Esta função já é uma Função Temporária deste membro. Você deseja editar a duração?\nAtualmente, esta Função Temporária expira {timestamp}."
                    ).format(timestamp=f"<t:{int(member_temp_roles[str(role.id)])}:R>"),
                ):
                    return await CogsUtils.delete_message(ctx.message)
                return await self.edit.callback(
                    self, ctx, member=member, role=role, duration=duration
                )
        elif role in member.roles:
            raise commands.UserFeedbackCheckFailure(
                _("Este membro já possui {role.mention} ({role.id}).").format(role=role)
            )
        if not role.is_assignable():
            raise commands.UserFeedbackCheckFailure(_("Esta função não pode ser atribuída."))
        if (
            ctx.command.name != "selfassign"
            and ctx.author != ctx.guild.owner
            and (member.top_role >= ctx.author.top_role or member == ctx.guild.owner)
        ):
            raise commands.UserFeedbackCheckFailure(
                _("Você não pode atribuir esta função a este membro, devido à hierarquia de funções do Discord.")
            )
        try:
            end_time: datetime.datetime = (
                datetime.datetime.now(tz=datetime.timezone.utc) + duration
            )
        except OverflowError:
            raise commands.UserFeedbackCheckFailure(
                _("O tempo definido é muito alto, considere definir algo razoável.")
            )
        end_time = end_time.replace(second=0 if end_time.second < 30 else 30)
        duration_string = CogsUtils.get_interval_string(duration)
        await member.add_roles(
            role,
            reason=("Auto " if ctx.command.name == "selfassign" else "")
            + f"Função Temporária atribuída por {ctx.author} ({ctx.author.id}), expira em {duration_string}.",
        )
        member_temp_roles[str(role.id)] = int(end_time.replace(microsecond=0).timestamp())
        await self.config.member(member).temp_roles.set(member_temp_roles)
        if (
            (logs_channel_id := await self.config.guild(ctx.guild).logs_channel()) is not None
            and (logs_channel := ctx.guild.get_channel(logs_channel_id)) is not None
            and logs_channel.permissions_for(ctx.guild.me).embed_links
        ):
            await logs_channel.send(
                embed=discord.Embed(
                    title=_("Funções Temporárias"),
                    description=(_("Auto ") if ctx.command.name == "selfassign" else "")
                    + _(
                        "A Função Temporária {role.mention} ({role.id}) foi atribuída a {member.mention} ({member.id}) por {author.mention} ({author.id}). Expira em {duration_string}."
                    ).format(
                        role=role,
                        member=member,
                        author=ctx.author,
                        duration_string=duration_string,
                    ),
                    color=await ctx.bot.get_embed_color(logs_channel),
                )
            )
        await ctx.send(
            (_("Auto ") if ctx.command.name == "selfassign" else "")
            + _(
                "A Função Temporária {role.mention} ({role.id}) foi atribuída a {member.mention} ({member.id}). Expira **em {duration_string}** ({timestamp})."
            ).format(
                role=role,
                member=member,
                duration_string=duration_string,
                timestamp=f"<t:{int(end_time.timestamp())}:F>",
            ),
            allowed_mentions=discord.AllowedMentions(roles=False, users=False),
        )

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def edit(
        self,
        ctx: commands.Context,
        member: discord.Member,
        role: discord.Role,
        *,
        duration: DurationConverter,
    ) -> None:
        """Editar uma Função Temporária para um membro, por um período especificado."""
        member_temp_roles = await self.config.member(member).temp_roles()
        if str(role.id) not in member_temp_roles:
            raise commands.UserFeedbackCheckFailure(
                _("Esta função não é uma Função Temporária deste membro.")
            )
        try:
            end_time: datetime.datetime = (
                datetime.datetime.now(tz=datetime.timezone.utc) + duration
            )
        except OverflowError:
            raise commands.UserFeedbackCheckFailure(
                _("O tempo definido é muito alto, considere definir algo razoável.")
            )
        end_time = end_time.replace(second=0 if end_time.second < 30 else 30)
        duration_string = CogsUtils.get_interval_string(duration)
        await member.add_roles(
            role,
            reason="Função Temporária editada por {ctx.author} ({ctx.author.id}), expira em {duration_string}.",
        )
        member_temp_roles[str(role.id)] = int(end_time.replace(microsecond=0).timestamp())
        await self.config.member(member).temp_roles.set(member_temp_roles)
        if (
            (logs_channel_id := await self.config.guild(ctx.guild).logs_channel()) is not None
            and (logs_channel := ctx.guild.get_channel(logs_channel_id)) is not None
            and logs_channel.permissions_for(ctx.guild.me).embed_links
        ):
            await logs_channel.send(
                embed=discord.Embed(
                    title=_("Funções Temporárias"),
                    description=_(
                        "A Função Temporária {role.mention} ({role.id}) foi editada para {member.mention} ({member.id}) por {author.mention} ({author.id}). Expira em {duration_string}."
                    ).format(
                        role=role,
                        member=member,
                        author=ctx.author,
                        duration_string=duration_string,
                    ),
                    color=await ctx.bot.get_embed_color(logs_channel),
                )
            )
        await ctx.send(
            _(
                "A Função Temporária {role.mention} ({role.id}) foi editada para {member.mention} ({member.id}). Expira **em {duration_string}** ({timestamp})."
            ).format(
                role=role,
                member=member,
                duration_string=duration_string,
                timestamp=f"<t:{int(end_time.timestamp())}:F>",
            ),
            allowed_mentions=discord.AllowedMentions(roles=False, users=False),
        )

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command(aliases=["remove", "-", "remover", "remover-vip"])
    async def unassign(
        self, ctx: commands.Context, member: discord.Member, role: discord.Role
    ) -> None:
        """Desatribuir/Remover uma Função Temporária de um membro."""
        member_temp_roles = await self.config.member(member).temp_roles()
        if str(role.id) not in member_temp_roles:
            raise commands.UserFeedbackCheckFailure(
                _("Esta função não é uma Função Temporária deste membro.")
            )
        try:
            await member.remove_roles(
                role, reason=f"Função Temporária desatribuída por {ctx.author} ({ctx.author.id})."
            )
        except discord.HTTPException:
            pass
        del member_temp_roles[str(role.id)]
        await self.config.member(member).temp_roles.set(member_temp_roles)
        if (
            (logs_channel_id := await self.config.guild(ctx.guild).logs_channel()) is not None
            and (logs_channel := ctx.guild.get_channel(logs_channel_id)) is not None
            and logs_channel.permissions_for(ctx.guild.me).embed_links
        ):
            await logs_channel.send(
                embed=discord.Embed(
                    title=_("Funções Temporárias"),
                    description=_(
                        "A Função Temporária {role.mention} ({role.id}) foi desatribuída de {member.mention} ({member.id}) por {author.mention} ({author.id})."
                    ).format(role=role, member=member, author=ctx.author),
                    color=await ctx.bot.get_embed_color(logs_channel),
                )
            )
        await ctx.send(
            _(
                "A Função Temporária {role.mention} ({role.id}) foi desatribuída de {member.mention} ({member.id})."
            ).format(role=role, member=member),
            allowed_mentions=discord.AllowedMentions(roles=False, users=False),
        )

    @commands.admin_or_permissions(manage_roles=True)
    @commands.bot_has_permissions(embed_links=True)
    @temproles.command(aliases=["listar"])
    async def list(
        self,
        ctx: commands.Context,
        member: typing.Optional[discord.Member] = None,
        role: typing.Optional[discord.Role] = None,
    ) -> None:
        """Listar Funções Temporárias ativas neste servidor, para membro e/ou função especificados opcionalmente."""
        embed: discord.Embed = discord.Embed(
            title=_("Funções Temporárias"),
            color=await ctx.embed_color(),
        )
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon)
        if member is not None and role is not None:
            if str(role.id) in await self.config.member(member).temp_roles():
                description = _("Este membro possui esta Função Temporária.")
            else:
                description = _("Este membro não possui esta Função Temporária.")
        elif member is not None:
            embed.set_author(
                name=f"{member.display_name} ({member.id})", icon_url=member.display_avatar
            )
            if not (temp_roles := await self.config.member(member).temp_roles()):
                description = _("Este membro não possui nenhuma Função Temporária.")
            else:
                description = "\n".join(
                    [
                        f"**•** {temp_role.mention} ({temp_role_id}) - <t:{int(end_time)}:R> (<t:{int(end_time)}:F>)"
                        for temp_role_id, end_time in temp_roles.items()
                        if (temp_role := ctx.guild.get_role(int(temp_role_id))) is not None
                    ]
                )
        elif role is not None:
            embed.set_author(text=f"{role.name} ({role.id})", icon_url=role.icon)
            members_data = await self.config.all_members(guild=ctx.guild)
            temp_roles_members = {}
            for member_id, data in members_data.items():
                if str(role.id) not in data["temp_roles"]:
                    continue
                if (member := ctx.guild.get_member(member_id)) is None:
                    continue
                temp_roles_members[member] = data["temp_roles"][str(role.id)]
            if not temp_roles_members:
                description = _("Nenhum membro possui esta Função Temporária.")
            else:
                description = "\n".join(
                    [
                        f"**•** {member.mention} ({member.id}) - <t:{int(end_time)}:R> (<t:{int(end_time)}:F>)"
                        for member, end_time in temp_roles_members.items()
                    ]
                )
        else:
            description = []
            members_data = await self.config.all_members(guild=ctx.guild)
            for member_id, data in members_data.items():
                if (member := ctx.guild.get_member(member_id)) is None:
                    continue
                if member_temp_roles := {
                    temp_role: end_time
                    for temp_role_id, end_time in data["temp_roles"].items()
                    if (temp_role := ctx.guild.get_role(int(temp_role_id))) is not None
                }:
                    description.append(
                        f"**•** {member.mention} ({member.id}): {humanize_list([f'{temp_role.mention} ({temp_role.id}) - <t:{int(end_time)}:R> (<t:{int(end_time)}:F>)' for temp_role, end_time in member_temp_roles.items()])}."
                    )
            if description:
                description = "\n".join(description)
            else:
                description = _("Nenhuma Função Temporária ativa neste servidor.")
        embeds = []
        pages = list(pagify(description, page_length=3000))
        for page in pages:
            e = embed.copy()
            e.description = page
            embeds.append(e)
        await Menu(pages=embeds).start(ctx)

    @commands.bot_has_permissions(embed_links=True)
    @temproles.command()
    async def mylist(self, ctx: commands.Context) -> None:
        """Listar Funções Temporárias ativas para você mesmo."""
        await self.list.callback(self, ctx, member=ctx.author)

    @commands.admin_or_permissions(administrator=True)
    @temproles.command()
    async def logschannel(
        self, ctx: commands.Context, logs_channel: discord.TextChannel = None
    ) -> None:
        """Definir o canal de logs para Funções Temporárias."""
        if logs_channel is None:
            await self.config.guild(ctx.guild).logs_channel.clear()
            await ctx.send(_("Canal de logs desconfigurado."))
        else:
            if not logs_channel.permissions_for(ctx.me).embed_links:
                raise commands.UserFeedbackCheckFailure(
                    _("Eu preciso da permissão `embed_links` no canal de logs.")
                )
            await self.config.guild(ctx.guild).logs_channel.set(logs_channel.id)
            await ctx.send(_("Canal de logs configurado."))

    @commands.admin_or_permissions(administrator=True)
    @temproles.command()
    async def addallowedselftemprole(
        self,
        ctx: commands.Context,
        role: discord.Role,
        min_duration: typing.Optional[OptionalDurationConverter] = datetime.timedelta(days=1),
        max_duration: typing.Optional[OptionalDurationConverter] = datetime.timedelta(days=365),
    ) -> None:
        """Adicionar uma Função Temporária permitida para autoatribuição.

        **Parâmetros:**
        - `min_duration`: A duração mínima para a função temporária autoatribuída. `none` para desativar. O padrão é 1 dia.
        - `max_duration`: A duração máxima para a função temporária autoatribuída. `none` para desativar. O padrão é 365 dias.
        """
        if role >= ctx.guild.me.top_role or (
            role >= ctx.author.top_role and ctx.author != ctx.guild.owner
        ):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "A função {role.mention} ({role.id}) não pode ser atribuída devido à hierarquia de funções do Discord."
                ).format(role=role)
            )
        allowed_self_temp_roles = await self.config.guild(ctx.guild).allowed_self_temp_roles()
        if str(role.id) in allowed_self_temp_roles:
            raise commands.UserFeedbackCheckFailure(
                _("Esta função já é uma função temporária autoatribuída permitida.")
            )
        allowed_self_temp_roles[str(role.id)] = {
            "min_time": None if min_duration is None else int(min_duration.total_seconds()),
            "max_time": None if max_duration is None else int(max_duration.total_seconds()),
        }
        await self.config.guild(ctx.guild).allowed_self_temp_roles.set(allowed_self_temp_roles)
        await ctx.send(_("Função Temporária autoatribuída permitida adicionada."))

    @commands.admin_or_permissions(administrator=True)
    @temproles.command()
    async def removeallowedselftemprole(self, ctx: commands.Context, role: discord.Role) -> None:
        """Remover uma Função Temporária permitida para autoatribuição."""
        allowed_self_temp_roles = await self.config.guild(ctx.guild).allowed_self_temp_roles()
        if str(role.id) not in allowed_self_temp_roles:
            raise commands.UserFeedbackCheckFailure(
                _("Esta função não é uma função temporária autoatribuída permitida.")
            )
        del allowed_self_temp_roles[str(role.id)]
        await self.config.guild(ctx.guild).allowed_self_temp_roles.set(allowed_self_temp_roles)
        await ctx.send(_("Função Temporária autoatribuída permitida removida."))

    @temproles.command(aliases=["selfadd"])
    async def selfassign(
        self, ctx: commands.Context, role: discord.Role, *, duration: DurationConverter
    ) -> None:
        """Atribuir/Adicionar uma Função Temporária permitida para autoatribuição a você mesmo, por um período especificado."""
        if str(role.id) not in (
            allowed_self_temp_roles := await self.config.guild(ctx.guild).allowed_self_temp_roles()
        ):
            raise commands.UserFeedbackCheckFailure(
                _("Esta função não é uma Função Temporária permitida para autoatribuição neste servidor.")
            )
        if allowed_self_temp_roles[str(role.id)]["min_time"] is not None:
            min_duration = datetime.timedelta(
                seconds=allowed_self_temp_roles[str(role.id)]["min_time"]
            )
            if duration < min_duration:
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "A duração para esta função deve ser maior que {min_duration_string}."
                    ).format(min_duration_string=CogsUtils.get_interval_string(min_duration))
                )
        if allowed_self_temp_roles[str(role.id)]["max_time"] is not None:
            max_duration = datetime.timedelta(
                seconds=allowed_self_temp_roles[str(role.id)]["max_time"]
            )
            if duration > max_duration:
                raise commands.UserFeedbackCheckFailure(
                    _(
                        "A duração para esta função deve ser menor que {max_duration_string}."
                    ).format(max_duration_string=CogsUtils.get_interval_string(max_duration))
                )
        await self.assign.callback(self, ctx, member=ctx.author, role=role, duration=duration)

    @temproles.command(aliases=["selfremove"])
    async def selfunassign(self, ctx: commands.Context, role: discord.Role) -> None:
        """Desatribuir/Remover uma Função Temporária permitida para autoatribuição de você mesmo."""
        if str(role.id) not in await self.config.guild(ctx.guild).allowed_self_temp_roles():
            raise commands.UserFeedbackCheckFailure(_("Você não pode remover esta função de si mesmo."))
        await self.unassign.callback(self, ctx, member=ctx.author, role=role)

    @temproles.command()
    async def selflist(self, ctx: commands.Context) -> None:
        """Listar Funções Temporárias permitidas para autoatribuição de você mesmo."""
        description = ""
        BREAK_LINE = "\n"
        if member_temp_roles := {
            temp_role: end_time
            for temp_role_id, end_time in (
                await self.config.member(ctx.author).temp_roles()
            ).items()
            if (temp_role := ctx.guild.get_role(int(temp_role_id))) is not None
        }:
            description += f"**Suas Funções Temporárias atuais:**\n{BREAK_LINE.join([f'**•** {temp_role.mention} ({temp_role.id}) - Expira <t:{int(end_time)}:R>.' for temp_role, end_time in member_temp_roles.items()])}\n\n"
        if allowed_self_temp_roles := {
            role: (data["min_time"], data["max_time"])
            for role_id, data in (
                await self.config.guild(ctx.guild).allowed_self_temp_roles()
            ).items()
            if (role := ctx.guild.get_role(int(role_id))) is not None
        }:
            description += f"**Funções Temporárias permitidas para autoatribuição neste servidor:**\n{BREAK_LINE.join([f'**•** {role.mention} ({role.id}) - Duração mínima `{CogsUtils.get_interval_string(min_duration) if min_duration is not None else None}`. - Duração máxima `{CogsUtils.get_interval_string(max_duration) if max_duration is not None else None}`.' for role, (min_duration, max_duration) in allowed_self_temp_roles.items()])}"
        embeds = []
        pages = list(pagify(description, page_length=3000))
        for page in pages:
            embed: discord.Embed = discord.Embed(
                title=_("Funções Temporárias Autoatribuídas"), color=await ctx.embed_color()
            )
            embed.description = page
            embeds.append(embed)
        await Menu(pages=embeds).start(ctx)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def addjoiningtemprole(
        self,
        ctx: commands.Context,
        role: discord.Role,
        duration: DurationConverter,
    ) -> None:
        """Adicionar uma Função Temporária de Entrada.

        **Parâmetros:**
        - `role`: A função a ser atribuída a novos membros.
        - `duration`: A duração da função.
        """
        if role >= ctx.guild.me.top_role or (
            role >= ctx.author.top_role and ctx.author != ctx.guild.owner
        ):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "A função {role.mention} ({role.id}) não pode ser atribuída devido à hierarquia de funções do Discord."
                ).format(role=role)
            )
        joining_temp_roles = await self.config.guild(ctx.guild).joining_temp_roles()
        if str(role.id) in joining_temp_roles:
            raise commands.UserFeedbackCheckFailure(_("Esta função já é uma Função Temporária de Entrada."))
        joining_temp_roles[str(role.id)] = int(duration.total_seconds())
        await self.config.guild(ctx.guild).joining_temp_roles.set(joining_temp_roles)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def removejoiningtemprole(self, ctx: commands.Context, role: discord.Role) -> None:
        """Remover uma Função Temporária de Entrada."""
        joining_temp_roles = await self.config.guild(ctx.guild).joining_temp_roles()
        if str(role.id) not in joining_temp_roles:
            raise commands.UserFeedbackCheckFailure(_("Esta função não é uma Função Temporária de Entrada."))
        del joining_temp_roles[str(role.id)]
        await self.config.guild(ctx.guild).joining_temp_roles.set(joining_temp_roles)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def joiningtemproles(self, ctx: commands.Context) -> None:
        """Listar as Funções Temporárias de Entrada."""
        joining_temp_roles = await self.config.guild(ctx.guild).joining_temp_roles()
        if not joining_temp_roles:
            await ctx.send(_("Nenhuma Função Temporária de Entrada."))
            return
        description = "\n".join(
            [
                f"**•** {role.mention} ({role.id}) - {CogsUtils.get_interval_string(duration)}."
                for role_id, duration in joining_temp_roles.items()
                if (role := ctx.guild.get_role(int(role_id))) is not None
            ]
        )
        embeds = []
        pages = list(pagify(description, page_length=3000))
        for page in pages:
            embed: discord.Embed = discord.Embed(
                title=_("Funções Temporárias de Entrada"), color=await ctx.embed_color()
            )
            embed.description = page
            embeds.append(embed)
        await Menu(pages=embeds).start(ctx)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def autoaddtemprole(
        self,
        ctx: commands.Context,
        role: discord.Role,
        duration: DurationConverter,
    ) -> None:
        """Adicionar uma Função Temporária Automática.

        **Parâmetros:**
        - `role`: A função a ser atribuída a novos membros.
        - `duration`: A duração da função.
        """
        if role >= ctx.guild.me.top_role or (
            role >= ctx.author.top_role and ctx.author != ctx.guild.owner
        ):
            raise commands.UserFeedbackCheckFailure(
                _(
                    "A função {role.mention} ({role.id}) não pode ser atribuída devido à hierarquia de funções do Discord."
                ).format(role=role)
            )
        auto_temp_roles = await self.config.guild(ctx.guild).auto_temp_roles()
        if str(role.id) in auto_temp_roles:
            raise commands.UserFeedbackCheckFailure(_("Esta função já é uma Função Temporária Automática."))
        auto_temp_roles[str(role.id)] = int(duration.total_seconds())
        await self.config.guild(ctx.guild).auto_temp_roles.set(auto_temp_roles)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def removeautoaddtemprole(self, ctx: commands.Context, role: discord.Role) -> None:
        """Remover uma Função Temporária Automática."""
        auto_temp_roles = await self.config.guild(ctx.guild).auto_temp_roles()
        if str(role.id) not in auto_temp_roles:
            raise commands.UserFeedbackCheckFailure(_("Esta função não é uma Função Temporária Automática."))
        del auto_temp_roles[str(role.id)]
        await self.config.guild(ctx.guild).auto_temp_roles.set(auto_temp_roles)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def autotemproles(self, ctx: commands.Context) -> None:
        """Listar as Funções Temporárias Automáticas."""
        auto_temp_roles = await self.config.guild(ctx.guild).auto_temp_roles()
        if not auto_temp_roles:
            await ctx.send(_("Nenhuma Função Temporária Automática."))
            return
        description = "\n".join(
            [
                f"**•** {role.mention} ({role.id}) - {CogsUtils.get_interval_string(duration)}."
                for role_id, duration in auto_temp_roles.items()
                if (role := ctx.guild.get_role(int(role_id))) is not None
            ]
        )
        embeds = []
        pages = list(pagify(description, page_length=3000))
        for page in pages:
            embed: discord.Embed = discord.Embed(
                title=_("Funções Temporárias Automáticas"), color=await ctx.embed_color()
            )
            embed.description = page
            embeds.append(embed)
        await Menu(pages=embeds).start(ctx)

    @commands.admin_or_permissions(manage_roles=True)
    @temproles.command()
    async def setpersonalroleid(
        self, ctx: commands.Context, role: discord.Role
    ) -> None:
        """Definir o cargo que pode criar cargos pessoais."""
        await self.config.guild(ctx.guild).allowed_personal_role_id.set(role.id)
        await ctx.send(_("O ID do cargo permitido para criar cargos pessoais foi definido como {role.mention}.").format(role=role))

    @temproles.command(aliases=["criar"])
    async def createpersonalrole(
        self, ctx: commands.Context, role_name: str
    ) -> None:
        """Criar um cargo pessoal que só você pode editar com a mesma duração do cargo da pessoa."""
        # Obtém o ID do cargo permitido da configuração
        allowed_role_id = 1176861125799854100
        position_role_id = 1174124070414057512  # ID do cargo abaixo do qual o novo cargo deve ser criado

        # Verifica se o ID do cargo permitido está definido
        if allowed_role_id is None:
            raise commands.UserFeedbackCheckFailure(_("O ID do cargo permitido não foi definido. Use o comando `setpersonalroleid` para configurá-lo."))

        # Verifica se o usuário tem a permissão para criar um cargo pessoal
        if allowed_role_id not in [role.id for role in ctx.author.roles]:
            raise commands.UserFeedbackCheckFailure(_("Você não tem permissão para criar um cargo pessoal."))

        # Verifica se o usuário já criou um cargo pessoal
        user_roles = await self.config.guild(ctx.guild).user_roles()
        if str(ctx.author.id) in user_roles and len(user_roles[str(ctx.author.id)]) >= 1:
            raise commands.UserFeedbackCheckFailure(_("Você já criou dois cargos temporários."))

        # Cria o novo cargo
        guild = ctx.guild
        try:
            new_role = await guild.create_role(
                name=f"{role_name}",  # Nome do cargo
                permissions=discord.Permissions(send_messages=True),  # Defina as permissões conforme necessário
                reason=f"Cargo pessoal criado por {ctx.author} ({ctx.author.id})"
            )
            await ctx.send(_("Cargo pessoal '{role_name}' criado com sucesso!").format(role_name=new_role.name))
            await ctx.author.add_roles(new_role)

            # Salva a relação do usuário com o cargo criado
            if str(ctx.author.id) not in user_roles:
                user_roles[str(ctx.author.id)] = []
            user_roles[str(ctx.author.id)].append(new_role.id)
            await self.config.guild(ctx.guild).user_roles.set(user_roles)

            # Define a posição do novo cargo abaixo do cargo especificado
            position_role = guild.get_role(position_role_id)
            if position_role:
                await new_role.edit(position=position_role.position - 1)
                await ctx.send(_("A posição do cargo pessoal foi ajustada com sucesso."))

            # Define as permissões do cargo para que apenas o membro possa editá-lo
            await new_role.edit(
                permissions=discord.Permissions.none(),
                reason="Permissões ajustadas para cargo pessoal."
            )
            await ctx.send(_("As permissões do cargo pessoal foram ajustadas com sucesso."))
        except discord.HTTPException as e:
            await ctx.send(_("Ocorreu um erro ao criar o cargo."))
            self.logger.error(f"Erro ao criar cargo: {e}")

    @temproles.command(aliases=["adicionare"])
    async def addmembertopersonalrole(
        self, ctx: commands.Context, member: discord.Member
    ) -> None:
        """Adicionar um membro ao seu cargo pessoal."""
        allowed_role_id = 1176861125799854100

        if allowed_role_id not in [role.id for role in ctx.author.roles]:
            raise commands.UserFeedbackCheckFailure(
                _("Você não tem permissão para adicionar membros a este cargo.")
            )

        personal_roles = [role for role in ctx.author.roles if role.id == allowed_role_id]
        if not personal_roles:
            raise commands.UserFeedbackCheckFailure(_("Você não possui um cargo pessoal."))

        # Adiciona o membro ao cargo pessoal
        try:
            personal_role = personal_roles[0]  # Assume que o membro só tem um cargo pessoal
            await member.add_roles(personal_role)
            await ctx.send(_("Membro {member.mention} adicionado ao seu cargo pessoal.").format(member=member))
        except discord.HTTPException as e:
            await ctx.send(_("Ocorreu um erro ao adicionar o membro ao cargo."))
            self.logger.error(f"Erro ao adicionar membro ao cargo: {e}")
