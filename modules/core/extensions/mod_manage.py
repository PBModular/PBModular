from base.mod_ext import ModuleExtension
from base.module import command, callback_query, allowed_for, Permissions, InfoFile
from base.loader import ModuleLoader

from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from pyrogram import filters
from urllib.parse import urlparse
import requests
import os
import shutil
import requirements
from typing import Optional
from config import config


class ModManageExtension(ModuleExtension):
    def on_init(self):
        self.install_confirmations = {}
        self.update_confirmations = {}

    @allowed_for("owner")
    @command("mod_install")
    async def mod_install_cmd(self, _, message: Message):
        """Install new module from git repo"""
        self.loader: ModuleLoader
        if len(message.text.split()) == 1:
            await message.reply(self.S["install"]["args_err"])
            return
        
        arg = message.text.split()[1] 
        if "http://" in arg or "https://" in arg:
            url = arg
        else:
            url = f"https://github.com/{config.name_org}/{arg}"
        
        name = urlparse(url).path.split("/")[-1].removesuffix(".git")

        msg = await message.reply(self.S["install"]["start"].format(name))

        # Start downloading
        code, stdout = self.loader.install_from_git(url)
        if code != 0:
            await msg.edit_text(self.S["install"]["down_err"].format(name, stdout))
            return

        # Parse info file
        info_file = InfoFile.from_yaml_file(f"{os.getcwd()}/modules/{name}/info.yaml")
        info = info_file.info
        permissions = info_file.permissions

        text = (
            self.S["install"]["confirm"].format(
                name=name, author=info.author, version=info.version
            )
            + "\n"
        )

        # Check for permissions
        perm_list = ""
        for p in permissions:
            perm_list += f"- {self.S['install']['perms'][p.value]}\n"

        if len(permissions) > 0:
            text += self.S["install"]["confirm_perms"].format(perms=perm_list)
        if Permissions.use_loader in permissions:
            text += self.S["install"]["confirm_warn_perms"]

        self.install_confirmations[msg.id] = [msg, name]

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        self.S["yes_btn"], callback_data=f"install_yes"
                    ),
                    InlineKeyboardButton(self.S["no_btn"], callback_data=f"install_no"),
                ]
            ]
        )
        await msg.edit_text(text, reply_markup=keyboard)

    @allowed_for("owner")
    @command("mods_list")
    async def mods_list_cmd(self, _, message: Message):
        """"List all modules in git-org"""
        if len(message.text.split()) == 1:
            acc_name = config.mod_org_name
        else:
            acc_name = message.text.split()[1]
        list_str = self.S["install"]["list"]["ok"].format(acc_name)
        err_list_str = self.S["install"]["list"]["error"]
        url = f"https://api.github.com/users/{acc_name}/repos"
        response = requests.get(url)
        repositories = []
    
        if response.status_code == 200:
            data = response.json()
            for repo in data:
                repositories.append(f'<code>{repo["name"]}</code>')
            msg = await message.reply(f"{list_str}\n" + ', '.join(repositories))
        else:
            await message.reply(err_list_str.format(response.status_code))
        


    @allowed_for("owner")
    @callback_query(filters.regex("install_yes"))
    async def install_yes(self, _, call: CallbackQuery):
        msg, name = self.install_confirmations[call.message.id]
        self.install_confirmations.pop(call.message.id)

        await call.answer()

        if os.path.exists(f"{os.getcwd()}/modules/{name}/requirements.txt"):
            # Install deps
            await msg.edit_text(self.S["install"]["down_reqs_next"].format(name))
            code, data = self.loader.install_deps(name, "modules")
            if code != 0:
                await msg.edit_text(self.S["install"]["reqs_err"].format(name, data))
                return

            # Load module
            result = self.loader.load_module(name)
            if result is None:
                await msg.edit_text(self.S["install"]["load_err"].format(name))
                return

            reqs_list = ""
            for req in data:
                reqs_list += f"- {req}"

            await msg.edit_text(self.S["install"]["end_reqs"].format(result, reqs_list))

        else:
            await msg.edit_text(self.S["install"]["down_end_next"].format(name))

            # Load module
            result = self.loader.load_module(name)
            if result is None:
                await msg.edit_text(self.S["install"]["load_err"].format(name))
                return

            await msg.edit_text(self.S["install"]["end"].format(result))

    @allowed_for("owner")
    @callback_query(filters.regex("install_no"))
    async def install_no(self, _, call: CallbackQuery):
        msg, name = self.install_confirmations[call.message.id]
        self.install_confirmations.pop(call.message.id)

        shutil.rmtree(f"./modules/{name}")
        await call.answer(self.S["install"]["aborted"])
        await msg.delete()

    @allowed_for("owner")
    @command("mod_uninstall")
    async def mod_uninstall_cmd(self, _, message: Message):
        """Uninstall module"""
        self.loader: ModuleLoader
        if len(message.text.split()) == 1:
            await message.reply(self.S["uninstall"]["args_err"])
            return

        name = " ".join(message.text.split()[1:])

        # Uninstall module
        int_name = self.loader.get_int_name(name)
        if int_name is None:
            await message.reply(self.S["uninstall"]["not_found"].format(name))
            return

        result = self.loader.uninstall_module(int_name)
        await message.reply(
            (
                self.S["uninstall"]["ok"] if result else self.S["uninstall"]["err"]
            ).format(name)
        )

    @allowed_for("owner")
    @command("mod_update")
    async def mod_update_cmd(self, _, message: Message):
        """Update module to the upstream version"""
        self.loader: ModuleLoader
        if len(message.text.split()) == 1:
            await message.reply(self.S["update"]["args_err"])
            return

        name = " ".join(message.text.split()[1:])
        int_name = self.loader.get_int_name(name)
        if int_name is None:
            await message.reply(self.S["uninstall"]["not_found"].format(name))
            return

        msg = await message.reply(self.S["install"]["start"].format(name))

        old_ver = self.loader.get_module_info(int_name).version
        old_reqs = None

        reqs_path = f"{os.getcwd()}/modules/{int_name}/requirements.txt"
        if os.path.exists(reqs_path):
            old_reqs = requirements.parse(open(reqs_path, encoding="utf-8"))

        code, stdout = self.loader.update_from_git(int_name, "modules")
        if code != 0:
            await msg.edit_text(self.S["update"]["err"].format(name=name, out=stdout))
            self.loader.revert_update(int_name, "modules")
            return

        # Parse info file
        try:
            info_file = InfoFile.from_yaml_file(
                f"{os.getcwd()}/modules/{int_name}/info.yaml"
            )
        except FileNotFoundError:
            return

        info = info_file.info
        permissions = info_file.permissions

        text = (
            self.S["update"]["confirm"].format(
                name=name, author=info.author, version=info.version
            )
            + "\n"
        )

        # Check for permissions
        perm_list = ""
        for p in permissions:
            perm_list += f"- {self.S['install']['perms'][p.value]}\n"

        if len(permissions) > 0:
            text += self.S["install"]["confirm_perms"].format(perms=perm_list)
        if Permissions.use_loader in permissions:
            text += self.S["install"]["confirm_warn_perms"]

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        self.S["yes_btn"], callback_data=f"update_yes"
                    ),
                    InlineKeyboardButton(self.S["no_btn"], callback_data=f"update_no"),
                ]
            ]
        )
        await msg.edit_text(text, reply_markup=keyboard)
        self.update_confirmations[msg.id] = [msg, name, int_name, old_ver, old_reqs]

    @allowed_for("owner")
    @callback_query(filters.regex("update_yes"))
    async def update_yes(self, _, call: CallbackQuery):
        self.loader: ModuleLoader
        msg, name, int_name, old_ver, old_reqs = self.update_confirmations[
            call.message.id
        ]
        await call.answer()

        try_again_keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        self.S["try_again_btn"], callback_data=f"update_yes"
                    ),
                    InlineKeyboardButton(
                        self.S["abort_btn"], callback_data=f"update_no"
                    ),
                ]
            ]
        )

        reqs_path = f"{os.getcwd()}/modules/{int_name}/requirements.txt"
        if os.path.exists(reqs_path):
            reqs = requirements.parse(open(reqs_path, encoding="utf-8"))
            del_reqs = []
            for req in old_reqs:
                found = False
                for new_req in reqs:
                    if req.name.lower() == new_req.name.lower():
                        found = True
                        break

                if not found:
                    del_reqs.append(req.name.lower())

            # Install deps
            await msg.edit_text(self.S["install"]["down_reqs_next"].format(name))
            code, data = self.loader.install_deps(int_name, "modules")
            if code != 0:
                await msg.edit_text(
                    self.S["install"]["reqs_err"].format(name, data),
                    reply_markup=try_again_keyboard,
                )
                return

            # Load module
            result = self.loader.load_module(int_name)
            if result is None:
                await msg.edit_text(
                    self.S["install"]["load_err"].format(name),
                    reply_markup=try_again_keyboard,
                )
                return

            # Cleanup
            self.loader.uninstall_packages(del_reqs)

            info = self.loader.get_module_info(int_name)
            text = (
                self.S["update"]["ok"].format(
                    name=result, old_ver=old_ver, new_ver=info.version, url=info.src_url
                )
                + "\n"
                + self.S["update"]["reqs"]
                + "\n"
            )

            for req in data:
                text += f"- {req}\n"

            await msg.edit_text(text)
        else:
            await msg.edit_text(self.S["install"]["down_end_next"].format(name))

            # Load module
            result = self.loader.load_module(int_name)
            if result is None:
                await msg.edit_text(
                    self.S["install"]["load_err"].format(name),
                    reply_markup=try_again_keyboard,
                )
                return

            info = self.loader.get_module_info(int_name)
            await msg.edit_text(
                self.S["update"]["ok"].format(
                    name=result, old_ver=old_ver, new_ver=info.version, url=info.src_url
                )
            )

        self.update_confirmations.pop(call.message.id)

    @allowed_for("owner")
    @callback_query(filters.regex("update_no"))
    async def update_no(self, _, call: CallbackQuery):
        msg, name, int_name, _, _ = self.update_confirmations[call.message.id]
        self.update_confirmations.pop(call.message.id)

        self.loader.revert_update(int_name, "modules")
        self.loader.load_module(int_name)

        await call.answer(self.S["update"]["abort"])
        await msg.delete()

    @allowed_for("owner")
    @command("mod_info")
    async def mod_info_cmd(self, _, message: Message):
        """Displays full info about module"""
        self.loader: ModuleLoader

        args = message.text.split()
        if len(args) != 2:
            await message.reply(self.S["info"]["args_err"], quote=True)
            return

        int_name = self.loader.get_int_name(args[-1])
        if int_name is None:
            await message.reply(self.S["info"]["not_found"], quote=True)
            return

        info = self.loader.get_module_info(int_name)
        text = self.S["info"]["header"].format(
            name=info.name, author=info.author, version=info.version
        )

        if info.src_url:
            text += self.S["info"]["src_url"].format(url=info.src_url)

        text += "\n" + self.S["info"]["description"].format(
            description=info.description
        )

        await message.reply(text, quote=True)
    
    async def mod_load(self, message: Message, name: str, silent = False, edit = False) -> Optional[str]:
        if edit:
            reply_func = message.edit_text
        else:
            reply_func = message.reply
        
        if self.loader.get_module(name):
            await reply_func(self.S["load"]["already_loaded_err"].format(name))
            return
        
        try:
            res = self.loader.load_module(name)
            if res is None:
                await reply_func(self.S["load"]["load_err"].format(name))
                return
        except FileNotFoundError:
            await reply_func(self.S["load"]["not_found"].format(name))
            return
        except:
            await reply_func(self.S["load"]["load_err"].format(name))
            return
        
        if not silent:
            await reply_func(self.S["load"]["ok"].format(res))
        
        return res

    async def mod_unload(self, message: Message, name: str, silent = False, edit = False) -> Optional[str]:
        if edit:
            reply_func = message.edit_text
        else:
            reply_func = message.reply

        if name.lower() == "core":
            await reply_func(self.S["unload"]["unload_core"])
            return
        
        int_name = self.loader.get_int_name(name)
        if int_name is None:
            await reply_func(self.S["unload"]["not_loaded_err"].format(name))
            return
        
        self.loader.unload_module(int_name)
        if not silent:
            await reply_func(self.S["unload"]["ok"].format(name))
        
        return int_name

    @allowed_for("owner")
    @command("mod_load")
    async def mod_load_cmd(self, _, message: Message):
        """Loads module if not loaded. Accepts directory name of a module"""
        args = message.text.split()
        if len(args) != 2:
            await message.reply(self.S["load"]["args_err"])
            return
        
        await self.mod_load(message, args[1])

    @allowed_for("owner")
    @command("mod_unload")
    async def mod_unload_cmd(self, _, message: Message):
        """Unloads module if it is loaded already"""
        args = message.text.split()
        if len(args) != 2:
            await message.reply(self.S["unload"]["args_err"])
            return False
        
        await self.mod_unload(message, args[1])
    
    @allowed_for("owner")
    @command("mod_reload")
    async def mod_reload_cmd(self, message: Message):
        args = message.text.split()
        if len(args) != 2:
            await message.reply(self.S["reload"]["args_err"])
            return
                
        int_name = await self.mod_unload(message, args[1], True, False)
        if int_name is None:
            return
        
        msg = await message.reply(self.S["reload"]["loading"].format(args[1]))
        name = await self.mod_load(msg, int_name, True, True)
        if name is None:
            return
        
        await msg.edit_text(self.S["reload"]["ok"].format(name))
