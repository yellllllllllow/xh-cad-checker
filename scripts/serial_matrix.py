# -*- coding: utf-8 -*-
"""
xh-cad-checker · serial_matrix.py
生成「序号矩阵表」：把每个层级从最小号到最大号逐行列出，每格显示
  [序号 | 完整文件名(带扩展名) | 状态(有/缺)]
绿=有文件，红=缺(无文件)。按层级分段，便于一眼看出哪个号缺文件、哪个号重号/变体。

布局：默认每行 3 个单元 = 9 列（贴「10 列」密度）。可用 --units 调整每行单元数。
输出：HTML 始终生成（标准库，零依赖）；XLSX 在检测到 openpyxl 时一并生成，
      否则提示 `pip install openpyxl` 并仅出 HTML。全程只读。

用法：
  python serial_matrix.py --dir "E:/智能药仓 4.2B/02-01 固定货架"
  python serial_matrix.py --dir <目录> --out matrix.html --xlsx matrix.xlsx
  python serial_matrix.py --dir <目录> --recursive --units 4      # 每行4单元=12列
"""
import os
import re
import argparse

try:
    import html as _html
    _esc = _html.escape
except Exception:
    _esc = lambda s: s


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


def collect(root, recursive):
    """level -> seq -> [完整文件名(带扩展名)]"""
    occ = {}
    for full in scan(root, recursive):
        fn = os.path.basename(full)
        if "." not in fn:
            continue
        base, ext = fn.rsplit(".", 1)
        ext = ext.lower()
        if ext in ("sldprt", "sldasm", "slddrw"):
            m = re.match(r"^XH\d+\.(\d+\.\d+)-(\d+)", base)
            if m:
                occ.setdefault(m.group(1), {}).setdefault(int(m.group(2)), []).append(fn)
    return occ


def build_html(occ, units):
    SUB = 3                      # 序号 | 完整文件名 | 状态
    COLS = units * SUB
    h = ['<html><head><meta charset="utf-8"><title>序号矩阵</title>']
    h.append('<style>'
             'body{font-family:-apple-system,Segoe UI,Microsoft YaHei,sans-serif;color:#222;background:#fafafa;margin:20px;}'
             'h2{color:#1a3c6e;}'
             'table{border-collapse:collapse;background:#fff;font-size:11.5px;margin-bottom:18px;}'
             'th,td{border:1px solid #d4d9e2;padding:3px 6px;text-align:left;vertical-align:top;}'
             'th{background:#1a3c6e;color:#fff;}'
             'td.seq{font-family:Consolas,monospace;font-weight:600;text-align:center;}'
             'td.name{font-family:Consolas,monospace;}'
             'td.have{background:#eafaef;color:#1a7a3c;font-weight:700;text-align:center;}'
             'td.miss{background:#fdecec;color:#b00020;font-weight:700;text-align:center;}'
             '.sum{background:#eef4ff;padding:8px 12px;border-left:4px solid #1a3c6e;margin:8px 0;font-size:13px;}'
             '</style></head><body>')
    h.append('<h2>序号矩阵（序号 | 完整文件名 | 状态）</h2>')
    h.append('<div class="sum">每 %d 列 = %d 单元(序号|完整文件名|状态) | 绿=有 红=缺 | 仅读取分析</div>'
             % (COLS, units))
    for level in sorted(occ.keys()):
        seqs = sorted(occ[level].keys())
        lo, hi = min(seqs), max(seqs)
        nums = list(range(lo, hi + 1))
        have = len(seqs)
        miss = (hi - lo + 1) - have
        h.append('<h3 style="color:#1a3c6e;margin:16px 0 4px;">层级 %s &nbsp; 范围 %03d~%03d &nbsp; 有 %d / 缺 %d</h3>'
                 % (level, lo, hi, have, miss))
        h.append('<table><tr>')
        for _ in range(units):
            h.append('<th>序号</th><th>完整文件名</th><th>状态</th>')
        h.append('</tr>')
        for i, n in enumerate(nums):
            if i % units == 0:
                h.append('<tr>')
            h.append('<td class="seq">%03d</td>' % n)
            if n in occ[level]:
                names = '<br>'.join(_esc(x) for x in sorted(occ[level][n]))
                h.append('<td class="name">%s</td>' % names)
                h.append('<td class="have">有</td>')
            else:
                h.append('<td class="name"></td><td class="miss">缺</td>')
            if i % units == units - 1:
                h.append('</tr>')
        if len(nums) % units != 0:
            for _ in range(units - (len(nums) % units)):
                h.append('<td></td><td></td><td></td>')
            h.append('</tr>')
        h.append('</table>')
    h.append('</body></html>')
    return '\n'.join(h)


def build_xlsx(occ, units, out_path):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except Exception:
        return False, "未安装 openpyxl（pip install openpyxl 后可生成 xlsx）"
    SUB = 3
    COLS = units * SUB
    thin = Side(style='thin', color='D4D9E2')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    have_fill = PatternFill('solid', fgColor='EAF7EF')
    miss_fill = PatternFill('solid', fgColor='FDECEC')
    hdr_fill = PatternFill('solid', fgColor='1A3C6E')
    hdr_font = Font(color='FFFFFF', bold=True)
    have_font = Font(color='1A7A3C', bold=True)
    miss_font = Font(color='B00020', bold=True)
    seq_font = Font(name='Consolas', bold=True)
    center = Alignment(horizontal='center', vertical='center')
    leftwrap = Alignment(horizontal='left', vertical='top', wrap_text=True)
    wb = Workbook()
    for level in sorted(occ.keys()):
        seqs = sorted(occ[level].keys())
        lo, hi = min(seqs), max(seqs)
        nums = list(range(lo, hi + 1))
        ws = wb.create_sheet(title='层级 ' + level)
        ws.append(['层级 %s  范围 %03d~%03d  有 %d / 缺 %d'
                   % (level, lo, hi, len(seqs), (hi - lo + 1) - len(seqs))])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=COLS)
        hdr = []
        for _ in range(units):
            hdr += ['序号', '完整文件名', '状态']
        ws.append(hdr)
        for c in range(1, COLS + 1):
            cell = ws.cell(row=2, column=c)
            cell.fill = hdr_fill
            cell.font = hdr_font
            cell.alignment = center
            cell.border = border
        for i, n in enumerate(nums):
            r = 3 + i // units
            u = i % units
            cseq, cname, cst = 1 + u * SUB, 2 + u * SUB, 3 + u * SUB
            a = ws.cell(row=r, column=cseq, value='%03d' % n)
            a.font = seq_font
            a.alignment = center
            a.border = border
            if n in occ[level]:
                b = ws.cell(row=r, column=cname, value='\n'.join(sorted(occ[level][n])))
                b.alignment = leftwrap
                b.border = border
                st = ws.cell(row=r, column=cst, value='有')
                st.fill = have_fill
                st.font = have_font
            else:
                ws.cell(row=r, column=cname, value='').border = border
                st = ws.cell(row=r, column=cst, value='缺')
                st.fill = miss_fill
                st.font = miss_font
            st.alignment = center
            st.border = border
        for u in range(units):
            ws.column_dimensions[chr(65 + u * SUB)].width = 7
            ws.column_dimensions[chr(65 + u * SUB + 1)].width = 30
            ws.column_dimensions[chr(65 + u * SUB + 2)].width = 6
        ws.freeze_panes = 'A3'
    if 'Sheet' in wb.sheetnames:
        del wb['Sheet']
    wb.save(out_path)
    return True, out_path


def main():
    ap = argparse.ArgumentParser(description="生成序号矩阵表（序号|完整文件名|状态）")
    ap.add_argument("--dir", required=True, help="目标目录")
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "serial_matrix.html"),
                    help="HTML 输出路径（默认当前目录 serial_matrix.html）")
    ap.add_argument("--xlsx", default=None, help="XLSX 输出路径（可选；需 openpyxl）")
    ap.add_argument("--units", type=int, default=3, help="每行单元数（默认3=9列）")
    ap.add_argument("--recursive", action="store_true", help="递归子目录")
    args = ap.parse_args()

    if args.units < 1:
        args.units = 1
    occ = collect(args.dir, args.recursive)
    if not occ:
        print("[提示] 未在该目录发现带项目代号的 sldprt/sldasm/slddrw 文件。")
    html_txt = build_html(occ, args.units)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(html_txt)
    print(f"HTML -> {args.out}  (层级: {', '.join(sorted(occ.keys())) or '无'})")

    if args.xlsx:
        ok, msg = build_xlsx(occ, args.units, args.xlsx)
        print(("XLSX -> " + msg) if ok else ("XLSX 跳过: " + msg))


if __name__ == "__main__":
    main()
