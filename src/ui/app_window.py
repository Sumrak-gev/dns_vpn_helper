"""Ultra-minimalist modern GUI for DNS & VPN Helper with 2-3 dark tones and animated controls."""
import logging
import os
import threading
from tkinter import filedialog
from typing import Optional
import customtkinter as ctk

from src.core.dns_manager import DNSManager
from src.core.happ_manager import HappManager
from src.core.zapret_manager import ZapretManager
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
            placeholder_text="Второй DNS IP (опц.)",
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
    """Main minimalist application window."""

    def __init__(self):
        super().__init__()

        self.title("DNS & VPN Helper")
        self.geometry("540x790")
        self.minsize(500, 680)
        self.configure(fg_color=THEME["bg_main"])

        self.profiles_mgr = ProfilesManager()
        self.zapret_config = ZapretManager.load_config()
        self.active_adapter: Optional[dict] = None

        self._build_ui()
        self._refresh_status_async()

    def _build_ui(self):
        # 1. Header (Minimalist bar)
        self.header_frame = ctk.CTkFrame(
            self, fg_color=THEME["card_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=10
        )
        self.header_frame.pack(fill="x", padx=16, pady=(14, 6))

        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(fill="x", padx=16, pady=(12, 2))

        # Brand title with subtle accent dot
        brand_container = ctk.CTkFrame(title_box, fg_color="transparent")
        brand_container.pack(side="left")

        self.dot_status = ctk.CTkLabel(
            brand_container,
            text="●",
            font=ctk.CTkFont(size=16),
            text_color=THEME["accent_primary"],
        )
        self.dot_status.pack(side="left", padx=(0, 6))

        title_lbl = ctk.CTkLabel(
            brand_container,
            text="DNS & VPN Helper",
            font=ctk.CTkFont(size=17, weight="bold"),
            text_color=THEME["text_primary"],
        )
        title_lbl.pack(side="left")

        # Smooth animated refresh button
        self.btn_refresh = AnimatedButton(
            title_box,
            text="Обновить",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            font=ctk.CTkFont(size=11),
            width=90,
            height=28,
            command=self._refresh_status_async,
        )
        self.btn_refresh.pack(side="right")

        self.lbl_adapter = ctk.CTkLabel(
            self.header_frame,
            text="Адаптер: сканирование сети...",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        )
        self.lbl_adapter.pack(anchor="w", padx=16, pady=(0, 10))

        # 2. Scrollable Content Area
        self.scroll_content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_content.pack(fill="both", expand=True, padx=8, pady=4)

        # 3. Status Card (Telemetry)
        self.status_card = ctk.CTkFrame(
            self.scroll_content,
            fg_color=THEME["card_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=10,
        )
        self.status_card.pack(fill="x", padx=8, pady=4)

        status_box = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_box.pack(fill="x", padx=14, pady=10)

        self.lbl_current_mode = ctk.CTkLabel(
            status_box,
            text="Режим: Определение...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=THEME["text_primary"],
        )
        self.lbl_current_mode.pack(anchor="w", pady=(0, 2))

        self.lbl_current_dns = ctk.CTkLabel(
            status_box,
            text="DNS: ...",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=THEME["text_accent"],
        )
        self.lbl_current_dns.pack(anchor="w", pady=(0, 4))

        substatus_row = ctk.CTkFrame(status_box, fg_color="transparent")
        substatus_row.pack(fill="x", pady=(2, 0))

        self.lbl_happ_status = ctk.CTkLabel(
            substatus_row,
            text="Happ VPN: —",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        )
        self.lbl_happ_status.pack(side="left", padx=(0, 16))

        self.lbl_zapret_status = ctk.CTkLabel(
            substatus_row,
            text="Zapret: —",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        )
        self.lbl_zapret_status.pack(side="left")

        # 4. Mode 1: Regular Internet (DHCP)
        self.frame_dhcp = ctk.CTkFrame(
            self.scroll_content,
            fg_color=THEME["card_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=10,
        )
        self.frame_dhcp.pack(fill="x", padx=8, pady=4)

        dhcp_content = ctk.CTkFrame(self.frame_dhcp, fg_color="transparent")
        dhcp_content.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            dhcp_content,
            text="1. Обычный интернет",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            dhcp_content,
            text="Автоматическое получение DNS от вашего роутера / провайдера (DHCP).",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        ).pack(anchor="w", pady=(1, 8))

        self.btn_set_dhcp = AnimatedButton(
            dhcp_content,
            text="Сбросить DNS на авто (DHCP)",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_set_dhcp_clicked,
        )
        self.btn_set_dhcp.pack(fill="x")

        # 5. Mode 2: DNS Profiles & Custom IP Input
        self.frame_dns = ctk.CTkFrame(
            self.scroll_content,
            fg_color=THEME["card_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=10,
        )
        self.frame_dns.pack(fill="x", padx=8, pady=4)

        dns_content = ctk.CTkFrame(self.frame_dns, fg_color="transparent")
        dns_content.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            dns_content,
            text="2. DNS Сервер (Пресеты или свои адреса)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(anchor="w")

        # Dropdown selection row
        preset_row = ctk.CTkFrame(dns_content, fg_color="transparent")
        preset_row.pack(fill="x", pady=(8, 6))

        ctk.CTkLabel(
            preset_row,
            text="Профиль:",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        self.profile_names = [p["name"] for p in self.profiles_mgr.get_all()]
        self.combo_profiles = ctk.CTkComboBox(
            preset_row,
            values=self.profile_names,
            command=self._on_profile_selected,
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            button_color=THEME["btn_neutral_bg"],
            button_hover_color=THEME["btn_neutral_hover"],
            text_color=THEME["text_primary"],
            height=28,
        )
        if self.profile_names:
            self.combo_profiles.set(self.profile_names[0])
        self.combo_profiles.pack(side="left", fill="x", expand=True)

        # Custom IP entry fields container
        ip_frame = ctk.CTkFrame(dns_content, fg_color=THEME["input_bg"], border_color=THEME["card_border"], border_width=1, corner_radius=8)
        ip_frame.pack(fill="x", pady=(2, 8))

        inputs_row = ctk.CTkFrame(ip_frame, fg_color="transparent")
        inputs_row.pack(fill="x", padx=8, pady=8)

        # Primary input
        box_primary = ctk.CTkFrame(inputs_row, fg_color="transparent")
        box_primary.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkLabel(box_primary, text="Основной DNS:", font=ctk.CTkFont(size=10), text_color=THEME["text_secondary"]).pack(anchor="w")
        self.entry_primary_dns = ctk.CTkEntry(
            box_primary,
            placeholder_text="94.250.253.55",
            fg_color=THEME["bg_main"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12),
            height=28,
        )
        self.entry_primary_dns.pack(fill="x", pady=(2, 0))

        # Secondary input
        box_secondary = ctk.CTkFrame(inputs_row, fg_color="transparent")
        box_secondary.pack(side="right", fill="x", expand=True, padx=(4, 0))
        ctk.CTkLabel(box_secondary, text="Второй DNS:", font=ctk.CTkFont(size=10), text_color=THEME["text_secondary"]).pack(anchor="w")
        self.entry_secondary_dns = ctk.CTkEntry(
            box_secondary,
            placeholder_text="195.133.25.16",
            fg_color=THEME["bg_main"],
            border_color=THEME["input_border"],
            text_color=THEME["text_primary"],
            font=ctk.CTkFont(family="Consolas", size=12),
            height=28,
        )
        self.entry_secondary_dns.pack(fill="x", pady=(2, 0))

        self._sync_inputs_from_selected_profile()

        # Action Buttons row: Apply & Comss Fetch
        btn_box = ctk.CTkFrame(dns_content, fg_color="transparent")
        btn_box.pack(fill="x", pady=(0, 6))

        # Primary Accent Button for Apply DNS
        self.btn_apply_dns = AnimatedButton(
            btn_box,
            text="Применить DNS",
            normal_bg=THEME["accent_primary"],
            hover_bg=THEME["accent_hover"],
            normal_border=THEME["accent_primary"],
            hover_border=THEME["accent_hover"],
            text_color="#0F172A",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_apply_dns_clicked,
        )
        self.btn_apply_dns.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_fetch_comss = AnimatedButton(
            btn_box,
            text="С сайта Comss",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=11),
            command=self._on_fetch_comss_clicked,
            width=120,
        )
        self.btn_fetch_comss.pack(side="right", padx=(4, 0))

        # Manage Profile Actions row
        manage_row = ctk.CTkFrame(dns_content, fg_color="transparent")
        manage_row.pack(fill="x")

        self.btn_save_as_profile = AnimatedButton(
            manage_row,
            text="+ Сохранить в профили",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=24,
            font=ctk.CTkFont(size=10),
            command=self._on_save_as_profile_clicked,
        )
        self.btn_save_as_profile.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_del_profile = AnimatedButton(
            manage_row,
            text="Удалить профиль",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["danger_bg"],
            normal_border=THEME["card_border"],
            hover_border=THEME["danger_border"],
            text_color=THEME["text_secondary"],
            height=24,
            font=ctk.CTkFont(size=10),
            command=self._on_del_profile_clicked,
            width=115,
        )
        self.btn_del_profile.pack(side="right", padx=(4, 0))

        # 6. Mode 3: Zapret DPI Bypass
        self.frame_zapret = ctk.CTkFrame(
            self.scroll_content,
            fg_color=THEME["card_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=10,
        )
        self.frame_zapret.pack(fill="x", padx=8, pady=4)

        zapret_content = ctk.CTkFrame(self.frame_zapret, fg_color="transparent")
        zapret_content.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            zapret_content,
            text="3. Обход DPI (Zapret / winws)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            zapret_content,
            text="Ускорение YouTube и звонки Discord без использования VPN.",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        ).pack(anchor="w", pady=(1, 6))

        # Strategy selector
        zapret_row = ctk.CTkFrame(zapret_content, fg_color="transparent")
        zapret_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            zapret_row,
            text="Режим:",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        ).pack(side="left", padx=(0, 8))

        presets_dict = self.zapret_config.get("presets", {})
        self.zapret_preset_keys = list(presets_dict.keys())
        preset_display_names = [presets_dict[k].get("name", k) for k in self.zapret_preset_keys]

        self.combo_zapret_presets = ctk.CTkComboBox(
            zapret_row,
            values=preset_display_names,
            fg_color=THEME["input_bg"],
            border_color=THEME["input_border"],
            button_color=THEME["btn_neutral_bg"],
            button_hover_color=THEME["btn_neutral_hover"],
            text_color=THEME["text_primary"],
            height=28,
        )
        sel_key = self.zapret_config.get("selected_preset", "general")
        if sel_key in presets_dict:
            self.combo_zapret_presets.set(presets_dict[sel_key].get("name", sel_key))
        elif preset_display_names:
            self.combo_zapret_presets.set(preset_display_names[0])
        self.combo_zapret_presets.pack(side="left", fill="x", expand=True)

        # Zapret Action Buttons
        zapret_btns = ctk.CTkFrame(zapret_content, fg_color="transparent")
        zapret_btns.pack(fill="x", pady=(0, 6))

        self.btn_start_zapret = AnimatedButton(
            zapret_btns,
            text="Включить Zapret",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_start_zapret_clicked,
        )
        self.btn_start_zapret.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_stop_zapret = AnimatedButton(
            zapret_btns,
            text="Остановить",
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
        self.btn_stop_zapret.pack(side="right", padx=(4, 0))

        # Zapret Folder path row
        folder_row = ctk.CTkFrame(zapret_content, fg_color="transparent")
        folder_row.pack(fill="x")

        self.lbl_zapret_path = ctk.CTkLabel(
            folder_row,
            text=f"Папка: {self.zapret_config.get('zapret_dir', 'tools/zapret')}",
            font=ctk.CTkFont(size=10),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.lbl_zapret_path.pack(side="left", fill="x", expand=True)

        self.btn_choose_folder = AnimatedButton(
            folder_row,
            text="Выбрать папку",
            normal_bg=THEME["input_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_secondary"],
            height=22,
            font=ctk.CTkFont(size=10),
            command=self._on_choose_zapret_folder,
            width=95,
        )
        self.btn_choose_folder.pack(side="right")

        # 7. Mode 4: Happ VPN
        self.frame_vpn = ctk.CTkFrame(
            self.scroll_content,
            fg_color=THEME["card_bg"],
            border_color=THEME["card_border"],
            border_width=1,
            corner_radius=10,
        )
        self.frame_vpn.pack(fill="x", padx=8, pady=4)

        vpn_content = ctk.CTkFrame(self.frame_vpn, fg_color="transparent")
        vpn_content.pack(fill="x", padx=14, pady=10)

        ctk.CTkLabel(
            vpn_content,
            text="4. VPN Режим (Happ)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=THEME["text_primary"],
        ).pack(anchor="w")

        ctk.CTkLabel(
            vpn_content,
            text="Сброс DNS, безопасная пауза Zapret и открытие клиента Happ.",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
        ).pack(anchor="w", pady=(1, 8))

        self.btn_vpn_mode = AnimatedButton(
            vpn_content,
            text="Включить VPN (Happ)",
            normal_bg=THEME["btn_neutral_bg"],
            hover_bg=THEME["btn_neutral_hover"],
            normal_border=THEME["card_border"],
            hover_border=THEME["accent_primary"],
            text_color=THEME["text_primary"],
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._on_vpn_mode_clicked,
        )
        self.btn_vpn_mode.pack(fill="x")

        # 8. Bottom Minimalist Status Bar
        self.status_bar_frame = ctk.CTkFrame(
            self, fg_color=THEME["bg_main"], border_color=THEME["card_border"], border_width=1, corner_radius=0, height=32
        )
        self.status_bar_frame.pack(side="bottom", fill="x")

        self.lbl_status_msg = ctk.CTkLabel(
            self.status_bar_frame,
            text="Готово к работе",
            font=ctk.CTkFont(size=11),
            text_color=THEME["text_secondary"],
            anchor="w",
        )
        self.lbl_status_msg.pack(fill="x", padx=16, pady=4)

    def _set_status_msg(self, msg: str, is_accent: bool = False, is_error: bool = False):
        if is_error:
            color = "#F43F5E"
        elif is_accent:
            color = THEME["accent_primary"]
        else:
            color = THEME["text_secondary"]
        self.lbl_status_msg.configure(text=msg, text_color=color)

    def _sync_inputs_from_selected_profile(self):
        selected_name = self.combo_profiles.get()
        profile = next((p for p in self.profiles_mgr.get_all() if p["name"] == selected_name), None)
        if profile:
            self.entry_primary_dns.delete(0, "end")
            self.entry_primary_dns.insert(0, profile.get("primary", ""))

            self.entry_secondary_dns.delete(0, "end")
            self.entry_secondary_dns.insert(0, profile.get("secondary", ""))

    def _on_profile_selected(self, _):
        self._sync_inputs_from_selected_profile()

    def _refresh_status_async(self):
        def task():
            adapter = DNSManager.get_active_adapter()
            happ_running = HappManager.is_running()
            zapret_running = ZapretManager.is_running()
            winws_found = ZapretManager.find_winws_binary() is not None
            self.after(0, lambda: self._update_status_ui(adapter, happ_running, zapret_running, winws_found))

        threading.Thread(target=task, daemon=True).start()

    def _update_status_ui(self, adapter: Optional[dict], happ_running: bool, zapret_running: bool, winws_found: bool):
        self.active_adapter = adapter
        if adapter:
            desc = adapter.get("description") or adapter.get("alias")
            self.lbl_adapter.configure(text=f"Адаптер: {desc} (#{adapter['index']})")

            dns_servers = adapter.get("ipv4_dns", [])
            is_dhcp = adapter.get("is_dhcp", True)

            if is_dhcp:
                self.lbl_current_mode.configure(text="Режим: Обычный интернет (DHCP)")
                self.lbl_current_dns.configure(text="DNS: Авто (DHCP от роутера)", text_color=THEME["text_secondary"])
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

                label = f"Режим: DNS ({matched_name})" if matched_name else "Режим: Пользовательский DNS"
                self.lbl_current_mode.configure(text=label)
                self.lbl_current_dns.configure(text=f"DNS: {', '.join(dns_servers)}", text_color=THEME["text_accent"])
                self.dot_status.configure(text_color=THEME["accent_primary"])
        else:
            self.lbl_adapter.configure(text="Адаптер: Сеть не обнаружена")
            self.lbl_current_mode.configure(text="Режим: Неизвестно")
            self.lbl_current_dns.configure(text="DNS: —", text_color=THEME["text_secondary"])
            self.dot_status.configure(text_color=THEME["text_secondary"])

        # Happ status
        if happ_running:
            self.lbl_happ_status.configure(text="Happ: Активен ●", text_color=THEME["success_dot"])
        else:
            self.lbl_happ_status.configure(text="Happ: Не запущен", text_color=THEME["text_secondary"])

        # Zapret status
        if zapret_running:
            self.lbl_zapret_status.configure(text="Zapret: Активен ●", text_color=THEME["success_dot"])
            self.btn_start_zapret.set_colors(
                normal_bg=THEME["btn_neutral_hover"],
                hover_bg=THEME["btn_neutral_bg"],
                normal_border=THEME["accent_primary"],
                hover_border=THEME["accent_primary"],
            )
            self.btn_start_zapret.configure(text="Перезапустить Zapret")
        elif not winws_found:
            self.lbl_zapret_status.configure(text="Zapret: winws.exe не найден", text_color="#F43F5E")
            self.btn_start_zapret.set_colors(
                normal_bg=THEME["btn_neutral_bg"],
                hover_bg=THEME["btn_neutral_hover"],
                normal_border=THEME["card_border"],
                hover_border=THEME["accent_primary"],
            )
            self.btn_start_zapret.configure(text="Включить Zapret")
        else:
            self.lbl_zapret_status.configure(text="Zapret: Остановлен", text_color=THEME["text_secondary"])
            self.btn_start_zapret.set_colors(
                normal_bg=THEME["btn_neutral_bg"],
                hover_bg=THEME["btn_neutral_hover"],
                normal_border=THEME["card_border"],
                hover_border=THEME["accent_primary"],
            )
            self.btn_start_zapret.configure(text="Включить Zapret")

    def _on_set_dhcp_clicked(self):
        self._set_status_msg("Переключение на автополучение DNS...", is_accent=True)

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
            self._set_status_msg(f"Некорректный IP: {primary}", is_error=True)
            return

        ips = [primary]
        if secondary:
            if not is_valid_ipv4(secondary):
                self._set_status_msg(f"Некорректный второй IP: {secondary}", is_error=True)
                return
            ips.append(secondary)

        self._set_status_msg(f"Применение DNS: {', '.join(ips)}...", is_accent=True)

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
                    self.combo_profiles.set("Comss.one DNS")
                    self.entry_primary_dns.delete(0, "end")
                    self.entry_primary_dns.insert(0, p_ip)
                    self.entry_secondary_dns.delete(0, "end")
                    self.entry_secondary_dns.insert(0, s_ip)
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
                names = [prof["name"] for prof in self.profiles_mgr.get_all()]
                self.combo_profiles.configure(values=names)
                self.combo_profiles.set(name)
                self._set_status_msg(f"Профиль '{name}' сохранен", is_accent=True)

        AddProfileDialog(self, save_callback, initial_primary=primary, initial_secondary=secondary)

    def _on_del_profile_clicked(self):
        selected_name = self.combo_profiles.get()
        profile = next((p for p in self.profiles_mgr.get_all() if p["name"] == selected_name), None)
        if not profile:
            return

        if profile.get("id") in ["comss", "adguard", "cloudflare", "google"]:
            self._set_status_msg("Базовые системные профили нельзя удалять", is_error=True)
            return

        self.profiles_mgr.delete_profile(profile["id"])
        names = [p["name"] for p in self.profiles_mgr.get_all()]
        self.combo_profiles.configure(values=names)
        if names:
            self.combo_profiles.set(names[0])
            self._sync_inputs_from_selected_profile()
        self._set_status_msg(f"Профиль '{selected_name}' удален")

    def _on_start_zapret_clicked(self):
        sel_display_name = self.combo_zapret_presets.get()
        presets_dict = self.zapret_config.get("presets", {})
        preset_key = "general"
        for k, v in presets_dict.items():
            if v.get("name") == sel_display_name or k == sel_display_name:
                preset_key = k
                break

        self._set_status_msg(f"Запуск Zapret ({sel_display_name})...", is_accent=True)

        def task():
            success, msg = ZapretManager.start(preset_key)
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
            self.lbl_zapret_path.configure(text=f"Папка: {folder}")
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
