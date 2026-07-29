#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cad-archive-checker — 工程图归档完整性检查脚本

功能：
  1. 扫描某目录下所有 CAD 文件（排除 SolidWorks 锁文件 ~$*）
  2. 按扩展名分类：sldprt / sldasm / slddrw / step(stp,iges,igs) / pdf / dwg(dxf)
  3. 以"图号（无扩展名基础名）"为键做交叉比对：
     - 缺工程图 slddrw
     - 缺 3D 中性格式 step
     - 缺 PDF
     - 缺 DWG
     - 异常：仅有 slddrw 但无 3D 源（sldprt/sldasm）
  4. （可选）按图样编号规则解析 A(部件) / B(加工类型) / C(流水号)，
     输出 A×B 矩阵、各流水号段的断号（缺失编号）、重号检测
  5. 生成一份自包含 HTML 报告

用法：
  python check_archive.py --dir "D:/工作资料/智能实验仓/03 皮带线"
  python check_archive.py --dir <目录> --out report.html [--no-abcc]
  python check_archive.py --dir <目录> --proj XH042601 --recursive

注意：
  - 严格只读，不修改、不删除任何源文件
  - 图样编号默认规则（可通过 --proj / --a-map / --b-map 覆盖）：
      <前缀>.<A 项 2 位>.<B 项 2 位>-<C 流水号>
    例如 XH042601.03.01-001  => A=03(柜体) B=01(钣金) C=001
"""
import os
import re
import argparse
import html
import datetime
from collections import defaultdict, OrderedDict
from pathlib import Path

# ---------- 默认 A / B 项名称映射（机械设计常见）----------
DEFAULT_A_MAP = {
    "01": "小车组件", "02": "主控门组件", "03": "柜体组件",
    "04": "货道组件", "05": "层架组件", "06": "玻璃门组件",
}
DEFAULT_B_MAP = {
    "01": "钣金件", "02": "机加工件", "03": "塑胶件",
    "04": "电气件", "05": "标准件", "06": "外购定制件", "07": "其它",
}

# 图样编号正则：<前缀>.<A 2位>.<B 2位>[-<C 流水号>][-<子流水号>]
CODE_RE = re.compile(
    r'^(?P<prefix>[A-Za-z0-9]+)\.(?P<A>\d{2})\.(?P<B>\d{2})'
    r'(?:-(?P<C>\d{1,4}))?(?:-(?P<C2>\d{1,4}))?'
)

# STEP / DWG 系列别名
STEP_EXTS = {"step", "stp", "iges", "igs"}
DWG_EXTS = {"dwg", "dxf"}


def scan_files(directory, recursive):
    """返回 [(base, ext, abs_path), ...]，排除 ~$ 锁文件。"""
    items = []
    if recursive:
        it = Path(directory).rglob("*")
    else:
        it = Path(directory).glob("*")
    for p in it:
        if not p.is_file():
            continue
        name = p.name
        if name.startswith("~$"):           # SolidWorks 锁文件
            continue
        if name.startswith("."):
            continue
        base, ext = p.stem, p.suffix[1:].lower() if p.suffix else ""
        items.append((base, ext, str(p)))
    return items


def classify(items):
    exts = defaultdict(set)      # ext -> set(base)
    base_ext_map = defaultdict(dict)  # base -> {ext: path}
    for base, ext, ap in items:
        exts[ext].add(base)
        base_ext_map[base][ext] = ap

    # 合并 step / dwg 系列
    step_set = set()
    for e in STEP_EXTS:
        step_set |= exts.get(e, set())
    dwg_set = set()
    for e in DWG_EXTS:
        dwg_set |= exts.get(e, set())

    out = {
        "sldprt": exts.get("sldprt", set()),
        "sldasm": exts.get("sldasm", set()),
        "slddrw": exts.get("slddrw", set()),
        "step": step_set,
        "pdf": exts.get("pdf", set()),
        "dwg": dwg_set,
    }
    return out, base_ext_map


def analyze(out, base_ext_map):
    src = out["sldprt"] | out["sldasm"]
    entities = src | out["slddrw"]

    no_src = sorted(out["slddrw"] - src)          # 仅有图无源
    no_drw = sorted(src - out["slddrw"])          # 有源无图

    miss = {
        "step": sorted(entities - out["step"]),
        "pdf": sorted(entities - out["pdf"]),
        "dwg": sorted(entities - out["dwg"]),
        "slddrw": no_drw,
        "src": no_src,
    }
    ok = sum(1 for e in entities
             if e in src and e in out["slddrw"] and e in out["step"]
             and e in out["pdf"] and e in out["dwg"])
    return src, entities, ok, miss


def parse_code(out, base_ext_map):
    """解析 A/B/C，返回 groups[(A,B)]=list of (C, C2, base)，以及未识别列表。"""
    groups = defaultdict(list)
    unparsed = []
    kind_of = {}
    for base, ext in base_ext_map.items():
        if "sldprt" in ext:
            kind = "sldprt"
        elif "sldasm" in ext:
            kind = "sldasm"
        elif "slddrw" in ext:
            kind = "slddrw"
        else:
            kind = None
        if kind:
            kind_of[base] = kind

    parsed_bases = set()
    for base in (out["sldprt"] | out["sldasm"] | out["slddrw"]):
        m = CODE_RE.match(base)
        if not m:
            unparsed.append(base)
            continue
        A, B = m.group("A"), m.group("B")
        C = int(m.group("C")) if m.group("C") else 0
        C2 = int(m.group("C2")) if m.group("C2") else 0
        kind = kind_of.get(base, "sldprt")
        groups[(A, B)].append((C, C2, base, kind))
        parsed_bases.add(base)
    return groups, unparsed


def matrix_and_breaks(groups, a_map, b_map):
    """返回 A×B 计数矩阵，以及每个 (A,B) 的断号段。"""
    matrix = defaultdict(lambda: defaultdict(int))
    breaks = OrderedDict()
    for (A, B), items in groups.items():
        matrix[A][B] = len(items)
        cs = sorted(set(c[0] for c in items if c[0] > 0))
        if cs:
            max_c = max(cs)
            missing = sorted(set(range(1, max_c + 1)) - set(cs))
            if missing:
                # 合并连续断号为区间
                segs = []
                s = missing[0]; prev = s
                for v in missing[1:]:
                    if v == prev + 1:
                        prev = v
                    else:
                        segs.append((s, prev)); s = v; prev = v
                segs.append((s, prev))
                seg_txt = ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in segs)
                breaks[(A, B)] = (max_c, len(missing), seg_txt)
    return matrix, breaks


def detect_dup_codes(groups, base_ext_map):
    """检测图号重号：同一 (A, B, C, 子号) 出现多个不同零件名才算重号。

    注意：父装配 (C, 子号=0) 与子件 (C, 子号=1) 属于正常父子关系，不视为重号。
    """
    dups = []
    for (A, B), items in groups.items():
        by_cc = defaultdict(list)
        for C, C2, base, kind in items:
            by_cc[(C, C2)].append(base)
        for (C, C2), lst in by_cc.items():
            if len(lst) > 1:
                names = []
                for base in lst:
                    # 取 base 中 C 段之后的部分作为零件名
                    m = re.search(r'-(?:\d{1,4})(?:-\d{1,4})?\s+(.*)$', base)
                    nm = m.group(1) if m else base
                    names.append(nm)
                dups.append((A, B, C, names))
    return dups


# ---------- HTML 报告 ----------
def build_html(directory, counts, ok, miss, src, entities,
               matrix, breaks, dups, unparsed, a_map, b_map, proj_prefix):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    pct = ok / len(entities) * 100 if entities else 0

    def tag(b):
        return '<span class="y">有</span>' if b else '<span class="n">缺</span>'

    # 异常：仅有图无源
    no_src_rows = "".join(
        f"<tr><td class='mono'>{html.escape(x)}</td></tr>" for x in miss["src"]) or "<tr><td>无</td></tr>"

    # 缺工程图清单
    no_drw_rows = "".join(
        f"<tr><td class='mono'>{html.escape(x)}</td></tr>" for x in miss["slddrw"])

    # A×B 矩阵
    b_keys = [str(i).zfill(2) for i in range(1, 8)]
    b_head = "".join(f"<th>B={k} {html.escape(b_map.get(k,''))}</th>" for k in b_keys)
    a_rows = ""
    totals_b = defaultdict(int)
    for A in sorted(matrix.keys(), key=lambda x: int(x)):
        cells = ""
        row_total = 0
        for B in b_keys:
            c = matrix[A].get(B, 0)
            cells += f"<td>{c}</td>"
            row_total += c
            totals_b[B] += c
        a_rows += (f"<tr><td><b>{A}</b> {html.escape(a_map.get(A,''))}</td>"
                   f"{cells}<td><b>{row_total}</b></td></tr>")
    b_totals = "".join(f"<td>{totals_b[k]}</td>" for k in b_keys)
    grand = sum(totals_b.values())
    b_head += "<th>合计</th>"

    # 断号分析
    break_rows = ""
    for (A, B), (max_c, n, seg) in breaks.items():
        break_rows += (f"<tr><td class='mono'>{A} {html.escape(a_map.get(A,''))}</td>"
                       f"<td class='mono'>B={B} {html.escape(b_map.get(B,''))}</td>"
                       f"<td>{max_c}</td><td>{n}</td>"
                       f"<td class='mono'>{html.escape(seg)}</td></tr>")
    if not break_rows:
        break_rows = "<tr><td colspan='5'>无断号</td></tr>"

    # 重号
    dup_rows = ""
    for A, B, C, names in dups:
        dup_rows += (f"<tr><td class='mono'>{A}.{B}-{C}</td>"
                     f"<td>{html.escape(' / '.join(names))}</td></tr>")
    if not dup_rows:
        dup_rows = "<tr><td colspan='2'>未检测到重号</td></tr>"

    # 未识别
    unparsed_rows = "".join(
        f"<tr><td class='mono'>{html.escape(x)}</td></tr>" for x in unparsed) or "<tr><td>无</td></tr>"

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<title>工程图归档完整性检查报告</title>
<style>
:root{{--bg:#f5f6f8;--panel:#fff;--bd:#e1e4ea;--tx:#1f2329;--mut:#6b7280;--ac:#2b6cff;--ok:#1f9d55;--wn:#d97706;--er:#dc2626;}}
*{{box-sizing:border-box;}}
body{{margin:0;padding:26px 30px;font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--tx);line-height:1.55;font-size:14px;}}
h1{{font-size:21px;margin:0 0 4px;}} h2{{font-size:15px;margin:26px 0 10px;padding-bottom:7px;border-bottom:2px solid var(--ac);}}
.sub{{color:var(--mut);margin:0 0 18px;font-size:13px;}}
.panel{{background:var(--panel);border:1px solid var(--bd);border-radius:8px;padding:15px 18px;margin-bottom:14px;box-shadow:0 1px 2px rgba(0,0,0,.03);}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:11px;}}
.card{{background:#f0f3f9;padding:13px;border-radius:6px;text-align:center;}}
.card .num{{font-size:21px;font-weight:700;color:var(--ac);}} .card .lbl{{font-size:12px;color:var(--mut);}}
.card.w .num{{color:var(--wn);}} .card.e .num{{color:var(--er);}} .card.ok .num{{color:var(--ok);}}
table{{border-collapse:collapse;width:100%;font-size:13px;}} th,td{{padding:6px 9px;text-align:left;border-bottom:1px solid var(--bd);}}
th{{background:#f0f3f9;font-weight:600;}} tr:hover td{{background:#f8f9fb;}}
.mono{{font-family:Consolas,"Courier New",monospace;font-size:12.5px;}}
.y{{background:#dcfce7;color:#166534;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600;}}
.n{{background:#fee2e2;color:#991b1b;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600;}}
.alert{{border-left:4px solid var(--er);background:#fef2f2;padding:11px 15px;margin:10px 0;border-radius:4px;}}
.alert.w{{border-color:var(--wn);background:#fffbeb;}}
pre{{background:#1f2329;color:#e4e7ed;padding:13px 15px;border-radius:6px;overflow:auto;max-height:320px;font-size:12px;}}
.foot{{margin-top:26px;padding-top:11px;border-top:1px solid var(--bd);color:var(--mut);font-size:12px;}}
</style></head><body>
<h1>工程图归档完整性检查报告</h1>
<p class="sub">目录：<span class="mono">{html.escape(directory)}</span>　·　生成：{now}　·　已忽略 SolidWorks ~$ 锁文件</p>

<div class="panel"><div class="grid">
<div class="card"><div class="num">{counts['total']}</div><div class="lbl">文件总数</div></div>
<div class="card"><div class="num">{len(entities)}</div><div class="lbl">总图号</div></div>
<div class="card ok"><div class="num">{ok}</div><div class="lbl">五件齐全 ({pct:.0f}%)</div></div>
<div class="card w"><div class="num">{len(miss['slddrw'])}</div><div class="lbl">缺工程图</div></div>
<div class="card w"><div class="num">{len(miss['step'])}</div><div class="lbl">缺 STEP</div></div>
<div class="card w"><div class="num">{len(miss['pdf'])}</div><div class="lbl">缺 PDF</div></div>
<div class="card w"><div class="num">{len(miss['dwg'])}</div><div class="lbl">缺 DWG</div></div>
<div class="card e"><div class="num">{len(miss['src'])}</div><div class="lbl">仅有图无源</div></div>
</div></div>

<h2>一 · 文件类型分布</h2>
<div class="panel"><table>
<tr><th>扩展名</th><th>含义</th><th>数量</th></tr>
<tr><td class="mono">.sldprt</td><td>SolidWorks 零件源</td><td>{counts['sldprt']}</td></tr>
<tr><td class="mono">.sldasm</td><td>SolidWorks 装配源</td><td>{counts['sldasm']}</td></tr>
<tr><td class="mono">.slddrw</td><td>SolidWorks 工程图</td><td>{counts['slddrw']}</td></tr>
<tr><td class="mono">.step/.stp/.igs</td><td>3D 中性格式</td><td>{counts['step']}</td></tr>
<tr><td class="mono">.pdf</td><td>2D 图纸</td><td>{counts['pdf']}</td></tr>
<tr><td class="mono">.dwg/.dxf</td><td>CAD 图纸</td><td>{counts['dwg']}</td></tr>
</table></div>

<h2>二 · 异常：仅有工程图但无 3D 源（{len(miss['src'])} 个）</h2>
<div class="alert">以下图号仅有 <code>.slddrw</code> 工程图，但找不到对应 <code>.sldprt/.sldasm</code> 源 —— 极可能是源文件漏存、改名或移动。</div>
<div class="panel"><table><tr><th>图号</th></tr>{no_src_rows}</table></div>

<h2>三 · 缺工程图 .slddrw 清单（{len(miss['slddrw'])} 个）</h2>
<div class="panel"><pre>{html.escape(chr(10).join(miss['slddrw']))}</pre></div>

<h2>四 · A × B 矩阵（按图样编号规则解析）</h2>
<p class="sub">编号规则：&lt;前缀&gt;.<b>A 项</b>(部件，2位).<b>B 项</b>(加工类型，2位)-C(流水号)　前缀参考：{html.escape(proj_prefix or '自动')}</p>
<div class="panel"><table>
<tr><th>A 项(部件)</th>{b_head}</tr>
{a_rows}
<tr><td><b>合计</b></td>{b_totals}<td><b>{grand}</b></td></tr>
</table></div>

<h2>五 · 断号分析（各 A·B 组内缺失的流水号 C）</h2>
<div class="panel"><table>
<tr><th>A 项</th><th>B 项</th><th>最大C</th><th>断号数</th><th>断号段</th></tr>
{break_rows}
</table></div>

<h2>六 · 图号重号检测（{len(dups)} 处）</h2>
<div class="panel"><table><tr><th>图号</th><th>重复零件名</th></tr>{dup_rows}</table></div>

<h2>七 · 未识别为标准编号的图号（{len(unparsed)} 个）</h2>
<p class="sub">这些图号不符合 &lt;前缀&gt;.AA.BB-C 模式，多为总成、外购件或未编号通用件，需另行确认。</p>
<div class="panel"><table><tr><th>图号</th></tr>{unparsed_rows}</table></div>

<div class="foot">本报告由 cad-archive-checker 自动生成 · 只读扫描，未对源目录做任何修改</div>
</body></html>"""
    return html_doc


def main():
    ap = argparse.ArgumentParser(description="CAD 工程图归档完整性检查")
    ap.add_argument("--dir", required=True, help="待扫描目录")
    ap.add_argument("--out", default=None, help="HTML 报告输出路径（默认 <dir>/archive_check_report.html）")
    ap.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    ap.add_argument("--no-abcc", action="store_true", help="跳过 A/B/C 图号解析与断号分析")
    ap.add_argument("--proj", default=None, help="产品代号前缀（如 XH042601），仅用于报告显示")
    ap.add_argument("--a-map", default=None, help="A 项名称映射 JSON，如 '{\"03\":\"柜体组件\"}'")
    ap.add_argument("--b-map", default=None, help="B 项名称映射 JSON")
    args = ap.parse_args()

    import json
    a_map = DEFAULT_A_MAP.copy()
    b_map = DEFAULT_B_MAP.copy()
    if args.a_map:
        a_map.update(json.loads(args.a_map))
    if args.b_map:
        b_map.update(json.loads(args.b_map))

    items = scan_files(args.dir, args.recursive)
    exts, base_ext_map = classify(items)
    out = {k: v for k, v in exts.items()}
    # 单独统计原始计数（含 alias 合并前）
    raw = defaultdict(int)
    for base, ext, _ in items:
        if ext in ("sldprt", "sldasm", "slddrw", "pdf"):
            raw[ext] += 1
        elif ext in STEP_EXTS:
            raw["step"] += 1
        elif ext in DWG_EXTS:
            raw["dwg"] += 1

    src, entities, ok, miss = analyze(out, base_ext_map)
    counts = {
        "total": len(items),
        "sldprt": len(out["sldprt"]),
        "sldasm": len(out["sldasm"]),
        "slddrw": len(out["slddrw"]),
        "step": len(out["step"]),
        "pdf": len(out["pdf"]),
        "dwg": len(out["dwg"]),
    }

    matrix = breaks = dups = None
    unparsed = []
    if not args.no_abcc:
        groups, unparsed = parse_code(out, base_ext_map)
        matrix, breaks = matrix_and_breaks(groups, a_map, b_map)
        dups = detect_dup_codes(groups, base_ext_map)

    report = build_html(args.dir, counts, ok, miss, src, entities,
                        matrix or {}, breaks or {}, dups or [], unparsed,
                        a_map, b_map, args.proj)

    out_path = args.out or os.path.join(args.dir, "archive_check_report.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)

    # 控制台摘要
    print("=" * 56)
    print("CAD 归档完整性检查完成")
    print("=" * 56)
    print(f"目录        : {args.dir}")
    print(f"文件总数    : {counts['total']}")
    print(f"总图号      : {len(entities)}")
    print(f"五件齐全    : {ok} ({ok/len(entities)*100:.0f}%)" if entities else "0")
    print(f"缺工程图    : {len(miss['slddrw'])}")
    print(f"缺 STEP     : {len(miss['step'])}")
    print(f"缺 PDF      : {len(miss['pdf'])}")
    print(f"缺 DWG      : {len(miss['dwg'])}")
    print(f"仅有图无源  : {len(miss['src'])}")
    if matrix is not None:
        print(f"识别 A·B 组 : {sum(len(v) for v in matrix.values())} 组")
        print(f"重号检测    : {len(dups)} 处")
    print(f"\n报告已生成  : {out_path}")


if __name__ == "__main__":
    main()
