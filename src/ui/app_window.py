"""Minimalist modular GUI with 4 bottom-navigable tabs, Zapret file binding and diagnostics."""
import datetime
import logging
import os
import subprocess
import threading
from tkinter import filedialog
from typing import Dict, List, Optional
import customtkinter as ctk

from src.core.dns_manager import DNSManager, ping_dns_server
from src.core.happ_manager import HappManager
from src.core.uac_helper import is_admin, request_admin_elevation
from src.core.zapret_manager import ZapretManager
from src.services.diagnostics import NetworkDiagnostics
from src.services.parser import DNSWebsiteParser
from src.services.profiles_manager import ProfilesManager, is_valid_ipv4
from src.ui.components import THEME, AnimatedButton

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AddProfileDialog(ctk.CTkToplevel):
    """Minimalist dialog for saving a new DNS profile."""

    def __init__(self, parent, on_save_callback, initial_primary="", initial_secondary=""):
        super().__init__(parent)
        self.title("Сохранить профиль")
        self.geometry("380x360")
        self.resizable(False, False)
        self.configure(fg_color=THEME["bg_main"])
        self.transient(parent)
        self.grab_set()

        self.on_save_callback = on_save_callback

        ctk.CTkLabel(
            self,
            text="Новый DNS профиль",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(pady=(22, 14))

        self.entry_name = ctk.CTkEntry(
            self,
            placeholder_text="Название профиля",
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            width=300,
            height=32,
        )
        self.entry_name.pack(pady=6)

        self.entry_primary = ctk.CTkEntry(
            self,
            placeholder_text="Основной DNS IP",
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            width=300,
            height=32,
        )
        self.entry_primary.insert(0, initial_primary)
        self.entry_primary.pack(pady=6)

        self.entry_secondary = ctk.CTkEntry(
            self,
            placeholder_text="Второй DNS IP (опционально)",
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            width=300,
            height=32,
        )
        self.entry_secondary.insert(0, initial_secondary)
        self.entry_secondary.pack(pady=6)

        self.entry_desc = ctk.CTkEntry(
            self,
            placeholder_text="Описание (необязательно)",
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            width=300,
            height=32,
        )
        self.entry_desc.pack(pady=6)

        self.label_error = ctk.CTkLabel(self, text="", text_color="#F43F5E", font=ctk.CTkFont(size=11))
        self.label_error.pack(pady=2)

        self.btn_save = AnimatedButton(
            self,
            text="Сохранить",
            normal_bg=THEME["accent_primary"],
            hover_bg=THEME["accent_hover"],
            normal_border=THEME["accent_primary"],
            hover_border=THEME["accent_hover"],
            text_color="#0F172A",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=150,
            height=32,
            command=self._save,
        )
        self.btn_save.pack(pady=(6, 16))

    def _save(self):
        name = self.entry_name.get().strip()
        p = self.entry_primary.get().strip()
        s = self.entry_secondary.get().strip()
        desc = self.entry_desc.get().strip()

        if not name:
            self.label_error.configure(text="Введите название профиля")
            return
        if not is_valid_ipv4(p):
            self.label_error.configure(text="Неверный формат основного IP")
            return
        if s and not is_valid_ipv4(s):
            self.label_error.configure(text="Неверный формат второго IP")
            return

        self.on_save_callback(name, p, s, desc)
        self.destroy()


class MainWindow(ctk.CTk):
    """Main application window with 4 bottom-tabbed modules."""

    def __init__(self):
        super().__init__()

        self.title("DNS & VPN Helper")
        self.geometry("560x790")
        self.minsize(520, 680)
        self.configure(fg_color=THEME["bg_main"])

        self.profiles_mgr = ProfilesManager()
        self.zapret_config = ZapretManager.load_config()
        self.active_adapter: Optional[dict] = None
        self.current_tab = "dns"
        self.ping_cache: Dict[str, str] = {}

        self._build_header()
        self._build_tab_views()
        self._build_bottom_nav()

        # Show first tab
        self._switch_tab("dns")
        self._refresh_status_async()

    # ==========================================
    # 1. HEADER (Permanent top bar)
    # ==========================================
    def _build_header(self):
        self.header_frame = ctk.CTkFrame(
            self, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10
        )
        self.header_frame.pack(fill="x", padx=14, pady=(12, 6))

        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(fill="x", padx=14, pady=(10, 2))

        brand_box = ctk.CTkFrame(title_box, fg_color="transparent")
        brand_box.pack(side="left")

        self.dot_status = ctk.CTkLabel(
            brand_box,
            text="●",
            font=ctk.CTkFont(size=16),
            text_color=THEME["accent_primary"],
        )
        self.dot_status.pack(side="left", padx=(0, 6))

        self.lbl_title = ctk.CTkLabel(
            brand_box,
            text="DNS & VPN Helper",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME["text_primary"],
        )
        self.lbl_title.pack(side="left")

        self.btn_refresh = AnimatedButton(
            title_box,
            text="🔄 Обновить",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(size=11),
            width=95,
            height=28,
            command=self._refresh_status_async,
        )
        self.btn_refresh.pack(side="right")

        # Subtitle info line
        sub_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        sub_box.pack(fill="x", padx=14, pady=(0, 8))

        self.lbl_adapter = ctk.CTkLabel(
            sub_box,
            text="Адаптер: сканирование сети...",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        )
        self.lbl_adapter.pack(side="left")

        self.lbl_header_mode = ctk.CTkLabel(
            sub_box,
            text="Режим: DHCP",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=THEME["text_accent"],
        )
        self.lbl_header_mode.pack(side="right")

    # ==========================================
    # 2. TAB CONTAINER & VIEWS
    # ==========================================
    def _build_tab_views(self):
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True, padx=6, pady=2)

        # Tab Frames
        self.view_dns = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self.view_zapret = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self.view_vpn = ctk.CTkScrollableFrame(self.container, fg_color="transparent")
        self.view_settings = ctk.CTkScrollableFrame(self.container, fg_color="transparent")

        self._init_dns_view()
        self._init_zapret_view()
        self._init_vpn_view()
        self._init_settings_view()

    # ------------------------------------------
    # VIEW 1: DNS & NETWORK
    # ------------------------------------------
    def _init_dns_view(self):
        v = self.view_dns

        # 1. Quick Switch Card
        card_quick = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_quick.pack(fill="x", padx=8, pady=4)
        c_quick = ctk.CTkFrame(card_quick, fg_color="transparent")
        c_quick.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(c_quick, text="Быстрое переключение DNS", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")

        btn_row = ctk.CTkFrame(c_quick, fg_color="transparent")
        btn_row.pack(fill="x", pady=(8, 2))

        self.btn_dns_dhcp = AnimatedButton(
            btn_row,
            text="🌐 Прямой интернет (DHCP)",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_set_dhcp_clicked,
        )
        self.btn_dns_dhcp.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_dns_apply = AnimatedButton(
            btn_row,
            text="⚡ Применить DNS",
            normal_bg=THEME["accent_primary"],
            hover_bg=THEME["accent_hover"],
            normal_border=THEME["accent_primary"],
            hover_border=THEME["accent_hover"],
            text_color="#0F172A",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_apply_dns_clicked,
        )
        self.btn_dns_apply.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # 2. Custom DNS Input Box
        card_input = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_input.pack(fill="x", padx=8, pady=4)
        c_input = ctk.CTkFrame(card_input, fg_color="transparent")
        c_input.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(c_input, text="Ввод произвольных адресов DNS", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")

        inputs_row = ctk.CTkFrame(c_input, fg_color="transparent")
        inputs_row.pack(fill="x", pady=(6, 8))

        b_prim = ctk.CTkFrame(inputs_row, fg_color="transparent")
        b_prim.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkLabel(b_prim, text="Основной DNS:", font=ctk.CTkFont(size=10), text_color=THEME["text_secondary"]).pack(anchor="w")
        self.entry_primary_dns = ctk.CTkEntry(
            b_prim,
            placeholder_text="94.250.253.55",
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12),
            height=28,
        )
        self.entry_primary_dns.pack(fill="x", pady=(2, 0))

        b_sec = ctk.CTkFrame(inputs_row, fg_color="transparent")
        b_sec.pack(side="right", fill="x", expand=True, padx=(4, 0))
        ctk.CTkLabel(b_sec, text="Второй DNS (опц.):", font=ctk.CTkFont(size=10), text_color=THEME["text_secondary"]).pack(anchor="w")
        self.entry_secondary_dns = ctk.CTkEntry(
            b_sec,
            placeholder_text="195.133.25.16",
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12),
            height=28,
        )
        self.entry_secondary_dns.pack(fill="x", pady=(2, 0))

        actions_row = ctk.CTkFrame(c_input, fg_color="transparent")
        actions_row.pack(fill="x")

        self.btn_fetch_comss = AnimatedButton(
            actions_row,
            text="🔄 С сайта Comss",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=28,
            font=ctk.CTkFont(size=11),
            command=self._on_fetch_comss_clicked,
        )
        self.btn_fetch_comss.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_save_as_profile = AnimatedButton(
            actions_row,
            text="💾 Сохранить в профили",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=28,
            font=ctk.CTkFont(size=11),
            command=self._on_save_as_profile_clicked,
        )
        self.btn_save_as_profile.pack(side="right", fill="x", expand=True, padx=(4, 0))

        # 3. Profiles List Container
        card_list = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_list.pack(fill="x", padx=8, pady=4)
        c_list = ctk.CTkFrame(card_list, fg_color="transparent")
        c_list.pack(fill="x", padx=14, pady=10)

        header_list = ctk.CTkFrame(c_list, fg_color="transparent")
        header_list.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(header_list, text="Каталог DNS профилей", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(side="left")

        self.btn_ping_all = AnimatedButton(
            header_list,
            text="🏓 Проверить пинг",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=24,
            width=110,
            font=ctk.CTkFont(size=10),
            command=self._on_ping_all_dns,
        )
        self.btn_ping_all.pack(side="right")

        self.profiles_container = ctk.CTkFrame(c_list, fg_color="transparent")
        self.profiles_container.pack(fill="x")
        self._render_profiles_list()

    def _render_profiles_list(self):
        for widget in self.profiles_container.winfo_children():
            widget.destroy()

        for prof in self.profiles_mgr.get_all():
            p_id = prof.get("id", "")
            p_name = prof.get("name", "DNS")
            p_prim = prof.get("primary", "")
            p_sec = prof.get("secondary", "")
            ips_text = f"{p_prim}" + (f", {p_sec}" if p_sec else "")

            row = ctk.CTkFrame(self.profiles_container, fg_color=THEME["input_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=8)
            row.pack(fill="x", pady=3)

            r_content = ctk.CTkFrame(row, fg_color="transparent")
            r_content.pack(fill="x", padx=10, pady=6)

            info_col = ctk.CTkFrame(r_content, fg_color="transparent")
            info_col.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(info_col, text=p_name, font=ctk.CTkFont(size=12, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")
            ctk.CTkLabel(info_col, text=ips_text, font=ctk.CTkFont(family="Consolas", size=10), text_color=THEME["text_accent"]).pack(anchor="w")

            btn_col = ctk.CTkFrame(r_content, fg_color="transparent")
            btn_col.pack(side="right")

            # Ping badge
            ping_val = self.ping_cache.get(p_prim, "—")
            lbl_ping = ctk.CTkLabel(btn_col, text=f"{ping_val}", font=ctk.CTkFont(family="Consolas", size=10), text_color=THEME["text_secondary"], width=45)
            lbl_ping.pack(side="left", padx=4)

            # Apply button
            btn_use = AnimatedButton(
                btn_col,
                text="Выбрать",
                normal_bg=THEME["btn_neutral_bg"],
                hover_bg=THEME["accent_primary"],
                normal_border=THEME["card_border"],
                hover_border=THEME["accent_primary"],
                text_color=THEME["text_primary"],
                height=24,
                width=65,
                font=ctk.CTkFont(size=10),
                command=lambda p=prof: self._select_profile_and_fill(p),
            )
            btn_use.pack(side="left", padx=2)

            # Delete button (for custom profiles)
            if p_id not in ["comss", "adguard", "cloudflare", "google", "quad9", "yandex"]:
                btn_del = AnimatedButton(
                    btn_col,
                    text="✕",
                    normal_bg=THEME["input_bg"],
                    hover_bg=THEME["danger_bg"],
                    normal_border=THEME["card_border"],
                    hover_border=THEME["danger_border"],
                    text_color="#F43F5E",
                    height=24,
                    width=28,
                    font=ctk.CTkFont(size=10),
                    command=lambda pid=p_id: self._delete_profile(pid),
                )
                btn_del.pack(side="left", padx=(2, 0))

    def _select_profile_and_fill(self, prof: dict):
        self.entry_primary_dns.delete(0, "end")
        self.entry_primary_dns.insert(0, prof.get("primary", ""))
        self.entry_secondary_dns.delete(0, "end")
        self.entry_secondary_dns.insert(0, prof.get("secondary", ""))
        self._set_status_msg(f"Выбран профиль '{prof.get('name')}' (нажмите 'Применить DNS')", is_accent=True)

    def _delete_profile(self, pid: str):
        self.profiles_mgr.delete_profile(pid)
        self._render_profiles_list()
        self._set_status_msg("Профиль удален")

    def _on_ping_all_dns(self):
        self._set_status_msg("Замер пинга до всех DNS серверов...", is_accent=True)

        def task():
            for p in self.profiles_mgr.get_all():
                prim = p.get("primary")
                if prim:
                    ms = ping_dns_server(prim)
                    self.ping_cache[prim] = f"{ms}ms" if ms is not None else "timeout"
            self.after(0, self._render_profiles_list)
            self.after(0, lambda: self._set_status_msg("Проверка пинга DNS завершена"))

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------
    # VIEW 2: ZAPRET (DPI BYPASS)
    # ------------------------------------------
    def _init_zapret_view(self):
        v = self.view_zapret

        # 1. Status & Control Card
        card_ctrl = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_ctrl.pack(fill="x", padx=8, pady=4)
        c_ctrl = ctk.CTkFrame(card_ctrl, fg_color="transparent")
        c_ctrl.pack(fill="x", padx=14, pady=10)

        header_ctrl = ctk.CTkFrame(c_ctrl, fg_color="transparent")
        header_ctrl.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(header_ctrl, text="Обход блокировок DPI (winws)", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(side="left")
        self.lbl_zapret_status_badge = ctk.CTkLabel(header_ctrl, text="● Остановлен", font=ctk.CTkFont(size=11, weight="bold"), text_color=THEME["text_secondary"])
        self.lbl_zapret_status_badge.pack(side="right")

        btn_row = ctk.CTkFrame(c_ctrl, fg_color="transparent")
        btn_row.pack(fill="x", pady=(4, 6))

        self.btn_zapret_toggle = AnimatedButton(
            btn_row,
            text="▶ Включить Zapret",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_start_zapret_clicked,
        )
        self.btn_zapret_toggle.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_zapret_stop = AnimatedButton(
            btn_row,
            text="⏹ Остановить",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["danger_bg"],
            normal_border=THEME["card_border"],
            hover_border=THEME["danger_border"],
            text_color=THEME["text_secondary"],
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._on_stop_zapret_clicked,
            width=100,
        )
        self.btn_zapret_stop.pack(side="right", padx=(4, 0))

        # Preset selector
        preset_box = ctk.CTkFrame(c_ctrl, fg_color="transparent")
        preset_box.pack(fill="x", pady=(4, 4))

        ctk.CTkLabel(preset_box, text="Стратегия обхода:", font=ctk.CTkFont(size=11), text_color=THEME["text_secondary"]).pack(anchor="w")

        presets_dict = self.zapret_config.get("presets", {})
        self.zapret_preset_keys = list(presets_dict.keys())
        preset_display_names = [presets_dict[k].get("name", k) for k in self.zapret_preset_keys]

        self.combo_zapret_presets = ctk.CTkComboBox(
            preset_box,
            values=preset_display_names,
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            button_color=THEME["btn_neutral_bg"],
            button_hover_color=THEME["btn_neutral_hover"],
            text_color=THEME["text_primary"],
            command=self._on_zapret_preset_changed,
            height=28,
        )
        sel_key = self.zapret_config.get("selected_preset", "general")
        if sel_key in presets_dict:
            self.combo_zapret_presets.set(presets_dict[sel_key].get("name", sel_key))
        elif preset_display_names:
            self.combo_zapret_presets.set(preset_display_names[0])
        self.combo_zapret_presets.pack(fill="x", pady=(2, 4))

        # Editable Command Line Arguments
        ctk.CTkLabel(c_ctrl, text="Параметры запуска winws.exe:", font=ctk.CTkFont(size=10), text_color=THEME["text_secondary"]).pack(anchor="w")
        self.entry_zapret_args = ctk.CTkEntry(
            c_ctrl,
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=10),
            height=28,
        )
        self.entry_zapret_args.pack(fill="x", pady=(2, 0))
        self._sync_zapret_args_input()

        # 2. File Bindings & Components Card
        card_files = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_files.pack(fill="x", padx=8, pady=4)
        c_files = ctk.CTkFrame(card_files, fg_color="transparent")
        c_files.pack(fill="x", padx=14, pady=10)

        header_f = ctk.CTkFrame(c_files, fg_color="transparent")
        header_f.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(header_f, text="Привязка файлов и компонентов", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(side="left")

        btn_f_row = ctk.CTkFrame(header_f, fg_color="transparent")
        btn_f_row.pack(side="right")

        self.btn_browse_zapret = AnimatedButton(
            btn_f_row,
            text="Выбрать папку",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=24,
            width=90,
            font=ctk.CTkFont(size=10),
            command=self._on_choose_zapret_folder,
        )
        self.btn_browse_zapret.pack(side="left", padx=(0, 4))

        self.btn_open_zapret_dir = AnimatedButton(
            btn_f_row,
            text="📂 Проводник",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=24,
            width=80,
            font=ctk.CTkFont(size=10),
            command=self._on_open_zapret_explorer,
        )
        self.btn_open_zapret_dir.pack(side="left")

        self.lbl_zapret_dir_path = ctk.CTkLabel(
            c_files,
            text=f"Папка: {self.zapret_config.get('zapret_dir', 'tools/zapret')}",
            font=ctk.CTkFont(size=10),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.lbl_zapret_dir_path.pack(fill="x", pady=(0, 6))

        # Checklist of components
        self.zapret_components_box = ctk.CTkFrame(c_files, fg_color=THEME["input_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=8)
        self.zapret_components_box.pack(fill="x", pady=4)

        self.lbl_status_winws = ctk.CTkLabel(self.zapret_components_box, text="winws.exe: ❌", font=ctk.CTkFont(size=11), text_color=THEME["text_secondary"])
        self.lbl_status_winws.pack(anchor="w", padx=10, pady=(6, 2))

        self.lbl_status_windivert_dll = ctk.CTkLabel(self.zapret_components_box, text="WinDivert.dll: ❌", font=ctk.CTkFont(size=11), text_color=THEME["text_secondary"])
        self.lbl_status_windivert_dll.pack(anchor="w", padx=10, pady=2)

        self.lbl_status_windivert_sys = ctk.CTkLabel(self.zapret_components_box, text="WinDivert64.sys: ❌", font=ctk.CTkFont(size=11), text_color=THEME["text_secondary"])
        self.lbl_status_windivert_sys.pack(anchor="w", padx=10, pady=(2, 6))

        # Hostlist dropdown selector
        hostlist_row = ctk.CTkFrame(c_files, fg_color="transparent")
        hostlist_row.pack(fill="x", pady=(6, 2))
        ctk.CTkLabel(hostlist_row, text="Файл хостлиста (.txt):", font=ctk.CTkFont(size=11), text_color=THEME["text_secondary"]).pack(side="left", padx=(0, 8))

        self.combo_hostlists = ctk.CTkComboBox(
            hostlist_row,
            values=["(Автоопределение)"],
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            button_color=THEME["btn_neutral_bg"],
            button_hover_color=THEME["btn_neutral_hover"],
            text_color=THEME["text_primary"],
            height=26,
        )
        self.combo_hostlists.pack(side="left", fill="x", expand=True)

        # 3. Log Console Card
        card_log = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_log.pack(fill="x", padx=8, pady=4)
        c_log = ctk.CTkFrame(card_log, fg_color="transparent")
        c_log.pack(fill="x", padx=14, pady=10)

        header_l = ctk.CTkFrame(c_log, fg_color="transparent")
        header_l.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(header_l, text="Логи работы Zapret", font=ctk.CTkFont(size=12, weight="bold"), text_color=THEME["text_primary"]).pack(side="left")

        self.txt_zapret_log = ctk.CTkTextbox(
            c_log,
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            border_width=1,
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(family="Consolas", size=10),
            height=110,
        )
        self.txt_zapret_log.pack(fill="x", pady=(2, 0))

    def _sync_zapret_args_input(self):
        sel_display_name = self.combo_zapret_presets.get()
        presets_dict = self.zapret_config.get("presets", {})
        for k, v in presets_dict.items():
            if v.get("name") == sel_display_name or k == sel_display_name:
                self.entry_zapret_args.delete(0, "end")
                self.entry_zapret_args.insert(0, v.get("args", ""))
                break

    def _on_zapret_preset_changed(self, _):
        self._sync_zapret_args_input()

    def _on_open_zapret_explorer(self):
        folder = self.zapret_config.get("zapret_dir", "tools/zapret")
        if not os.path.isabs(folder):
            from src.core.path_helper import get_base_dir
            folder = os.path.join(get_base_dir(), folder)
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    # ------------------------------------------
    # VIEW 3: HAPP VPN
    # ------------------------------------------
    def _init_vpn_view(self):
        v = self.view_vpn

        # 1. State Card
        card_state = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_state.pack(fill="x", padx=8, pady=4)
        c_state = ctk.CTkFrame(card_state, fg_color="transparent")
        c_state.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(c_state, text="Состояние клиента Happ VPN", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")

        self.lbl_vpn_proc_info = ctk.CTkLabel(c_state, text="Процесс Happ.exe: Определение...", font=ctk.CTkFont(size=12), text_color=THEME["text_secondary"])
        self.lbl_vpn_proc_info.pack(anchor="w", pady=(6, 2))

        self.lbl_vpn_service_info = ctk.CTkLabel(c_state, text="Служба HappService: Определение...", font=ctk.CTkFont(size=12), text_color=THEME["text_secondary"])
        self.lbl_vpn_service_info.pack(anchor="w", pady=(0, 6))

        self.lbl_vpn_path = ctk.CTkLabel(
            c_state,
            text=f"Путь: {HappManager.find_executable() or 'Не найден'}",
            font=ctk.CTkFont(size=10),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.lbl_vpn_path.pack(fill="x", pady=(0, 8))

        # Main Big Action
        self.btn_launch_happ = AnimatedButton(
            c_state,
            text="🚀 Включить VPN Режим (Запустить / Открыть Happ)",
            normal_bg=THEME["accent_primary"],
            hover_bg=THEME["accent_hover"],
            normal_border=THEME["accent_primary"],
            hover_border=THEME["accent_hover"],
            text_color="#0F172A",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_vpn_mode_clicked,
        )
        self.btn_launch_happ.pack(fill="x", pady=(0, 4))

        # 2. Controls & Utilities Card
        card_actions = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_actions.pack(fill="x", padx=8, pady=4)
        c_act = ctk.CTkFrame(card_actions, fg_color="transparent")
        c_act.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(c_act, text="Действия и службы", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")

        btn_grid = ctk.CTkFrame(c_act, fg_color="transparent")
        btn_grid.pack(fill="x", pady=(8, 4))

        self.btn_restart_service = AnimatedButton(
            btn_grid,
            text="🔄 Перезапустить HappService",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._on_restart_happ_service,
        )
        self.btn_restart_service.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_kill_happ = AnimatedButton(
            btn_grid,
            text="⏹ Закрыть Happ",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["danger_bg"],
            normal_border=THEME["card_border"],
            hover_border=THEME["danger_border"],
            text_color=THEME["text_secondary"],
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._on_kill_happ_clicked,
            width=110,
        )
        self.btn_kill_happ.pack(side="right", padx=(4, 0))

        # Open Windows Network Adapter Control panel
        self.btn_open_ncpa = AnimatedButton(
            c_act,
            text="🌐 Сетевые подключения Windows (ncpa.cpl)",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=28,
            font=ctk.CTkFont(size=10),
            command=lambda: subprocess.Popen(["ncpa.cpl"], shell=True),
        )
        self.btn_open_ncpa.pack(fill="x", pady=(6, 0))

    def _on_restart_happ_service(self):
        self._set_status_msg("Перезапуск службы HappService...", is_accent=True)

        def task():
            success, msg = HappManager.restart_service()
            self.after(0, lambda: self._set_status_msg(msg, is_accent=success, is_error=not success))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_kill_happ_clicked(self):
        self._set_status_msg("Завершение процесса Happ.exe...")

        def task():
            stopped = HappManager.stop()
            msg = "Happ.exe завершен" if stopped else "Не удалось завершить Happ"
            self.after(0, lambda: self._set_status_msg(msg))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------
    # VIEW 4: DIAGNOSTICS & SETTINGS
    # ------------------------------------------
    def _init_settings_view(self):
        v = self.view_settings

        # 1. Network Telemetry Card
        card_telem = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_telem.pack(fill="x", padx=8, pady=4)
        c_telem = ctk.CTkFrame(card_telem, fg_color="transparent")
        c_telem.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(c_telem, text="Сетевая диагностика и статус", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")

        ip_row = ctk.CTkFrame(c_telem, fg_color="transparent")
        ip_row.pack(fill="x", pady=(6, 2))

        self.lbl_external_ip = ctk.CTkLabel(ip_row, text="Внешний IP: —", font=ctk.CTkFont(family="Consolas", size=12), text_color=THEME["text_accent"])
        self.lbl_external_ip.pack(side="left")

        self.btn_get_ip = AnimatedButton(
            ip_row,
            text="Узнать IP",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=24,
            width=75,
            font=ctk.CTkFont(size=10),
            command=self._on_check_external_ip,
        )
        self.btn_get_ip.pack(side="right")

        self.lbl_uac_status = ctk.CTkLabel(c_telem, text="Права администратора: ...", font=ctk.CTkFont(size=11), text_color=THEME["text_secondary"])
        self.lbl_uac_status.pack(anchor="w", pady=(2, 4))

        # 2. Service Latency & Connectivity Test Card
        card_ping = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_ping.pack(fill="x", padx=8, pady=4)
        c_ping = ctk.CTkFrame(card_ping, fg_color="transparent")
        c_ping.pack(fill="x", padx=14, pady=10)

        header_p = ctk.CTkFrame(c_ping, fg_color="transparent")
        header_p.pack(fill="x", pady=(0, 6))

        ctk.CTkLabel(header_p, text="Проверка доступности сервисов", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(side="left")

        self.btn_test_all = AnimatedButton(
            header_p,
            text="⚡ Тест связи",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=24,
            width=90,
            font=ctk.CTkFont(size=10),
            command=self._on_test_connectivity,
        )
        self.btn_test_all.pack(side="right")

        self.services_container = ctk.CTkFrame(c_ping, fg_color="transparent")
        self.services_container.pack(fill="x")
        self.service_labels: Dict[str, ctk.CTkLabel] = {}
        for s_name in ["YouTube", "Discord", "Telegram", "GitHub", "Google"]:
            s_row = ctk.CTkFrame(self.services_container, fg_color=THEME["input_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=6)
            s_row.pack(fill="x", pady=2)
            c = ctk.CTkFrame(s_row, fg_color="transparent")
            c.pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(c, text=s_name, font=ctk.CTkFont(size=11), text_color=THEME["text_primary"]).pack(side="left")
            val_lbl = ctk.CTkLabel(c, text="—", font=ctk.CTkFont(family="Consolas", size=11), text_color=THEME["text_secondary"])
            val_lbl.pack(side="right")
            self.service_labels[s_name] = val_lbl

        # 3. System Utilities Card
        card_sys = ctk.CTkFrame(v, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10)
        card_sys.pack(fill="x", padx=8, pady=4)
        c_sys = ctk.CTkFrame(card_sys, fg_color="transparent")
        c_sys.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(c_sys, text="Системные утилиты", font=ctk.CTkFont(size=13, weight="bold"), text_color=THEME["text_primary"]).pack(anchor="w")

        sys_btns = ctk.CTkFrame(c_sys, fg_color="transparent")
        sys_btns.pack(fill="x", pady=(6, 2))

        self.btn_flush_dns = AnimatedButton(
            sys_btns,
            text="🧹 Очистить кэш DNS (flushdns)",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=30,
            font=ctk.CTkFont(size=11),
            command=self._on_flush_dns_clicked,
        )
        self.btn_flush_dns.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_relaunch_uac = AnimatedButton(
            sys_btns,
            text="🛡️ Перезапуск от Admin",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=30,
            width=140,
            font=ctk.CTkFont(size=11),
            command=request_admin_elevation,
        )
        self.btn_relaunch_uac.pack(side="right", padx=(4, 0))

    def _on_check_external_ip(self):
        self.lbl_external_ip.configure(text="Внешний IP: запрос...")

        def task():
            success, info = NetworkDiagnostics.get_external_ip()
            self.after(0, lambda: self.lbl_external_ip.configure(text=f"Внешний IP: {info}"))

        threading.Thread(target=task, daemon=True).start()

    def _on_test_connectivity(self):
        self._set_status_msg("Тестирование соединения с сервисами...", is_accent=True)
        for lbl in self.service_labels.values():
            lbl.configure(text="...", text_color=THEME["text_secondary"])

        def task():
            res = NetworkDiagnostics.test_all_services()

            def update_ui():
                for name, ms in res.items():
                    if name in self.service_labels:
                        if ms is not None:
                            self.service_labels[name].configure(text=f"{ms} ms", text_color=THEME["success_dot"])
                        else:
                            self.service_labels[name].configure(text="Недоступен ❌", text_color="#F43F5E")
                self._set_status_msg("Тест доступности сервисов завершен")

            self.after(0, update_ui)

        threading.Thread(target=task, daemon=True).start()

    def _on_flush_dns_clicked(self):
        self._set_status_msg("Очистка системного кэша DNS...")

        def task():
            success, msg = NetworkDiagnostics.flush_dns()
            self.after(0, lambda: self._set_status_msg(msg, is_accent=success, is_error=not success))

        threading.Thread(target=task, daemon=True).start()

    # ==========================================
    # 3. BOTTOM NAVIGATION MENU
    # ==========================================
    def _build_bottom_nav(self):
        # Bottom status bar
        self.status_bar_frame = ctk.CTkFrame(
            self, fg_color=THEME["bg_main"], border_color=THEME["card_border"], border_width=1, corner_radius=0, height=26
        )
        self.status_bar_frame.pack(side="bottom", fill="x")

        self.lbl_status_msg = ctk.CTkLabel(
            self.status_bar_frame,
            text="Готово к работе",
            font=ctk.CTkFont(size=10),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.lbl_status_msg.pack(fill="x", padx=16, pady=2)

        # Tabbar container
        self.nav_frame = ctk.CTkFrame(
            self, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=0, height=52
        )
        self.nav_frame.pack(side="bottom", fill="x")

        tabs_data = [
            ("dns", "🌐 DNS & Сеть"),
            ("zapret", "🛡️ Zapret"),
            ("vpn", "🚀 Happ VPN"),
            ("settings", "⚙️ Инфо & Тест"),
        ]

        self.nav_buttons: Dict[str, AnimatedButton] = {}

        for key, title in tabs_data:
            btn = AnimatedButton(
                self.nav_frame,
                text=title,
                normal_bg=THEME["card_bg"],
                hover_bg=THEME["btn_neutral_bg"],
                normal_border=THEME["card_bg"],
                hover_border=THEME["accent_primary"],
                text_color=THEME["text_secondary"],
                font=ctk.CTkFont(size=11, weight="bold"),
                corner_radius=0,
                border_width=0,
                height=48,
                command=lambda k=key: self._switch_tab(k),
            )
            btn.pack(side="left", fill="both", expand=True)
            self.nav_buttons[key] = btn

    def _switch_tab(self, tab_key: str):
        self.current_tab = tab_key

        # Hide all view frames
        self.view_dns.pack_forget()
        self.view_zapret.pack_forget()
        self.view_vpn.pack_forget()
        self.view_settings.pack_forget()

        # Update tabbar buttons styling
        for k, btn in self.nav_buttons.items():
            if k == tab_key:
                btn.set_colors(
                    normal_bg=THEME["tab_active_bg"],
                    hover_bg=THEME["tab_active_bg"],
                    normal_border=THEME["accent_primary"],
                    hover_border=THEME["accent_primary"],
                )
                btn.configure(text_color=THEME["accent_primary"])
            else:
                btn.set_colors(
                    normal_bg=THEME["card_bg"],
                    hover_bg=THEME["btn_neutral_bg"],
                    normal_border=THEME["card_bg"],
                    hover_border=THEME["card_border"],
                )
                btn.configure(text_color=THEME["text_secondary"])

        # Show target view frame
        if tab_key == "dns":
            self.view_dns.pack(fill="both", expand=True)
        elif tab_key == "zapret":
            self.view_zapret.pack(fill="both", expand=True)
            self._refresh_zapret_files_status()
        elif tab_key == "vpn":
            self.view_vpn.pack(fill="both", expand=True)
        elif tab_key == "settings":
            self.view_settings.pack(fill="both", expand=True)

    def _set_status_msg(self, msg: str, is_accent: bool = False, is_error: bool = False):
        if is_error:
            color = "#F43F5E"
        elif is_accent:
            color = THEME["accent_primary"]
        else:
            color = THEME["text_secondary"]
        self.lbl_status_msg.configure(text=msg, text_color=color)

    # ==========================================
    # 4. BACKGROUND REFRESH & TELEMETRY
    # ==========================================
    def _refresh_status_async(self):
        def task():
            adapter = DNSManager.get_active_adapter()
            happ_running = HappManager.is_running()
            happ_service_running = HappManager.is_service_running()
            happ_proc_info = HappManager.get_process_info()
            zapret_running = ZapretManager.is_running()
            winws_found = ZapretManager.find_winws_binary() is not None
            zapret_files = ZapretManager.scan_zapret_files()
            logs = ZapretManager.get_logs()

            self.after(
                0,
                lambda: self._update_status_ui(
                    adapter,
                    happ_running,
                    happ_service_running,
                    happ_proc_info,
                    zapret_running,
                    winws_found,
                    zapret_files,
                    logs,
                ),
            )

        threading.Thread(target=task, daemon=True).start()

    def _update_status_ui(
        self,
        adapter: Optional[dict],
        happ_running: bool,
        happ_service_running: bool,
        happ_proc_info: Optional[dict],
        zapret_running: bool,
        winws_found: bool,
        zapret_files: dict,
        logs: str,
    ):
        self.active_adapter = adapter
        if adapter:
            desc = adapter.get("description") or adapter.get("alias")
            self.lbl_adapter.configure(text=f"Адаптер: {desc} (#{adapter['index']})")

            dns_servers = adapter.get("ipv4_dns", [])
            is_dhcp = adapter.get("is_dhcp", True)

            if is_dhcp:
                self.lbl_header_mode.configure(text="Режим: DHCP", text_color=THEME["success_dot"])
                self.dot_status.configure(text_color=THEME["success_dot"])
            else:
                matched_name = None
                for p in self.profiles_mgr.get_all():
                    p_ips = [p.get("primary")]
                    if p.get("secondary"):
                        p_ips.append(p.get("secondary"))
                    if dns_servers == p_ips or (len(dns_servers) > 0 and dns_servers[0] == p.get("primary")):
                        matched_name = p["name"]
                        break

                label = f"Режим: {matched_name}" if matched_name else "Режим: Свой DNS"
                self.lbl_header_mode.configure(text=label, text_color=THEME["accent_primary"])
                self.dot_status.configure(text_color=THEME["accent_primary"])
        else:
            self.lbl_adapter.configure(text="Адаптер: Сеть не обнаружена")
            self.lbl_header_mode.configure(text="Режим: —", text_color=THEME["text_secondary"])
            self.dot_status.configure(text_color=THEME["text_secondary"])

        # Zapret Status
        if zapret_running:
            self.lbl_zapret_status_badge.configure(text="● Активен", text_color=THEME["success_dot"])
            self.btn_zapret_toggle.configure(text="🔄 Перезапустить Zapret")
        elif not winws_found:
            self.lbl_zapret_status_badge.configure(text="⚠️ winws.exe не найден", text_color="#F43F5E")
            self.btn_zapret_toggle.configure(text="▶ Включить Zapret")
        else:
            self.lbl_zapret_status_badge.configure(text="● Остановлен", text_color=THEME["text_secondary"])
            self.btn_zapret_toggle.configure(text="▶ Включить Zapret")

        # Zapret Files Status
        self.lbl_status_winws.configure(
            text="winws.exe: " + ("✅ Найдено" if zapret_files.get("has_winws") else "❌ Не найдено"),
            text_color=THEME["success_dot"] if zapret_files.get("has_winws") else "#F43F5E",
        )
        self.lbl_status_windivert_dll.configure(
            text="WinDivert.dll: " + ("✅ Найдено" if zapret_files.get("has_windivert_dll") else "❌ Не найдено"),
            text_color=THEME["success_dot"] if zapret_files.get("has_windivert_dll") else "#F43F5E",
        )
        self.lbl_status_windivert_sys.configure(
            text="WinDivert64.sys: " + ("✅ Найдено" if zapret_files.get("has_windivert_sys") else "❌ Не найдено"),
            text_color=THEME["success_dot"] if zapret_files.get("has_windivert_sys") else "#F43F5E",
        )

        # Hostlists in combo
        hostlists = zapret_files.get("hostlists", [])
        if hostlists:
            self.combo_hostlists.configure(values=hostlists)
            if self.combo_hostlists.get() not in hostlists:
                self.combo_hostlists.set(hostlists[0])

        # Zapret Logs
        if logs:
            self.txt_zapret_log.delete("1.0", "end")
            self.txt_zapret_log.insert("1.0", logs)
            self.txt_zapret_log.see("end")

        # Happ VPN Status
        if happ_running:
            pid_str = f"PID: {happ_proc_info.get('pid')}, Память: {happ_proc_info.get('mem')}" if happ_proc_info else "Работает"
            self.lbl_vpn_proc_info.configure(text=f"Процесс Happ.exe: 🟢 Запущен ({pid_str})", text_color=THEME["success_dot"])
        else:
            self.lbl_vpn_proc_info.configure(text="Процесс Happ.exe: ⚪ Не запущен", text_color=THEME["text_secondary"])

        if happ_service_running:
            self.lbl_vpn_service_info.configure(text="Служба HappService: 🟢 Запущена", text_color=THEME["success_dot"])
        else:
            self.lbl_vpn_service_info.configure(text="Служба HappService: ⚪ Остановлена", text_color=THEME["text_secondary"])

        # UAC
        adm = is_admin()
        self.lbl_uac_status.configure(
            text=f"Права администратора: {'✅ Активны' if adm else '⚠️ Ограниченный режим (UAC не получен)'}",
            text_color=THEME["success_dot"] if adm else "#F43F5E",
        )

    def _refresh_zapret_files_status(self):
        zf = ZapretManager.scan_zapret_files()
        self.lbl_status_winws.configure(text="winws.exe: " + ("✅ Найдено" if zf.get("has_winws") else "❌ Не найдено"))
        self.lbl_status_windivert_dll.configure(text="WinDivert.dll: " + ("✅ Найдено" if zf.get("has_windivert_dll") else "❌ Не найдено"))
        self.lbl_status_windivert_sys.configure(text="WinDivert64.sys: " + ("✅ Найдено" if zf.get("has_windivert_sys") else "❌ Не найдено"))

    # ==========================================
    # 5. USER ACTION HANDLERS
    # ==========================================
    def _on_set_dhcp_clicked(self):
        self._set_status_msg("Переключение на автополучение DNS (DHCP)...", is_accent=True)

        def task():
            success, msg = DNSManager.reset_to_dhcp()
            self.after(0, lambda: self._set_status_msg(msg, is_accent=success, is_error=not success))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_apply_dns_clicked(self):
        primary = self.entry_primary_dns.get().strip()
        secondary = self.entry_secondary_dns.get().strip()

        if not primary:
            self._set_status_msg("Укажите хотя бы основной IP адрес DNS", is_error=True)
            return

        if not is_valid_ipv4(primary):
            self._set_status_msg(f"Некорректный IP адрес: {primary}", is_error=True)
            return

        ips = [primary]
        if secondary:
            if not is_valid_ipv4(secondary):
                self._set_status_msg(f"Некорректный второй IP: {secondary}", is_error=True)
                return
            ips.append(secondary)

        self._set_status_msg(f"Установка DNS: {', '.join(ips)}...", is_accent=True)

        def task():
            success, msg = DNSManager.set_dns(ips)
            self.after(0, lambda: self._set_status_msg(msg, is_accent=success, is_error=not success))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_fetch_comss_clicked(self):
        self._set_status_msg("Запрос актуальных DNS с comss.one/dns...", is_accent=True)

        def task():
            success, ips, msg = DNSWebsiteParser.fetch_comss_dns()
            if success and ips:
                p_ip = ips[0]
                s_ip = ips[1] if len(ips) > 1 else ""
                self.profiles_mgr.update_ips("comss", p_ip, s_ip)

                def update_ui():
                    self.entry_primary_dns.delete(0, "end")
                    self.entry_primary_dns.insert(0, p_ip)
                    self.entry_secondary_dns.delete(0, "end")
                    self.entry_secondary_dns.insert(0, s_ip)
                    self._render_profiles_list()
                    self._set_status_msg(f"Получены DNS Comss: {', '.join(ips)}", is_accent=True)

                self.after(0, update_ui)
            else:
                self.after(0, lambda: self._set_status_msg(f"Ошибка получения: {msg}", is_error=True))

        threading.Thread(target=task, daemon=True).start()

    def _on_save_as_profile_clicked(self):
        primary = self.entry_primary_dns.get().strip()
        secondary = self.entry_secondary_dns.get().strip()

        def save_callback(name, p, s, desc):
            new_p = self.profiles_mgr.add_profile(name, p, s, desc)
            if new_p:
                self._render_profiles_list()
                self._set_status_msg(f"Профиль '{name}' сохранен", is_accent=True)

        AddProfileDialog(self, save_callback, initial_primary=primary, initial_secondary=secondary)

    def _on_start_zapret_clicked(self):
        sel_display_name = self.combo_zapret_presets.get()
        presets_dict = self.zapret_config.get("presets", {})
        preset_key = "general"
        for k, v in presets_dict.items():
            if v.get("name") == sel_display_name or k == sel_display_name:
                preset_key = k
                break

        custom_args = self.entry_zapret_args.get().strip()
        self._set_status_msg(f"Запуск Zapret ({sel_display_name})...", is_accent=True)

        def task():
            success, msg = ZapretManager.start(preset_key, custom_args=custom_args)
            self.after(0, lambda: self._set_status_msg(msg, is_accent=success, is_error=not success))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_stop_zapret_clicked(self):
        self._set_status_msg("Остановка Zapret...")

        def task():
            success, msg = ZapretManager.stop()
            self.after(0, lambda: self._set_status_msg(msg, is_error=not success))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_choose_zapret_folder(self):
        folder = filedialog.askdirectory(title="Выберите папку с Zapret (где находится winws.exe)")
        if folder:
            self.zapret_config["zapret_dir"] = folder
            ZapretManager.save_config(self.zapret_config)
            self.lbl_zapret_dir_path.configure(text=f"Папка: {folder}")
            binary = ZapretManager.find_winws_binary(folder)
            if binary:
                self._set_status_msg(f"Найдено: {os.path.basename(binary)}", is_accent=True)
            else:
                self._set_status_msg("winws.exe не найден в выбранной папке", is_error=True)
            self._refresh_status_async()

    def _on_vpn_mode_clicked(self):
        self._set_status_msg("Активация VPN: сброс DNS, пауза Zapret и запуск Happ...", is_accent=True)

        def task():
            DNSManager.reset_to_dhcp()
            if ZapretManager.is_running():
                ZapretManager.stop()
            launched = HappManager.launch_or_focus()
            msg = "VPN режим активен (Happ запущен)" if launched else "DNS сброшен, но не удалось запустить Happ"
            self.after(0, lambda: self._set_status_msg(msg, is_accent=launched, is_error=not launched))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()
