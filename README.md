# HonkaiStarRailAutoScript

> 崩坏：星穹铁道 **AI Agent 自动化脚本** —— 决策者不是写死的流程，而是 LLM。

[English](#english) | [中文](#中文)

---

## 中文

### 项目定位

与传统的游戏自动化脚本（如 Alas、SRC）不同，本项目的核心区别在于：

- **传统脚本**：人把流程写死，机器照着跑
- **本项目**：机器看屏幕，自己决定下一步 → **抄执行层，重写决策层**

专门用于「货币战争」玩法（自走棋 + Roguelike 模式），该模式需要动态权衡策略，正是 LLM 决策层的用武之地。

### 分层架构

```
编排层   main.py 统筹脚本
决策层   LLM                          ← 全新
工具层   click / swipe / wait / query  → 封装成 tool
感知层   截图 + OCR / 模板匹配 → 结构化状态
设备层   ADB / MuMu IPC                ← 抄 Alas
```

设计要点：**不把原始像素直接喂给模型**。感知层先把画面结构化（当前在哪、有哪些可点元素），LLM 只看结构做决策——省 token 且稳定。

### 运行环境

| 项目 | 配置 |
|---|---|
| 模拟器 | MuMu 12（adb 127.0.0.1:16416） |
| 游戏 | 崩坏：星穹铁道 国服 4.6.0 |
| 分辨率 | 1280×720（横屏），截图坐标 == 点击坐标 |
| ADB | 专属实例 v36，端口 5038，与 Alas（5037）完全隔离 |
| OCR | Tesseract v5.5.0 自包含，不依赖外部安装 |

### 当前进度

| 阶段 | 状态 | 说明 |
|---|---|---|
| P0 通道打通 | ✅ | ADB 连接/截图/点击全部验证 |
| P1 设备层 | ✅ | `tools/devkit.py` 封装连接/截图/tap/swipe/重试/错误快照 |
| P2 感知层 | ✅ | OCR + 模板匹配 + 颜色匹配底层原语验证通过 |
| P3 启动与导航 | ✅ | `launch.py` + `navigate.py` + `main.py` 统筹 |
| P4 货币战争入口 | ✅ | `battle.py` 段位+层级识别，标准博弈进入流程 |
| P5 决策层 | 🔲 | 模型接入、Prompt 设计、成本控制（待实现） |

### 项目结构

```
HonkaiStarRailAutoScript/
├── main.py              # 统筹脚本，STAGES 注册表编排各阶段
├── launch.py            # 启动脚本（启动游戏 → 登录 → 进入主界面）
├── navigate.py          # 导航脚本（主界面 → 货币战争）
├── battle.py            # 货币战争入口（段位识别 → 标准博弈）
├── snap.py              # 通用截图工具
├── snap_rank.py         # 段位徽章模板截图工具
├── perception/          # 感知层模块
│   ├── matcher.py       # OCR / 模板匹配 / 颜色匹配底层原语
│   ├── templates.py     # 模板匹配库（自动扫描 image/ 目录）
│   ├── assets.py        # 资产注册表（区域定义、页面标识）
│   ├── pages.py         # 页面识别
│   ├── state.py         # 状态提取 → JSON
│   └── __init__.py      # 主 API perceive_screenshot()
├── tools/               # 设备层
│   ├── devkit.py        # 设备访问唯一入口（ADB 封装）
│   ├── adb/             # 专属 ADB 二进制（v36, 端口 5038）
│   ├── tesseract/       # 自包含 Tesseract OCR
│   └── adb.cmd          # 手工 ADB 命令行入口
├── image/rank/          # 段位徽章模板（A0.png ~ A8.png）
├── log/                 # 运行日志 + 错误快照归档
└── TASK.md              # 任务清单（项目上下文起点）
```

### 使用方式

```bash
# 全流程：启动 → 导航 → 进入货币战争标准博弈
python main.py

# 从指定阶段开始
python main.py --from navigate

# 只运行某个阶段
python main.py --only battle

# 截图工具
python snap.py my_screenshot
```

### 参考项目

| 项目 | 参考内容 |
|---|---|
| [AzurLaneAutoScript](https://github.com/LmeZero/AzurLaneAutoScript) (Alas) | 设备层、重试机制、错误快照 |
| [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) (SRC) | 崩铁适配思路、路线定义 |

---

## English

### Project Overview

An AI Agent automation script for Honkai: Star Rail, where the decision-maker is not a hardcoded flow, but an LLM.

- **Traditional scripts**: Humans hardcode the flow, machines follow it
- **This project**: Machines observe the screen and decide the next step → **Borrow the execution layer, rewrite the decision layer**

Specifically designed for the "Monetary War" game mode (auto-chess + Roguelike), which requires dynamic strategic trade-offs — exactly where LLM decision-making shines.

### Architecture

```
Orchestration   main.py stage coordinator
Decision        LLM                          ← New
Tools           click / swipe / wait / query  → wrapped as tools
Perception      Screenshot + OCR / Template Match → structured state
Device          ADB / MuMu IPC                ← Borrowed from Alas
```

Key design: **Don't feed raw pixels to the model**. The perception layer first structures the screen (where am I, what's clickable), and the LLM only sees structured data to make decisions — saving tokens and improving stability.

### Runtime Environment

| Item | Config |
|---|---|
| Emulator | MuMu 12 (adb 127.0.0.1:16416) |
| Game | Honkai: Star Rail CN 4.6.0 |
| Resolution | 1280×720 (landscape), screenshot coords == click coords |
| ADB | Dedicated instance v36, port 5038, fully isolated from Alas (5037) |
| OCR | Tesseract v5.5.0 self-contained, no external dependency |

### Current Progress

| Phase | Status | Description |
|---|---|---|
| P0 Channel | ✅ | ADB connect/screenshot/tap verified |
| P1 Device Layer | ✅ | `tools/devkit.py` wraps connect/screenshot/tap/swipe/retry/error snapshot |
| P2 Perception | ✅ | OCR + template match + color match primitives verified |
| P3 Launch & Navigate | ✅ | `launch.py` + `navigate.py` + `main.py` orchestrator |
| P4 Monetary War Entry | ✅ | `battle.py` rank+level detection, standard match entry flow |
| P5 Decision Layer | 🔲 | Model integration, Prompt design, cost control (TODO) |

### Usage

```bash
# Full flow: launch → navigate → enter monetary war standard match
python main.py

# Start from a specific stage
python main.py --from navigate

# Run only one stage
python main.py --only battle

# Screenshot tool
python snap.py my_screenshot
```

### References

| Project | What we borrowed |
|---|---|
| [AzurLaneAutoScript](https://github.com/LmeZero/AzurLaneAutoScript) (Alas) | Device layer, retry mechanism, error snapshots |
| [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) (SRC) | HSR adaptation ideas, route definitions |