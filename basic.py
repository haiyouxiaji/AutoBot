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


# ==========================================
# 辅助类：截图工具 (ESC 焦点修复版)
# ==========================================
class SnippingTool(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback

        # 窗口设置
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3)
        self.attributes('-topmost', True)
        self.config(cursor="cross")
        self.configure(background='black')

        self.canvas = tk.Canvas(self, cursor="cross", bg="grey11")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(self.winfo_screenwidth() // 2, 100,
                                text="按住左键框选 / 按 ESC 退出",
                                fill="white", font=("Arial", 16, "bold"))

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        # 强制获取焦点，确保 ESC 生效
        self.bind("<Escape>", self.exit_tool)
        self.focus_force()
        self.grab_set()

        self.start_x = None
        self.start_y = None
        self.rect = None

    def exit_tool(self, event=None):
        self.grab_release()
        self.destroy()
        self.callback(None)

    def on_press(self, event):
        self.start_x = self.canvas.canvasx(event.x)
        self.start_y = self.canvas.canvasy(event.y)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red',
                                                 width=2)

    def on_drag(self, event):
        cur_x = self.canvas.canvasx(event.x)
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
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
class AutoBotPro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoBot v8.5 - 最终修复版")
        self.geometry("1000x880")

        self.action_list = []
        self.is_recording = False
        self.is_playing = False
        self.current_img_path = None

        self.mouse_listener = None
        self.key_listener = None
        self.last_action_time = 0

        self.setup_ui()

        # 启动热键监听
        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        self.update_mouse_coords()

    def setup_ui(self):
        # --- 1. 顶部热键 ---
        f_top = tk.LabelFrame(self, text="🕹️ 热键配置", padx=10, pady=5, bg="#f0f0f0")
        f_top.pack(fill="x", padx=10, pady=5)

        tk.Label(f_top, text="截图[F7]  抓点[F8]  录制[F9]  停止[F10]", bg="#f0f0f0", fg="#333",
                 font=("Arial", 10)).pack(side="left")

        # 隐藏 Entry 保持逻辑兼容
        self.e_cap = tk.Entry(self);
        self.e_cap.insert(0, "f7")
        self.e_pick = tk.Entry(self);
        self.e_pick.insert(0, "f8")
        self.e_start = tk.Entry(self);
        self.e_start.insert(0, "f9")
        self.e_stop = tk.Entry(self);
        self.e_stop.insert(0, "f10")

        self.lbl_status = tk.Label(f_top, text="● 就绪", fg="gray", bg="#f0f0f0", font=("Arial", 10, "bold"))
        self.lbl_status.pack(side="right", padx=10)
        self.lbl_mouse = tk.Label(f_top, text="0, 0", bg="#f0f0f0", font=("Consolas", 9))
        self.lbl_mouse.pack(side="right", padx=10)

        # --- 2. 主体区域 ---
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        # 左侧：编辑器
        f_edit = tk.LabelFrame(paned, text=" 🛠️ 动作参数 ", padx=10, pady=10)
        paned.add(f_edit, width=380)

        # 类型
        tk.Label(f_edit, text="类型:").grid(row=0, column=0, sticky="w")
        self.cb_type = ttk.Combobox(f_edit, state="readonly",
                                    values=["寻找图片", "点击坐标", "输入文本", "按下按键", "等待", "移动", "拖拽"])
        self.cb_type.current(1)
        self.cb_type.grid(row=0, column=1, columnspan=2, sticky="we", pady=5)
        self.cb_type.bind("<<ComboboxSelected>>", self.on_type_change)

        # 坐标
        self.lbl_x = tk.Label(f_edit, text="X:");
        self.lbl_x.grid(row=1, column=0, sticky="w")
        self.e_x = tk.Entry(f_edit, bg="#e3f2fd");
        self.e_x.grid(row=1, column=1, sticky="we")
        self.lbl_y = tk.Label(f_edit, text="Y:");
        self.lbl_y.grid(row=2, column=0, sticky="w")
        self.e_y = tk.Entry(f_edit, bg="#e3f2fd");
        self.e_y.grid(row=2, column=1, sticky="we")

        # 截图按钮
        self.btn_cap = tk.Button(f_edit, text="📷 截图(F7)", command=self.start_capture, bg="#ffcc80", state="disabled")
        self.btn_cap.grid(row=1, column=2, rowspan=2, padx=5, sticky="news")

        # 区域找图设置
        self.f_region = tk.LabelFrame(f_edit, text=" 🔍 找图设置 ", padx=5, pady=5, fg="blue")
        self.f_region.grid(row=3, column=0, columnspan=3, sticky="we", pady=5)

        self.var_regional = tk.BooleanVar()
        self.chk_region = tk.Checkbutton(self.f_region, text="区域限制 (只在红圈内找)", variable=self.var_regional,
                                         command=self.toggle_region_ui)
        self.chk_region.pack(anchor="w")

        f_r_sub = tk.Frame(self.f_region)
        f_r_sub.pack(fill="x")
        tk.Label(f_r_sub, text="半径:").pack(side="left")
        self.e_radius = tk.Entry(f_r_sub, width=5);
        self.e_radius.insert(0, "300");
        self.e_radius.pack(side="left")

        self.var_stop_fail = tk.BooleanVar(value=True)
        tk.Checkbutton(self.f_region, text="失败则停止脚本", variable=self.var_stop_fail, fg="red").pack(anchor="w")

        # 图片预览
        self.lbl_img = tk.Label(f_edit, text="[无图片]", relief="sunken", bg="#ddd", height=4)
        self.lbl_img.grid(row=4, column=0, columnspan=3, sticky="we", pady=5)

        # 参数
        self.lbl_p = tk.Label(f_edit, text="参数:");
        self.lbl_p.grid(row=5, column=0, sticky="w")
        self.e_param = tk.Entry(f_edit);
        self.e_param.grid(row=5, column=1, columnspan=2, sticky="we")

        # 提示
        self.lbl_hint = tk.Label(f_edit, text="", fg="gray", font=("Arial", 8), wraplength=350, justify="left")
        self.lbl_hint.grid(row=6, column=0, columnspan=3, pady=5)

        # 操作按钮
        f_ops = tk.Frame(f_edit)
        f_ops.grid(row=7, column=0, columnspan=3, pady=10, sticky="we")
        tk.Button(f_ops, text="➕ 新增", command=self.add_action, bg="#c8e6c9", height=2).pack(side="left", fill="x",
                                                                                              expand=True)
        tk.Button(f_ops, text="✏️ 修改", command=self.update_action, bg="#ffecb3", height=2).pack(side="left", fill="x",
                                                                                                  expand=True)
        tk.Button(f_ops, text="🧪 测试", command=self.test_single_action, bg="#b3e5fc", height=2).pack(side="left",
                                                                                                      fill="x",
                                                                                                      expand=True)

        # 右侧列表
        f_list = tk.LabelFrame(paned, text=" 执行队列 ", padx=5, pady=5)
        paned.add(f_list)
        self.lb = tk.Listbox(f_list, font=("Consolas", 10))
        scr = tk.Scrollbar(f_list, command=self.lb.yview);
        self.lb.config(yscrollcommand=scr.set)
        self.lb.pack(side="left", fill="both", expand=True);
        scr.pack(side="right", fill="y")
        self.lb.bind('<Double-1>', self.load_action)

        f_ctrl = tk.Frame(f_list)
        f_ctrl.pack(side="bottom", fill="x")
        tk.Button(f_ctrl, text="⬆️", command=lambda: self.move(-1)).pack(side="left")
        tk.Button(f_ctrl, text="⬇️", command=lambda: self.move(1)).pack(side="left")
        tk.Button(f_ctrl, text="❌ 删除", command=self.delete_item).pack(side="right")

        # --- 3. 底部 ---
        f_bot = tk.Frame(self, pady=10, bd=1, relief="raised")
        f_bot.pack(fill="x", side="bottom")

        tk.Label(f_bot, text="循环次数:").pack(side="left", padx=5)
        self.e_loops = tk.Entry(f_bot, width=5);
        self.e_loops.insert(0, "1");
        self.e_loops.pack(side="left")

        tk.Button(f_bot, text="💾 保存", command=self.save).pack(side="left", padx=15)
        tk.Button(f_bot, text="📂 读取", command=self.load).pack(side="left")
        tk.Button(f_bot, text="🗑️ 清空", command=self.clear).pack(side="left")

        self.btn_run = tk.Button(f_bot, text="▶ 开始运行", command=self.toggle_run, bg="#4CAF50", fg="white", width=20,
                                 font=("Arial", 11, "bold"))
        self.btn_run.pack(side="right", padx=20)

        self.on_type_change(None)

    # ==========================
    # 核心：找图与测试
    # ==========================
    def find_and_click_image(self, action_data, is_test=False):
        img_path = action_data['img']
        timeout = action_data.get('timeout', 5)

        if not os.path.exists(img_path):
            if is_test: messagebox.showerror("错误", "图片文件不存在！")
            return False

        # 计算区域
        search_region = None
        if action_data.get('regional', False):
            cx, cy = int(action_data['val_x']), int(action_data['val_y'])
            r = int(action_data['radius'])
            search_region = (cx - r, cy - r, r * 2, r * 2)

        start_time = time.time()
        found_pos = None

        self.lbl_status.config(text=f"🔍 寻找: {os.path.basename(img_path)}...", fg="blue")

        while time.time() - start_time < timeout:
            if not self.is_playing and not is_test: return False

            try:
                # 移除了 grayscale=True 以减少误判
                pos = pyautogui.locateOnScreen(img_path, confidence=0.9, region=search_region)
                if pos:
                    found_pos = pyautogui.center(pos)
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if found_pos:
            final_x, final_y = found_pos.x, found_pos.y
            if not action_data.get('regional', False):
                final_x += int(action_data['val_x'])
                final_y += int(action_data['val_y'])

            self.lbl_status.config(text=f"✅ 找到! 点击 ({final_x},{final_y})", fg="green")

            if is_test:
                pyautogui.moveTo(final_x, final_y, duration=0.5)
                messagebox.showinfo("测试成功", f"找到图片！\n坐标: {final_x}, {final_y}")
            else:
                pyautogui.click(final_x, final_y)
            return True
        else:
            self.lbl_status.config(text="❌ 未找到图片", fg="red")
            if is_test:
                messagebox.showwarning("测试失败", "未找到图片。请检查屏幕显示或区域设置。")
            return False

    def test_single_action(self):
        sel = self.lb.curselection()
        if not sel: return
        d = self.action_list[sel[0]]

        if d['type'] == 'find_img':
            self.find_and_click_image(d, is_test=True)
        elif d['type'] == 'click':
            pyautogui.moveTo(d['x'], d['y'], duration=1)
            messagebox.showinfo("测试", f"鼠标已移动到 ({d['x']}, {d['y']})")

    # ==========================
    # 核心：热键与录制
    # ==========================
    def hotkey_loop(self):
        def on_press(key):
            try:
                k = key.char.lower() if hasattr(key, 'char') else key.name.lower()
            except:
                return

            if self.is_playing: return

            if k == "f7" and "寻找图片" in self.cb_type.get():
                self.after(0, self.start_capture)
            elif k == "f8":
                self.after(0, self.grab_pos)
            elif k == "f9" and not self.is_recording:
                self.after(0, self.start_record)
            elif k == "f10" and self.is_recording:
                self.after(0, self.stop_record)

        with keyboard.Listener(on_press=on_press) as l:
            l.join()

    def start_record(self):
        self.is_recording = True;
        self.action_list = [];
        self.refresh_list()
        self.last_action_time = time.time()
        self.lbl_status.config(text="🔴 录制中... 按 F10 结束", fg="red")
        self.mouse_listener = mouse.Listener(on_click=self.on_rec_click)
        self.key_listener = keyboard.Listener(on_press=self.on_rec_key)
        self.mouse_listener.start();
        self.key_listener.start()

    def stop_record(self):
        if not self.is_recording: return
        self.is_recording = False
        if self.mouse_listener: self.mouse_listener.stop()
        if self.key_listener: self.key_listener.stop()
        self.lbl_status.config(text="✅ 录制完成", fg="green")
        self.refresh_list()

    def rec_gap(self):
        gap = time.time() - self.last_action_time;
        self.last_action_time = time.time()
        if gap > 0.05: self.action_list.append({"type": "wait", "time": round(gap, 3)})

    def on_rec_click(self, x, y, button, pressed):
        if not pressed or not self.is_recording: return
        self.rec_gap()
        btn = "left" if button == mouse.Button.left else "right"
        self.action_list.append({"type": "click", "x": x, "y": y, "btn": btn})
        self.after(0, lambda: self.lb.insert(tk.END, f"🖱️ 点击 {btn} ({x},{y})"))

    def on_rec_key(self, key):
        if not self.is_recording: return
        try:
            k = key.char.lower() if hasattr(key, 'char') else key.name.lower()
        except:
            return
        if k == "f10": self.after(0, self.stop_record); return
        if k == "f9": return
        self.rec_gap()
        self.action_list.append({"type": "press", "key": k})
        self.after(0, lambda: self.lb.insert(tk.END, f"🎹 按键 [{k}]"))

    # ==========================
    # 截图与抓点
    # ==========================
    def start_capture(self):
        self.state('iconic');
        time.sleep(0.3)
        SnippingTool(self, self.capture_done)

    def capture_done(self, bbox):
        self.state('normal')
        if not bbox: return
        ts = int(time.time() * 1000);
        path = f"assets/img_{ts}.png"
        ImageGrab.grab(bbox).save(path)
        self.current_img_path = path;
        self.show_img(path)
        self.cb_type.current(0);
        self.on_type_change(None)
        messagebox.showinfo("截图", "截图成功！")

    def grab_pos(self):
        x, y = pyautogui.position()
        self.e_x.delete(0, tk.END);
        self.e_x.insert(0, str(x))
        self.e_y.delete(0, tk.END);
        self.e_y.insert(0, str(y))
        bg = self.lbl_status.cget("bg")
        self.lbl_status.config(text=f"📍 坐标 {x},{y}", bg="#bbdefb")
        self.after(1000, lambda: self.lbl_status.config(text="● 就绪", bg=bg))

    # ==========================
    # UI 交互
    # ==========================
    def on_type_change(self, event):
        t = self.cb_type.get()
        self.f_region.grid_remove()
        self.btn_cap.config(state='disabled')
        self.e_x.config(state='normal');
        self.e_y.config(state='normal')
        self.lbl_img.config(text="[无图片]")

        if "寻找图片" in t:
            self.btn_cap.config(state='normal')
            self.f_region.grid()
            self.toggle_region_ui()
            self.lbl_x.config(text="点击偏X:")
            self.lbl_y.config(text="点击偏Y:")
            self.lbl_p.config(text="超时(秒):")
            self.e_param.delete(0, tk.END);
            self.e_param.insert(0, "5")
            self.lbl_hint.config(text="找图 -> 点击(中心+偏移)。F7截图，F8抓取。")
            if self.current_img_path: self.show_img(self.current_img_path)
        elif "点击" in t or "移动" in t or "拖拽" in t:
            self.lbl_x.config(text="X坐标:")
            self.lbl_y.config(text="Y坐标:")
            self.lbl_p.config(text="参数:")
            self.lbl_hint.config(text="提示：按 F8 抓取坐标。")
            if "拖拽" in t: self.e_param.insert(0, "1.0")
        elif "输入" in t:
            self.e_x.config(state='disabled');
            self.e_y.config(state='disabled')
            self.lbl_p.config(text="文本:")
        elif "按键" in t:
            self.e_x.config(state='disabled');
            self.e_y.config(state='disabled')
            self.lbl_p.config(text="键名:")
        elif "等待" in t:
            self.e_x.config(state='disabled');
            self.e_y.config(state='disabled')
            self.lbl_p.config(text="秒数:")

    def toggle_region_ui(self):
        if self.var_regional.get():
            self.lbl_hint.config(text="⚠️ 区域模式：请在 X/Y 框中填入【搜索中心点】(按F8抓取)。")
            self.lbl_x.config(text="中心 X:");
            self.lbl_y.config(text="中心 Y:")
            self.e_x.config(bg="#fff9c4");
            self.e_y.config(bg="#fff9c4")
        else:
            self.lbl_hint.config(text="逻辑：全屏找图。X/Y 代表点击偏移。")
            self.lbl_x.config(text="偏移 X:");
            self.lbl_y.config(text="偏移 Y:")
            self.e_x.config(bg="#e3f2fd");
            self.e_y.config(bg="#e3f2fd")

    def show_img(self, path):
        if not path or not os.path.exists(path): return
        try:
            pil = Image.open(path);
            pil.thumbnail((280, 70))
            tk_img = ImageTk.PhotoImage(pil)
            self.lbl_img.config(image=tk_img, text="");
            self.lbl_img.image = tk_img
        except:
            pass

    # ==========================
    # 数据与列表
    # ==========================
    def get_data(self):
        t = self.cb_type.get()
        try:
            if "寻找图片" in t:
                if not self.current_img_path: messagebox.showerror("错", "无图片"); return None
                return {
                    "type": "find_img", "img": self.current_img_path,
                    "timeout": float(self.e_param.get()),
                    "val_x": int(self.e_x.get()), "val_y": int(self.e_y.get()),
                    "regional": self.var_regional.get(),
                    "radius": int(self.e_radius.get()) if self.var_regional.get() else 0,
                    "stop_fail": self.var_stop_fail.get()
                }
            elif "点击" in t:
                return {"type": "click", "x": int(self.e_x.get()), "y": int(self.e_y.get()), "btn": "left"}
            elif "输入" in t:
                return {"type": "text", "text": self.e_param.get()}
            elif "按键" in t:
                return {"type": "press", "key": self.e_param.get().lower()}
            elif "等待" in t:
                return {"type": "wait", "time": float(self.e_param.get())}
            elif "移动" in t:
                return {"type": "move", "x": int(self.e_x.get()), "y": int(self.e_y.get())}
            elif "拖拽" in t:
                return {"type": "drag", "x": int(self.e_x.get()), "y": int(self.e_y.get()),
                        "dur": float(self.e_param.get())}
        except:
            return None

    def add_action(self):
        d = self.get_data()
        if d: self.action_list.append(d); self.refresh_list()

    def update_action(self):
        sel = self.lb.curselection()
        if sel and self.get_data(): self.action_list[sel[0]] = self.get_data(); self.refresh_list()

    def load_action(self, event):
        sel = self.lb.curselection()
        if not sel: return
        d = self.action_list[sel[0]]

        map_t = {'find_img': 0, 'click': 1, 'text': 2, 'press': 3, 'wait': 4, 'move': 5, 'drag': 6}
        if d['type'] in map_t: self.cb_type.current(map_t[d['type']])

        if d['type'] == 'find_img':
            self.current_img_path = d['img'];
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

    def refresh_list(self):
        self.lb.delete(0, tk.END)
        for i, d in enumerate(self.action_list):
            txt = f"{i + 1}. {d['type']}"
            if d['type'] == 'find_img':
                r_txt = f"区域[{d['val_x']},{d['val_y']}]" if d['regional'] else f"全屏"
                txt += f" [{os.path.basename(d['img'])}] {r_txt}"
            elif 'x' in d:
                txt += f" ({d['x']},{d['y']})"
            elif 'key' in d:
                txt += f" [{d['key']}]"
            elif 'time' in d:
                txt += f" {d['time']}s"
            self.lb.insert(tk.END, txt)
        self.lb.see(tk.END)

    # ==========================
    # 执行逻辑
    # ==========================
    def toggle_run(self):
        if self.is_playing:
            self.is_playing = False;
            self.btn_run.config(text="停止中...", bg="orange")
        else:
            self.is_playing = True;
            self.btn_run.config(text="⏹ 停止运行", bg="#ff5252")
            threading.Thread(target=self.run_logic, daemon=True).start()

    def run_logic(self):
        try:
            loops = int(self.e_loops.get())
            cur = 0
            while self.is_playing:
                if loops > 0 and cur >= loops: break
                cur += 1
                for idx, d in enumerate(self.action_list):
                    if not self.is_playing: break
                    self.lb.selection_clear(0, tk.END);
                    self.lb.selection_set(idx);
                    self.lb.see(idx)

                    if d['type'] == 'wait':
                        time.sleep(d['time'])
                    elif d['type'] == 'click':
                        pyautogui.click(d['x'], d['y'])
                    elif d['type'] == 'move':
                        pyautogui.moveTo(d['x'], d['y'])
                    elif d['type'] == 'drag':
                        pyautogui.dragTo(d['x'], d['y'], duration=d['dur'], button='left')
                    elif d['type'] == 'text':
                        pyautogui.write(d['text'])
                    elif d['type'] == 'press':
                        k = d['key'];
                        m = {'ctrl_l': 'ctrl', 'alt_l': 'alt', 'shift_l': 'shift'}
                        pyautogui.press(m.get(k, k))
                    elif d['type'] == 'find_img':
                        success = self.find_and_click_image(d)
                        if not success and d.get('stop_fail', True):
                            self.is_playing = False
                            messagebox.showerror("中断", f"未找到图片。\n步骤: {idx + 1}")
                            break
                    time.sleep(0.1)
        except Exception as e:
            print(e)
        finally:
            self.is_playing = False
            self.btn_run.config(text="▶ 开始运行", bg="#4CAF50")
            self.lbl_status.config(text="● 就绪", fg="gray")

    def update_mouse_coords(self):
        try:
            x, y = pyautogui.position(); self.lbl_mouse.config(text=f"{x},{y}")
        except:
            pass
        self.after(100, self.update_mouse_coords)

    def move(self, d):
        sel = self.lb.curselection()
        if not sel: return
        i = sel[0];
        n = i + d
        if 0 <= n < len(self.action_list):
            self.action_list[i], self.action_list[n] = self.action_list[n], self.action_list[i]
            self.refresh_list();
            self.lb.selection_set(n)

    def delete_item(self):
        sel = self.lb.curselection()
        if sel: del self.action_list[sel[0]]; self.refresh_list()

    def clear(self):
        self.action_list = []; self.refresh_list()

    def save(self):
        f = filedialog.asksaveasfilename(defaultextension=".json")
        if f: json.dump(self.action_list, open(f, 'w'))

    def load(self):
        f = filedialog.askopenfilename()
        if f: self.action_list = json.load(open(f, 'r')); self.refresh_list()


if __name__ == "__main__":
    app = AutoBotPro()
    app.mainloop()