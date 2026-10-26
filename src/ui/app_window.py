"""Modern GUI for DNS & VPN Helper using CustomTkinter."""
import logging
import threading
from typing import Optional
import customtkinter as ctk

from src.core.dns_manager import DNSManager
from src.core.happ_manager import HappManager
from src.services.parser import DNSWebsiteParser
from src.services.profiles_manager import ProfilesManager, is_valid_ipv4

logger = logging.getLogger(__name__)

# UI Configuration
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class AddProfileDialog(ctk.CTkToplevel):
    """Dialog for creating a new DNS profile."""

    def __init__(self, parent, on_save_callback):
        super().__init__(parent)
        self.title("Добавить DNS профиль")
        self.geometry("400x380")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.on_save_callback = on_save_callback

        self.label_title = ctk.CTkLabel(
            self, text="Новый DNS профиль", font=ctk.CTkFont(size=18, weight="bold")
        )
        self.label_title.pack(pady=(18, 12))

        self.entry_name = ctk.CTkEntry(self, placeholder_text="Название (напр. My DNS)", width=320)
        self.entry_name.pack(pady=6)

        self.entry_primary = ctk.CTkEntry(self, placeholder_text="Основной DNS (напр. 1.1.1.1)", width=320)
        self.entry_primary.pack(pady=6)

        self.entry_secondary = ctk.CTkEntry(self, placeholder_text="Второй DNS (необязательно)", width=320)
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

        self.title("DNS & VPN Helper")
        self.geometry("520x690")
        self.minsize(500, 660)

        self.profiles_mgr = ProfilesManager()
        self.active_adapter: Optional[dict] = None

        self._build_ui()
        self._refresh_status_async()

    def _build_ui(self):
        # 1. Header Frame
        self.header_frame = ctk.CTkFrame(self, corner_radius=10)
        self.header_frame.pack(fill="x", padx=16, pady=(16, 10))

        title_lbl = ctk.CTkLabel(
            self.header_frame,
            text="⚡ DNS & VPN Helper",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title_lbl.pack(anchor="w", padx=16, pady=(12, 2))

        self.lbl_adapter = ctk.CTkLabel(
            self.header_frame,
            text="📡 Адаптер: определение...",
            font=ctk.CTkFont(size=12),
            text_color="#AAAAAA",
        )
        self.lbl_adapter.pack(anchor="w", padx=16, pady=(0, 10))

        # 2. Status Card
        self.status_card = ctk.CTkFrame(self, corner_radius=10, fg_color="#1E232A")
        self.status_card.pack(fill="x", padx=16, pady=6)

        self.lbl_current_mode = ctk.CTkLabel(
            self.status_card,
            text="Текущий режим: Определение...",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#4E9FFF",
        )
        self.lbl_current_mode.pack(anchor="w", padx=16, pady=(10, 2))

        self.lbl_current_dns = ctk.CTkLabel(
            self.status_card,
            text="Текущие DNS: ...",
            font=ctk.CTkFont(size=13),
            text_color="#CCCCCC",
        )
        self.lbl_current_dns.pack(anchor="w", padx=16, pady=(0, 6))

        self.lbl_happ_status = ctk.CTkLabel(
            self.status_card,
            text="Happ VPN: ...",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        )
        self.lbl_happ_status.pack(anchor="w", padx=16, pady=(0, 10))

        # 3. Actions / Modes Section
        # Mode A: Regular Internet (DHCP)
        self.frame_dhcp = ctk.CTkFrame(self, corner_radius=10)
        self.frame_dhcp.pack(fill="x", padx=16, pady=6)

        lbl_dhcp_title = ctk.CTkLabel(
            self.frame_dhcp,
            text="🌐 Обычный интернет (DHCP)",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        lbl_dhcp_title.pack(anchor="w", padx=16, pady=(10, 2))

        lbl_dhcp_desc = ctk.CTkLabel(
            self.frame_dhcp,
            text="Сбросить настройки DNS на автоматические от роутера/провайдера.",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        )
        lbl_dhcp_desc.pack(anchor="w", padx=16, pady=(0, 8))

        self.btn_set_dhcp = ctk.CTkButton(
            self.frame_dhcp,
            text="Включить прямой интернет",
            fg_color="#2E7D32",
            hover_color="#1B5E20",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_set_dhcp_clicked,
        )
        self.btn_set_dhcp.pack(fill="x", padx=16, pady=(0, 12))

        # Mode B: DNS Profiles
        self.frame_dns = ctk.CTkFrame(self, corner_radius=10)
        self.frame_dns.pack(fill="x", padx=16, pady=6)

        lbl_dns_title = ctk.CTkLabel(
            self.frame_dns,
            text="⚡ DNS Профиль (Обход / Защита)",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        lbl_dns_title.pack(anchor="w", padx=16, pady=(10, 2))

        # Profile selection
        self.profile_names = [p["name"] for p in self.profiles_mgr.get_all()]
        self.combo_profiles = ctk.CTkComboBox(
            self.frame_dns,
            values=self.profile_names,
            command=self._on_profile_selected,
            width=280,
        )
        if self.profile_names:
            self.combo_profiles.set(self.profile_names[0])
        self.combo_profiles.pack(fill="x", padx=16, pady=(4, 6))

        self.lbl_selected_ips = ctk.CTkLabel(
            self.frame_dns,
            text="",
            font=ctk.CTkFont(size=12),
            text_color="#4E9FFF",
        )
        self.lbl_selected_ips.pack(anchor="w", padx=16, pady=(0, 8))
        self._update_selected_profile_info()

        # Action buttons for DNS
        btn_box = ctk.CTkFrame(self.frame_dns, fg_color="transparent")
        btn_box.pack(fill="x", padx=16, pady=(0, 10))

        self.btn_apply_dns = ctk.CTkButton(
            btn_box,
            text="Применить DNS",
            fg_color="#1976D2",
            hover_color="#1565C0",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_apply_dns_clicked,
        )
        self.btn_apply_dns.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_fetch_comss = ctk.CTkButton(
            btn_box,
            text="🔄 С сайта Comss",
            fg_color="#455A64",
            hover_color="#37474F",
            command=self._on_fetch_comss_clicked,
            width=140,
        )
        self.btn_fetch_comss.pack(side="right", padx=(6, 0))

        # Manage profiles buttons
        manage_box = ctk.CTkFrame(self.frame_dns, fg_color="transparent")
        manage_box.pack(fill="x", padx=16, pady=(0, 12))

        self.btn_add_profile = ctk.CTkButton(
            manage_box,
            text="+ Добавить свой DNS",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            border_color="#555555",
            hover_color="#333333",
            command=self._on_add_profile_clicked,
        )
        self.btn_add_profile.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.btn_del_profile = ctk.CTkButton(
            manage_box,
            text="Удалить профиль",
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            border_width=1,
            border_color="#555555",
            hover_color="#442222",
            command=self._on_del_profile_clicked,
            width=120,
        )
        self.btn_del_profile.pack(side="right", padx=(6, 0))

        # Mode C: VPN (Happ)
        self.frame_vpn = ctk.CTkFrame(self, corner_radius=10)
        self.frame_vpn.pack(fill="x", padx=16, pady=6)

        lbl_vpn_title = ctk.CTkLabel(
            self.frame_vpn,
            text="🛡️ VPN Режим (Happ)",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        lbl_vpn_title.pack(anchor="w", padx=16, pady=(10, 2))

        lbl_vpn_desc = ctk.CTkLabel(
            self.frame_vpn,
            text="Сбрасывает DNS на авто (DHCP) и запускает / открывает Happ VPN.",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        )
        lbl_vpn_desc.pack(anchor="w", padx=16, pady=(0, 8))

        self.btn_vpn_mode = ctk.CTkButton(
            self.frame_vpn,
            text="Включить VPN (Happ)",
            fg_color="#7B1FA2",
            hover_color="#6A1B9A",
            font=ctk.CTkFont(weight="bold"),
            command=self._on_vpn_mode_clicked,
        )
        self.btn_vpn_mode.pack(fill="x", padx=16, pady=(0, 12))

        # 4. Status Bar at bottom
        self.lbl_status_msg = ctk.CTkLabel(
            self,
            text="Готово",
            font=ctk.CTkFont(size=12),
            text_color="#888888",
        )
        self.lbl_status_msg.pack(side="bottom", fill="x", padx=16, pady=(6, 12))

    def _set_status_msg(self, msg: str, color: str = "#888888"):
        self.lbl_status_msg.configure(text=msg, text_color=color)

    def _update_selected_profile_info(self):
        selected_name = self.combo_profiles.get()
        profile = next((p for p in self.profiles_mgr.get_all() if p["name"] == selected_name), None)
        if profile:
            ips = [profile.get("primary", "")]
            if profile.get("secondary"):
                ips.append(profile["secondary"])
            desc = profile.get("description", "")
            info_text = f"IP: {', '.join(ips)}"
            if desc:
                info_text += f" • {desc}"
            self.lbl_selected_ips.configure(text=info_text)
        else:
            self.lbl_selected_ips.configure(text="")

    def _on_profile_selected(self, _):
        self._update_selected_profile_info()

    def _refresh_status_async(self):
        def task():
            adapter = DNSManager.get_active_adapter()
            happ_running = HappManager.is_running()
            self.after(0, lambda: self._update_status_ui(adapter, happ_running))

        threading.Thread(target=task, daemon=True).start()

    def _update_status_ui(self, adapter: Optional[dict], happ_running: bool):
        self.active_adapter = adapter
        if adapter:
            desc = adapter.get("description") or adapter.get("alias")
            self.lbl_adapter.configure(text=f"📡 Адаптер: {desc} (Индекс #{adapter['index']})")

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

                mode_str = f"⚡ DNS Режим ({matched_name})" if matched_name else "⚡ DNS Режим (Пользовательский)"
                self.lbl_current_mode.configure(text=f"Текущий режим: {mode_str}", text_color="#42A5F5")
                self.lbl_current_dns.configure(text=f"Текущие DNS: {', '.join(dns_servers)}")
        else:
            self.lbl_adapter.configure(text="📡 Адаптер: Не обнаружен")
            self.lbl_current_mode.configure(text="Текущий режим: Неизвестно", text_color="#FFA726")
            self.lbl_current_dns.configure(text="Текущие DNS: -")

        if happ_running:
            self.lbl_happ_status.configure(text="Happ VPN: Запущен 🟢", text_color="#81C784")
        else:
            self.lbl_happ_status.configure(text="Happ VPN: Не запущен ⚪", text_color="#9E9E9E")

    def _on_set_dhcp_clicked(self):
        self._set_status_msg("Переключение на автоматический DNS (DHCP)...", "#4E9FFF")

        def task():
            success, msg = DNSManager.reset_to_dhcp()
            color = "#66BB6A" if success else "#EF5350"
            self.after(0, lambda: self._set_status_msg(msg, color))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_apply_dns_clicked(self):
        selected_name = self.combo_profiles.get()
        profile = next((p for p in self.profiles_mgr.get_all() if p["name"] == selected_name), None)
        if not profile:
            self._set_status_msg("Выберите профиль DNS", "#EF5350")
            return

        ips = [profile["primary"]]
        if profile.get("secondary"):
            ips.append(profile["secondary"])

        self._set_status_msg(f"Установка {profile['name']}...", "#4E9FFF")

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
                    self._update_selected_profile_info()
                    self._set_status_msg(f"Адрес Comss обновлен: {', '.join(ips)}", "#66BB6A")
                    # If currently selected is Comss, update label
                    if self.combo_profiles.get() == "Comss.one DNS":
                        self._update_selected_profile_info()

                self.after(0, update_ui)
            else:
                self.after(0, lambda: self._set_status_msg(f"Ошибка парсинга: {msg}", "#EF5350"))

        threading.Thread(target=task, daemon=True).start()

    def _on_vpn_mode_clicked(self):
        self._set_status_msg("Переключение на режим VPN: сброс DNS и запуск Happ...", "#AB47BC")

        def task():
            # 1. Reset DNS to DHCP
            DNSManager.reset_to_dhcp()
            # 2. Launch or activate Happ
            launched = HappManager.launch_or_focus()
            msg = "Режим VPN активен (DNS сброшен, Happ запущен)" if launched else "DNS сброшен, но не удалось запустить Happ"
            color = "#AB47BC" if launched else "#FFA726"
            self.after(0, lambda: self._set_status_msg(msg, color))
            self.after(0, self._refresh_status_async)

        threading.Thread(target=task, daemon=True).start()

    def _on_add_profile_clicked(self):
        def save_callback(name, primary, secondary, desc):
            new_p = self.profiles_mgr.add_profile(name, primary, secondary, desc)
            if new_p:
                names = [p["name"] for p in self.profiles_mgr.get_all()]
                self.combo_profiles.configure(values=names)
                self.combo_profiles.set(name)
                self._update_selected_profile_info()
                self._set_status_msg(f"Профиль '{name}' добавлен", "#66BB6A")

        AddProfileDialog(self, save_callback)

    def _on_del_profile_clicked(self):
        selected_name = self.combo_profiles.get()
        profile = next((p for p in self.profiles_mgr.get_all() if p["name"] == selected_name), None)
        if not profile:
            return

        if profile.get("id") in ["comss", "adguard", "cloudflare", "google"]:
            self._set_status_msg("Базовые профили нельзя удалять", "#FFA726")
            return

        self.profiles_mgr.delete_profile(profile["id"])
        names = [p["name"] for p in self.profiles_mgr.get_all()]
        self.combo_profiles.configure(values=names)
        if names:
            self.combo_profiles.set(names[0])
        self._update_selected_profile_info()
        self._set_status_msg(f"Профиль '{selected_name}' удален", "#66BB6A")
