---
name: xh-cad-checker
description: This skill should be used when auditing CAD archive completeness for a SolidWorks (or similar CAD) project directory — checking which engineering drawings are missing their derived deliverables (STEP/STP, PDF, DWG), detecting drawings that exist without a 3D source, parsing part-number structure into A(assy/component) / B(process type) / C(serial) to find numbering gaps and duplicate part numbers, and producing an HTML report. Triggers include requests like "检查工程图归档缺什么", "哪些图缺 stp/pdf/dwg", "钣金件机加工件排到哪了", "查图号断号/重号", "出一份归档完整性报告".
description_zh: 【私有】CAD 归档完整性检查：只读扫描目录，检测 sldprt/sldasm+slddrw+step/pdf/dwg 格式齐套、仅有工程图无3D源、图样编号(A部件/B加工/C流水号)断号与重号，输出 HTML 报告。
agent_created: true
---

# CAD 归档完整性检查 (xh-cad-checker)

## Overview

对某个 CAD 项目目录做**只读**归档体检：扫描所有文件，按图号（无扩展名基础名）交叉比对，找出缺失的派生交付物（`.slddrw` 工程图 / `.step` 3D 中性格式 / `.pdf` 图纸 / `.dwg` CAD 图纸），识别「仅有工程图但无 3D 源」的异常，并按图样编号规则解析 `A(部件) / B(加工类型) / C(流水号)`，输出断号段与重号清单，最终生成一份自包含 HTML 报告。

适用领域：机械设计、钣金/机加工零件归档、BOM 前检查、外发图纸齐套性确认。

## Principles

- **只读**：绝不对源目录做任何修改、删除、重命名。仅生成一份报告文件（默认写到目标目录下或用户指定路径）。
- **锁文件忽略**：自动跳过 SolidWorks 锁文件 `~$*`（SolidWorks 运行时会留下），避免误判。
- **图号即基础名**：以「文件名去掉扩展名」作为图号键，同一图号的多种格式（prt/asm/drw/step/pdf/dwg）应共存。

## Quick Start

```bash
# 基础体检（输出报告到目标目录）
python scripts/check_archive.py --dir "D:/工作资料/智能实验仓/03 皮带线"

# 指定报告输出位置、标注产品代号前缀
python scripts/check_archive.py --dir <目录> --out report.html --proj XH042601

# 递归扫描子目录
python scripts/check_archive.py --dir <目录> --recursive

# 只做格式完整性检查，不做 A/B/C 编号解析
python scripts/check_archive.py --dir <目录> --no-abcc
```

> 运行环境：使用受管 Python（如 `C:/Users/H/.workbuddy/binaries/python/versions/3.13.12/python.exe`）。脚本仅依赖标准库，无第三方依赖。

## What the report contains

1. **总体指标卡**：文件总数、总图号、五件齐全率、缺工程图/STEP/PDF/DWG 数量、仅有图无源数量。
2. **文件类型分布**：sldprt / sldasm / slddrw / step / pdf / dwg 各自计数。
3. **异常：仅有工程图无 3D 源**：列出这些图号（源文件可能漏存、改名或移动）。
4. **缺工程图清单**：有 3D 源但未出 `.slddrw` 的全部图号。
5. **A × B 矩阵**：按图样编号解析后，各「部件类型 × 加工类型」的零件数量分布。
6. **断号分析**：每个 (A,B) 组内 `1..max` 之间缺失的流水号 C，用于判断漏缺或预留空位。
7. **重号检测**：同一 (A,B,C,子号) 出现多个不同零件名（父子件不算）。
8. **未识别图号**：不符合标准编号模式的总成/外购件，需另行确认。

## Part-number parsing

默认解析规则：`<前缀>.<A 项 2位>.<B 项 2位>-<C 流水号>`，例如 `XH042601.03.01-001`。
A/B 项名称默认映射见 `references/coding_rules.md`（机械设计常见：01-06 部件类型、01-07 加工类型）。

不同项目可覆盖映射：

```bash
python scripts/check_archive.py --dir <目录> \
  --a-map '{"01":"组件A","02":"组件B"}' \
  --b-map '{"01":"钣金","02":"机加"}'
```

## Workflow

1. 与用户确认待扫描目录（机械设计场景多在项目「归档/出图」目录）。
2. 运行 `scripts/check_archive.py`，先做一次基础体检；如需编号分析，保留 A/B/C 解析（默认开启）。
3. 用 `present_files` 打开生成的 HTML 报告给用户查看。
4. 若用户指出某批缺失需要补齐，可口头/列表反馈，但**不要自动改动源目录**——补图、转 STEP/PDF/DWG 属于出图操作，应在 SolidWorks 中由用户执行，或经用户明确授权后再做。
5. 编号分析若发现大量断号/重号，先与用户确认是「预留空位」还是「真实漏缺」，再给建议。

## Notes & edge cases

- 子装配多级流水号（`…-001-002`）按父/子关系处理，**不会**误判为重号。
- 总装配（如 `03-01 升降交接台`）、未编号外购件（如 `TXCJ-H6-2040-L815`）归入「未识别」，完整性检查仍照常统计其缺格式情况。
- SolidWorks 正在运行时目录会有 `~$*` 锁文件，脚本自动忽略；建议在 SolidWorks 关闭或保存后扫描，结果更稳定。
- 报告默认写到 `--dir` 下 `archive_check_report.html`；为避免污染项目归档目录，可用 `--out` 指定到临时/工作区路径。
