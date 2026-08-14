# -*- coding: utf-8 -*-
"""
xh-cad-checker · delete_orphan_drawings.py
删除「仅有 .slddrw 工程图、无对应 .sldprt/.sldasm 3D 源」的孤儿图。

安全模型（删除必须确认）：
  - 默认【只读演习】：扫描并列出将要删除的清单，不改动任何文件、不打印删除序列表。
  - 必须显式加 --apply 才真正删除——这是「删除需要确认」的硬闸门。
  - 真正删除前：① 先把所有候选文件整批备份到 --backup-dir（默认 ./orphan_backup_<时间戳>）；
    ② 再逐個(隐含≤10的保守粒度)移入系统回收站(SHFileOperation FO_ALLOWUNDO)，非永久删除，可找回；
    ③ 用「操作前后存在性」校验成败，不依赖不可靠的返回码。
  - 仅作用于 --dir 目录，绝不触碰其它位置。
  - 自动跳过 SolidWorks 锁文件 ~$*。

分类：
  - 真·孤儿图 = 图号核心编码在 3D 源中完全找不到（含「无图号」件）= 删除候选
  - 命名未同步 = 同核心编码的 3D 源存在，但图名与件名差一个字/后缀 = 保留，建议改名对齐

用法：
  python delete_orphan_drawings.py --dir "E:/智能药仓 4.2B/02-01 固定货架"        # 演习(只看不改)
  python delete_orphan_drawings.py --dir <目录> --apply                          # 确认后删除
  python delete_orphan_drawings.py --dir <目录> --apply --backup-dir D:/bak      # 指定备份位置
  python delete_orphan_drawings.py --dir <目录> --recursive                      # 递归子目录
"""
import os
import re
import sys
import shutil
import datetime
import argparse

try:
    import ctypes
    from ctypes import wintypes
    _HAS_CTYPES = True
except Exception:  # 非 Windows 环境
    _HAS_CTYPES = False


# ----------------------------- 扫描 & 分类 -----------------------------
def scan(root, recursive):
    items = []
    if recursive:
        for dp, _, fns in os.walk(root):
            for fn in fns:
                if not fn.startswith("~$"):
                    items.append(os.path.join(dp, fn))
    else:
        for fn in os.listdir(root):
            full = os.path.join(root, fn)
            if os.path.isfile(full) and not fn.startswith("~$"):
                items.append(full)
    return items


def core_of(base):
    """提取图号核心编码，如 XH022501.02.01-032-001 -> XH022501.02.01-032"""
    m = re.search(r"(XH\d+\.\d+\.\d+-\d+)(?:-\d+)?", base)
    return m.group(1) if m else None


def collect(root, recursive):
    """返回 groups: base -> set(ext); paths: base -> full path"""
    groups, paths = {}, {}
    for full in scan(root, recursive):
        fn = os.path.basename(full)
        if "." not in fn:
            continue
        base, ext = fn.rsplit(".", 1)
        ext = ext.lower()
        if ext in ("sldprt", "sldasm", "slddrw"):
            groups.setdefault(base, set()).add(ext)
            paths[base] = full
    return groups, paths


def classify(groups):
    """把仅有 .slddrw 的图分为 真·孤儿(删除) / 命名未同步(保留)"""
    src_cores = set()
    for base, exts in groups.items():
        if ("sldprt" in exts or "sldasm" in exts):
            c = core_of(base)
            if c:
                src_cores.add(c)
    drawings_only = [b for b, exts in groups.items()
                     if "slddrw" in exts and not ("sldprt" in exts or "sldasm" in exts)]
    orphans, mismatch = [], []
    for b in drawings_only:
        c = core_of(b)
        if c is None or c not in src_cores:
            orphans.append(b)          # 真·孤儿（含无图号件）
        else:
            mismatch.append(b)         # 命名未同步，源其实存在
    return orphans, mismatch


# ----------------------------- 回收站 -----------------------------
def _send_to_recycle(path):
    """移入回收站（FO_ALLOWUNDO）。返回 (rc, aborted)。靠存在性校验成败，不依赖 rc。"""
    if not _HAS_CTYPES:
        raise RuntimeError("非 Windows 环境，无法调用回收站 API")
    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", wintypes.UINT),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]
    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_NOERRORUI = 0x0400
    op = SHFILEOPSTRUCT()
    op.hwnd = 0
    op.wFunc = FO_DELETE
    op.pFrom = path + "\0\0"          # 双 NULL 结尾
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc, bool(op.fAnyOperationsAborted)


# ----------------------------- 演习 / 执行 -----------------------------
def dump_list(title, bases, paths):
    print(f"\n=== {title}（{len(bases)} 个）===")
    for b in sorted(bases):
        print("   " + b)


def main():
    ap = argparse.ArgumentParser(description="删除仅有 .slddrw 无 3D 源的孤儿工程图（默认演习）")
    ap.add_argument("--dir", required=True, help="目标目录（仅此目录会被处理）")
    ap.add_argument("--apply", action="store_true", help="真正删除（不加=只读演习）。这是删除确认闸门")
    ap.add_argument("--backup-dir", default=None, help="备份目录（默认 ./orphan_backup_<时间戳>）")
    ap.add_argument("--recursive", action="store_true", help="递归子目录")
    args = ap.parse_args()

    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        print(f"[错误] 目录不存在: {root}")
        sys.exit(2)

    groups, paths = collect(root, args.recursive)
    orphans, mismatch = classify(groups)

    print(f"目录: {root}")
    print(f"模式: {'【真正删除】' if args.apply else '【只读演习】'}   "
          f"递归: {'是' if args.recursive else '否(仅顶层)'}")
    print(f"仅有 .slddrw 无源的图共 {len(orphans) + len(mismatch)} 个")
    dump_list("真·孤儿图（删除候选）", orphans, paths)
    dump_list("命名未同步（源存在，保留/建议改名）", mismatch, paths)

    if not args.apply:
        print("\n[演习结束] 未做任何改动。确认清单无误后，加 --apply 执行删除。")
        print("提示: 命名未同步类不会删除，建议后续在 SolidWorks 中统一命名。")
        sys.exit(0)

    if not orphans:
        print("\n没有可删除的孤儿图，结束。")
        sys.exit(0)

    # ---------------- 真正删除 ----------------
    print("\n⚠️ 即将删除以上 %d 个孤儿图（先备份、再移入回收站）。" % len(orphans))
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = args.backup_dir or os.path.join(os.getcwd(), f"orphan_backup_{ts}")
    os.makedirs(bak, exist_ok=True)

    # 1) 整批备份（用相对路径避免重名）
    ok_bak = 0
    for b in orphans:
        src = paths[b]
        rel = os.path.relpath(src, root).replace(os.sep, "_")
        try:
            shutil.copy2(src, os.path.join(bak, rel))
            ok_bak += 1
        except Exception as e:
            print(f"  [备份失败] {src} -> {e}")
    print(f"已备份 {ok_bak}/{len(orphans)} 个到: {bak}")

    # 2) 逐个移入回收站，存在性校验
    done, failed = 0, []
    for b in sorted(orphans):
        p = os.path.normpath(paths[b])     # 关键: 统一为反斜杠，避免 SHFileOperation 误报
        if not os.path.exists(p):
            continue
        try:
            _send_to_recycle(p)
        except Exception as e:
            print(f"  [调用异常] {p} -> {e}")
        # 用存在性判断成败（rc 不可靠）
        if not os.path.exists(p):
            done += 1
        else:
            failed.append(p)
            print(f"  [删除未生效，保留] {p}")

    # 3) 导出已删除序列表
    seq_path = os.path.join(os.getcwd(), f"deleted_drawings_{ts}.txt")
    with open(seq_path, "w", encoding="utf-8") as fh:
        for b in sorted(orphans):
            fh.write(b + "\n")

    print(f"\n[完成] 移入回收站 {done} 个, 未生效 {len(failed)} 个")
    print(f"备份目录: {bak}  (回收站内文件可找回；备份为双保险)")
    print(f"已删除序列表: {seq_path}")
    if failed:
        print("[警告] 以下未删除，请检查: " + "; ".join(failed))
    print("[后续] 关闭 SolidWorks 后重跑一次可得到稳定数字；命名未同步类建议在 SW 中改名对齐。")


if __name__ == "__main__":
    main()
