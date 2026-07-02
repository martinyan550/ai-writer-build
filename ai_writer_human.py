#!/usr/bin/env python3
"""
AI 写作助手 — 基于 DeepSeek API 的文本扩写 / 润色 / 续写工具
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import json
import os
import ssl
from urllib.request import Request, urlopen, HTTPSHandler, build_opener
from urllib.error import URLError

# 尝试使用 certifi 的 CA 证书包（解决 macOS SSL 问题）
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # 回退：尝试系统默认，不验证（非理想但保证可用）
    _SSL_CONTEXT = ssl.create_default_context()
    # 如果默认仍然失败，降级为不验证证书
    _FALLBACK_SSL = ssl.create_default_context()
    _FALLBACK_SSL.check_hostname = False
    _FALLBACK_SSL.verify_mode = ssl.CERT_NONE
    _SSL_CONTEXT = None  # 标记为需要动态尝试

# ── 配置 ──────────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.ai_writer_config.json")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

# ── 颜色主题 ──────────────────────────────────────────
class Theme:
    BG           = "#0f172a"   # 深蓝黑背景
    SURFACE      = "#1e293b"   # 卡片 / 面板
    SURFACE_ALT  = "#334155"   # 输入框背景
    PRIMARY      = "#4f46e5"   # 深靛紫（按钮背景）
    PRIMARY_HOVER = "#6366f1"  # 悬停
    PRIMARY_DARK  = "#3730a3"  # 点击
    ACCENT       = "#22d3ee"   # 青色强调
    TEXT         = "#f1f5f9"
    TEXT_SECONDARY = "#94a3b8"
    BORDER       = "#475569"
    BTN_BORDER   = "#818cf8"   # 按钮边框色（与背景有差异）
    SUCCESS      = "#34d399"
    WARNING      = "#fbbf24"
    ERROR        = "#f87171"

# ── 持久化配置 ────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ── API 调用 ──────────────────────────────────────────
def call_deepseek(api_key: str, system_prompt: str, user_text: str) -> str:
    """调用 DeepSeek API，返回生成的文本"""
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.8,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = Request(DEEPSEEK_API_URL, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })

    # SSL 兼容处理：优先使用 certifi，失败则尝试系统默认，最终降级
    if _SSL_CONTEXT is not None:
        # certifi 可用，直接使用
        opener = build_opener(HTTPSHandler(context=_SSL_CONTEXT))
    else:
        # certifi 不可用，依次尝试
        errors = []
        for ctx, label in [
            (ssl.create_default_context(), "系统默认证书"),
            (_FALLBACK_SSL, "跳过证书验证"),
        ]:
            try:
                opener = build_opener(HTTPSHandler(context=ctx))
                opener.open(Request("https://api.deepseek.com"), timeout=5)
                opener = build_opener(HTTPSHandler(context=ctx))
                break
            except Exception as e:
                errors.append(f"  - {label}: {e}")
        else:
            raise URLError(
                "SSL 证书验证失败，所有方案均不可用。\n\n"
                "👉 推荐执行以下命令安装证书包：\n"
                "   pip3 install certifi\n\n"
                "详细错误：\n" + "\n".join(errors)
            )

    with opener.open(req, timeout=90) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"]

# ── 各功能的 System Prompt ────────────────────────────
PROMPTS = {
    "扩写": (
        "你是一位专业的中文写作助手。请将用户提供的文本进行扩写，"
        "在保留原意的基础上，丰富细节、补充论据、增加生动的描写或例证，"
        "使内容更加充实饱满。直接输出扩写后的结果，不要加任何前缀说明。"
    ),
    "润色": (
        "你是一位资深的中文编辑。请对用户提供的文本进行润色，"
        "优化用词、调整句式、提升文采，使表达更加流畅优美、富有感染力。"
        "保持原意不变。直接输出润色后的结果，不要加任何前缀说明。"
    ),
    "续写": (
        "你是一位富有创意的中文作家。请根据用户提供的文本开头，"
        "进行自然、连贯的续写。延续原文的风格和语气，"
        "写出合理的后续内容。直接输出续写结果（包含原文+续写），不要加任何前缀说明。"
    ),
}

# ── GUI 应用 ──────────────────────────────────────────
class AIWriterApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("✍️ AI 写作助手")
        self.root.geometry("900x720")
        self.root.minsize(700, 560)
        self.root.configure(bg=Theme.BG)

        # 图标（emoji 替代）
        self.root.tk_setPalette(
            background=Theme.BG,
            foreground=Theme.TEXT,
        )

        # 加载配置
        self.config = load_config()

        self._build_ui()
        self._load_api_key()

    # ── UI 构建 ────────────────────────────────────────
    def _build_ui(self):
        # 主容器
        main = tk.Frame(self.root, bg=Theme.BG)
        main.pack(fill=tk.BOTH, expand=True, padx=24, pady=20)

        # ── 标题栏 ──
        title_frame = tk.Frame(main, bg=Theme.BG)
        title_frame.pack(fill=tk.X, pady=(0, 16))

        tk.Label(
            title_frame,
            text="✍️ AI 写作助手",
            font=("SF Pro Display", 24, "bold"),
            fg=Theme.TEXT,
            bg=Theme.BG,
        ).pack(side=tk.LEFT)

        tk.Label(
            title_frame,
            text="DeepSeek · 扩写 · 润色 · 续写",
            font=("SF Pro Display", 12),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG,
        ).pack(side=tk.LEFT, padx=(12, 0), pady=(8, 0))

        # ── API Key 行 ──
        api_frame = tk.Frame(main, bg=Theme.SURFACE, highlightthickness=1,
                             highlightbackground=Theme.BORDER, highlightcolor=Theme.BORDER)
        api_frame.pack(fill=tk.X, pady=(0, 16), ipady=8)

        tk.Label(
            api_frame,
            text="🔑 API Key",
            font=("SF Pro Display", 12, "bold"),
            fg=Theme.TEXT,
            bg=Theme.SURFACE,
        ).pack(side=tk.LEFT, padx=(16, 12))

        self.api_key_var = tk.StringVar()
        self.api_entry = tk.Entry(
            api_frame,
            textvariable=self.api_key_var,
            show="•",
            font=("SF Mono", 12),
            bg=Theme.SURFACE_ALT,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief=tk.FLAT,
            bd=8,
        )
        self.api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))

        save_wrapper = tk.Frame(api_frame, bg=Theme.BTN_BORDER, bd=0)
        save_wrapper.pack(side=tk.LEFT, padx=(0, 6))
        self.save_btn = tk.Button(
            save_wrapper,
            text="💾 保存",
            font=("SF Pro Display", 11, "bold"),
            bg=Theme.PRIMARY,
            fg="#000000",
            activebackground=Theme.PRIMARY_HOVER,
            activeforeground="#000000",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=14,
            pady=5,
            command=self._save_api_key,
        )
        self.save_btn.pack(padx=2, pady=2)
        # 悬停效果
        self.save_btn.bind("<Enter>", lambda e: self.save_btn.configure(bg=Theme.PRIMARY_HOVER))
        self.save_btn.bind("<Leave>", lambda e: self.save_btn.configure(bg=Theme.PRIMARY))

        self.clear_key_btn = tk.Button(
            api_frame,
            text="✕",
            font=("SF Pro Display", 11, "bold"),
            bg=Theme.SURFACE_ALT,
            fg="#94a3b8",
            activebackground=Theme.ERROR,
            activeforeground="#000000",
            relief=tk.FLAT,
            cursor="hand2",
            padx=10,
            pady=4,
            command=self._clear_api_key,
        )
        self.clear_key_btn.pack(side=tk.LEFT, padx=(0, 12))

        # ── 输入区 ──
        tk.Label(
            main,
            text="📥 输入文本",
            font=("SF Pro Display", 13, "bold"),
            fg=Theme.TEXT,
            bg=Theme.BG,
        ).pack(anchor=tk.W, pady=(0, 6))

        self.input_text = scrolledtext.ScrolledText(
            main,
            font=("SF Pro Text", 13),
            bg=Theme.SURFACE,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief=tk.FLAT,
            bd=12,
            wrap=tk.WORD,
            height=8,
            selectbackground=Theme.PRIMARY,
            selectforeground=Theme.TEXT,
        )
        self.input_text.pack(fill=tk.BOTH, expand=False, pady=(0, 16))

        # 输入区占位提示
        self._input_placeholder = "在此粘贴或输入你的文本…… ✨"
        self.input_text.insert("1.0", self._input_placeholder)
        self.input_text.configure(fg=Theme.TEXT_SECONDARY)
        self.input_text.bind("<FocusIn>", self._on_input_focus_in)
        self.input_text.bind("<FocusOut>", self._on_input_focus_out)

        # ── 功能按钮 ──
        btn_frame = tk.Frame(main, bg=Theme.BG)
        btn_frame.pack(fill=tk.X, pady=(0, 16))

        self.buttons = {}
        actions = [
            ("📝  扩  写", "expand", "丰富细节，充实内容"),
            ("✨  润  色", "polish", "优化用词，提升文采"),
            ("📖  续  写", "continue", "延续风格，自然衔接"),
        ]

        for i, (label, key, tip) in enumerate(actions):
            # 用 Frame 包裹，绘制可见边框
            wrapper = tk.Frame(btn_frame, bg=Theme.BTN_BORDER, bd=0)
            wrapper.pack(side=tk.LEFT, padx=(0 if i == 0 else 14, 0), fill=tk.X, expand=True)

            btn = tk.Button(
                wrapper,
                text=label,
                font=("SF Pro Display", 14, "bold"),
                bg=Theme.PRIMARY,
                fg="#000000",
                activebackground=Theme.PRIMARY_HOVER,
                activeforeground="#000000",
                relief=tk.FLAT,
                bd=0,
                cursor="hand2",
                padx=24,
                pady=14,
                highlightthickness=0,
            )
            btn.configure(command=lambda k=key: self._start_task(k))
            btn.pack(padx=2, pady=2, fill=tk.BOTH, expand=True)

            # 悬停效果
            btn.bind("<Enter>", lambda e, b=btn, w=wrapper: (
                b.configure(bg=Theme.PRIMARY_HOVER),
                w.configure(bg=Theme.ACCENT)
            ))
            btn.bind("<Leave>", lambda e, b=btn, w=wrapper: (
                b.configure(bg=Theme.PRIMARY),
                w.configure(bg=Theme.BTN_BORDER)
            ))
            btn.bind("<ButtonPress-1>", lambda e, b=btn: b.configure(bg=Theme.PRIMARY_DARK))
            btn.bind("<ButtonRelease-1>", lambda e, b=btn: b.configure(bg=Theme.PRIMARY_HOVER))

            self.buttons[key] = btn

        # Tip label
        tip_frame = tk.Frame(main, bg=Theme.BG)
        tip_frame.pack(fill=tk.X, pady=(0, 8))
        self.tip_labels = {}
        for i, (_, key, tip) in enumerate(actions):
            lbl = tk.Label(
                tip_frame,
                text=tip,
                font=("SF Pro Display", 10),
                fg=Theme.TEXT_SECONDARY,
                bg=Theme.BG,
            )
            lbl.pack(side=tk.LEFT, expand=True)
            self.tip_labels[key] = lbl

        # ── 状态指示 ──
        self.status_frame = tk.Frame(main, bg=Theme.BG)
        self.status_frame.pack(fill=tk.X, pady=(0, 8))

        self.spinner_label = tk.Label(
            self.status_frame,
            text="",
            font=("SF Pro Display", 12),
            fg=Theme.ACCENT,
            bg=Theme.BG,
        )
        self.spinner_label.pack(side=tk.LEFT)

        self.status_label = tk.Label(
            self.status_frame,
            text="✅ 就绪",
            font=("SF Pro Display", 11),
            fg=Theme.SUCCESS,
            bg=Theme.BG,
        )
        self.status_label.pack(side=tk.RIGHT)

        # ── 输出区 ──
        tk.Label(
            main,
            text="📤 生成结果",
            font=("SF Pro Display", 13, "bold"),
            fg=Theme.TEXT,
            bg=Theme.BG,
        ).pack(anchor=tk.W, pady=(0, 6))

        self.output_text = scrolledtext.ScrolledText(
            main,
            font=("SF Pro Text", 13),
            bg=Theme.SURFACE,
            fg=Theme.TEXT,
            relief=tk.FLAT,
            bd=12,
            wrap=tk.WORD,
            height=10,
            selectbackground=Theme.PRIMARY,
            selectforeground=Theme.TEXT,
        )
        self.output_text.pack(fill=tk.BOTH, expand=True, pady=(0, 12))

        # ── 底部操作栏 ──
        bottom = tk.Frame(main, bg=Theme.BG)
        bottom.pack(fill=tk.X)

        copy_wrapper = tk.Frame(bottom, bg=Theme.BORDER, bd=0)
        copy_wrapper.pack(side=tk.LEFT)
        copy_btn = tk.Button(
            copy_wrapper,
            text="📋 复制结果",
            font=("SF Pro Display", 11, "bold"),
            bg=Theme.SURFACE,
            fg="#ffffff",
            activebackground=Theme.SURFACE_ALT,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            padx=14,
            pady=6,
            command=self._copy_output,
        )
        copy_btn.pack(padx=2, pady=2)
        # 悬停效果
        copy_btn.bind("<Enter>", lambda e: copy_btn.configure(bg=Theme.SURFACE_ALT))
        copy_btn.bind("<Leave>", lambda e: copy_btn.configure(bg=Theme.SURFACE))

        clear_btn = tk.Button(
            bottom,
            text="🗑️ 清空",
            font=("SF Pro Display", 11),
            bg=Theme.SURFACE,
            fg="#94a3b8",
            activebackground=Theme.ERROR,
            activeforeground="#ffffff",
            relief=tk.FLAT,
            cursor="hand2",
            padx=16,
            pady=6,
            command=self._clear_output,
        )
        clear_btn.pack(side=tk.RIGHT)

    # ── 输入框 Placeholder ─────────────────────────────
    def _on_input_focus_in(self, event):
        if self.input_text.get("1.0", "end-1c") == self._input_placeholder:
            self.input_text.delete("1.0", tk.END)
            self.input_text.configure(fg=Theme.TEXT)

    def _on_input_focus_out(self, event):
        if not self.input_text.get("1.0", "end-1c").strip():
            self.input_text.insert("1.0", self._input_placeholder)
            self.input_text.configure(fg=Theme.TEXT_SECONDARY)

    # ── API Key 管理 ───────────────────────────────────
    def _load_api_key(self):
        key = self.config.get("api_key", "")
        if key:
            self.api_key_var.set(key)

    def _save_api_key(self):
        key = self.api_key_var.get().strip()
        if key:
            self.config["api_key"] = key
            save_config(self.config)
            self._set_status("🔑 API Key 已保存", Theme.SUCCESS)
        else:
            self._set_status("⚠️ 请输入有效的 API Key", Theme.WARNING)

    def _clear_api_key(self):
        self.api_key_var.set("")
        self.config.pop("api_key", None)
        save_config(self.config)
        self._set_status("🗑️ API Key 已清除", Theme.TEXT_SECONDARY)

    # ── 状态更新 ───────────────────────────────────────
    def _set_status(self, msg: str, color: str):
        self.status_label.configure(text=msg, fg=color)

    # ── 任务调度 ───────────────────────────────────────
    def _start_task(self, action: str):
        api_key = self.api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning(
                "缺少 API Key",
                "请先在上方输入你的 DeepSeek API Key 并点击保存。\n\n"
                "获取地址: https://platform.deepseek.com/api_keys"
            )
            return

        text = self.input_text.get("1.0", "end-1c").strip()
        if not text or text == self._input_placeholder:
            messagebox.showwarning("缺少文本", "请在输入框中粘贴或输入你需要处理的文本。")
            return

        # 禁用按钮
        for btn in self.buttons.values():
            btn.configure(state=tk.DISABLED)

        action_names = {"expand": "扩写", "polish": "润色", "continue": "续写"}
        name = action_names[action]

        self._set_status(f"⏳ 正在{name}中……", Theme.WARNING)
        self._start_spinner()

        # 在新线程中调用 API
        t = threading.Thread(target=self._run_task, args=(action, api_key, text, name), daemon=True)
        t.start()

    def _run_task(self, action: str, api_key: str, text: str, name: str):
        try:
            system_prompt = PROMPTS[name]
            result = call_deepseek(api_key, system_prompt, text)
            self.root.after(0, lambda: self._on_task_done(name, result))
        except URLError as e:
            err_msg = str(e)
            if hasattr(e, "read"):
                try:
                    err_body = json.loads(e.read().decode())
                    err_msg = err_body.get("error", {}).get("message", err_msg)
                except Exception:
                    pass
            self.root.after(0, lambda: self._on_task_error(f"网络错误: {err_msg}"))
        except Exception as e:
            self.root.after(0, lambda: self._on_task_error(str(e)))

    def _on_task_done(self, name: str, result: str):
        self._stop_spinner()
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert("1.0", result)
        self._set_status(f"✅ {name}完成！", Theme.SUCCESS)

        for btn in self.buttons.values():
            btn.configure(state=tk.NORMAL)

    def _on_task_error(self, err: str):
        self._stop_spinner()
        self._set_status(f"❌ 出错了", Theme.ERROR)
        messagebox.showerror("调用失败", f"API 请求失败：\n\n{err}")
        for btn in self.buttons.values():
            btn.configure(state=tk.NORMAL)

    # ── 简易 Spinner 动画 ──────────────────────────────
    def _animate_spinner(self):
        if not hasattr(self, "_spinning") or not self._spinning:
            return
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        current = getattr(self, "_spinner_idx", 0)
        self.spinner_label.configure(text=frames[current])
        self._spinner_idx = (current + 1) % len(frames)
        self._spinner_job = self.root.after(80, self._animate_spinner)

    def _stop_spinner(self):
        self._spinning = False
        if hasattr(self, "_spinner_job"):
            self.root.after_cancel(self._spinner_job)
        self.spinner_label.configure(text="")

    def _start_spinner(self):
        self._spinning = True
        self._spinner_idx = 0
        self._animate_spinner()

    # ── 复制 / 清空 ────────────────────────────────────
    def _copy_output(self):
        text = self.output_text.get("1.0", "end-1c").strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self._set_status("📋 已复制到剪贴板！", Theme.ACCENT)
            # 1.5 秒后恢复
            self.root.after(1500, lambda: self._set_status("✅ 就绪", Theme.SUCCESS))
        else:
            self._set_status("⚠️ 没有可复制的内容", Theme.TEXT_SECONDARY)

    def _clear_output(self):
        self.output_text.delete("1.0", tk.END)


# ── 入口 ──────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = AIWriterApp(root)

    # 居中显示
    root.update_idletasks()
    w = root.winfo_width()
    h = root.winfo_height()
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    root.geometry(f"+{x}+{y}")

    root.mainloop()
