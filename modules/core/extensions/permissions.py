from base.mod_ext import ModuleExtension
from base.module import command
from base import command_registry
from base.loader import ModuleLoader

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors.exceptions.bad_request_400 import BadRequest

from sqlalchemy import select
from db import CommandPermission, User


class PermissionsExtension(ModuleExtension):
    @command('allow_cmd')
    async def allow_cmd(self, _, message: Message):
        self.loader: ModuleLoader
        args = message.text.split()
        if len(args) < 3:
            await message.reply(self.S["allow_cmd"]["args_err"])
            return

        cmd = args[1]
        roles = args[2:]
        if not command_registry.check_command(cmd):
            await message.reply(self.S["allow_cmd"]["command_not_found"])
            return

        db_cmd = self.loader.bot_db_session.scalar(select(CommandPermission).where(CommandPermission.command == cmd))
        if db_cmd is None:
            db_cmd = CommandPermission(command=cmd, module=command_registry.get_command_owner(cmd))
            self.loader.bot_db_session.add(db_cmd)

        db_cmd.allowed_for = ":".join(roles)
        self.loader.bot_db_session.commit()
        await message.reply(self.S["allow_cmd"]["ok"].format(command=cmd, roles=" ".join(roles)))

    @command('reset_perms')
    async def reset_perms(self, _, message: Message):
        self.loader: ModuleLoader
        args = message.text.split()
        if len(args) != 2:
            await message.reply(self.S["reset_perms"]["args_err"])
            return

        cmd = args[1]
        if not command_registry.check_command(cmd):
            await message.reply(self.S["reset_perms"]["command_not_found"])
            return

        db_cmd = self.loader.bot_db_session.scalar(select(CommandPermission).where(CommandPermission.command == cmd))
        if db_cmd is None:
            await message.reply(self.S["reset_perms"]["settings_not_found"])
            return

        self.loader.bot_db_session.delete(db_cmd)
        self.loader.bot_db_session.commit()

        await message.reply(self.S["reset_perms"]["ok"].format(command=cmd))

    @command('set_role')
    async def set_role_cmd(self, bot: Client, message: Message):
        self.loader: ModuleLoader
        args = message.text.split()
        if len(args) < 3:
            await message.reply(self.S["set_role"]["args_err"])
            return

        username, role = args[1:]
        try:
            user = await bot.get_users(username)
        except BadRequest:
            await message.reply(self.S["set_role"]["user_not_found"])
            return

        if role in ("chat_owner", "chat_admins", "owner", "all"):
            await message.reply(self.S["set_role"]["reserved_role"])
            return

        db_user = self.loader.bot_db_session.scalar(select(User).where(User.id == user.id))
        if db_user is None:
            db_user = User(id=user.id, name=user.username)
            self.loader.bot_db_session.add(db_user)

        db_user.role = role
        self.loader.bot_db_session.commit()
        await message.reply(self.S["set_role"]["ok"].format(user=user.username, role=role))

    @command('reset_role')
    async def reset_role(self, bot: Client, message: Message):
        self.loader: ModuleLoader
        args = message.text.split()
        if len(args) != 2:
            await message.reply(self.S["reset_role"]["args_err"])
            return

        username = args[1]
        try:
            user = await bot.get_users(username)
        except BadRequest:
            await message.reply(self.S["reset_role"]["user_not_found"])
            return

        db_user = self.loader.bot_db_session.scalar(select(User).where(User.id == user.id))
        if db_user is None:
            await message.reply(self.S["reset_role"]["settings_not_found"])
            return

        self.loader.bot_db_session.delete(db_user)
        self.loader.bot_db_session.commit()

        await message.reply(self.S["reset_role"]["ok"].format(user=user.username))

    @command('perms')
    async def perm_settings_cmd(self, _, message: Message):
        self.loader: ModuleLoader
        args = message.text.split()
        if len(args) != 2 or args[1] not in ("roles", "commands"):
            await message.reply(self.S["perm_settings"]["args_err"])
            return

        if args[1] == "commands":
            permissions = self.loader.bot_db_session.scalars(select(CommandPermission)).all()
            if len(permissions) == 0:
                text = self.S["perm_settings"]["no_perms"]
            else:
                text = self.S["perm_settings"]["perms_header"] + "\n"
                for perm in permissions:
                    text += f"/{perm.command}: <code>{perm.allowed_for.replace(':', ' ')}</code>\n"
        else:
            users = self.loader.bot_db_session.scalars(select(User)).all()
            if len(users) == 0:
                text = self.S["perm_settings"]["no_roles"]
            else:
                text = self.S["perm_settings"]["roles_header"] + "\n"
                for user in users:
                    text += f"@{user.name}: <code>{user.role}</code>\n"

        await message.reply(text)
