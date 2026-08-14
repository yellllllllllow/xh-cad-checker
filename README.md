# xh-cad-checker

> WorkBuddy 用户级技能 —— CAD（SolidWorks）归档完整性检查工具。

对某个 CAD 项目目录做**只读**归档体检：扫描所有文件，按图号（无扩展名基础名）交叉比对，
找出缺失的派生交付物（`.slddrw` / `.step` / `.pdf` / `.dwg`），识别「仅有工程图却无 3D 源」的异常，
并按图样编号规则解析 `A(部件) / B(加工类型) / C(流水号)`，输出断号段与重号清单，最终生成一份自包含 HTML 报告。

---

## 一、能查什么

| 检查项 | 说明 |
|---|---|
| 格式齐套性 | 缺 `.slddrw` 工程图 / `.step` 3D 中性格式 / `.pdf` 图纸 / `.dwg` CAD 图纸 |
| 异常检测 | 仅有工程图（`.slddrw`）却找不到 3D 源（`.sldprt` / `.sldasm`）——源文件可能漏存、改名或移动 |
| 编号解析 | 按 `<前缀>.<A 部件>.<B 加工类型>-<C 流水号>` 解析，输出 A×B 矩阵、断号段、重号清单 |
| 真缺口判定（check_gaps.py） | 把 `sldprt/sldasm` 合并为 3D 源，对缺交付物的件按装配体 / 标准件 / 自制件分类，直接给出「缺失=真缺口 or 本不需出图」结论 |
| 锁文件忽略 | 自动跳过 SolidWorks 锁文件 `~$*`，避免误判 |
| 只读安全 | 全程不修改、不删除、不重命名源目录，只生成一份报告 |

适用场景：机械设计 / 钣金·机加工零件归档 / BOM 前检查 / 外发图纸齐套性确认。

---

## 二、作为 WorkBuddy 技能安装

将本仓库克隆或下载到用户级技能目录：

```bash
# Windows（Git Bash）
git clone https://github.com/yellllllllllow/xh-cad-checker.git \
  "$HOME/.workbuddy/skills/xh-cad-checker"
```

目录结构需为 `~/.workbuddy/skills/xh-cad-checker/SKILL.md`，WorkBuddy 会自动识别。
之后在对话中说「检查工程图归档缺什么」「哪些图缺 stp/pdf/dwg」「查图号断号/重号」即可触发。

---

## 三、独立使用脚本（不依赖 WorkBuddy）

```bash
# 基础体检，报告写到目录内 archive_check_report.html
python scripts/check_archive.py --dir "D:/工作资料/智能实验仓/03 皮带线"

# 指定报告输出位置、标注产品代号前缀
python scripts/check_archive.py --dir <目录> --out report.html --proj XH042601

# 递归扫描子目录
python scripts/check_archive.py --dir <目录> --recursive

# 只做格式齐套检查，关闭 A/B/C 编号解析
python scripts/check_archive.py --dir <目录> --no-abcc
```

参数说明：

| 参数 | 必填 | 说明 |
|---|---|---|
| `--dir` | 是 | 待检查目录 |
| `--out` | 否 | 输出 HTML 报告路径（默认写到 `--dir` 下 `archive_check_report.html`） |
| `--proj` | 否 | 图样前缀，如 `XH042601`，用于 A/B/C 编号解析 |
| `--recursive` | 否 | 递归扫描子目录 |
| `--no-abcc` | 否 | 关闭 A/B/C 编号解析 |
| `--a-map` / `--b-map` | 否 | 覆盖 A/B 项名称映射（JSON 字符串） |

> 环境：Python 3，脚本仅依赖标准库，无需 `pip install`。

### 简化模型：3D 源齐套 + 真缺口判定（check_gaps.py）

`check_archive.py` 偏完整（五件齐套 + A/B/C 编号解析）；若只想快速判断「缺的文件是不是真缺口」，用 `check_gaps.py`：

```bash
# 3D 源齐套 + 真缺口判定（报告默认写到当前目录 xh_cad_gap_report.html）
python scripts/check_gaps.py --dir "D:/工作资料/智能实验仓/03 皮带线"

# 指定输出、标注项目代号前缀
python scripts/check_gaps.py --dir <目录> --out report.html --proj XH042601

# 递归子目录
python scripts/check_gaps.py --dir <目录> --recursive
```

`check_gaps.py` 的逻辑：

- `sldprt` + `sldasm` → 合并为「3D 源」一类；`stp` / `step` → 「STP 导出 3D」一类；
- 检查 `slddrw / stp / pdf / dwg` 四项交付物是否齐全；
- 对**不齐全**的 3D 件按【名字】分类判定：
  - **自制件（真缺口）**：名字带 钣金 / 机加工 / 焊接 / 冲压 等加工标记，或编号里 `B=01`(钣金) / `B=02`(机加工) → 本应按编号出图，缺失即你「忘了出图」
  - **装配体（非缺口）**：`sldasm` 文件，或名字明显是装配 / 总成 / 组件 / 机构 → 本不需零件加工图
  - **标准件 / 外购（非缺口）**：名字能直接读出参数（如 `10x240轴`、`12x24x4垫圈`、`外径13.5内径11.5`、`38-200辊`），或含标准词汇（垫圈 / 型材 / TXCJ / 同步带 / PE板 / 传送带 / 轴承…）→ 本不需自制图纸
  - **待确认** → 以上都判断不出，需人工确认
- 报告直接给出「真缺口数量」与结论（如「逻辑完全成立 ✅：所有不齐全件均为装配体或标准件，无真缺口」）。
- 仅顶层目录（默认），`--recursive` 可递归。连续两次扫描对比可验证「缺失件 = 装配体 / 标准件」假设。

### 删除孤儿图（delete_orphan_drawings.py）

找出「仅有 `.slddrw` 工程图、没有对应 `.sldprt`/`.sldasm` 3D 源」的孤儿图并删除。**删除必须确认**：默认只读演习（只打印待删清单），加 `--apply` 才真正删除；`--apply` 前先整批备份、再逐一移入回收站（可找回），仅作用于 `--dir`。

```bash
# 只读演习：列出将要删除的孤儿图（不改动任何文件）
python scripts/delete_orphan_drawings.py --dir "D:/工作资料/智能实验仓/03 皮带线"

# 确认后删除（先备份到 ./orphan_backup_<时间戳>，再移入回收站）
python scripts/delete_orphan_drawings.py --dir <目录> --apply

# 指定备份位置 / 递归
python scripts/delete_orphan_drawings.py --dir <目录> --apply --backup-dir D:/bak
python scripts/delete_orphan_drawings.py --dir <目录> --recursive
```

- **真·孤儿图（删除）**：图号核心编码在 3D 源中完全找不到（含无图号件）。
- **命名未同步（保留）**：同核心编码的 3D 源存在，只是图名与件名差一个字/后缀 → 不删，建议改名对齐。

### 序号矩阵表（serial_matrix.py）

把一个层级从最小号到最大号逐行列出，每格 `序号 | 完整文件名(带扩展名) | 状态(有/缺)`，绿=有红=缺，便于一眼看出缺号/重号。

```bash
# 生成序号矩阵表（HTML，标准库零依赖）
python scripts/serial_matrix.py --dir "D:/工作资料/智能实验仓/03 皮带线"

# 同时生成 XLSX（需 openpyxl；未安装则仅出 HTML 并提示）
python scripts/serial_matrix.py --dir <目录> --out matrix.html --xlsx matrix.xlsx

# 每行 4 单元 = 12 列（调整密度）
python scripts/serial_matrix.py --dir <目录> --recursive --units 4
```

---

## 四、图样编号规则

默认解析规则：`<前缀>.<A 项 2位>.<B 项 2位>-<C 流水号>`，例如 `XH042601.03.01-001`。

- **A 项**：部件类型（如 01 组件、03 柜体组件、04 货道组件…）
- **B 项**：加工类型（01 钣金、02 机加工、03 塑胶、04 电气、05 标准、06 外购定制…）
- **C 项**：流水号

完整映射表见 [`references/coding_rules.md`](references/coding_rules.md)。
不同项目可用 `--a-map` / `--b-map` 覆盖。

---

## 五、报告包含的内容

1. 总体指标卡：文件总数、总图号、五件齐全率、缺工程图 / STEP / PDF / DWG 数量、仅有图无源数量
2. 文件类型分布：sldprt / sldasm / slddrw / step / pdf / dwg 各自计数
3. 异常清单：仅有工程图无 3D 源的图号
4. 缺工程图清单：有 3D 源但未出 `.slddrw` 的全部图号
5. A × B 矩阵：各「部件类型 × 加工类型」零件数量分布
6. 断号分析：每个 (A,B) 组内 `1..max` 之间缺失的流水号 C
7. 重号检测：同一 (A,B,C,子号) 出现多个不同零件名
8. 未识别图号：不符合标准编号模式的总成 / 外购件

---

## 六、注意事项

- **建议在 SolidWorks 关闭或保存后再扫描**，结果更稳定（SW 运行时临时 / 中间文件可能干扰判断）。
- 子装配多级流水号（如 `…-001-002`）按父 / 子关系处理，**不会**误判为重号。
- 总装配（如 `03-01 升降交接台`）、未编号外购件（如 `TXCJ-H6-2040-L815`）归入「未识别」，完整性检查仍照常统计其缺格式情况。
- 报告默认写到 `--dir` 下；为避免污染项目归档目录，可用 `--out` 指定到临时 / 工作区路径。
- `delete_orphan_drawings.py` 会真正删除文件，**默认只读演习**，必须 `--apply` 才执行；执行前自动整批备份、并移入回收站（非永久删除），可随时找回。

---

## 七、目录结构

```
xh-cad-checker/
├── SKILL.md                 # 技能定义（WorkBuddy 加载入口）
├── README.md                # 本文档
├── scripts/
│   ├── check_archive.py              # 完整检查：五件齐套 + A/B/C 编号解析（纯标准库，只读）
│   ├── check_gaps.py                 # 简化模型：3D 源齐套 + 真缺口判定（装配体/标准件/自制件分类）
│   ├── delete_orphan_drawings.py     # 删除「仅有.slddrw 无3D源」的孤儿图（默认演习，--apply 才删：备份+回收站）
│   └── serial_matrix.py              # 生成序号矩阵表（序号|完整文件名|状态，有/缺）；HTML 零依赖，XLSX 需 openpyxl
└── references/
    └── coding_rules.md      # 图样编号规则与 A/B 映射表
```
