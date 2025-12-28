import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageGrab
import pyautogui
import threading
import time
import json
import os
from pynput import mouse, keyboard

# === 全局配置 ===
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

if not os.path.exists("assets"):
    os.makedirs("assets")

# === UI 主题配色 ===
THEME = {
    "bg_main": "#2b2b2b", "bg_panel": "#3c3f41", "bg_canvas": "#1e1e1e",
    "grid_line": "#2b2b2b", "text_main": "#ffffff", "text_dim": "#bbbbbb",
    "node_bg": "#3c3f41", "node_border": "#555555", "wire": "#a9b7c6",
    "wire_active": "#00e676",
    "entry_bg": "#505354", "entry_hlt": "#5d4037",
    "header_start": "#5c8d89", "header_find": "#4a90e2", "header_click": "#f5a623",
    "header_input": "#bd10e0", "header_logic": "#9013fe", "header_default": "#607d8b"
}


# ==========================================
# 辅助类：截图工具 (ESC 暴力修复版)
# ==========================================
class SnippingTool(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3)
        self.attributes('-topmost', True)
        self.config(cursor="cross", bg='black')

        self.canvas = tk.Canvas(self, cursor="cross", bg="grey11", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(self.winfo_screenwidth() // 2, 100, text="按住左键框选 / 按 ESC 退出", fill="white",
                                font=("Segoe UI", 16, "bold"))

        # 鼠标事件
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # 【核心修复】全局绑定 ESC，防止焦点丢失导致无法退出
        self.bind_all("<Escape>", self.exit_tool)

        # 强制获取焦点
        self.focus_force()
        self.grab_set()

        self.start_x = None
        self.start_y = None
        self.rect = None

    def exit_tool(self, event=None):
        # 解除绑定，防止影响主程序
        self.unbind_all("<Escape>")
        self.grab_release()
        self.destroy()
        self.callback(None)

    def on_press(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y,
                                                 outline='#00e676', width=2)

    def on_drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        self.unbind_all("<Escape>")  # 同样解除绑定
        end_x = self.canvas.canvasx(event.x)
        end_y = self.canvas.canvasy(event.y)
        self.grab_release()
        self.destroy()
        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.callback((int(x1), int(y1), int(x2), int(y2)))
        else:
            self.callback(None)


# ==========================================
# 主程序类
# ==========================================
class AutoBotGraph(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoBot v1.1 - Updated")
        self.geometry("1350x900")
        self.configure(bg=THEME["bg_main"])

        # 点击空白处释放焦点（重要！否则热键不生效）
        self.bind("<Button-1>", self.release_focus_global)

        # 数据
        self.nodes = {}
        self.node_counter = 0
        self.start_node_id = "start"
        self.nodes[self.start_node_id] = {'type': 'start', 'x': 80, 'y': 80, 'next': None, 'data': {}}

        self.selected_node_id = None
        self.recording_last_id = None
        self.current_img_path = None
        self.is_recording = False
        self.is_playing = False
        self.is_paused = False
        self.temp_line = None
        self.drag_data = {"item": None, "x": 0, "y": 0, "type": None, "source_id": None}

        self.mouse_listener = None
        self.key_listener = None
        self.last_action_time = 0

        self.setup_styles()
        self.setup_ui()
        self.refresh_canvas()

        # 启动监听
        threading.Thread(target=self.hotkey_thread_worker, daemon=True).start()

        self.update_mouse_coords()
        self.focus_set()  # 启动时聚焦主窗口

    def release_focus_global(self, event):
        """点击非输入框区域，强制让输入框失去焦点，激活热键"""
        if not isinstance(event.widget, tk.Entry):
            self.focus_set()

    def release_focus_entry(self, event):
        """回车键确认修改，释放焦点"""
        self.focus_set()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TCombobox", fieldbackground=THEME["bg_panel"], background="#555", foreground="white",
                        arrowcolor="white")
        style.map("TCombobox", fieldbackground=[("readonly", THEME["bg_panel"])],
                  selectbackground=[("readonly", "#555")])

    def setup_ui(self):
        # === 1. 顶部热键设置 ===
        f_top = tk.LabelFrame(self, text="🕹️ 全局热键配置 (修改后请点击空白处或按回车生效)", padx=5, pady=5,
                              bg=THEME["bg_panel"], fg="#00e676")
        f_top.pack(fill="x", padx=5, pady=5)

        entry_hk_conf = {"width": 6, "bg": "#505354", "fg": "#00e676", "relief": "flat", "justify": "center"}
        lbl_hk_conf = {"bg": THEME["bg_panel"], "fg": "white"}

        def create_hk(parent, val):
            e = tk.Entry(parent, **entry_hk_conf)
            e.insert(0, val)
            e.bind("<Return>", self.release_focus_entry)
            return e

        tk.Label(f_top, text="截图:", **lbl_hk_conf).pack(side="left")
        self.e_cap = create_hk(f_top, "f7")
        self.e_cap.pack(side="left", padx=(2, 10))

        tk.Label(f_top, text="抓点:", **lbl_hk_conf).pack(side="left")
        self.e_pick = create_hk(f_top, "f8")
        self.e_pick.pack(side="left", padx=(2, 10))

        tk.Frame(f_top, width=20, bg=THEME["bg_panel"]).pack(side="left")

        tk.Label(f_top, text="| 开始录制:", bg=THEME["bg_panel"], fg="#ff8a80").pack(side="left")
        self.e_rec_start = create_hk(f_top, "f9")
        self.e_rec_start.pack(side="left", padx=(2, 5))

        tk.Label(f_top, text="结束录制:", bg=THEME["bg_panel"], fg="#ff8a80").pack(side="left")
        self.e_rec_stop = create_hk(f_top, "f10")
        self.e_rec_stop.pack(side="left", padx=(2, 10))

        tk.Label(f_top, text="| 开始运行:", bg=THEME["bg_panel"], fg="#b9f6ca").pack(side="left")
        self.e_run_start = create_hk(f_top, "f11")
        self.e_run_start.pack(side="left", padx=(2, 5))

        tk.Label(f_top, text="停止运行:", bg=THEME["bg_panel"], fg="#b9f6ca").pack(side="left")
        self.e_run_stop = create_hk(f_top, "f12")
        self.e_run_stop.pack(side="left", padx=(2, 10))

        tk.Label(f_top, text="| 暂停/恢复:", bg=THEME["bg_panel"], fg="#ffe57f").pack(side="left")
        self.e_pause = create_hk(f_top, "f6")
        self.e_pause.pack(side="left", padx=(2, 5))

        self.lbl_status = tk.Label(f_top, text="● 就绪", fg="gray", bg=THEME["bg_panel"], font=("Arial", 10, "bold"))
        self.lbl_status.pack(side="right", padx=15)
        self.lbl_mouse = tk.Label(f_top, text="XY: 0, 0", fg="#bbbbbb", bg=THEME["bg_panel"], font=("Consolas", 9))
        self.lbl_mouse.pack(side="right", padx=10)

        # === 2. 主体 ===
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=THEME["bg_main"], sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        # 左侧
        f_left = tk.Frame(paned, bg=THEME["bg_panel"], width=420)
        f_left.pack_propagate(False)
        paned.add(f_left)
        self.entry_conf = {"bg": THEME["entry_bg"], "fg": "white", "relief": "flat", "insertbackground": "white"}
        title_style = {"bg": THEME["bg_panel"], "fg": THEME["text_dim"], "font": ("Segoe UI", 9, "bold"), "anchor": "w"}

        f_form = tk.Frame(f_left, bg=THEME["bg_panel"], padx=15, pady=15)
        f_form.pack(fill="x")
        tk.Label(f_form, text="节点类型 / TYPE", **title_style).pack(fill="x", pady=(0, 5))
        self.cb_type = ttk.Combobox(f_form, state="readonly", font=("Segoe UI", 10),
                                    values=["寻找图片", "点击坐标", "输入文本", "按下按键", "等待", "移动", "拖拽"])
        self.cb_type.current(1)
        self.cb_type.pack(fill="x", pady=(0, 15))
        self.cb_type.bind("<<ComboboxSelected>>", self.on_type_change)

        f_coords = tk.Frame(f_form, bg=THEME["bg_panel"])
        f_coords.pack(fill="x", pady=(0, 15))
        f_cx = tk.Frame(f_coords, bg=THEME["bg_panel"])
        f_cx.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.lbl_x = tk.Label(f_cx, text="X 坐标", **title_style)
        self.lbl_x.pack(fill="x")
        self.e_x = tk.Entry(f_cx, **self.entry_conf)
        self.e_x.pack(fill="x", ipady=4)
        f_cy = tk.Frame(f_coords, bg=THEME["bg_panel"])
        f_cy.pack(side="left", fill="x", expand=True, padx=(5, 0))
        self.lbl_y = tk.Label(f_cy, text="Y 坐标", **title_style)
        self.lbl_y.pack(fill="x")
        self.e_y = tk.Entry(f_cy, **self.entry_conf)
        self.e_y.pack(fill="x", ipady=4)

        self.btn_cap = tk.Button(f_form, text="📷 截取屏幕 (F7)", command=self.start_capture, bg="#ff9800", fg="white",
                                 relief="flat", font=("Segoe UI", 9, "bold"), state="disabled")
        self.btn_cap.pack(fill="x", pady=(0, 15), ipady=2)

        self.f_region = tk.Frame(f_form, bg=THEME["bg_panel"])
        self.f_region.pack(fill="x", pady=(0, 10))
        self.var_regional = tk.BooleanVar()
        self.chk_region = tk.Checkbutton(self.f_region, text="启用区域搜索", variable=self.var_regional,
                                         command=self.toggle_region_ui, bg=THEME["bg_panel"], fg="white",
                                         selectcolor=THEME["bg_panel"], activebackground=THEME["bg_panel"])
        self.chk_region.pack(anchor="w")
        f_rad = tk.Frame(self.f_region, bg=THEME["bg_panel"])
        f_rad.pack(fill="x", pady=2)
        tk.Label(f_rad, text="搜索半径:", **title_style).pack(side="left")
        self.e_radius = tk.Entry(f_rad, width=8, **self.entry_conf)
        self.e_radius.insert(0, "300")
        self.e_radius.pack(side="left", padx=5)
        self.var_stop_fail = tk.BooleanVar(value=True)
        tk.Checkbutton(self.f_region, text="未找到时停止脚本", variable=self.var_stop_fail, fg="#ff5252",
                       bg=THEME["bg_panel"], selectcolor=THEME["bg_panel"], activebackground=THEME["bg_panel"]).pack(
            anchor="w")

        self.lbl_img = tk.Label(f_form, text="[无图片]", bg="#2b2b2b", fg="#666", relief="flat", height=4)
        self.lbl_img.pack(fill="x", pady=(0, 15))
        self.lbl_p = tk.Label(f_form, text="参数值 / PARAM", **title_style)
        self.lbl_p.pack(fill="x")
        self.e_param = tk.Entry(f_form, **self.entry_conf)
        self.e_param.pack(fill="x", ipady=4)
        self.lbl_hint = tk.Label(f_form, text="提示...", fg="#888", bg=THEME["bg_panel"], font=("Segoe UI", 8),
                                 wraplength=380, justify="left")
        self.lbl_hint.pack(fill="x", pady=(10, 0))

        # === 按钮区域 (修改了这里) ===
        f_btns = tk.Frame(f_left, bg=THEME["bg_panel"], padx=15, pady=10)
        f_btns.pack(fill="x", side="top")

        btn_conf = {"relief": "flat", "font": ("Segoe UI", 9), "fg": "white", "width": 12}

        # 第一排：新增 | 更新
        tk.Button(f_btns, text="➕ 新增节点", command=self.add_node_btn, bg="#43a047", **btn_conf) \
            .grid(row=0, column=0, padx=2, pady=5)

        # 【新增】更新节点按钮
        tk.Button(f_btns, text="💾 更新节点", command=self.update_node_btn, bg="#00bcd4", **btn_conf) \
            .grid(row=0, column=1, padx=2, pady=5)

        # 第二排：测试 | 删除
        tk.Button(f_btns, text="🧪 测试", command=self.test_single_action, bg="#1e88e5", **btn_conf) \
            .grid(row=1, column=0, padx=2, pady=5)

        tk.Button(f_btns, text="❌ 删除节点", command=self.delete_node, bg="#e53935", **btn_conf) \
            .grid(row=1, column=1, padx=2, pady=5)

        # 画布
        self.canvas = tk.Canvas(paned, bg=THEME["bg_canvas"], highlightthickness=0)
        h_scroll = tk.Scrollbar(self.canvas, orient="horizontal", command=self.canvas.xview, bg=THEME["bg_panel"])
        v_scroll = tk.Scrollbar(self.canvas, orient="vertical", command=self.canvas.yview, bg=THEME["bg_panel"])
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
        v_scroll.pack(side="right", fill="y")
        h_scroll.pack(side="bottom", fill="x")
        self.canvas.pack(side="left", fill="both", expand=True)
        paned.add(self.canvas)

        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<ButtonPress-3>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B3-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind('<Enter>', self._bind_mousewheel)
        self.canvas.bind('<Leave>', self._unbind_mousewheel)

        # 底部
        f_bot = tk.Frame(self, bg=THEME["bg_panel"], height=50)
        f_bot.pack(fill="x", side="bottom")
        b_style = {"bg": "#505354", "fg": "white", "relief": "flat", "font": ("Segoe UI", 9)}
        tk.Button(f_bot, text="💾 保存工程", command=self.save_file, **b_style).pack(side="left", padx=10, pady=10)
        tk.Button(f_bot, text="📂 读取工程", command=self.load_file, **b_style).pack(side="left", padx=5, pady=10)
        tk.Button(f_bot, text="✨ 自动排列", command=self.auto_layout, **b_style).pack(side="left", padx=20, pady=10)
        tk.Button(f_bot, text="🗑️ 清空画布", command=self.reset_graph, **b_style).pack(side="left", padx=5, pady=10)
        f_run = tk.Frame(f_bot, bg=THEME["bg_panel"])
        f_run.pack(side="right", padx=20)
        tk.Label(f_run, text="循环:", fg="white", bg=THEME["bg_panel"]).pack(side="left")
        self.e_loops = tk.Entry(f_run, width=5, bg=THEME["entry_bg"], fg="white", relief="flat")
        self.e_loops.insert(0, "1")
        self.e_loops.pack(side="left", padx=5)
        self.btn_run = tk.Button(f_run, text="▶ 开始运行", command=self.toggle_run, bg="#00e676", fg="black",
                                 font=("Segoe UI", 10, "bold"), relief="flat", width=15)
        self.btn_run.pack(side="left", padx=10)

        self.on_type_change(None)

    # ==================================================
    # 核心：热键监听 (修复版)
    # ==================================================
    def hotkey_thread_worker(self):
        def on_press(key):
            try:
                k = key.char.lower() if hasattr(key, 'char') else key.name.lower()
            except:
                return
            self.after(0, lambda: self.process_hotkey(k))

        with keyboard.Listener(on_press=on_press) as l:
            l.join()

    def process_hotkey(self, k):
        # 【核心修复】如果焦点在 Entry 中，彻底屏蔽所有按键，防止误触
        if isinstance(self.focus_get(), tk.Entry): return

        # 获取当前设置的键位
        hk = {
            "cap": self.e_cap.get().lower().strip(),
            "pick": self.e_pick.get().lower().strip(),
            "rec_start": self.e_rec_start.get().lower().strip(),
            "rec_stop": self.e_rec_stop.get().lower().strip(),
            "run_start": self.e_run_start.get().lower().strip(),
            "run_stop": self.e_run_stop.get().lower().strip(),
            "pause": self.e_pause.get().lower().strip(),
        }

        # 1. 运行态
        if self.is_playing:
            if k == hk["run_stop"]:
                self.flash_status(f"停止: {k}")
                self.stop_playback()
            elif k == hk["pause"]:
                self.flash_status(f"暂停/恢复: {k}")
                self.toggle_pause()
            return

            # 2. 录制态
        if self.is_recording:
            if k == hk["rec_stop"]:
                self.flash_status(f"结束录制: {k}")
                self.stop_record()
            # 录制时忽略其他功能键
            elif k in [hk["rec_start"], hk["run_start"], hk["run_stop"], hk["pause"]]:
                pass
            else:
                self.rec_gap()
                d = {"type": "press", "key": k}
                self._create_and_link_node(d, from_recording=True)
            return

        # 3. 闲置态
        if k == hk["cap"] and "寻找图片" in self.cb_type.get():
            self.flash_status(f"截图: {k}")
            self.start_capture()
        elif k == hk["pick"]:
            self.flash_status(f"抓点: {k}")
            self.grab_pos()
        elif k == hk["rec_start"]:
            self.flash_status(f"开始录制: {k}")
            self.start_record()
        elif k == hk["run_start"]:
            self.flash_status(f"开始运行: {k}")
            self.toggle_run()

    def flash_status(self, msg):
        """按键反馈"""
        old_bg = self.lbl_status.cget("bg")
        old_fg = self.lbl_status.cget("fg")
        old_text = self.lbl_status.cget("text")
        self.lbl_status.config(text=msg, fg="#00e676")
        self.after(800, lambda: self.lbl_status.config(text=old_text, fg=old_fg))

    # ==================================================
    # 逻辑控制
    # ==================================================
    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            self.lbl_status.config(text="⏸ 已暂停", fg="orange")
        else:
            self.lbl_status.config(text="▶ 运行中...", fg="#00e676")

    def stop_playback(self):
        self.is_playing = False
        self.is_paused = False
        self.btn_run.config(text="停止中...", bg="#ff9800")

    def toggle_run(self):
        if self.is_playing:
            self.stop_playback()
        else:
            self.is_playing = True
            self.is_paused = False
            self.btn_run.config(text="⏹ 停止运行", bg="#ff5252")
            threading.Thread(target=self.run_logic, daemon=True).start()

    def _bind_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        if event.num == 5 or event.delta == -120: self.canvas.yview_scroll(1, "units")
        if event.num == 4 or event.delta == 120: self.canvas.yview_scroll(-1, "units")

    def toggle_region_ui(self):
        if self.var_regional.get():
            self.lbl_x.config(text="中心 X:", fg="#ffb74d")
            self.lbl_y.config(text="中心 Y:", fg="#ffb74d")
            self.e_x.config(bg=THEME["entry_hlt"])
            self.e_y.config(bg=THEME["entry_hlt"])
        else:
            self.lbl_x.config(text="偏移 X:", fg=THEME["text_dim"])
            self.lbl_y.config(text="偏移 Y:", fg=THEME["text_dim"])
            self.e_x.config(bg=THEME["entry_bg"])
            self.e_y.config(bg=THEME["entry_bg"])

    def on_type_change(self, event):
        t = self.cb_type.get()
        self.f_region.pack_forget()
        self.btn_cap.config(state='disabled')
        self.e_x.config(state='normal')
        self.e_y.config(state='normal')
        self.lbl_img.config(text="[无图片]", image="", height=4)
        self.lbl_x.config(text="X 坐标:", fg=THEME["text_dim"])
        self.lbl_y.config(text="Y 坐标:", fg=THEME["text_dim"])
        self.e_x.config(bg=THEME["entry_bg"])
        self.e_y.config(bg=THEME["entry_bg"])
        if "寻找图片" in t:
            self.btn_cap.config(state='normal')
            self.f_region.pack(fill="x", pady=(0, 10))
            self.toggle_region_ui()
            self.lbl_p.config(text="超时(秒):")
            self.e_param.delete(0, tk.END)
            self.e_param.insert(0, "5")
            self.lbl_hint.config(text="提示：拖动节点位置，绿点拖红点连线。")
            if self.current_img_path: self.show_img(self.current_img_path)
        elif "点击" in t:
            self.lbl_x.config(text="X坐标:")
            self.lbl_y.config(text="Y坐标:")
            self.lbl_p.config(text="参数:")
            self.lbl_hint.config(text="提示：按 F8 抓取坐标。")
        elif "输入" in t:
            self.e_x.config(state='disabled')
            self.e_y.config(state='disabled')
            self.lbl_p.config(text="文本:")
        elif "按键" in t:
            self.e_x.config(state='disabled')
            self.e_y.config(state='disabled')
            self.lbl_p.config(text="键名:")
        elif "等待" in t:
            self.e_x.config(state='disabled')
            self.e_y.config(state='disabled')
            self.lbl_p.config(text="秒数:")

    def draw_grid(self, max_w, max_h):
        grid_size = 40
        for i in range(0, max_w + 100, grid_size):
            color = "#2b2b2b" if i % (grid_size * 5) != 0 else "#3a3a3a"
            self.canvas.create_line([(i, 0), (i, max_h + 100)], fill=color, tags="grid")
        for i in range(0, max_h + 100, grid_size):
            color = "#2b2b2b" if i % (grid_size * 5) != 0 else "#3a3a3a"
            self.canvas.create_line([(0, i), (max_w + 100, i)], fill=color, tags="grid")

    def draw_bezier(self, x1, y1, x2, y2, color="#a9b7c6", width=2):
        dist = abs(x2 - x1) * 0.5
        if dist < 50: dist = 50
        cx1, cy1 = x1 + dist, y1
        cx2, cy2 = x2 - dist, y2
        self.canvas.create_line(x1, y1, cx1, cy1, cx2, cy2, x2, y2, smooth=True, arrow=tk.LAST, width=width, fill=color,
                                tags="wire")

    def refresh_canvas(self):
        self.canvas.delete("all")
        bbox = self.canvas.bbox("drag_body")
        if not bbox:
            max_w, max_h = 1500, 1000
        else:
            max_w_node = 0
            max_h_node = 0
            for nid, node in self.nodes.items():
                if node['x'] > max_w_node: max_w_node = node['x']
                if node['y'] > max_h_node: max_h_node = node['y']
            max_w = max(1200, max_w_node + 500)
            max_h = max(800, max_h_node + 500)
        self.draw_grid(int(max_w), int(max_h))
        self.canvas.config(scrollregion=(0, 0, max_w, max_h))
        for nid, node in self.nodes.items():
            if node.get('next'):
                next_node = self.nodes.get(node['next'])
                if next_node:
                    x1, y1 = node['x'] + 150, node['y'] + 30
                    x2, y2 = next_node['x'], next_node['y'] + 30
                    color = THEME["wire_active"] if nid == self.selected_node_id else THEME["wire"]
                    width = 3 if nid == self.selected_node_id else 2
                    self.draw_bezier(x1, y1, x2, y2, color, width)
        for nid, node in self.nodes.items():
            x, y = node['x'], node['y']
            w, h = 150, 60
            t = node['type']
            header_color = THEME["header_default"]
            if t == 'start':
                header_color = THEME["header_start"]
            elif t == 'find_img':
                header_color = THEME["header_find"]
            elif t == 'click':
                header_color = THEME["header_click"]
            elif t in ['text', 'press']:
                header_color = THEME["header_input"]
            outline = "#ffffff" if nid == self.selected_node_id else THEME["node_border"]
            tag = f"node_{nid}"
            self.canvas.create_rectangle(x + 4, y + 4, x + w + 4, y + h + 4, fill="#111111", outline="", tags="grid")
            self.canvas.create_rectangle(x, y, x + w, y + h, fill=THEME["node_bg"], outline=outline, width=1,
                                         tags=(tag, "drag_body"))
            self.canvas.create_rectangle(x + 1, y + 1, x + 6, y + h - 1, fill=header_color, outline="",
                                         tags=(tag, "drag_body"))
            title = t.upper().replace("_", " ")
            self.canvas.create_text(x + 15, y + 20, text=title, anchor="w", fill="white", font=("Segoe UI", 9, "bold"),
                                    tags=(tag, "drag_body"))
            detail = ""
            if t == 'find_img':
                detail = f"[{os.path.basename(node['data'].get('img', ''))[:15]}]"
            elif t == 'click':
                detail = f"({node['data'].get('x')}, {node['data'].get('y')})"
            elif t == 'wait':
                detail = f"{node['data'].get('time')}s"
            self.canvas.create_text(x + 15, y + 40, text=detail, anchor="w", fill="#999", font=("Consolas", 8),
                                    tags=(tag, "drag_body"))
            if t != 'start': self.canvas.create_oval(x - 5, y + 25, x + 5, y + 35, fill="#ff5252",
                                                     outline=THEME["bg_canvas"], width=2, tags=(f"in_{nid}", "port_in"))
            self.canvas.create_oval(x + w - 5, y + 25, x + w + 5, y + 35, fill="#00e676", outline=THEME["bg_canvas"],
                                    width=2, tags=(f"out_{nid}", "port_out"))

    def on_canvas_press(self, event):
        wx = self.canvas.canvasx(event.x)
        wy = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(wx - 5, wy - 5, wx + 5, wy + 5)
        for item in items:
            tags = self.canvas.gettags(item)
            if "port_out" in tags:
                for t in tags:
                    if t.startswith("out_"):
                        nid = t.split("_", 1)[1]
                        self.drag_data["type"] = "wire"
                        self.drag_data["source_id"] = nid
                        self.drag_data["x"] = wx
                        self.drag_data["y"] = wy
                        return
        for item in items:
            tags = self.canvas.gettags(item)
            if "drag_body" in tags:
                for t in tags:
                    if t.startswith("node_"):
                        nid = t.split("_", 1)[1]
                        self.selected_node_id = nid
                        self.drag_data["type"] = "move"
                        self.drag_data["source_id"] = nid
                        self.drag_data["x"] = wx
                        self.drag_data["y"] = wy
                        self.refresh_canvas()
                        self.load_node_to_ui(nid)
                        return
        self.selected_node_id = None
        self.refresh_canvas()

    def on_canvas_drag(self, event):
        wx = self.canvas.canvasx(event.x)
        wy = self.canvas.canvasy(event.y)
        if self.drag_data["type"] == "move":
            dx = wx - self.drag_data["x"]
            dy = wy - self.drag_data["y"]
            nid = self.drag_data["source_id"]
            self.nodes[nid]['x'] += dx
            self.nodes[nid]['y'] += dy
            self.drag_data["x"] = wx
            self.drag_data["y"] = wy
            self.refresh_canvas()
        elif self.drag_data["type"] == "wire":
            if self.temp_line: self.canvas.delete(self.temp_line)
            self.temp_line = self.canvas.create_line(self.drag_data["x"], self.drag_data["y"], wx, wy, fill="white",
                                                     dash=(4, 4), width=2)

    def on_canvas_release(self, event):
        wx = self.canvas.canvasx(event.x)
        wy = self.canvas.canvasy(event.y)
        if self.drag_data["type"] == "wire":
            if self.temp_line: self.canvas.delete(self.temp_line); self.temp_line = None
            items = self.canvas.find_overlapping(wx - 10, wy - 10, wx + 10, wy + 10)
            connected = False
            for item in items:
                tags = self.canvas.gettags(item)
                if "port_in" in tags:
                    for t in tags:
                        if t.startswith("in_"):
                            target_id = t.split("_", 1)[1]
                            source_id = self.drag_data["source_id"]
                            if source_id != target_id:
                                self.nodes[source_id]['next'] = target_id
                                connected = True
            if not connected: self.nodes[self.drag_data["source_id"]]['next'] = None
            self.refresh_canvas()
        self.drag_data["type"] = None

    def get_ui_data(self):
        t = self.cb_type.get()
        try:
            def safe_int(val_str):
                return int(val_str) if val_str and val_str.strip() else 0

            def safe_float(val_str):
                return float(val_str) if val_str and val_str.strip() else 0.0

            if "寻找图片" in t:
                if not self.current_img_path or not os.path.exists(self.current_img_path):
                    # 如果只是更新参数（比如超时时间），允许不重新截图，直接使用已有的
                    # 但如果是全新增，必须检查。这里为了简单，如果有旧图且文件存在，也允许
                    pass

                    # 注意：如果用户清空了 current_img_path，这里会报错。
                # 在更新逻辑中，我们通常假设 UI 上的数据是准的。
                # 可以在这里做一个小的容错：如果是 Update 操作且 UI 没有新图，保持旧图？
                # 但 get_ui_data 是纯粹从 UI 获取数据的。

                if not self.current_img_path or not os.path.exists(self.current_img_path):
                    messagebox.showerror("错误", "请先截图！\n(按 F7 或点击截图按钮)")
                    return None

                to = safe_float(self.e_param.get())
                if to == 0: to = 5.0
                return {"type": "find_img", "img": self.current_img_path, "timeout": to,
                        "val_x": safe_int(self.e_x.get()), "val_y": safe_int(self.e_y.get()),
                        "regional": self.var_regional.get(), "radius": safe_int(self.e_radius.get()),
                        "stop_fail": self.var_stop_fail.get()}
            elif "点击" in t:
                return {"type": "click", "x": safe_int(self.e_x.get()), "y": safe_int(self.e_y.get()), "btn": "left"}
            elif "输入" in t:
                return {"type": "text", "text": self.e_param.get()}
            elif "按键" in t:
                return {"type": "press", "key": self.e_param.get().lower()}
            elif "等待" in t:
                return {"type": "wait", "time": safe_float(self.e_param.get())}
            elif "移动" in t:
                return {"type": "move", "x": safe_int(self.e_x.get()), "y": safe_int(self.e_y.get())}
            elif "拖拽" in t:
                return {"type": "drag", "x": safe_int(self.e_x.get()), "y": safe_int(self.e_y.get()),
                        "dur": safe_float(self.e_param.get())}
            return None
        except Exception as e:
            messagebox.showerror("参数错误", f"输入格式不正确：\n{e}")
            return None

    def add_node_btn(self):
        data = self.get_ui_data()
        if not data: return
        self._create_and_link_node(data)

    # ==================================================
    # 【新增】更新节点功能
    # ==================================================
    def update_node_btn(self):
        """更新当前选中节点的参数"""
        if not self.selected_node_id:
            messagebox.showwarning("操作无效", "请先在右侧画布上点击选中一个节点！")
            return

        if self.selected_node_id == self.start_node_id:
            messagebox.showwarning("禁止操作", "无法修改 [START] 起始节点。")
            return

        data = self.get_ui_data()
        if not data: return

        # 更新数据
        self.nodes[self.selected_node_id]['type'] = data['type']
        self.nodes[self.selected_node_id]['data'] = data

        self.refresh_canvas()
        self.flash_status(f"✅ 节点 {self.selected_node_id} 已更新")
        # 重新加载回 UI 确认
        self.load_node_to_ui(self.selected_node_id)

    def _create_and_link_node(self, data, from_recording=False):
        self.node_counter += 1
        nid = str(self.node_counter)
        prev_id = None
        if from_recording:
            prev_id = self.recording_last_id
        elif self.selected_node_id:
            prev_id = self.selected_node_id
        else:
            prev_id = self.start_node_id
        if prev_id and prev_id in self.nodes:
            prev_node = self.nodes[prev_id]
            nx = prev_node['x']
            ny = prev_node['y'] + 100
        else:
            nx, ny = 100, 100
        self.nodes[nid] = {'type': data['type'], 'x': nx, 'y': ny, 'next': None, 'data': data}
        if prev_id and prev_id in self.nodes: self.nodes[prev_id]['next'] = nid
        if from_recording:
            self.recording_last_id = nid
        else:
            self.selected_node_id = nid
        self.refresh_canvas()

    def delete_node(self):
        if not self.selected_node_id or self.selected_node_id == 'start': return
        del self.nodes[self.selected_node_id]
        for nid, node in self.nodes.items():
            if node['next'] == self.selected_node_id: node['next'] = None
        self.selected_node_id = None
        self.refresh_canvas()

    def load_node_to_ui(self, nid):
        node = self.nodes[nid]
        if node['type'] == 'start': return
        d = node['data']
        map_t = {'find_img': 0, 'click': 1, 'text': 2, 'press': 3, 'wait': 4, 'move': 5, 'drag': 6}
        if d['type'] in map_t: self.cb_type.current(map_t[d['type']])
        if d['type'] == 'find_img':
            self.current_img_path = d['img']
            self.show_img(d['img'])
            self.var_regional.set(d.get('regional', False))
            if d.get('regional'): self.e_radius.delete(0, tk.END); self.e_radius.insert(0, d.get('radius', 300))
            self.var_stop_fail.set(d.get('stop_fail', True))
        self.on_type_change(None)
        k_x = 'val_x' if d['type'] == 'find_img' else 'x'
        k_y = 'val_y' if d['type'] == 'find_img' else 'y'
        if k_x in d: self.e_x.delete(0, tk.END); self.e_x.insert(0, d[k_x])
        if k_y in d: self.e_y.delete(0, tk.END); self.e_y.insert(0, d[k_y])
        p = d.get('text') or d.get('key') or d.get('time') or d.get('dur') or d.get('timeout')
        if p is not None: self.e_param.delete(0, tk.END); self.e_param.insert(0, p)

    def auto_layout(self):
        start_x, start_y = 80, 80
        gap_y = 100
        current_id = self.start_node_id
        current_y = start_y
        visited = set()
        while current_id:
            if current_id in visited: break
            visited.add(current_id)
            if current_id in self.nodes:
                self.nodes[current_id]['x'] = start_x
                self.nodes[current_id]['y'] = current_y
                current_y += gap_y
                current_id = self.nodes[current_id].get('next')
                if current_id and current_id not in self.nodes: current_id = None
        orphan_x = start_x + 250
        orphan_y = start_y
        for nid in self.nodes:
            if nid not in visited:
                self.nodes[nid]['x'] = orphan_x
                self.nodes[nid]['y'] = orphan_y
                orphan_y += gap_y
        self.refresh_canvas()
        self.canvas.yview_moveto(0)

    def start_record(self):
        should_clear = True
        if len(self.nodes) > 1:
            if self.selected_node_id:
                if not messagebox.askyesno("录制",
                                           "是否清空画布？\n是=清空重录，否=在选中节点后追加"): should_clear = False
            else:
                self.reset_graph()
        if should_clear:
            self.reset_graph();
            self.recording_last_id = self.start_node_id
        else:
            self.recording_last_id = self.selected_node_id
        self.is_recording = True
        self.last_action_time = time.time()
        self.lbl_status.config(text="🔴 录制中...", fg="#ff5252")
        self.mouse_listener = mouse.Listener(on_click=self.on_rec_click)
        self.key_listener = keyboard.Listener(on_press=self.on_rec_key)
        self.mouse_listener.start()
        self.key_listener.start()

    def stop_record(self):
        self.is_recording = False
        if self.mouse_listener: self.mouse_listener.stop()
        if self.key_listener: self.key_listener.stop()
        self.lbl_status.config(text="✅ 完成", fg="#00e676")
        self.auto_layout()

    def rec_gap(self):
        gap = time.time() - self.last_action_time
        self.last_action_time = time.time()
        if gap > 0.05:
            d = {"type": "wait", "time": round(gap, 3)}
            self.after(0, lambda: self._create_and_link_node(d, from_recording=True))

    def on_rec_click(self, x, y, button, pressed):
        if not pressed or not self.is_recording: return
        self.rec_gap()
        btn = "left" if button == mouse.Button.left else "right"
        d = {"type": "click", "x": x, "y": y, "btn": btn}
        self.after(0, lambda: self._create_and_link_node(d, from_recording=True))

    def on_rec_key(self, key):
        if not self.is_recording: return
        try:
            k = key.char.lower() if hasattr(key, 'char') else key.name.lower()
        except:
            return
        hk = {
            "rec_stop": self.e_rec_stop.get().lower().strip(),
            "rec_start": self.e_rec_start.get().lower().strip(),
            "run_start": self.e_run_start.get().lower().strip(),
            "run_stop": self.e_run_stop.get().lower().strip(),
            "pause": self.e_pause.get().lower().strip()
        }
        if k == hk["rec_stop"]: self.after(0, self.stop_record); return
        if k in [hk["rec_start"], hk["run_start"], hk["run_stop"], hk["pause"]]: return
        self.rec_gap()
        d = {"type": "press", "key": k}
        self.after(0, lambda: self._create_and_link_node(d, from_recording=True))

    def update_mouse_coords(self):
        try:
            x, y = pyautogui.position();
            self.lbl_mouse.config(text=f"XY: {x},{y}")
        except:
            pass
        self.after(100, self.update_mouse_coords)

    def find_and_click_image(self, action_data, is_test=False):
        img_path = action_data['img']
        timeout = action_data.get('timeout', 5)
        if not os.path.exists(img_path): return False
        search_region = None
        if action_data.get('regional', False):
            cx, cy = int(action_data['val_x']), int(action_data['val_y'])
            r = int(action_data['radius'])
            search_region = (cx - r, cy - r, r * 2, r * 2)
        start = time.time()
        found_pos = None
        self.lbl_status.config(text=f"🔍 寻找: {os.path.basename(img_path)}...", fg="#4fc3f7")
        while time.time() - start < timeout:
            if not self.is_playing and not is_test: return False
            try:
                pos = pyautogui.locateOnScreen(img_path, confidence=0.9, region=search_region)
                if pos: found_pos = pyautogui.center(pos); break
            except:
                pass
            time.sleep(0.5)
        if found_pos:
            fx, fy = found_pos.x, found_pos.y
            if not action_data.get('regional', False): fx += int(action_data['val_x']); fy += int(action_data['val_y'])
            self.lbl_status.config(text=f"✅ 点击 ({fx},{fy})", fg="#00e676")
            if is_test:
                pyautogui.moveTo(fx, fy, duration=0.5);
                messagebox.showinfo("成功", "找到图片")
            else:
                pyautogui.click(fx, fy)
            return True
        return False

    def test_single_action(self):
        if not self.selected_node_id or self.selected_node_id == 'start': return
        d = self.nodes[self.selected_node_id]['data']
        if d['type'] == 'find_img':
            self.find_and_click_image(d, is_test=True)
        elif d['type'] == 'click':
            pyautogui.moveTo(d['x'], d['y'], duration=1)

    def start_capture(self):
        self.state('iconic');
        time.sleep(0.3);
        SnippingTool(self, self.capture_done)

    def capture_done(self, bbox):
        self.state('normal')
        self.focus_set()
        if not bbox: return
        ts = int(time.time() * 1000)
        path = f"assets/img_{ts}.png"
        ImageGrab.grab(bbox).save(path)
        self.current_img_path = path
        self.show_img(path)
        self.cb_type.current(0)
        self.on_type_change(None)
        messagebox.showinfo("截图", "成功")

    def grab_pos(self):
        x, y = pyautogui.position()
        self.e_x.delete(0, tk.END)
        self.e_x.insert(0, str(x))
        self.e_y.delete(0, tk.END)
        self.e_y.insert(0, str(y))
        self.lbl_status.config(text=f"📍 {x},{y}", fg="#00e676")

    def show_img(self, path):
        if not path or not os.path.exists(path): return
        try:
            pil = Image.open(path);
            pil.thumbnail((320, 100));
            tk_img = ImageTk.PhotoImage(pil);
            self.lbl_img.config(
                image=tk_img, text="", height=0);
            self.lbl_img.image = tk_img
        except:
            pass

    def reset_graph(self):
        self.nodes = {self.start_node_id: {'type': 'start', 'x': 80, 'y': 80, 'next': None, 'data': {}}}
        self.refresh_canvas()

    def save_file(self):
        f = filedialog.asksaveasfilename(defaultextension=".json")
        if f: json.dump({"nodes": self.nodes, "counter": self.node_counter}, open(f, 'w'))

    def load_file(self):
        f = filedialog.askopenfilename()
        if f: d = json.load(open(f, 'r')); self.nodes = d["nodes"]; self.node_counter = d[
            "counter"]; self.refresh_canvas()

    def run_logic(self):
        try:
            loops = int(self.e_loops.get())
            cur = 0
            while self.is_playing:
                if loops > 0 and cur >= loops: break
                cur += 1
                curr_id = self.start_node_id
                while self.is_playing:
                    while self.is_paused:
                        if not self.is_playing: break
                        time.sleep(0.1)
                    if not self.is_playing: break

                    node = self.nodes.get(curr_id)
                    if not node: break
                    self.selected_node_id = curr_id
                    self.refresh_canvas()
                    if node['type'] != 'start':
                        d = node['data']
                        if d['type'] == 'wait':
                            time.sleep(d['time'])
                        elif d['type'] == 'click':
                            pyautogui.click(d['x'], d['y'])
                        elif d['type'] == 'text':
                            pyautogui.write(d['text'])
                        elif d['type'] == 'press':
                            m = {'ctrl_l': 'ctrl', 'alt_l': 'alt', 'shift_l': 'shift'}
                            pyautogui.press(m.get(d['key'], d['key']))
                        elif d['type'] == 'find_img':
                            suc = self.find_and_click_image(d)
                            if not suc and d.get('stop_fail', True): messagebox.showerror("中断", "找图失败"); break
                        time.sleep(0.1)
                    curr_id = node['next']
                    if not curr_id: break
        except Exception as e:
            print(e)
        finally:
            self.is_playing = False
            self.btn_run.config(text="▶ 开始运行", bg="#00e676")
            self.lbl_status.config(text="● 就绪", fg="#bbbbbb")


if __name__ == "__main__":
    app = AutoBotGraph()
    app.mainloop()