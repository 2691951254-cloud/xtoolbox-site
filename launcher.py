# -*- coding: utf-8 -*-
"""
X机房盒子 Java 开发版 v3.9.1 —— 一键自动启动器

双击 exe 后全自动完成：
  1. 找 JDK（java/javac）
  2. 自动编译 Java 源码 → jar（源码比 jar 新才编译）
  3. 弹窗选 HPM 文件
  4. 调 HotPE 官方 HPMLoadCLI.exe quick 模式加载（/lp 指定目录，不跑桌面）
  5. 弹出结果（含找到的主程序 exe）

用户完全不用敲命令。机房同学拿到整个文件夹，双击 exe 就行。
"""
import os
import sys
import subprocess
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

VERSION = "3.9.1"
HERE = getattr(sys, "_MEIPASS", "") or os.path.dirname(os.path.abspath(__file__))
# onefile 下源码可能不在 _MEIPASS（我们只把启动器打包，Java 源码在 exe 旁边）
BASE = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, "frozen", False) else HERE

SRC_DIR = os.path.join(BASE, "src", "main", "java")
CLASSES_DIR = os.path.join(BASE, "build", "classes")
JAR = os.path.join(BASE, "X机房盒子-%s.jar" % VERSION)
MANIFEST = os.path.join(BASE, "build", "manifest.txt")
CLI = None
for _rel in ("HPM官方工具/HPMLoadCLI.exe", "_补丁包/HPM官方工具/HPMLoadCLI.exe"):
    _p = os.path.join(BASE, *_rel.split("/"))
    if os.path.isfile(_p):
        CLI = _p
        break


def find_javac():
    """找 javac：先看 PATH，再看常见安装位置。"""
    import shutil
    j = shutil.which("javac")
    if j:
        return j
    for p in (r"C:\Program Files\Java\jdk-17\bin\javac.exe",
              r"C:\Program Files\Java\jdk-21\bin\javac.exe",
              r"C:\Program Files\Eclipse Adoptium\jdk-17\bin\javac.exe",
              r"C:\Program Files\Java\jdk-1.8\bin\javac.exe"):
        if os.path.isfile(p):
            return p
    return ""


def find_java():
    import shutil
    j = shutil.which("java")
    if j:
        return j
    for p in (r"C:\Program Files\Java\jdk-17\bin\java.exe",
              r"C:\Program Files\Java\jdk-21\bin\java.exe"):
        if os.path.isfile(p):
            return p
    return ""


def need_build():
    """源码比 jar 新（或 jar 不存在）就要重新编译。"""
    if not os.path.isfile(JAR):
        return True
    jar_t = os.path.getmtime(JAR)
    for root, _dirs, files in os.walk(SRC_DIR):
        for fn in files:
            if fn.endswith(".java"):
                p = os.path.join(root, fn)
                if os.path.getmtime(p) > jar_t:
                    return True
    return False


def build(log):
    javac = find_javac()
    if not javac:
        return False, "找不到 javac。请装 JDK 17 或更高版本，装完重新双击本程序。"
    if not os.path.isdir(SRC_DIR):
        return False, "找不到 Java 源码目录：\n" + SRC_DIR + "\n\n请把本 exe 和 src 文件夹放一起。"
    log("正在编译 Java 源码…")
    os.makedirs(CLASSES_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    # 收集源文件
    sources = []
    for root, _dirs, files in os.walk(SRC_DIR):
        for fn in files:
            if fn.endswith(".java"):
                sources.append(os.path.join(root, fn))
    if not sources:
        return False, "src 目录下没有 .java 文件。"
    srcfile = os.path.join(BASE, "build", "sources.txt")
    with open(srcfile, "w", encoding="utf-8") as f:
        f.write("\n".join(sources))
    # 编译
    r = subprocess.run([javac, "-encoding", "UTF-8", "--release", "17",
                        "-d", CLASSES_DIR, "@" + srcfile],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return False, "编译失败：\n" + (r.stderr or r.stdout)[:1000]
    # manifest
    with open(MANIFEST, "w", encoding="utf-8") as f:
        f.write("Manifest-Version: 1.0\nMain-Class: com.xtoolbox.Main\n"
                "Implementation-Version: %s\n" % VERSION)
    r2 = subprocess.run(["jar", "cfm", JAR, MANIFEST, "-C", CLASSES_DIR, "."],
                        capture_output=True, text=True, timeout=120)
    if r2.returncode != 0:
        return False, "打包 jar 失败：\n" + (r2.stderr or r2.stdout)[:600]
    log("编译完成 ✓")
    return True, ""


def load_hpm(hpm_path, log):
    """用官方 HPMLoadCLI.exe 加载 HPM 到工具箱自己的目录。"""
    if not CLI or not os.path.isfile(CLI):
        return False, "找不到官方 HPMLoadCLI.exe。\n请确认 HPM官方工具 文件夹和本 exe 在同一目录。"
    dest = os.path.join(BASE, "插件测试")
    os.makedirs(dest, exist_ok=True)
    # 清空目标
    for fn in os.listdir(dest):
        p = os.path.join(dest, fn)
        try:
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except Exception:
            pass
    cmd = '"%s" quick "%s" /lp:"%s" /h /wait' % (CLI, hpm_path, dest)
    log("正在用官方工具加载 HPM…")
    r = subprocess.run(cmd, shell=True, capture_output=True, timeout=300)
    out = ((r.stderr or b"").decode("utf-8", "ignore")
           or (r.stdout or b"").decode("utf-8", "ignore")).strip()[:400]
    # 找最大 exe
    entry = ""
    biggest = 0
    for root, _dirs, files in os.walk(dest):
        for fn in files:
            if fn.lower().endswith(".exe") and "卸载" not in fn and "unins" not in fn.lower():
                p = os.path.join(root, fn)
                try:
                    sz = os.path.getsize(p)
                    if sz > biggest:
                        biggest, entry = sz, p
                except Exception:
                    pass
    if entry:
        return True, ("加载成功！\n\n主程序：%s\n大小：%.1f MB\n\n"
                      "路径由 /lp 指定在「插件测试」文件夹，不会跑桌面。"
                      % (os.path.basename(entry), biggest / 1048576.0))
    return False, "官方工具没解出 exe。\n退出码 %d\n%s" % (r.returncode, out or "无输出")


def main():
    root = tk.Tk()
    root.title("X机房盒子 Java 版 v" + VERSION + " · 一键启动器")
    root.geometry("640x440")
    root.resizable(False, False)

    txt = tk.Text(root, wrap="word", font=("Microsoft YaHei", 10))
    txt.pack(fill="both", expand=True, padx=14, pady=(14, 8))

    def log(msg):
        txt.insert("end", msg + "\n")
        txt.see("end")
        root.update_idletasks()

    log("X机房盒子 Java 开发版 v" + VERSION)
    log("=" * 50)
    log("目录：" + BASE)

    frm = tk.Frame(root)
    frm.pack(fill="x", padx=14, pady=(0, 14))

    def do_all():
        btn_build.config(state="disabled")
        btn_load.config(state="disabled")
        def work():
            try:
                if need_build():
                    ok, err = build(log)
                    if not ok:
                        root.after(0, lambda: messagebox.showerror("编译失败", err))
                        return
                else:
                    log("jar 已是最新，跳过编译 ✓")
                log("准备就绪。点「选择 HPM 并加载」开始。")
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("出错", str(e)))
            root.after(0, lambda: (btn_build.config(state="normal"),
                                   btn_load.config(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    def do_load():
        hpm = filedialog.askopenfilename(
            title="选择一个 HotPE 模块（.HPM）",
            filetypes=[("HotPE 模块", "*.HPM"), ("所有文件", "*.*")])
        if not hpm:
            return
        btn_build.config(state="disabled")
        btn_load.config(state="disabled")
        def work():
            try:
                ok, msg = load_hpm(hpm, log)
                root.after(0, lambda: (messagebox.showinfo(
                    "加载" + ("成功" if ok else "失败"), msg) if ok
                    else messagebox.showerror("加载失败", msg)))
            except Exception as e:
                root.after(0, lambda: messagebox.showerror("出错", str(e)))
            root.after(0, lambda: (btn_build.config(state="normal"),
                                   btn_load.config(state="normal")))
        threading.Thread(target=work, daemon=True).start()

    btn_build = tk.Button(frm, text="① 只编译/检查", command=do_all, width=16)
    btn_build.pack(side="left", padx=(0, 8))
    btn_load = tk.Button(frm, text="② 选择 HPM 并加载", command=do_load, width=20)
    btn_load.pack(side="left")

    # 启动后自动编译
    root.after(200, do_all)
    root.mainloop()


if __name__ == "__main__":
    main()
