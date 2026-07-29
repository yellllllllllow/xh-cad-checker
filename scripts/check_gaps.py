# -*- coding: utf-8 -*-
"""
xh-cad-checker · check_gaps.py
3D 源齐套检查 + 真缺口判定（合并模型）

模型：
  - sldprt + sldasm 合并为「3D 源」一类
  - stp / step 合并为「STP 导出 3D」一类
  - 检查交付物 slddrw / stp / pdf / dwg 是否齐全
  - 对「不齐全」的 3D 件，按【名字】判定是否为真缺口（不是看固定前缀）：
        带 钣金/机加工 标记 或 编号 B=01(钣金)/B=02(机加工) -> 自制加工件，缺失即真缺口
        装配体(sldasm 或名字像 装配/台/线/组件)            -> 本不需零件加工图（非缺口）
        名字能读出参数(尺寸类)或含标准件词汇(垫圈/型材/TXCJ…) -> 标准件/外购（非缺口）
        以上都不沾边                                      -> 待确认（人工判断）

用法：
  python check_gaps.py --dir "D:/工作资料/智能实验仓/03 皮带线" --out report.html
  python check_gaps.py --dir <目录> --proj XH042601 --recursive
仅顶层（默认），--recursive 可递归子目录。全程只读。
"""
import os, re, html, datetime, argparse

CLASS_MAP = {"sldprt": "3D源", "sldasm": "3D源", "slddrw": "工程图",
             "stp": "STP", "step": "STP", "pdf": "PDF", "dwg": "DWG"}
DEL = ["工程图", "STP", "PDF", "DWG"]
SOURCE = "3D源"

# 自制加工件标记（带这些 = 应按编号出图，缺失即真缺口）
FAB = ["钣金", "机加工", "机加", "焊接", "冲压", "cnc", "加工"]
# 装配体名称暗示（仅强信号；sldasm 文件类型本身即装配体）
ASSEMBLY_KW = ["装配", "总成", "组件", "机构", "模块", "工作站"]
# 标准件/外购 名称词汇（从名字即可知参数或品类）
STD_VOCAB = ["垫圈", "套筒", "同步带", "皮带", "传送带", "型材", "铝型材", "TXCJ", "硅胶",
             "海绵", "PE板", "笼盒", "轴承", "螺栓", "螺钉", "螺母", "销", "键", "法兰",
             "弹簧", "电机", "气缸", "传感器", "链条", "齿轮", "导轨", "滑块", "辊",
             "密封圈", "o型", "o形", "卡簧", "管", "接头", "光轴", "滚筒", "同步轮", "张紧"]


def classify(base, is_asm, proj):
    # 1) 自制加工件（应出图）：钣金/机加工 标记，或编号 B=01(钣金)/02(机加工)
    low = base.lower()
    for k in FAB:
        if k.lower() in low:
            return "自制件(应出图)"
    pref = re.escape(proj) if proj else r"XH\d+"
    if re.search(rf"{pref}\.\d{{2}}\.(0[12])-", base):
        return "自制件(应出图)"
    # 2) 装配体
    if is_asm:
        return "装配体"
    for k in ASSEMBLY_KW:
        if k in base:
            return "装配体"
    # 3) 标准件/外购：名字直接带尺寸参数 -> 可读数即标准件
    if re.search(r"\d+\s*[xX×]\s*\d+", base) or re.search(r"\d+\s*-\s*\d+", base) \
       or re.search(r"外径|内径|直径|Φ|phi", base, re.I) \
       or re.search(r"\d+(\.\d+)?\s*mm", base, re.I):
        return "标准件/外购"
    # 4) 标准词汇
    for k in STD_VOCAB:
        if k in base:
            return "标准件/外购"
    # 5) 待确认
    return "待确认"


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="待检查目录")
    ap.add_argument("--out", default=os.path.join(os.getcwd(), "xh_cad_gap_report.html"),
                    help="输出 HTML 路径（默认当前目录 xh_cad_gap_report.html）")
    ap.add_argument("--proj", default="XH042601", help="项目代号前缀，用于识别自制件")
    ap.add_argument("--recursive", action="store_true", help="递归子目录")
    args = ap.parse_args()

    items = scan(args.dir, args.recursive)
    parts = {}          # base -> set(classes)
    srctype = {}        # base -> sldprt/sldasm/both
    ext_count = {}
    for full in items:
        fn = os.path.basename(full)
        if "." not in fn:
            continue
        base, ext = fn.rsplit(".", 1); ext = ext.lower()
        ext_count[ext] = ext_count.get(ext, 0) + 1
        if ext in CLASS_MAP:
            parts.setdefault(base, set()).add(CLASS_MAP[ext])
            if CLASS_MAP[ext] == SOURCE:
                cur = srctype.get(base, "")
                srctype[base] = ext if cur == "" else ("both" if cur != ext else cur)

    # 3D 件齐套分析
    rows = []                       # (base, srctype, [工程图,STP,PDF,DWG], missing, cat)
    miss_count = {d: 0 for d in DEL}
    complete = 0
    for base, cls in parts.items():
        if SOURCE not in cls:
            continue
        st = [d in cls for d in DEL]
        missing = [DEL[i] for i, ok in enumerate(st) if not ok]
        for d in missing:
            miss_count[d] += 1
        is_asm = srctype.get(base) == "sldasm"
        cat = classify(base, is_asm, args.proj)
        if not missing:
            complete += 1
        rows.append((base, srctype.get(base, "?"), st, missing, cat))

    total_src = len(rows)
    total_files = len(items)
    rows.sort(key=lambda r: (-len(r[3]), r[4] != "装配体", r[4] != "标准件/外购", r[0]))

    # 仅在「不齐全件」中统计分类与真缺口
    incomplete = [r for r in rows if r[3]]
    from collections import Counter
    catcnt = Counter(r[4] for r in incomplete)
    asm = catcnt.get("装配体", 0)
    std = catcnt.get("标准件/外购", 0)
    selfm = catcnt.get("自制件(应出图)", 0)
    other = catcnt.get("待确认", 0)
    real_gap = selfm + other

    if real_gap == 0:
        verdict = "逻辑完全成立 ✅：所有不齐全件均为装配体或标准件/外购，无真缺口。"
    else:
        verdict = f"存在 {real_gap} 个例外需人工确认（自制件应出图 {selfm} + 待确认 {other}）。"

    mx = max(miss_count.values()) if total_src else 0
    worst = "、".join([k for k, v in miss_count.items() if v == mx]) if mx else "-"
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    scope = "递归全目录" if args.recursive else "仅顶层（忽略子文件夹）"

    def esc(s): return html.escape(str(s))
    def chk(ok): return '<span class="ok">✓</span>' if ok else '<span class="no">✗</span>'

    # 齐套明细表
    detail = ""
    for base, st0, st, miss, cat in rows:
        miss_txt = "、".join(miss) if miss else "齐全"
        rc = "" if miss else "row-ok"
        detail += (f'<tr class="{rc}"><td class="bk">{esc(base)}</td><td>{esc(st0)}</td>'
                   f'<td>{chk(st[0])}</td><td>{chk(st[1])}</td><td>{chk(st[2])}</td>'
                   f'<td>{chk(st[3])}</td><td class="cnt">{len(miss)}</td>'
                   f'<td>{esc(cat)}</td><td class="miss">{esc(miss_txt)}</td></tr>')

    # 分类表（仅不齐全件）
    def block(cat, color):
        rs = [r for r in rows if r[4] == cat and r[3]]
        if not rs:
            return ""
        h = f'<div class="cat" style="border-left:4px solid {color}"><b>{esc(cat)}（{len(rs)} 个）</b></div>'
        b = '<table><tr><th>图号/名称</th><th>源</th><th>工程图</th><th>STP</th><th>PDF</th><th>DWG</th><th>缺失项</th></tr>'
        for base, st0, st, miss, _ in rs:
            b += (f'<tr><td class="bk">{esc(base)}</td><td>{esc(st0)}</td>'
                  f'<td>{chk(st[0])}</td><td>{chk(st[1])}</td><td>{chk(st[2])}</td><td>{chk(st[3])}</td>'
                  f'<td class="miss">{esc("、".join(miss))}</td></tr>')
        return h + b + "</table>"

    ext_rows = ""
    for e in ["sldprt", "sldasm", "slddrw", "stp", "step", "pdf", "dwg"]:
        if e in ext_count:
            ext_rows += f'<tr><td>{e}</td><td>{ext_count[e]}</td></tr>'

    doc = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>3D 源齐套 + 真缺口判定</title>
<style>
*{{box-sizing:border-box}}
body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;margin:0;background:#f5f6f8;color:#1f2329;padding:28px}}
.wrap{{max-width:1180px;margin:0 auto}}
h1{{font-size:22px;margin:0 0 4px}}
.sub{{color:#6b7280;font-size:13px;margin-bottom:18px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}}
.card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px;flex:1;min-width:110px}}
.card .n{{font-size:23px;font-weight:700}}.card .l{{font-size:12px;color:#6b7280;margin-top:2px}}
.card.bad{{border-color:#ef4444;background:#fef2f2}}
.callout{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:13px 18px;font-size:14px;margin-bottom:14px}}
.callout b{{color:#1d4ed8}}
.cat{{margin:16px 0 6px;font-size:15px}}
table{{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:8px;font-size:13px}}
th,td{{padding:7px 10px;border-bottom:1px solid #eef0f2;text-align:left}}
th{{background:#f0f2f5;font-weight:600}}
td.bk{{font-family:Consolas,Menlo,monospace;font-size:12px}}
td.cnt{{text-align:center;font-weight:700}}
td.miss{{color:#b91c1c}}
.row-ok{{background:#f0fdf4}}
.ok{{color:#16a34a;font-weight:700}}.no{{color:#dc2626;font-weight:700}}
.section{{font-size:16px;font-weight:700;margin:22px 0 10px;border-left:4px solid #2563eb;padding-left:10px}}
.note{{color:#6b7280;font-size:12px;margin-top:22px}}
</style></head><body><div class="wrap">
<h1>3D 源齐套检查 + 真缺口判定</h1>
<div class="sub">目录：{esc(args.dir)}　|　{esc(scope)}　|　项目代号：{esc(args.proj)}　|　{gen}</div>

<div class="cards">
  <div class="card"><div class="n">{total_files}</div><div class="l">文件总数</div></div>
  <div class="card"><div class="n">{total_src}</div><div class="l">3D 源件数</div></div>
  <div class="card"><div class="n" style="color:#16a34a">{complete}</div><div class="l">四项齐全</div></div>
  <div class="card"><div class="n">{total_src-complete}</div><div class="l">不齐全</div></div>
  <div class="card bad"><div class="n">{real_gap}</div><div class="l">需关注<br>(应出图+待确认)</div></div>
</div>

<div class="callout"><b>哪个类交付物缺得最多？</b><br>
  工程图(slddrw) 缺 <b>{miss_count['工程图']}</b>　|　STP 缺 <b>{miss_count['STP']}</b>　|
  PDF 缺 <b>{miss_count['PDF']}</b>　|　DWG 缺 <b>{miss_count['DWG']}</b>。缺失最多：<b>{esc(worst)}</b>。</div>

<div class="callout"><b>真缺口判定：{esc(verdict)}</b><br>
  不齐全件 {total_src-complete} 个中：装配体 <b>{asm}</b>、标准件/外购 <b>{std}</b>（合计 {asm+std}，占 {round((asm+std)/max(total_src-complete,1)*100)}%，本不需加工图纸）；
  自制件(应出图) <b style="color:#dc2626">{selfm}</b>、待确认 <b style="color:#d97706">{other}</b>。</div>

<div class="section">一、扩展名计数</div>
<table><tr><th>扩展名</th><th>数量</th></tr>{ext_rows}</table>

<div class="section">二、3D 件齐套明细（按缺失数排序）</div>
<table><tr><th>图号/名称</th><th>源</th><th>工程图</th><th>STP</th><th>PDF</th><th>DWG</th><th>缺项数</th><th>分类</th><th>缺失项</th></tr>{detail}</table>

<div class="section">三、分类明细</div>
{block("装配体","#2563eb") or '<p style="color:#6b7280">无</p>'}
{block("标准件/外购","#0891b2") or '<p style="color:#6b7280">无</p>'}
{block("自制件(应出图)","#dc2626") or '<p style="color:#16a34a">无 —— 假设完全成立 ✅</p>'}
{block("待确认","#d97706") or '<p style="color:#6b7280">无</p>'}

<p class="note">说明：① sldprt+sldasm=3D源，stp/step=STP 导出3D。② 装配体=不需零件加工图；标准件/外购（名称命中关键词或尺寸件，或未带项目代号）=不需自制图纸；自制件=含项目代号（按编号规则应出图）=真缺口。③ 仅读取，未改动源目录。</p>
</div></body></html>"""

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"文件总数: {total_files}  3D源件数: {total_src}")
    print(f"四项齐全: {complete}  不齐全: {total_src-complete}")
    print(f"缺失: 工程图{miss_count['工程图']} STP{miss_count['STP']} PDF{miss_count['PDF']} DWG{miss_count['DWG']}")
    print(f"分类: 装配体{asm} 标准件/外购{std} 自制件(应出图){selfm} 待确认{other}")
    print(f"真缺口: {real_gap}")
    print(f"报告: {args.out}")


if __name__ == "__main__":
    main()
