"""Modern GUI for DNS & VPN Helper with Zapret DPI bypass and custom DNS editing."""
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

logger = logging.getLogger(__name__)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AddProfileDialog(ctk.CTkToplevel):
    """Dialog for creating a new DNS profile."""

    def __init__(self, parent, on_save_callback, initial_primary="", initial_secondary=""):
        super().__init__(parent)
        self.title("Сохранить как новый профиль")
        self.geometry("400x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_save_callback = on_save_callback

        self.label_title = ctk.CTkLabel(
            self, text="Сохранить профиль DNS", font=ctk.CTkFont(size=18, weight="bold")
        )
        self.label_title.pack(pady=(18, 12))

        self.entry_name = ctk.CTkEntry(self, placeholder_text="Название профиля (напр. Домашний DNS)", width=320)
        self.entry_name.pack(pady=6)

        self.entry_primary = ctk.CTkEntry(self, placeholder_text="Основной DNS IP", width=320)
        self.entry_primary.insert(0, initial_primary)
        self.entry_primary.pack(pady=6)

        self.entry_secondary = ctk.CTkEntry(self, placeholder_text="Второй DNS IP (необязательно)", width=320)
        self.entry_secondary.insert(0, initial_secondary)
        self.entry_secondary.pack(pady=6)

        self.entry_desc = ctk.CTkEntry(self, placeholder_text="Описание (необязательно)", width=320)
        self.entry_desc.pack(pady=6)

        self.label_error = ctk.CTkLabel(self, text="", text_color="#FF5555", font=ctk.CTkFont(size=12))
        self.label_error.pack(pady=4)

        self.btn_save = ctk.CTkButton(self, text="Сохранить", width=150, command=self._save)
        self.btn_save.pack(pady=(8, 12))

    def _save(self):
        name = self.entry_name.get().strip()
        p = self.entry_primary.get().strip()
        s = self.entry_secondary.get().strip()
        desc = self.entry_desc.get().strip()

        if not name:
            self.label_error.configure(text="Введите название профиля")
            return
        if not is_valid_ipv4(p):
            self.label_error.configure(text="Неверный формат основного IP адреса")
            return
        if s and not is_valid_ipv4(s):
            self.label_error.configure(text="Неверный формат второго IP адреса")
            return

        self.on_save_callback(name, p, s, desc)
        self.destroy()


class MainWindow(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("DNS & VPN Helper (with Zapret)")
        self.geometry("560x780")
        self.minsize(520, 680)

        self.profiles_mgr = ProfilesManager()
        self.zapret_config = ZapretManager.load_config()
        self.active_adapter: Optional[dict] = None

        self._build_ui()
        self._refresh_status_async()

    def _build_ui(self):
        # Top title & status header (always visible)
        self.header_frame = ctk.CTkFrame(self, corner_radius=10)
        self.header_frame.pack(fill="x", padx=14, pady=(12, 6))

        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(fill="x", padx=14, pady=(10, 2))

        title_lbl = ctk.CTkLabel(
            title_box,
            text="⚡ DNS & VPN Helper",
            font=ctk.CTkFont(size=19, weight="bold"),
        )
        title_lbl.pack(side="left")

        self.btn_refresh = ctk.CTkButton(
            title_box,
            text="🔄 Обновить статус",
            width=130,
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#37474F",
            hover_color="#263238",
            command=self._refresh_status_async,
        )
        self.btn_refresh.pack(side="right")

        self.lbl_adapter = ctk.CTkLabel(
            self.header_frame,
            text="📡 Адаптер: определение...",
            font=ctk.CTkFont(size=12),
            text_color="#AAAAAA",
        )
        self.lbl_adapter.pack(anchor="w", padx=14, pady=(0, 8))

        # Scrollable content area
        self.scroll_content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_content.pack(fill="both", expand=True, padx=6, pady=4)

        # 1. Status Overview Card
        self.status_card = ctk.CTkFrame(self.scroll_content, corner_radius=10, fg_color="#1E232A")
        self.status_card.pack(fill="x", padx=8, pady=4)

        self.lbl_current_mode = ctk.CTkLabel(
            self.status_card,
            text="Текущий режим: Определение...",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#4E9FFF",
        )
        self.lbl_current_mode.pack(anchor="w", padx=14, pady=(8, 2))

        self.lbl_current_dns = ctk.CTkLabel(
            self.status_card,
            text="Текущие DNS: ...",
            font=ctk.CTkFont(size=12),
            text_color="#CCCCCC",
        )
        self.lbl_current_dns.pack(anchor="w", padx=14, pady=(0, 4))

        status_indicators_box = ctk.CTkFrame(self.status_card, fg_color="transparent")
        status_indicators_box.pack(fill="x", padx=14, pady=(0, 8))

        self.lbl_happ_status = ctk.CTkLabel(
            status_indicators_box,
            text="Happ VPN: ...",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        self.lbl_happ_status.pack(side="left", padx=(0, 16))

        self.lbl_zapret_status = ctk.CTkLabel(
            status_indicators_box,
            text="Zapret (DPI): ...",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        self.lbl_zapret_status.pack(side="left")

        # 2. Mode A: Regular Internet (DHCP)
        self.frame_dhcp = ctk.CTkFrame(self.scroll_content, corner_radius=10)
        self.frame_dhcp.pack(fill="x", padx=8, pady=4)

        lbl_dhcp_title = ctk.CTkLabel(
            self.frame_dhcp,
            text="🌐 1. Обычный интернет (DHCP)",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_dhcp_title.pack(anchor="w", padx=14, pady=(8, 2))

        lbl_dhcp_desc = ctk.CTkLabel(
            self.frame_dhcp,
            text="Сбросить настройки DNS на автоматические от роутера/провайдера.",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        lbl_dhcp_desc.pack(anchor="w", padx=14, pady=(0, 6))

        self.btn_set_dhcp = ctk.CTkButton(
            self.frame_dhcp,
            text="Включить прямой интернет (Сбросить DNS)",
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_set_dhcp_clicked,
        )
        self.btn_set_dhcp.pack(fill="x", padx=14, pady=(0, 10))

        # 3. Mode B: DNS Profiles & Custom Input
        self.frame_dns = ctk.CTkFrame(self.scroll_content, corner_radius=10)
        self.frame_dns.pack(fill="x", padx=8, pady=4)

        lbl_dns_title = ctk.CTkLabel(
            self.frame_dns,
            text="⚡ 2. DNS Сервер (Пресеты или свои адреса)",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_dns_title.pack(anchor="w", padx=14, pady=(8, 2))

        # Preset Dropdown row
        preset_row = ctk.CTkFrame(self.frame_dns, fg_color="transparent")
        preset_row.pack(fill="x", padx=14, pady=(2, 4))

        lbl_preset = ctk.CTkLabel(preset_row, text="Готовый профиль:", font=ctk.CTkFont(size=11), text_color="#AAAAAA")
        lbl_preset.pack(side="left", padx=(0, 8))

        self.profile_names = [p["name"] for p in self.profiles_mgr.get_all()]
        self.combo_profiles = ctk.CTkComboBox(
            preset_row,
            values=self.profile_names,
            command=self._on_profile_selected,
            height=28,
        )
        if self.profile_names:
            self.combo_profiles.set(self.profile_names[0])
        self.combo_profiles.pack(side="left", fill="x", expand=True)

        # Custom IP entry fields
        ip_frame = ctk.CTkFrame(self.frame_dns, fg_color="#1B1E23", corner_radius=8)
        ip_frame.pack(fill="x", padx=14, pady=6)

        dns_inputs_row = ctk.CTkFrame(ip_frame, fg_color="transparent")
        dns_inputs_row.pack(fill="x", padx=8, pady=8)

        # Primary input
        box_primary = ctk.CTkFrame(dns_inputs_row, fg_color="transparent")
        box_primary.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ctk.CTkLabel(box_primary, text="Основной DNS IP:", font=ctk.CTkFont(size=11), text_color="#AAAAAA").pack(anchor="w")
        self.entry_primary_dns = ctk.CTkEntry(box_primary, placeholder_text="напр. 94.250.253.55", height=28)
        self.entry_primary_dns.pack(fill="x", pady=(2, 0))

        # Secondary input
        box_secondary = ctk.CTkFrame(dns_inputs_row, fg_color="transparent")
        box_secondary.pack(side="right", fill="x", expand=True, padx=(4, 0))
        ctk.CTkLabel(box_secondary, text="Второй DNS IP (опц.):", font=ctk.CTkFont(size=11), text_color="#AAAAAA").pack(anchor="w")
        self.entry_secondary_dns = ctk.CTkEntry(box_secondary, placeholder_text="напр. 195.133.25.16", height=28)
        self.entry_secondary_dns.pack(fill="x", pady=(2, 0))

        # Populate entry boxes from first profile
        self._sync_inputs_from_selected_profile()

        # Action Buttons row: Apply & Fetch from Comss
        btn_box = ctk.CTkFrame(self.frame_dns, fg_color="transparent")
        btn_box.pack(fill="x", padx=14, pady=(2, 6))

        self.btn_apply_dns = ctk.CTkButton(
            btn_box,
            text="Применить DNS",
            fg_color="#1976D2",
            hover_color="#1565C0",
            height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_apply_dns_clicked,
        )
        self.btn_apply_dns.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_fetch_comss = ctk.CTkButton(
            btn_box,
            text="🔄 С сайта Comss",
            fg_color="#37474F",
            hover_color="#263238",
            height=32,
            command=self._on_fetch_comss_clicked,
            width=130,
        )
        self.btn_fetch_comss.pack(side="right", padx=(4, 0))

        # Save as profile / Delete profile row
        manage_box = ctk.CTkFrame(self.frame_dns, fg_color="transparent")
        manage_box.pack(fill="x", padx=14, pady=(0, 10))

        self.btn_save_as_profile = ctk.CTkButton(
            manage_box,
            text="💾 Сохранить в профили",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            border_color="#555555",
            hover_color="#333333",
            height=26,
            command=self._on_save_as_profile_clicked,
        )
        self.btn_save_as_profile.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_del_profile = ctk.CTkButton(
            manage_box,
            text="Удалить профиль",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            border_color="#555555",
            hover_color="#442222",
            height=26,
            command=self._on_del_profile_clicked,
            width=120,
        )
        self.btn_del_profile.pack(side="right", padx=(4, 0))

        # 4. Mode C: Zapret (winws) DPI Bypass Module
        self.frame_zapret = ctk.CTkFrame(self.scroll_content, corner_radius=10)
        self.frame_zapret.pack(fill="x", padx=8, pady=4)

        lbl_zapret_title = ctk.CTkLabel(
            self.frame_zapret,
            text="🛡️ 3. Обход блокировок DPI (Zapret / winws)",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_zapret_title.pack(anchor="w", padx=14, pady=(8, 2))

        lbl_zapret_desc = ctk.CTkLabel(
            self.frame_zapret,
            text="Обход замедления YouTube, блокировок Discord и сайтов без VPN (на базе winws).",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        lbl_zapret_desc.pack(anchor="w", padx=14, pady=(0, 6))

        # Preset selector for Zapret
        zapret_preset_row = ctk.CTkFrame(self.frame_zapret, fg_color="transparent")
        zapret_preset_row.pack(fill="x", padx=14, pady=(0, 6))

        ctk.CTkLabel(zapret_preset_row, text="Стратегия DPI:", font=ctk.CTkFont(size=11), text_color="#AAAAAA").pack(side="left", padx=(0, 8))

        presets_dict = self.zapret_config.get("presets", {})
        self.zapret_preset_keys = list(presets_dict.keys())
        preset_display_names = [presets_dict[k].get("name", k) for k in self.zapret_preset_keys]

        self.combo_zapret_presets = ctk.CTkComboBox(
            zapret_preset_row,
            values=preset_display_names,
            height=28,
        )
        sel_key = self.zapret_config.get("selected_preset", "general")
        if sel_key in presets_dict:
            self.combo_zapret_presets.set(presets_dict[sel_key].get("name", sel_key))
        elif preset_display_names:
            self.combo_zapret_presets.set(preset_display_names[0])
        self.combo_zapret_presets.pack(side="left", fill="x", expand=True)

        # Zapret Control Buttons
        zapret_btn_box = ctk.CTkFrame(self.frame_zapret, fg_color="transparent")
        zapret_btn_box.pack(fill="x", padx=14, pady=(0, 6))

        self.btn_start_zapret = ctk.CTkButton(
            zapret_btn_box,
            text="Включить Zapret",
            fg_color="#00897B",
            hover_color="#00695C",
            height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_start_zapret_clicked,
        )
        self.btn_start_zapret.pack(side="left", expand=True, fill="x", padx=(0, 4))

        self.btn_stop_zapret = ctk.CTkButton(
            zapret_btn_box,
            text="Остановить",
            fg_color="#C62828",
            hover_color="#B71C1C",
            height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_stop_zapret_clicked,
            width=110,
        )
        self.btn_stop_zapret.pack(side="right", padx=(4, 0))

        # Folder location row
        zapret_folder_row = ctk.CTkFrame(self.frame_zapret, fg_color="transparent")
        zapret_folder_row.pack(fill="x", padx=14, pady=(0, 10))

        self.lbl_zapret_path = ctk.CTkLabel(
            zapret_folder_row,
            text=f"Папка: {self.zapret_config.get('zapret_dir', 'tools/zapret')}",
            font=ctk.CTkFont(size=10),
            text_color="#777777",
            anchor="w",
        )
        self.lbl_zapret_path.pack(side="left", fill="x", expand=True)

        self.btn_choose_zapret_folder = ctk.CTkButton(
            zapret_folder_row,
            text="⚙️ Выбрать папку",
            font=ctk.CTkFont(size=10),
            fg_color="transparent",
            border_width=1,
            border_color="#555555",
            hover_color="#333333",
            height=24,
            width=110,
            command=self._on_choose_zapret_folder,
        )
        self.btn_choose_zapret_folder.pack(side="right")

        # 5. Mode D: VPN Mode (Happ)
        self.frame_vpn = ctk.CTkFrame(self.scroll_content, corner_radius=10)
        self.frame_vpn.pack(fill="x", padx=8, pady=4)

        lbl_vpn_title = ctk.CTkLabel(
            self.frame_vpn,
            text="🛡️ 4. VPN Режим (Happ)",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        lbl_vpn_title.pack(anchor="w", padx=14, pady=(8, 2))

        lbl_vpn_desc = ctk.CTkLabel(
            self.frame_vpn,
            text="Сбрасывает DNS на авто, останавливает Zapret (во избежание конфликтов) и открывает Happ.",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
        )
        lbl_vpn_desc.pack(anchor="w", padx=14, pady=(0, 6))

        self.btn_vpn_mode = ctk.CTkButton(
            self.frame_vpn,
            text="Включить VPN (Happ)",
            fg_color="#7B1FA2",
            hover_color="#6A1B9A",
            height=32,
            font=ctk.CTkFont(weight="bold"),
            command=self._on_vpn_mode_clicked,
        )
        self.btn_vpn_mode.pack(fill="x", padx=14, pady=(0, 10))

        # Bottom Status Bar (always visible)
        self.status_bar_frame = ctk.CTkFrame(self, fg_color="#181A1F", corner_radius=0, height=30)
        self.status_bar_frame.pack(side="bottom", fill="x")

        self.lbl_status_msg = ctk.CTkLabel(
            self.status_bar_frame,
            text="Готово к работе",
            font=ctk.CTkFont(size=11),
            text_color="#888888",
            anchor="w",
        )
        self.lbl_status_msg.pack(fill="x", padx=14, pady=4)

    def _set_status_msg(self, msg: str, color: str = "#888888"):
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
            self.lbl_adapter.configure(text=f"📡 Адаптер: {desc} (Интерфейс #{adapter['index']})")

            dns_servers = adapter.get("ipv4_dns", [])
            is_dhcp = adapter.get("is_dhcp", True)

            if is_dhcp:
                self.lbl_current_mode.configure(text="Текущий режим: 🌐 Обычный интернет (DHCP)", text_color="#66BB6A")
                self.lbl_current_dns.configure(text="Текущие DNS: Автоматически (DHCP от роутера)")
            else:
                matched_name = None
                for p in self.profiles_mgr.get_all():
                    p_ips = [p.get("primary")]
                    if p.get("secondary"):
                        p_ips.append(p.get("secondary"))
                    if dns_servers == p_ips or (len(dns_servers) > 0 and dns_servers[0] == p.get("primary")):
                        matched_name = p["name"]
                        break

                mode_str = f"⚡ DNS: {matched_name}" if matched_name else "⚡ DNS: Пользовательский"
                self.lbl_current_mode.configure(text=f"Текущий режим: {mode_str}", text_color="#42A5F5")
                self.lbl_current_dns.configure(text=f"Текущие DNS: {', '.join(dns_servers)}")
        else:
            self.lbl_adapter.configure(text="📡 Адаптер: Не обнаружен")
            self.lbl_current_mode.configure(text="Текущий режим: Неизвестно", text_color="#FFA726")
            self.lbl_current_dns.configure(text="Текущие DNS: -")

        # Happ status
        if happ_running:
            self.lbl_happ_status.configure(text="Happ VPN: Запущен 🟢", text_color="#81C784")
        else:
            self.lbl_happ_status.configure(text="Happ VPN: Не запущен ⚪", text_color="#9E9E9E")

        # Zapret status
        if zapret_running:
            self.lbl_zapret_status.configure(text="Zapret: Активен 🟢", text_color="#81C784")
            self.btn_start_zapret.configure(text="Перезапустить Zapret", fg_color="#00695C")
        elif not winws_found:
            self.lbl_zapret_status.configure(text="Zapret: winws.exe не найден ⚠️", text_color="#FFA726")
            self.btn_start_zapret.configure(text="Включить Zapret", fg_color="#00897B")
        else:
            self.lbl_zapret_status.configure(text="Zapret: Остановлен ⚪", text_color="#9E9E9E")
            self.btn_start_zapret.configure(text="Включить Zapret", fg_color="#00897B")

    def _on_set_dhcp_clicked(self):
        self._set_status_msg("Переключение на автоматический DNS (DHCP)...", "#4E9FFF")

        def task():
            success, msg = DNSManager.reset_to_dhcp()
            color = "#66BB6A" if success else "#EF5350"
            self.after(0, lambda: self._set_status_msg(msg, color))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_apply_dns_clicked(self):
        primary = self.entry_primary_dns.get().strip()
        secondary = self.entry_secondary_dns.get().strip()

        if not primary:
            self._set_status_msg("Введите хотя бы основной DNS IP адрес", "#EF5350")
            return

        if not is_valid_ipv4(primary):
            self._set_status_msg(f"Неверный формат IP: {primary}", "#EF5350")
            return

        ips = [primary]
        if secondary:
            if not is_valid_ipv4(secondary):
                self._set_status_msg(f"Неверный формат второго IP: {secondary}", "#EF5350")
                return
            ips.append(secondary)

        self._set_status_msg(f"Установка DNS: {', '.join(ips)}...", "#4E9FFF")

        def task():
            success, msg = DNSManager.set_dns(ips)
            color = "#66BB6A" if success else "#EF5350"
            self.after(0, lambda: self._set_status_msg(msg, color))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_fetch_comss_clicked(self):
        self._set_status_msg("Получение актуального DNS с comss.one/dns...", "#4E9FFF")

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
                    self._set_status_msg(f"Адреса Comss обновлены: {', '.join(ips)} (нажмите 'Применить DNS')", "#66BB6A")

                self.after(0, update_ui)
            else:
                self.after(0, lambda: self._set_status_msg(f"Ошибка парсинга: {msg}", "#EF5350"))

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
                self._set_status_msg(f"Профиль '{name}' успешно сохранен", "#66BB6A")

        AddProfileDialog(self, save_callback, initial_primary=primary, initial_secondary=secondary)

    def _on_del_profile_clicked(self):
        selected_name = self.combo_profiles.get()
        profile = next((p for p in self.profiles_mgr.get_all() if p["name"] == selected_name), None)
        if not profile:
            return

        if profile.get("id") in ["comss", "adguard", "cloudflare", "google"]:
            self._set_status_msg("Базовые профили по умолчанию нельзя удалять", "#FFA726")
            return

        self.profiles_mgr.delete_profile(profile["id"])
        names = [p["name"] for p in self.profiles_mgr.get_all()]
        self.combo_profiles.configure(values=names)
        if names:
            self.combo_profiles.set(names[0])
            self._sync_inputs_from_selected_profile()
        self._set_status_msg(f"Профиль '{selected_name}' удален", "#66BB6A")

    # Zapret Handlers
    def _on_start_zapret_clicked(self):
        sel_display_name = self.combo_zapret_presets.get()
        presets_dict = self.zapret_config.get("presets", {})
        preset_key = "general"
        for k, v in presets_dict.items():
            if v.get("name") == sel_display_name or k == sel_display_name:
                preset_key = k
                break

        self._set_status_msg(f"Запуск Zapret ({sel_display_name})...", "#4E9FFF")

        def task():
            success, msg = ZapretManager.start(preset_key)
            color = "#66BB6A" if success else "#EF5350"
            self.after(0, lambda: self._set_status_msg(msg, color))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_stop_zapret_clicked(self):
        self._set_status_msg("Остановка Zapret...", "#FFA726")

        def task():
            success, msg = ZapretManager.stop()
            color = "#FFA726" if success else "#EF5350"
            self.after(0, lambda: self._set_status_msg(msg, color))
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
                self._set_status_msg(f"winws.exe найден: {binary}", "#66BB6A")
            else:
                self._set_status_msg("В выбранной папке winws.exe не найден", "#FFA726")
            self._refresh_status_async()

    # VPN Mode Handler
    def _on_vpn_mode_clicked(self):
        self._set_status_msg("Активация VPN Режима: сброс DNS, остановка Zapret и запуск Happ...", "#AB47BC")

        def task():
            # 1. Reset DNS to DHCP
            DNSManager.reset_to_dhcp()
            # 2. Stop Zapret to prevent packet clash
            if ZapretManager.is_running():
                ZapretManager.stop()
            # 3. Launch or activate Happ
            launched = HappManager.launch_or_focus()
            msg = "Режим VPN активен (DNS сброшен, Happ запущен)" if launched else "DNS сброшен, но не удалось запустить Happ"
            color = "#AB47BC" if launched else "#FFA726"
            self.after(0, lambda: self._set_status_msg(msg, color))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()
