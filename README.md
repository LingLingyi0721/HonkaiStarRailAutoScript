# HonkaiStarRailAutoScript

> 崩坏：星穹铁道 **AI Agent 自动化脚本** —— 决策者不是写死的流程，而是 LLM。

[English](#english) | [中文](#中文)

---

## 中文

### 项目定位

与传统的游戏自动化脚本不同，本项目的核心区别在于：

- **传统脚本**：人把流程写死，机器照着跑
- **本项目**：机器看屏幕，自己决定下一步 → **借鉴执行层，重写决策层**

专门用于「货币战争」玩法（自走棋 + Roguelike 模式），该模式需要动态权衡策略，正是 LLM 决策层的用武之地。

### 分层架构

```
编排层   main.py 统筹脚本
决策层   LLM                          ← 全新
工具层   click / swipe / wait / query  → 封装成 tool
感知层   截图 + OCR / 模板匹配 → 结构化状态
设备层   ADB / 模拟器 IPC
```

设计要点：**不把原始像素直接喂给模型**。感知层先把画面结构化（当前在哪、有哪些可点元素），LLM 只看结构做决策——省 token 且稳定。

### 当前进度

| 阶段 | 状态 | 说明 |
|---|---|---|
| P0 通道打通 | ✅ | ADB 连接/截图/点击全部验证 |
| P1 设备层 | ✅ | 设备封装、重试机制、错误快照 |
| P2 感知层 | ✅ | OCR + 模板匹配 + 颜色匹配 |
| P3 启动与导航 | ✅ | 启动 → 登录 → 导航 → 货币战争 |
| P4 货币战争入口 | ✅ | 段位+层级识别，标准博弈进入流程 |
| P5 决策层 | 🔲 | 模型接入、Prompt 设计、成本控制（待实现） |

### 项目结构

```
HonkaiStarRailAutoScript/
├── main.py              # 统筹脚本，STAGES 注册表编排各阶段
├── launch.py            # 启动脚本（启动游戏 → 登录 → 进入主界面）
├── navigate.py          # 导航脚本（主界面 → 货币战争）
├── battle.py            # 货币战争入口（段位识别 → 标准博弈）
├── perception/          # 感知层模块
│   ├── matcher.py       # OCR / 模板匹配 / 颜色匹配底层原语
│   ├── templates.py     # 模板匹配库
│   ├── assets.py        # 资产注册表（区域定义、页面标识）
│   ├── pages.py         # 页面识别
│   ├── state.py         # 状态提取 → JSON
│   └── __init__.py      # 主 API
├── tools/               # 设备层
│   ├── devkit.py        # 设备访问入口（ADB 封装）
│   ├── adb/             # 专属 ADB 二进制
│   └── tesseract/       # 自包含 Tesseract OCR
├── image/rank/          # 段位徽章模板
├── log/                 # 运行日志 + 错误快照
└── TASK.md              # 任务清单
```

### 使用方式

```bash
# 全流程：启动 → 导航 → 进入货币战争标准博弈
python main.py

# 从指定阶段开始
python main.py --from navigate

# 只运行某个阶段
python main.py --only battle
```

### 参考项目

| 项目 | 借鉴内容 |
|---|---|
| [AzurLaneAutoScript](https://github.com/LmeSzinc/AzurLaneAutoScript) | 设备层架构、重试机制、错误快照设计 |
| [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) | 崩铁适配思路、路线定义理念 |

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
Device          ADB / Emulator IPC
```

Key design: **Don't feed raw pixels to the model**. The perception layer first structures the screen (where am I, what's clickable), and the LLM only sees structured data to make decisions — saving tokens and improving stability.

### Current Progress

| Phase | Status | Description |
|---|---|---|
| P0 Channel | ✅ | ADB connect/screenshot/tap verified |
| P1 Device Layer | ✅ | Device wrapper, retry mechanism, error snapshots |
| P2 Perception | ✅ | OCR + template match + color match |
| P3 Launch & Navigate | ✅ | Launch → login → navigate → monetary war |
| P4 Monetary War Entry | ✅ | Rank+level detection, standard match entry |
| P5 Decision Layer | 🔲 | Model integration, Prompt design, cost control (TODO) |

### Usage

```bash
# Full flow: launch → navigate → enter monetary war standard match
python main.py

# Start from a specific stage
python main.py --from navigate

# Run only one stage
python main.py --only battle
```

### References

| Project | What we borrowed |
|---|---|
| [AzurLaneAutoScript](https://github.com/LmeZero/AzurLaneAutoScript) | Device layer architecture, retry mechanism, error snapshot design |
| [StarRailCopilot](https://github.com/LmeSzinc/StarRailCopilot) | HSR adaptation ideas, route definition concepts |