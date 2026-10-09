# HonkaiStarRailAutoScript

> 崩坏：星穹铁道「货币战争」玩法 AI Agent 自动化脚本 —— 决策者不是写死流程，而是 LLM。

[中文](#中文) | [English](#english)

---

## 中文

### 项目定位

传统脚本把流程写死、机器照着跑；本项目让机器看屏幕、自己决定下一步。感知层先将画面结构化为 JSON（当前在哪、有哪些可点元素），LLM 只看结构化数据做决策——不把原始像素喂给模型，省 token 且稳定。

专门用于「货币战争」玩法（自走棋 + Roguelike 模式），该模式需要动态权衡策略，正是 LLM 决策层的用武之地。

### 架构

```
编排层   main.py — STAGES 注册表编排各阶段
决策层   LLM（待实现）
感知层   OCR + 模板匹配 → 结构化 JSON
设备层   ADB / 模拟器 IPC
```

### 项目进度

| 阶段 | 状态 | 说明 |
|---|---|---|
| P0 通道打通 | ✅ | ADB 连接/截图/点击验证 |
| P1 设备层 | ✅ | 设备封装、重试机制、错误快照 |
| P2 感知层 | ✅ | OCR + 模板匹配 + 颜色匹配 |
| P3 启动与导航 | ✅ | 启动 → 登录 → 导航 → 货币战争 |
| P4 货币战争入口 | ✅ | 段位+层级识别，标准博弈进入流程 |
| P5 决策层 | 🔲 | LLM 接入、Prompt 设计、成本控制 |
| P6 编排与调试 | ✅ | main.py STAGES + 错误快照 |
| P7 对局内操作 | 🔧 | 投资环境选择已实现，备战阶段待实现 |

### 数据层

| 数据 | 条数 | 说明 |
|---|---|---|
| 角色详情 | 72 | 含属性/技能/羁绊/推荐装备 |
| 投资策略 | 334 | 含稀有度/内容/出现位面 |
| 羁绊 | 33 | 含触发条件/分级效果 |
| 装备 | 159 | 含合成途径/获取方式 |
| 竞争对手 | 20 | 含技能/属性 |
| 词缀描述 | 55 | 货币战争词缀效果说明 |

数据来源：[BiliGame Wiki](https://wiki.biligame.com/sr/)，持久化于 `data/` 目录，通过 `data/db.py` 提供查询接口。

### 项目结构

```
├── main.py          # 编排层，STAGES 注册表
├── launch.py        # 启动游戏 → 登录 → 主界面
├── navigate.py      # 导航 → 货币战争入口
├── boss_info.py     # BOSS 信息识别
├── gameplay.py      # 对局内操作（投资环境选择）
├── common.py        # 公共基础设施
├── perception/      # 感知层（OCR/模板匹配/颜色匹配）
├── tools/           # 设备层（ADB 封装/OCR 引擎）
├── data/            # 数据层（CSV + db.py 查询接口）
├── image/           # 模板图片
└── log/             # 运行日志
```

### 使用方式

```bash
python main.py                  # 全流程
python main.py --from navigate  # 从指定阶段开始
python main.py --only gameplay  # 只运行某个阶段
```

---

## English

### Overview

An AI Agent automation script for Honkai: Star Rail's "Monetary War" mode (auto-chess + Roguelike). Unlike traditional scripts with hardcoded flows, this project lets the machine observe the screen and decide the next step via LLM.

Key design: the perception layer first structures the screen into JSON (where am I, what's clickable), and the LLM only sees structured data — no raw pixels fed to the model, saving tokens and improving stability.

### Architecture

```
Orchestration   main.py — STAGES registry
Decision        LLM (TODO)
Perception      OCR + Template Match → Structured JSON
Device          ADB / Emulator IPC
```

### Progress

| Phase | Status | Description |
|---|---|---|
| P0 Channel | ✅ | ADB connect/screenshot/tap verified |
| P1 Device Layer | ✅ | Device wrapper, retry, error snapshots |
| P2 Perception | ✅ | OCR + template match + color match |
| P3 Launch & Navigate | ✅ | Launch → login → navigate → monetary war |
| P4 War Entry | ✅ | Rank+level detection, standard match entry |
| P5 Decision Layer | 🔲 | LLM integration, Prompt design, cost control |
| P6 Orchestration | ✅ | main.py STAGES + error snapshots |
| P7 In-Match Ops | 🔧 | Investment selection done, prep phase TODO |

### Data Layer

| Data | Count | Description |
|---|---|---|
| Characters | 72 | Attributes/skills/bonds/recommended gear |
| Strategies | 334 | Rarity/content/dimensions |
| Bonds | 33 | Trigger conditions/graded effects |
| Equipment | 159 | Craft paths/acquisition |
| Competitors | 20 | Skills/attributes |
| Affixes | 55 | Monetary War affix descriptions |

Data sourced from [BiliGame Wiki](https://wiki.biligame.com/sr/), persisted in `data/`, queried via `data/db.py`.

### Project Structure

```
├── main.py          # Orchestration, STAGES registry
├── launch.py        # Launch game → login → main screen
├── navigate.py      # Navigate → monetary war entry
├── boss_info.py     # BOSS info recognition
├── gameplay.py      # In-match operations
├── common.py        # Shared infrastructure
├── perception/      # Perception layer (OCR/template/color)
├── tools/           # Device layer (ADB/OCR engines)
├── data/            # Data layer (CSV + db.py queries)
├── image/           # Template images
└── log/             # Runtime logs
```

### Usage

```bash
python main.py                  # Full flow
python main.py --from navigate  # Start from a specific stage
python main.py --only gameplay  # Run only one stage
```