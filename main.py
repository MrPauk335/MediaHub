import customtkinter as ctk
from tkinter import messagebox, filedialog, Canvas, Toplevel, Menu
import yt_dlp
import threading
import os
import json
import vlc
import time
import requests
import re
import random
import math
import shutil

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- КОНСТАНТЫ ---
TAG_COLORS = {"Музыка": "#e74c3c", "Видео": "#3498db", "Юмор": "#2ecc71", "Фильмы": "#f1c40f", "Гейминг": "#9b59b6", "TikTok": "#ff0050"}
TAG_FOLDERS = {"Музыка": "Музыка", "Видео": "Видео", "Юмор": "Юмор", "Фильмы": "Фильмы", "Гейминг": "Гейминг", "TikTok": "TikTok"}
YT_MAP = {"Music": "Музыка", "Comedy": "Юмор", "Entertainment": "Юмор", "Film & Animation": "Фильмы", "Gaming": "Гейминг"}
PARTICLE_COLORS = ["#FF0000", "#FFD700", "#FFFFFF", "#FF69B4", "#00FFFF"]
REACTION_ICONS = {"Музыка": "🎵", "Юмор": "😆", "Гейминг": "🎮", "Фильмы": "🎬", "Видео": "👍", "TikTok": "📱"}

def clean_ansi(text):
    return re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', str(text))

class YouTubeSlider(Canvas):
    def __init__(self, master, command=None, **kwargs):
        super().__init__(master, height=25, bg="#1a1a1a", highlightthickness=0, **kwargs)
        self.command = command
        self.progress = 0
        self.segments = []
        self.bind("<Button-1>", self.handle_click)
        self.bind("<B1-Motion>", self.handle_click)
        self.bind("<Configure>", lambda e: self.render())

    def update_segments(self, segments_data, duration_sec):
        self.segments = []
        if duration_sec <= 0:
            return
        colors = {"sponsor": "#00d400", "interaction": "#ff00ff", "outro": "#0000ff", "intro": "#00ffff"}
        for seg in segments_data:
            start = seg['segment'][0] / duration_sec
            end = seg['segment'][1] / duration_sec
            self.segments.append((start, end, colors.get(seg['category'], "#555555")))
        self.render()

    def set_progress(self, val):
        self.progress = val
        self.render()

    def render(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        mid_y = h // 2
        bar_h = 10
        self.create_rectangle(0, mid_y-bar_h//2, w, mid_y+bar_h//2, fill="#3d3d3d", outline="")
        for s, e, c in self.segments:
            self.create_rectangle(s*w, mid_y-bar_h//2-2, e*w, mid_y+bar_h//2+2, fill=c, outline="")
        self.create_rectangle(0, mid_y-bar_h//2, self.progress*w, mid_y+bar_h//2, fill="#FF0000", outline="")
        if self.progress > 0:
            cx = self.progress * w
            self.create_oval(cx-8, mid_y-8, cx+8, mid_y+8, fill="#FF0000", outline="#fff")

    def handle_click(self, event):
        w = self.winfo_width()
        if w > 0:
            val = max(0, min(1, event.x / w))
            if self.command:
                self.command(val * 100)

class MediaHub(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MediaHub")
        self.geometry("1400x950")

        # Настройки
        self.config_file = "mediahub_config.json"
        self.config_data = {
            "save_path": os.getcwd(), # По умолчанию папка программы
            "res": "1080p", "concurrent_frags": "10", "sponsor_block": True, 
            "liked_files": [], "metadata_cache": {}, "proxy": ""
        }
        self.load_settings()
        self.ensure_folders()

        self.vlc_instance = vlc.Instance("--no-xlib --quiet")
        self.vlc_player = self.vlc_instance.media_player_new()
        
        self.current_view = "all"
        self.current_file_path = None
        self.current_cat = "Видео"
        
        self.create_widgets()
        self.refresh_playlist()
        self.update_loop()

        # Хоткеи
        self.bind_all("<space>", self.hk_pause)
        self.bind_all("<Right>", self.hk_forward)
        self.bind_all("<Left>", self.hk_backward)
        self.bind_all("<Up>", self.hk_vol_up)
        self.bind_all("<Down>", self.hk_vol_down)
        
        # Универсальный Ctrl+V
        def handle_ctrl_v(event):
            if event.keycode == 86:
                self.paste_url()
                return "break"
        self.bind_all("<Control-KeyPress>", handle_ctrl_v)

    def is_typing(self):
        focus = self.focus_get()
        return isinstance(focus, ctk.CTkEntry)

    def hk_pause(self, e):
        if not self.is_typing():
            self.vlc_player.pause()

    def hk_forward(self, e):
        if not self.is_typing():
            self.vlc_player.set_time(self.vlc_player.get_time() + 10000)

    def hk_backward(self, e):
        if not self.is_typing():
            self.vlc_player.set_time(self.vlc_player.get_time() - 10000)

    def hk_vol_up(self, e):
        if not self.is_typing():
            v = min(100, int(self.vol_slider.get() + 5))
            self.vol_slider.set(v)
            self.vlc_player.audio_set_volume(v)

    def hk_vol_down(self, e):
        if not self.is_typing():
            v = max(0, int(self.vol_slider.get() - 5))
            self.vol_slider.set(v)
            self.vlc_player.audio_set_volume(v)

    def ensure_folders(self):
        base = self.config_data["save_path"]
        for f in ["img", "Музыка", "Видео", "Юмор", "Фильмы", "Гейминг", "TikTok"]:
            path = os.path.join(base, f)
            if not os.path.exists(path):
                os.makedirs(path)

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding='utf-8') as f:
                    self.config_data.update(json.load(f))
            except:
                pass

    def save_settings(self):
        with open(self.config_file, "w", encoding='utf-8') as f:
            json.dump(self.config_data, f, ensure_ascii=False, indent=4)

    def create_widgets(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(padx=10, pady=10, fill="both", expand=True)

        self.tab_dl = self.tabview.add("📥 Загрузка и Поиск")
        self.tab_player = self.tabview.add("🎵 Плеер")
        self.tab_set = self.tabview.add("⚙️ Настройки")

        # --- ЗАГРУЗКА ---
        ctk.CTkLabel(self.tab_dl, text="MediaHub", font=("Arial", 28, "bold")).pack(pady=10)
        search_f = ctk.CTkFrame(self.tab_dl, fg_color="transparent")
        search_f.pack(pady=5)
        self.url_entry = ctk.CTkEntry(search_f, placeholder_text="Поиск или ссылка YouTube...", width=600, height=50)
        self.url_entry.pack(side="left", padx=5)
        self.dl_main_btn = ctk.CTkButton(search_f, text="НАЙТИ / СКАЧАТЬ", width=150, height=50, fg_color="#27ae60", command=self.analyze_link)
        self.dl_main_btn.pack(side="left")

        self.search_results_frame = ctk.CTkScrollableFrame(self.tab_dl, width=850, height=300, label_text="Результаты")
        self.search_results_frame.pack(pady=10, padx=20)

        self.dl_mode = ctk.CTkSegmentedButton(self.tab_dl, values=["Видео", "Аудио (MP3)"])
        self.dl_mode.set("Видео")
        self.dl_mode.pack(pady=5)
        self.dl_progress = ctk.CTkProgressBar(self.tab_dl, width=800)
        self.dl_progress.set(0)
        self.dl_progress.pack(pady=10)
        self.dl_status = ctk.CTkLabel(self.tab_dl, text="Готов", font=("Arial", 14, "bold"), text_color="#1abc9c")
        self.dl_status.pack()

        # === ПЛЕЕР ===
        p_main = ctk.CTkFrame(self.tab_player, fg_color="transparent")
        p_main.pack(fill="both", expand=True)
        
        left_side = ctk.CTkFrame(p_main, width=480)
        left_side.pack(side="left", fill="y", padx=5, pady=5)
        
        filter_f = ctk.CTkFrame(left_side, fg_color="transparent")
        filter_f.pack(fill="x", padx=5, pady=5)
        ctk.CTkButton(filter_f, text="Все", width=70, command=lambda: self.switch_view("all")).grid(row=0, column=0, padx=2)
        ctk.CTkButton(filter_f, text="Музыка", width=80, command=lambda: self.switch_view("Музыка")).grid(row=0, column=1, padx=2)
        ctk.CTkButton(filter_f, text="Юмор", width=70, command=lambda: self.switch_view("Юмор")).grid(row=0, column=2, padx=2)
        ctk.CTkButton(filter_f, text="TikTok", width=70, command=lambda: self.switch_view("TikTok")).grid(row=0, column=3, padx=2)
        ctk.CTkButton(filter_f, text="❤", width=50, fg_color="#c0392b", command=lambda: self.switch_view("liked")).grid(row=0, column=4, padx=2)

        self.lib_scroll = ctk.CTkScrollableFrame(left_side, label_text="Библиотека (ПКМ для управления)")
        self.lib_scroll.pack(fill="both", expand=True, padx=5, pady=5)

        right_side = ctk.CTkFrame(p_main, fg_color="black")
        right_side.pack(side="right", fill="both", expand=True, padx=5, pady=5)
        self.vid_box = ctk.CTkFrame(right_side, fg_color="black")
        self.vid_box.pack(fill="both", expand=True)

        ctrls = ctk.CTkFrame(right_side, height=150, fg_color="#1a1a1a")
        ctrls.pack(fill="x", side="bottom")
        self.seek_bar = YouTubeSlider(ctrls, command=self.seek_media)
        self.seek_bar.pack(fill="x", padx=15, pady=5)
        
        info_f = ctk.CTkFrame(ctrls, fg_color="transparent")
        info_f.pack(fill="x", padx=15)
        self.track_name = ctk.CTkLabel(info_f, text="Файл не выбран", font=("Arial", 12, "bold"), text_color="white", wraplength=500, justify="left")
        self.track_name.pack(side="left")
        self.time_lbl = ctk.CTkLabel(info_f, text="00:00 / 00:00", font=("Consolas", 14))
        self.time_lbl.pack(side="right")

        btn_f = ctk.CTkFrame(ctrls, fg_color="transparent")
        btn_f.pack(pady=5)
        ctk.CTkButton(btn_f, text="▶/⏸", width=60, command=lambda: self.vlc_player.pause()).grid(row=0, column=0, padx=5)
        
        self.like_container = ctk.CTkFrame(btn_f, width=75, height=60, fg_color="transparent")
        self.like_container.grid(row=0, column=1, padx=5)
        self.like_container.grid_propagate(False)
        self.like_btn = ctk.CTkButton(self.like_container, text="👍", width=50, height=50, font=("Arial", 22), fg_color="#333", command=self.toggle_like)
        self.like_btn.place(relx=0.5, rely=0.5, anchor="center")

        self.vol_slider = ctk.CTkSlider(btn_f, from_=0, to=100, width=150, command=lambda v: self.vlc_player.audio_set_volume(int(float(v))))
        self.vol_slider.set(70)
        self.vol_slider.grid(row=0, column=2, padx=20)

        # --- НАСТРОЙКИ ---
        self.build_settings()

    def build_settings(self):
        s = ctk.CTkScrollableFrame(self.tab_set)
        s.pack(fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(s, text="📂 Путь скачивания:").pack(anchor="w", pady=(10,0))
        path_f = ctk.CTkFrame(s)
        path_f.pack(fill="x", pady=5)
        self.set_path_lbl = ctk.CTkLabel(path_f, text=self.config_data["save_path"], text_color="yellow")
        self.set_path_lbl.pack(side="left", padx=10)
        ctk.CTkButton(path_f, text="Изменить", width=100, command=self.change_save_path).pack(side="right", padx=10)
        
        ctk.CTkLabel(s, text="📺 Качество:").pack(anchor="w")
        self.opt_res = ctk.CTkOptionMenu(s, values=["4K", "1440p", "1080p", "720p"], command=lambda v: self.update_cfg("res", v))
        self.opt_res.set(self.config_data["res"])
        self.opt_res.pack(fill="x", pady=5)

        self.cb_sb = ctk.CTkCheckBox(s, text="Использовать SponsorBlock", command=lambda: self.update_cfg("sponsor_block", self.cb_sb.get()))
        if self.config_data["sponsor_block"]:
            self.cb_sb.select()
        self.cb_sb.pack(anchor="w", pady=10)

        ctk.CTkLabel(s, text="📦 Offline Mirror (Sneakernet):").pack(anchor="w", pady=(10,0))
        ctk.CTkButton(s, text="ЭКСПОРТИРОВАТЬ ДЛЯ ДРУГА (USB)", fg_color="#34495e", height=40, command=self.export_library).pack(fill="x", pady=5)

    def update_cfg(self, k, v):
        self.config_data[k] = v
        self.save_settings()

    # --- МЕНЕДЖМЕНТ ---
    def show_context_menu(self, event, full_p, filename, current_cat):
        m = Menu(self, tearoff=0, bg="#2b2b2b", fg="white", font=("Arial", 10))
        sub = Menu(m, tearoff=0, bg="#2b2b2b", fg="white")
        for cat in TAG_FOLDERS.keys():
            if cat != current_cat:
                sub.add_command(label=f"В {cat}", command=lambda c=cat: self.move_file(full_p, filename, c))
        m.add_cascade(label="📦 Перенести в класс...", menu=sub)
        m.add_separator()
        m.add_command(label="❌ Удалить файл", command=lambda: self.delete_file(full_p))
        m.post(event.x_root, event.y_root)

    def move_file(self, old_path, filename, new_cat):
        try:
            new_dir = os.path.join(self.config_data["save_path"], TAG_FOLDERS[new_cat])
            if not os.path.exists(new_dir):
                os.makedirs(new_dir)
            shutil.move(old_path, os.path.join(new_dir, filename))
            self.config_data["metadata_cache"][filename] = {"category": new_cat}
            self.save_settings()
            self.refresh_playlist()
        except:
            pass

    def delete_file(self, path):
        if messagebox.askyesno("Удаление", "Удалить навсегда?"):
            os.remove(path)
            self.refresh_playlist()

    def get_final_cat(self, title, info):
        yt_cat = info.get('categories', [''])[0]
        cat = YT_MAP.get(yt_cat, "Видео")
        title_l = title.lower()
        # Железный приоритет Музыки
        if any(x in title_l for x in ["дайте танк", "рекурсия", "песня", "shadowraze", "music"]):
            cat = "Музыка"
        if any(x in title_l for x in ["братишкин", "стинт", "нарезка", "смешно"]):
            cat = "Юмор"
        if "tiktok" in title_l or "tiktok" in str(info.get('webpage_url', '')).lower():
            cat = "TikTok"
        return cat

    def refresh_playlist(self):
        for w in self.lib_scroll.winfo_children():
            w.destroy()
        base = self.config_data["save_path"]
        
        for cat_tag, folder_name in TAG_FOLDERS.items():
            f_path = os.path.join(base, folder_name)
            if not os.path.exists(f_path):
                continue
            
            files = [f for f in os.listdir(f_path) if f.lower().endswith(('.mp4', '.mp3', '.mkv', '.webm'))]
            if files:
                ctk.CTkLabel(self.lib_scroll, text=f"📂 {cat_tag.upper()}", font=("Arial", 11, "bold"), text_color="gray").pack(fill="x", pady=(10, 2), padx=5)
            
            for f in files:
                if self.current_view != "all" and self.current_view != "liked" and self.current_view != cat_tag:
                    continue
                if self.current_view == "liked" and f not in self.config_data["liked_files"]:
                    continue

                item_f = ctk.CTkFrame(self.lib_scroll, fg_color="transparent")
                item_f.pack(fill="x", pady=2, padx=5)
                ctk.CTkLabel(item_f, text=cat_tag.upper(), font=("Arial", 7, "bold"), fg_color=TAG_COLORS[cat_tag], text_color="white", corner_radius=3, width=50).pack(side="left", padx=2, anchor="n")
                
                full_p = os.path.join(f_path, f)
                clean_name = re.sub(r'\s\[.{11}\]', '', f)
                
                btn = ctk.CTkLabel(item_f, text=clean_name, anchor="w", text_color="white", 
                                   font=("Arial", 11), wraplength=380, justify="left", cursor="hand2")
                btn.pack(side="left", fill="x", expand=True, padx=5, pady=2)
                
                for widget in [item_f, btn]:
                    widget.bind("<Button-1>", lambda e, p=full_p, n=f, c=cat_tag: self.play_media(p, n, c))
                    widget.bind("<Button-3>", lambda e, p=full_p, n=f, c=cat_tag: self.show_context_menu(e, p, n, c))
                
                def on_enter(e, wid=item_f):
                    wid.configure(fg_color="#333333")
                def on_leave(e, wid=item_f):
                    wid.configure(fg_color="transparent")
                item_f.bind("<Enter>", on_enter)
                item_f.bind("<Leave>", on_leave)
                btn.bind("<Enter>", on_enter)
                btn.bind("<Leave>", on_leave)

    def play_media(self, full_path, filename, cat="Видео"):
        self.current_file_path = full_path
        if filename in self.config_data["metadata_cache"]:
            self.current_cat = self.config_data["metadata_cache"][filename]["category"]
        else:
            self.current_cat = cat
            
        self.like_btn.configure(text=REACTION_ICONS.get(self.current_cat, "👍"))
        self.track_name.configure(text=filename)
        
        media = self.vlc_instance.media_new(full_path)
        self.vlc_player.set_media(media)
        self.vlc_player.set_hwnd(self.vid_box.winfo_id())
        self.vlc_player.play()
        self.update_like_style(filename in self.config_data["liked_files"])
        
        vid_id = filename.split("[")[-1].split("]")[0] if "[" in filename else None
        if vid_id:
            threading.Thread(target=self.load_sb, args=(vid_id,), daemon=True).start()
        else:
            self.seek_bar.update_segments([], 0)

    # --- ЗАГРУЗКА ---
    def analyze_link(self):
        val = self.url_entry.get()
        if not val:
            return
        self.dl_status.configure(text="Обработка...", text_color="yellow")
        if any(x in val.lower() for x in ["youtube.com", "youtu.be", "tiktok.com"]):
            threading.Thread(target=self.proc_analyze, args=(val,), daemon=True).start()
        else:
            threading.Thread(target=self.search_youtube, args=(val,), daemon=True).start()

    def download_engine(self, urls):
        for url in urls:
            try:
                self.dl_status.configure(text="Анализ...", text_color="yellow")
                # Используем вспомогательную функцию для поиска ffmpeg внутри EXE или рядом
                bin_path = resource_path("./")
                with yt_dlp.YoutubeDL({'quiet': True, 'ffmpeg_location': bin_path, 'javascript_runtimes': ['node']}) as ydl:
                    info = ydl.extract_info(url, download=False)
                    cat = self.get_final_cat(info['title'], info)
                    save_dir = os.path.join(self.config_data["save_path"], TAG_FOLDERS[cat])
                    img_dir = os.path.join(self.config_data["save_path"], "img")
                    self.config_data["metadata_cache"][f"{info['title']} [{info['id']}].mp4"] = {"category": cat}
                    self.save_settings()

                opts = {
                    'outtmpl': f'{save_dir}/%(title)s [%(id)s].%(ext)s',
                    'writethumbnail': True, 'thumbnail_output': f'{img_dir}/%(title)s.%(ext)s',
                    'progress_hooks': [self.dl_hook], 'ffmpeg_location': bin_path,
                    'writesubtitles': True, 'embedsubtitles': True, 'subtitleslangs': ['ru', 'en'],
                    'javascript_runtimes': ['node'],
                    'postprocessors': [{'key': 'FFmpegEmbedSubtitle'}, {'key': 'FFmpegMetadata'}, {'key': 'EmbedThumbnail'}]
                }
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.download([url])
                self.after(0, lambda: [self.dl_status.configure(text="Скачано!", text_color="#27ae60"), self.refresh_playlist()])
            except:
                self.after(0, lambda: self.dl_status.configure(text="Ошибка!", text_color="red"))
        self.after(0, lambda: self.dl_main_btn.configure(state="normal"))

    # --- ЛАЙКИ ---
    def update_like_style(self, liked):
        if liked:
            self.like_btn.configure(fg_color="#FF0000", hover_color="#922b21")
        else:
            self.like_btn.configure(fg_color="#333", hover_color="#444")

    def toggle_like(self):
        if not self.current_file_path:
            return
        fname = os.path.basename(self.current_file_path)
        if fname in self.config_data["liked_files"]:
            self.config_data["liked_files"].remove(fname)
            self.update_like_style(False)
        else:
            self.config_data["liked_files"].append(fname)
            self.update_like_style(True)
            self.play_explosion_animation()
        self.save_settings()

    def play_explosion_animation(self):
        colors = PARTICLE_COLORS if self.current_cat != "Видео" else ["#3498DB", "#FFFFFF"]
        spark_win = Toplevel(self)
        spark_win.overrideredirect(True)
        spark_win.attributes("-topmost", True, "-transparentcolor", "black")
        
        # Увеличили окно до 600x600, чтобы не было "краёв", и центрируем точнее
        W, H = 600, 600
        bx, by = self.like_btn.winfo_rootx(), self.like_btn.winfo_rooty()
        bw, bh = self.like_btn.winfo_width(), self.like_btn.winfo_height()
        spark_win.geometry(f"{W}x{H}+{bx + bw//2 - W//2}+{by + bh//2 - H//2}")
        
        canvas = Canvas(spark_win, width=W, height=H, bg="black", highlightthickness=0)
        canvas.pack()
        
        # Частицы теперь разлетаются в центре 600x600 окна
        particles = [{"x": W//2, "y": H//2, "vx": math.cos(a)*random.uniform(5,15), "vy": math.sin(a)*random.uniform(5,15), 
                      "gravity": 0.25, "radius": random.randint(8,20), "color": random.choice(colors)} 
                     for a in [random.uniform(0, 2*math.pi) for _ in range(45)]]
        
        frames = 40
        def animate(f=0):
            if f < frames:
                canvas.delete("all")
                for p in particles:
                    p["x"] += p["vx"]
                    p["y"] += p["vy"]
                    p["vy"] += p["gravity"]
                    p["radius"] *= 0.93
                    canvas.create_oval(p["x"]-p["radius"], p["y"]-p["radius"], 
                                      p["x"]+p["radius"], p["y"]+p["radius"], fill=p["color"], outline="")
                self.after(15, lambda: animate(f + 1))
            else:
                spark_win.destroy()
        
        animate()

    # --- СИСТЕМНОЕ ---
    def search_youtube(self, q):
        for w in self.search_results_frame.winfo_children():
            w.destroy()
        try:
            with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'javascript_runtimes': ['node']}) as ydl:
                info = ydl.extract_info(f"ytsearch10:{q}", download=False)
                for e in info['entries']:
                    btn = ctk.CTkButton(self.search_results_frame, text=f"📺 {e['title']}", anchor="w", fg_color="transparent", command=lambda u=e['url']: [self.url_entry.delete(0, 'end'), self.url_entry.insert(0, u), self.analyze_link()])
                    btn.pack(fill="x", pady=1)
            self.dl_status.configure(text="Выберите видео", text_color="#1abc9c")
        except:
            pass

    def proc_analyze(self, u):
        try:
            with yt_dlp.YoutubeDL({'extract_flat': True, 'quiet': True, 'javascript_runtimes': ['node']}) as ydl:
                info = ydl.extract_info(u, download=False)
                if 'entries' in info:
                    self.after(0, lambda: self.show_sel(info))
                else:
                    self.start_dl([u])
        except:
            messagebox.showerror("Ошибка", "Анализ провален")

    def show_sel(self, info):
        win = Toplevel(self); win.title("Выбор"); win.geometry("650x750"); win.configure(bg="#1a1a1a"); win.attributes("-topmost", True)
        ctk.CTkButton(win, text="СКАЧАТЬ ВЫБРАННОЕ", fg_color="#27ae60", command=lambda: [self.start_dl([u for u,v in checks if v.get()]), win.destroy()]).pack(pady=15)
        checks = []
        scroll = ctk.CTkScrollableFrame(win); scroll.pack(fill="both", expand=True, padx=10, pady=10)
        for e in info['entries']:
            v = ctk.BooleanVar(value=True); cb = ctk.CTkCheckBox(scroll, text=e.get('title', 'Video'), variable=v); cb.pack(anchor="w", pady=5); checks.append((e['url'], v))

    def update_loop(self):
        if self.vlc_player.is_playing():
            l, c = self.vlc_player.get_length(), self.vlc_player.get_time()
            if l > 0:
                self.seek_bar.set_progress(c / l)
                self.time_lbl.configure(text=f"{time.strftime('%M:%S', time.gmtime(c//1000))} / {time.strftime('%M:%S', time.gmtime(l//1000))}")
        self.after(500, self.update_loop)

    def start_dl(self, urls):
        self.dl_main_btn.configure(state="disabled")
        threading.Thread(target=self.download_engine, args=(urls,), daemon=True).start()

    def dl_hook(self, d):
        if d['status'] == 'downloading':
            try:
                p = float(clean_ansi(d.get('_percent_str', '0%')).replace('%','')) / 100
                self.dl_progress.set(p)
                self.dl_status.configure(text=f"Загрузка: {d.get('_percent_str')}")
            except:
                pass

    def switch_view(self, v):
        self.current_view = v
        self.refresh_playlist()

    def paste_url(self):
        try:
            self.url_entry.delete(0, 'end')
            self.url_entry.insert(0, self.clipboard_get())
        except:
            pass

    def stop_media(self):
        self.vlc_player.stop()
        self.seek_bar.set_progress(0)

    def change_save_path(self):
        p = filedialog.askdirectory()
        if p:
            self.config_data["save_path"] = p
            self.ensure_folders()
            self.save_settings()
            self.refresh_playlist()
            self.set_path_lbl.configure(text=p)

    def export_library(self):
        dest = filedialog.askdirectory(title="Выберите папку для экспорта (флешку)")
        if not dest: return
        
        self.dl_status.configure(text="Экспорт...", text_color="yellow")
        self.dl_main_btn.configure(state="disabled")
        
        def run_export():
            try:
                base = self.config_data["save_path"]
                folders = ["img", "Музыка", "Видео", "Юмор", "Фильмы", "Гейминг", "TikTok"]
                for f in folders:
                    src_f = os.path.join(base, f)
                    dest_f = os.path.join(dest, f)
                    if os.path.exists(src_f):
                        if not os.path.exists(dest_f): os.makedirs(dest_f)
                        for item in os.listdir(src_f):
                            shutil.copy2(os.path.join(src_f, item), os.path.join(dest_f, item))
                
                # Создаем переносной конфиг
                portable_cfg = self.config_data.copy()
                portable_cfg["save_path"] = "./" # Относительный путь для друга
                with open(os.path.join(dest, "mediahub_config.json"), "w", encoding='utf-8') as f:
                    json.dump(portable_cfg, f, ensure_ascii=False, indent=4)
                
                self.after(0, lambda: messagebox.showinfo("Готово", f"Библиотека экспортирована в:\n{dest}"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Ошибка", f"Экспорт прерван: {e}"))
            finally:
                self.after(0, lambda: [self.dl_status.configure(text="Готов", text_color="#1abc9c"), self.dl_main_btn.configure(state="normal")])

        threading.Thread(target=run_export, daemon=True).start()

    def seek_media(self, pct):
        l = self.vlc_player.get_length()
        if l > 0:
            self.vlc_player.set_time(int((pct/100)*l))

    def load_sb(self, vid_id):
        try:
            r = requests.get(f"https://sponsor.ajay.app/api/skipSegments?videoID={vid_id}&categories=['sponsor','intro','outro','interaction']", timeout=5)
            if r.status_code == 200:
                self.seek_bar.update_segments(r.json(), self.vlc_player.get_length()/1000)
        except:
            pass

if __name__ == "__main__":
    app = MediaHub()
    app.mainloop()