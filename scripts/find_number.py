#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
find_number.py — 直接读盘核查/查找某个图号是否存在（不依赖 Windows 索引搜索）

为什么不用 Windows 资源管理器搜索：
    它的索引经常漏文件、匹配怪异（例如把文件「大小」数字当成文件名命中），
    结果不可靠。本脚本用 os.walk 直接遍历真实文件系统，结果权威、可复现，
    且全程只读、不改动任何文件，也不会弹出任何窗口干扰前端操作。

用法:
  # 查某个 C 流水号（片段匹配，递归整棵树）
  python scripts/find_number.py --dir "E:/智能药仓 4.2B/02-01 固定货架" --num 023

  # 查完整图号
  python scripts/find_number.py --dir "E:/智能药仓 4.2B" --num "XH022501.02.01-023"

  # 只查顶层、且要求文件名(去扩展名)完全等于该图号
  python scripts/find_number.py --dir "E:/智能药仓 4.2B/02-01 固定货架" --num 023 --no-recursive --exact

参数:
  --dir        待查根目录（默认当前目录）
  --num        要查的图号片段。可以是完整图号(如 XH022501.02.01-023)、
               C 流水号(023)、或任意子串。大小写不敏感。
  --recursive / -r      递归子目录（默认开启）
  --no-recursive         仅查顶层目录
  --exact                严格模式：仅当「文件名去掉扩展名」完全等于 --num 时命中
  --ext        限定扩展名（逗号分隔，如 sldprt,slddrw）；不指定则匹配所有
"""

import os
import argparse
import sys


def find_numbers(root, num, recursive=True, exact=False, ext_filter=None):
    """返回 (hits, scanned) —— hits 为匹配文件的完整路径列表。"""
    num_l = num.lower()
    hits = []
    scanned = 0
    exts = None
    if ext_filter:
        exts = set(e.strip().lower().lstrip('.') for e in ext_filter.split(',') if e.strip())

    if recursive:
        walker = os.walk(root)
    else:
        # 仅顶层：模拟非递归
        try:
            entries = sorted(os.listdir(root))
        except OSError as e:
            print(f"[错误] 无法读取目录 {root}: {e}", file=sys.stderr)
            return hits, scanned
        walker = [(root, [], entries)]

    for dp, _dirs, files in walker:
        for f in files:
            if f.startswith('~$'):          # 跳过 SolidWorks 锁文件
                continue
            base, ext = os.path.splitext(f)
            ext_l = ext.lower().lstrip('.')
            scanned += 1
            if exts is not None and ext_l not in exts:
                continue
            if exact:
                if base.lower() == num_l:
                    hits.append(os.path.join(dp, f))
            else:
                if num_l in f.lower():
                    hits.append(os.path.join(dp, f))
    return hits, scanned


def main():
    ap = argparse.ArgumentParser(
        description="直接读盘核查/查找某个图号是否存在（不依赖 Windows 索引搜索）")
    ap.add_argument("--dir", default=".", help="待查根目录（默认当前目录）")
    ap.add_argument("--num", required=True, help="要查的图号片段/完整图号/流水号")
    ap.add_argument("--recursive", "-r", dest="recursive", action="store_true", default=True,
                    help="递归子目录（默认开启）")
    ap.add_argument("--no-recursive", dest="recursive", action="store_false",
                    help="仅查顶层目录")
    ap.add_argument("--exact", action="store_true",
                    help="严格模式：仅文件名(去扩展名)完全等于 --num 时命中")
    ap.add_argument("--ext", default=None, help="限定扩展名，逗号分隔，如 sldprt,slddrw")
    args = ap.parse_args()

    root = os.path.abspath(args.dir)
    if not os.path.isdir(root):
        print(f"[错误] 目录不存在: {root}", file=sys.stderr)
        sys.exit(2)

    print(f"直接读盘扫描: {root}")
    print(f"查询片段    : {args.num}" + ("  (严格全匹配)" if args.exact else "") +
          (f"  [扩展名={args.ext}]" if args.ext else ""))
    print(f"递归        : {'是' if args.recursive else '否'}")
    print("-" * 60)

    hits, scanned = find_numbers(root, args.num, args.recursive, args.exact, args.ext)
    print(f"已扫描文件数: {scanned}")
    print("-" * 60)

    if hits:
        print(f"找到 {len(hits)} 个匹配文件：")
        for h in sorted(hits):
            print(f"  {h}")
        print("-" * 60)
        print(f">>> 结论: 图号片段 '{args.num}' 存在（共 {len(hits)} 个文件）。")
    else:
        print(">>> 结论: 未找到任何匹配文件 —— 该图号片段在当前范围内【不存在】。")


if __name__ == "__main__":
    main()
