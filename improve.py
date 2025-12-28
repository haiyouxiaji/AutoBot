import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageGrab
import pyautogui
import threading
import time
import json
import os
import math
from pynput import mouse, keyboard

# === 全局配置 ===
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

if not os.path.exists("assets"):
    os.makedirs("assets")


# ==========================================
# 辅助类：截图工具
# ==========================================
class SnippingTool(tk.Toplevel):
    def __init__(self, parent, callback):
        super().__init__(parent)
        self.callback = callback
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.3)
        self.attributes('-topmost', True)
        self.config(cursor="cross")
        self.configure(background='black')
        self.canvas = tk.Canvas(self, cursor="cross", bg="grey11")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(self.winfo_screenwidth() // 2, 100, text="按住左键框选 / 按 ESC 退出", fill="white",
                                font=("Arial", 16, "bold"))
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", self.exit_tool)
        self.focus_force();
        self.grab_set()
        self.start_x = None;
        self.start_y = None;
        self.rect = None

    def exit_tool(self, event=None):
        self.grab_release();
        self.destroy();
        self.callback(None)

    def on_press(self, event):
        self.start_x = self.canvas.canvasx(event.x);
        self.start_y = self.canvas.canvasy(event.y)
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red',
                                                 width=2)

    def on_drag(self, event):
        cur_x = self.canvas.canvasx(event.x);
        cur_y = self.canvas.canvasy(event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_release(self, event):
        end_x = self.canvas.canvasx(event.x);
        end_y = self.canvas.canvasy(event.y)
        self.grab_release();
        self.destroy()
        x1 = min(self.start_x, end_x);
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x);
        y2 = max(self.start_y, end_y)
        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.callback((int(x1), int(y1), int(x2), int(y2)))
        else:
            self.callback(None)


# ==========================================
# 主程序类：节点流编辑器
# ==========================================
class AutoBotGraph(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoBot v10.2 - 自动排列增强版")
        self.geometry("1300x900")

        # === 核心数据结构：图 ===
        self.nodes = {}
        self.node_counter = 0
        self.start_node_id = "start"

        # 初始化开始节点
        self.nodes[self.start_node_id] = {
            'type': 'start', 'x': 50, 'y': 50, 'next': None, 'data': {}
        }

        self.selected_node_id = None
        self.recording_last_id = None
        self.current_img_path = None

        # 运行状态
        self.is_recording = False
        self.is_playing = False

        # 拖拽临时数据
        self.drag_data = {"item": None, "x": 0, "y": 0, "type": None, "source_id": None}
        self.temp_line = None

        # 监听器
        self.mouse_listener = None
        self.key_listener = None
        self.last_action_time = 0

        self.setup_ui()
        self.refresh_canvas()

        threading.Thread(target=self.hotkey_loop, daemon=True).start()
        self.update_mouse_coords()

    def setup_ui(self):
        # 1. 顶部热键
        f_top = tk.LabelFrame(self, text="🕹️ 热键配置", padx=10, pady=5, bg="#f0f0f0")
        f_top.pack(fill="x", padx=10, pady=5)
        tk.Label(f_top, text="截图[F7]  抓点[F8]  录制[F9]  停止[F10]", bg="#f0f0f0", font=("Arial", 10)).pack(
            side="left")
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

        # 2. 主区域
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=10, pady=5)

        # === 左侧：编辑器 ===
        f_edit = tk.LabelFrame(paned, text=" 🛠️ 节点参数 ", padx=10, pady=10)
        paned.add(f_edit, width=380)

        tk.Label(f_edit, text="类型:").grid(row=0, column=0, sticky="w")
        self.cb_type = ttk.Combobox(f_edit, state="readonly",
                                    values=["寻找图片", "点击坐标", "输入文本", "按下按键", "等待", "移动", "拖拽"])
        self.cb_type.current(1)
        self.cb_type.grid(row=0, column=1, columnspan=2, sticky="we", pady=5)
        self.cb_type.bind("<<ComboboxSelected>>", self.on_type_change)

        self.lbl_x = tk.Label(f_edit, text="X:");
        self.lbl_x.grid(row=1, column=0, sticky="w")
        self.e_x = tk.Entry(f_edit, bg="#e3f2fd");
        self.e_x.grid(row=1, column=1, sticky="we")
        self.lbl_y = tk.Label(f_edit, text="Y:");
        self.lbl_y.grid(row=2, column=0, sticky="w")
        self.e_y = tk.Entry(f_edit, bg="#e3f2fd");
        self.e_y.grid(row=2, column=1, sticky="we")

        self.btn_cap = tk.Button(f_edit, text="📷 截图(F7)", command=self.start_capture, bg="#ffcc80", state="disabled")
        self.btn_cap.grid(row=1, column=2, rowspan=2, padx=5, sticky="news")

        # 区域设置
        self.f_region = tk.LabelFrame(f_edit, text=" 🔍 找图设置 ", padx=5, pady=5, fg="blue")
        self.f_region.grid(row=3, column=0, columnspan=3, sticky="we", pady=5)
        self.var_regional = tk.BooleanVar()
        self.chk_region = tk.Checkbutton(self.f_region, text="区域限制 (红圈)", variable=self.var_regional,
                                         command=self.toggle_region_ui)
        self.chk_region.pack(anchor="w")
        f_r_sub = tk.Frame(self.f_region);
        f_r_sub.pack(fill="x")
        tk.Label(f_r_sub, text="半径:").pack(side="left")
        self.e_radius = tk.Entry(f_r_sub, width=5);
        self.e_radius.insert(0, "300");
        self.e_radius.pack(side="left")
        self.var_stop_fail = tk.BooleanVar(value=True)
        tk.Checkbutton(self.f_region, text="失败则停止脚本", variable=self.var_stop_fail, fg="red").pack(anchor="w")

        self.lbl_img = tk.Label(f_edit, text="[无图片]", relief="sunken", bg="#ddd", height=4)
        self.lbl_img.grid(row=4, column=0, columnspan=3, sticky="we", pady=5)

        self.lbl_p = tk.Label(f_edit, text="参数:");
        self.lbl_p.grid(row=5, column=0, sticky="w")
        self.e_param = tk.Entry(f_edit);
        self.e_param.grid(row=5, column=1, columnspan=2, sticky="we")

        self.lbl_hint = tk.Label(f_edit, text="提示：拖动节点位置，绿点拖红点连线。", fg="gray", font=("Arial", 9),
                                 wraplength=350, justify="left")
        self.lbl_hint.grid(row=6, column=0, columnspan=3, pady=5)

        f_ops = tk.Frame(f_edit)
        f_ops.grid(row=7, column=0, columnspan=3, pady=10, sticky="we")
        tk.Button(f_ops, text="➕ 新增节点", command=self.add_node_btn, bg="#c8e6c9", height=2).pack(side="left",
                                                                                                    fill="x",
                                                                                                    expand=True, padx=2)
        tk.Button(f_ops, text="💾 保存参数", command=self.save_node_params, bg="#ffecb3", height=2).pack(side="left",
                                                                                                        fill="x",
                                                                                                        expand=True,
                                                                                                        padx=2)
        tk.Button(f_ops, text="❌ 删除节点", command=self.delete_node, fg="white", bg="#ef5350", height=2).pack(
            side="left", fill="x", expand=True, padx=2)

        # === 右侧：无限画布 ===
        f_canvas = tk.LabelFrame(paned, text=" 🕸️ 节点编排画布 (右键拖拽移动画布) ", padx=5, pady=5)
        paned.add(f_canvas)

        self.canvas = tk.Canvas(f_canvas, bg="#2b2b2b")
        h_scroll = tk.Scrollbar(f_canvas, orient="horizontal", command=self.canvas.xview)
        v_scroll = tk.Scrollbar(f_canvas, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

        h_scroll.pack(side="bottom", fill="x")
        v_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<ButtonPress-3>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B3-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))

        # 3. 底部
        f_bot = tk.Frame(self, pady=10, bd=1, relief="raised")
        f_bot.pack(fill="x", side="bottom")

        tk.Button(f_bot, text="💾 保存流程", command=self.save_file).pack(side="left", padx=20)
        tk.Button(f_bot, text="📂 读取流程", command=self.load_file).pack(side="left")
        # 新增自动排列按钮
        tk.Button(f_bot, text="✨ 自动排列", command=self.auto_layout, bg="#b2dfdb").pack(side="left", padx=20)
        tk.Button(f_bot, text="🗑️ 重置画布", command=self.reset_graph).pack(side="left")

        self.btn_run = tk.Button(f_bot, text="▶ 执行流程", command=self.toggle_run, bg="#4CAF50", fg="white", width=20,
                                 font=("Arial", 11, "bold"))
        self.btn_run.pack(side="right", padx=20)

        self.on_type_change(None)

    # ==================================================
    # 核心升级：自动排列 (Auto Layout)
    # ==================================================
    def auto_layout(self):
        """算法：自动整理节点位置"""
        start_x, start_y = 50, 50
        gap_y = 80  # 节点垂直间距

        # 1. 整理主链 (Start -> Next -> Next ...)
        current_id = self.start_node_id
        current_y = start_y

        visited = set()  # 防止环路死循环

        # 遍历主链
        while current_id:
            if current_id in visited: break
            visited.add(current_id)

            # 更新坐标
            if current_id in self.nodes:
                self.nodes[current_id]['x'] = start_x
                self.nodes[current_id]['y'] = current_y
                current_y += gap_y

                # 寻找下一个
                current_id = self.nodes[current_id].get('next')

                # 安全检查：如果指向了不存在的节点，中断
                if current_id and current_id not in self.nodes:
                    current_id = None

        # 2. 整理断开的孤儿节点 (Orphans)
        # 放在主链右侧
        orphan_x = start_x + 200
        orphan_y = start_y

        for nid in self.nodes:
            if nid not in visited:
                self.nodes[nid]['x'] = orphan_x
                self.nodes[nid]['y'] = orphan_y
                orphan_y += gap_y

        self.refresh_canvas()
        # 自动滚动回顶部
        self.canvas.yview_moveto(0)
        messagebox.showinfo("整理完成", "已自动对齐所有节点！\n主流程在左，断开的节点在右。")

    # ==================================================
    # 画布交互与绘制 (保持 v10.1 逻辑)
    # ==================================================
    def refresh_canvas(self):
        self.canvas.delete("all")

        # 1. 连线
        for nid, node in self.nodes.items():
            if node.get('next'):
                next_node = self.nodes.get(node['next'])
                if next_node:
                    x1, y1 = node['x'] + 140, node['y'] + 25
                    x2, y2 = next_node['x'], next_node['y'] + 25
                    self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST, width=2, fill="#00e676", tags="wire")

        # 2. 节点
        for nid, node in self.nodes.items():
            x, y = node['x'], node['y']
            w, h = 140, 50

            color_map = {'start': '#81c784', 'click': '#fff176', 'find_img': '#4fc3f7', 'text': '#ffb74d',
                         'press': '#ba68c8', 'wait': '#e0e0e0', 'move': '#a1887f', 'drag': '#90a4ae'}
            bg_color = color_map.get(node['type'], 'white')
            outline = "red" if nid == self.selected_node_id else "black"
            width = 3 if nid == self.selected_node_id else 1

            tag = f"node_{nid}"
            self.canvas.create_rectangle(x, y, x + w, y + h, fill=bg_color, outline=outline, width=width,
                                         tags=(tag, "drag_body"))

            title = node['type'].upper()
            if node['type'] == 'find_img':
                title = "FIND IMG"
            elif node['type'] == 'click':
                title = f"CLICK ({node['data'].get('x', 0)},{node['data'].get('y', 0)})"

            self.canvas.create_text(x + 10, y + 25, text=title, anchor="w", font=("Arial", 8, "bold"),
                                    tags=(tag, "drag_body"))

            if node['type'] != 'start':
                self.canvas.create_oval(x - 6, y + 20, x + 4, y + 30, fill="#ff5252", outline="black",
                                        tags=(f"in_{nid}", "port_in"))

            self.canvas.create_oval(x + w - 4, y + 20, x + w + 6, y + 30, fill="#00e676", outline="black",
                                    tags=(f"out_{nid}", "port_out"))

        self.canvas.config(scrollregion=self.canvas.bbox("all"))

    def on_canvas_press(self, event):
        wx = self.canvas.canvasx(event.x);
        wy = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(wx - 5, wy - 5, wx + 5, wy + 5)
        for item in items:
            tags = self.canvas.gettags(item)
            if "port_out" in tags:
                for t in tags:
                    if t.startswith("out_"):
                        nid = t.split("_", 1)[1]
                        self.drag_data["type"] = "wire";
                        self.drag_data["source_id"] = nid
                        self.drag_data["x"] = wx;
                        self.drag_data["y"] = wy
                        return
        for item in items:
            tags = self.canvas.gettags(item)
            if "drag_body" in tags:
                for t in tags:
                    if t.startswith("node_"):
                        nid = t.split("_", 1)[1]
                        self.selected_node_id = nid
                        self.drag_data["type"] = "move";
                        self.drag_data["source_id"] = nid
                        self.drag_data["x"] = wx;
                        self.drag_data["y"] = wy
                        self.refresh_canvas();
                        self.load_node_to_ui(nid)
                        return
        self.selected_node_id = None;
        self.refresh_canvas()

    def on_canvas_drag(self, event):
        wx = self.canvas.canvasx(event.x);
        wy = self.canvas.canvasy(event.y)
        if self.drag_data["type"] == "move":
            dx = wx - self.drag_data["x"];
            dy = wy - self.drag_data["y"]
            nid = self.drag_data["source_id"]
            self.nodes[nid]['x'] += dx;
            self.nodes[nid]['y'] += dy
            self.drag_data["x"] = wx;
            self.drag_data["y"] = wy
            self.refresh_canvas()
        elif self.drag_data["type"] == "wire":
            if self.temp_line: self.canvas.delete(self.temp_line)
            self.temp_line = self.canvas.create_line(self.drag_data["x"], self.drag_data["y"], wx, wy, fill="white",
                                                     dash=(4, 4), width=2)

    def on_canvas_release(self, event):
        wx = self.canvas.canvasx(event.x);
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

    # ==================================================
    # 数据管理
    # ==================================================
    def get_ui_data(self):
        t = self.cb_type.get()
        d = {}
        try:
            if "寻找图片" in t:
                if not self.current_img_path: messagebox.showerror("错", "无图片"); return None
                d = {"type": "find_img", "img": self.current_img_path, "timeout": float(self.e_param.get()),
                     "val_x": int(self.e_x.get()), "val_y": int(self.e_y.get()), "regional": self.var_regional.get(),
                     "radius": int(self.e_radius.get()), "stop_fail": self.var_stop_fail.get()}
            elif "点击" in t:
                d = {"type": "click", "x": int(self.e_x.get()), "y": int(self.e_y.get()), "btn": "left"}
            elif "输入" in t:
                d = {"type": "text", "text": self.e_param.get()}
            elif "按键" in t:
                d = {"type": "press", "key": self.e_param.get().lower()}
            elif "等待" in t:
                d = {"type": "wait", "time": float(self.e_param.get())}
            elif "移动" in t:
                d = {"type": "move", "x": int(self.e_x.get()), "y": int(self.e_y.get())}
            elif "拖拽" in t:
                d = {"type": "drag", "x": int(self.e_x.get()), "y": int(self.e_y.get()),
                     "dur": float(self.e_param.get())}
            return d
        except:
            return None

    def add_node_btn(self):
        data = self.get_ui_data()
        if not data: return
        self._create_and_link_node(data)

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
            nx = prev_node['x'];
            ny = prev_node['y'] + 80
        else:
            nx, ny = 100, 100

        self.nodes[nid] = {'type': data['type'], 'x': nx, 'y': ny, 'next': None, 'data': data}

        if prev_id and prev_id in self.nodes: self.nodes[prev_id]['next'] = nid

        if from_recording:
            self.recording_last_id = nid
        else:
            self.selected_node_id = nid

        self.refresh_canvas()
        self.canvas.yview_moveto(1.0)

    def save_node_params(self):
        if not self.selected_node_id or self.selected_node_id == 'start': return
        data = self.get_ui_data()
        if data:
            self.nodes[self.selected_node_id]['data'] = data
            self.nodes[self.selected_node_id]['type'] = data['type']
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

    # ==========================
    # 录制
    # ==========================
    def start_record(self):
        self.is_recording = True;
        self.last_action_time = time.time()
        if self.selected_node_id:
            self.recording_last_id = self.selected_node_id
        else:
            self.recording_last_id = self.start_node_id
        self.lbl_status.config(text="🔴 录制中...", fg="red")
        self.mouse_listener = mouse.Listener(on_click=self.on_rec_click)
        self.key_listener = keyboard.Listener(on_press=self.on_rec_key)
        self.mouse_listener.start();
        self.key_listener.start()

    def stop_record(self):
        self.is_recording = False
        if self.mouse_listener: self.mouse_listener.stop()
        if self.key_listener: self.key_listener.stop()
        self.lbl_status.config(text="✅ 完成", fg="green")

    def rec_gap(self):
        gap = time.time() - self.last_action_time;
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
        if k == "f10": self.after(0, self.stop_record); return
        if k == "f9": return
        self.rec_gap()
        d = {"type": "press", "key": k}
        self.after(0, lambda: self._create_and_link_node(d, from_recording=True))

    # ==========================
    # 复用逻辑
    # ==========================
    def update_mouse_coords(self):
        try:
            x, y = pyautogui.position(); self.lbl_mouse.config(text=f"{x},{y}")
        except:
            pass
        self.after(100, self.update_mouse_coords)

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

    def find_and_click_image(self, action_data, is_test=False):
        img_path = action_data['img'];
        timeout = action_data.get('timeout', 5)
        if not os.path.exists(img_path): return False
        search_region = None
        if action_data.get('regional', False):
            cx, cy = int(action_data['val_x']), int(action_data['val_y']);
            r = int(action_data['radius'])
            search_region = (cx - r, cy - r, r * 2, r * 2)
        start = time.time();
        found_pos = None
        self.lbl_status.config(text=f"🔍 寻找: {os.path.basename(img_path)}...", fg="blue")
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
            self.lbl_status.config(text=f"✅ 点击 ({fx},{fy})", fg="green")
            if is_test:
                pyautogui.moveTo(fx, fy, duration=0.5); messagebox.showinfo("成功", "找到图片")
            else:
                pyautogui.click(fx, fy)
            return True
        return False

    def start_capture(self):
        self.state('iconic'); time.sleep(0.3); SnippingTool(self, self.capture_done)

    def capture_done(self, bbox):
        self.state('normal');
        if not bbox: return
        ts = int(time.time() * 1000);
        path = f"assets/img_{ts}.png"
        ImageGrab.grab(bbox).save(path)
        self.current_img_path = path;
        self.show_img(path)
        self.cb_type.current(0);
        self.on_type_change(None);
        messagebox.showinfo("截图", "成功")

    def grab_pos(self):
        x, y = pyautogui.position()
        self.e_x.delete(0, tk.END);
        self.e_x.insert(0, str(x))
        self.e_y.delete(0, tk.END);
        self.e_y.insert(0, str(y))
        self.lbl_status.config(text=f"📍 {x},{y}", bg="#bbdefb")

    def on_type_change(self, event):
        t = self.cb_type.get()
        self.f_region.grid_remove();
        self.btn_cap.config(state='disabled')
        self.e_x.config(state='normal');
        self.e_y.config(state='normal')
        self.lbl_img.config(text="[无图片]")
        if "寻找图片" in t:
            self.btn_cap.config(state='normal');
            self.f_region.grid();
            self.toggle_region_ui()
            self.lbl_x.config(text="点击偏X:");
            self.lbl_y.config(text="点击偏Y:")
            self.lbl_p.config(text="超时(秒):");
            self.e_param.delete(0, tk.END);
            self.e_param.insert(0, "5")
            self.lbl_hint.config(text="提示：拖动节点位置，绿点拖红点连线。")
            if self.current_img_path: self.show_img(self.current_img_path)
        elif "点击" in t:
            self.lbl_x.config(text="X坐标:");
            self.lbl_y.config(text="Y坐标:")
            self.lbl_p.config(text="参数:");
            self.lbl_hint.config(text="提示：按 F8 抓取坐标。")
        elif "输入" in t:
            self.e_x.config(state='disabled');
            self.e_y.config(state='disabled');
            self.lbl_p.config(text="文本:")
        elif "按键" in t:
            self.e_x.config(state='disabled');
            self.e_y.config(state='disabled');
            self.lbl_p.config(text="键名:")
        elif "等待" in t:
            self.e_x.config(state='disabled');
            self.e_y.config(state='disabled');
            self.lbl_p.config(text="秒数:")

    def toggle_region_ui(self):
        if self.var_regional.get():
            self.lbl_x.config(text="中心 X:"); self.lbl_y.config(text="中心 Y:"); self.e_x.config(bg="#fff9c4")
        else:
            self.lbl_x.config(text="偏移 X:"); self.lbl_y.config(text="偏移 Y:"); self.e_x.config(bg="#e3f2fd")

    def show_img(self, path):
        if not path or not os.path.exists(path): return
        try:
            pil = Image.open(path); pil.thumbnail((280, 70)); tk_img = ImageTk.PhotoImage(pil); self.lbl_img.config(
                image=tk_img, text=""); self.lbl_img.image = tk_img
        except:
            pass

    def reset_graph(self):
        self.nodes = {self.start_node_id: {'type': 'start', 'x': 50, 'y': 50, 'next': None, 'data': {}}}
        self.refresh_canvas()

    def save_file(self):
        f = filedialog.asksaveasfilename(defaultextension=".json")
        if f: json.dump({"nodes": self.nodes, "counter": self.node_counter}, open(f, 'w'))

    def load_file(self):
        f = filedialog.askopenfilename()
        if f:
            d = json.load(open(f, 'r'))
            self.nodes = d["nodes"];
            self.node_counter = d["counter"]
            self.refresh_canvas()

    def toggle_run(self):
        if self.is_playing:
            self.is_playing = False; self.btn_run.config(text="停止中...", bg="orange")
        else:
            self.is_playing = True; self.btn_run.config(text="⏹ 停止运行", bg="#ff5252"); threading.Thread(
                target=self.run_logic, daemon=True).start()

    def run_logic(self):
        try:
            curr_id = self.start_node_id
            while self.is_playing:
                node = self.nodes.get(curr_id)
                if not node: break
                self.selected_node_id = curr_id;
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
                        m = {'ctrl_l': 'ctrl', 'alt_l': 'alt', 'shift_l': 'shift'}; pyautogui.press(
                            m.get(d['key'], d['key']))
                    elif d['type'] == 'find_img':
                        suc = self.find_and_click_image(d)
                        if not suc and d.get('stop_fail', True): messagebox.showerror("中断", "找图失败"); break
                    time.sleep(0.1)

                curr_id = node['next']
                if not curr_id: break
        except Exception as e:
            print(e)
        finally:
            self.is_playing = False;
            self.btn_run.config(text="▶ 执行流程", bg="#4CAF50");
            self.lbl_status.config(text="● 就绪", fg="gray")


if __name__ == "__main__":
    app = AutoBotGraph()
    app.mainloop()