# HonkaiStarRailAutoScript — 任务单

> 崩铁货币战争 AI Agent 自动化脚本。决策者不是写死流程，而是 LLM。
> 借鉴执行层，重写决策层。感知层先结构化画面，LLM 只看 JSON 做决策。

## 分层架构

```
编排层   main.py
决策层   LLM                          ← 待实现
感知层   OCR + 模板匹配 → 结构化 JSON
设备层   ADB / MuMu IPC
```

## 运行环境

- MuMu 实例1（adb 127.0.0.1:16416），崩铁国服 4.6.0
- MuMu 安装路径：`E:\APP\Netease\MuMu Player 12\nx_main\MuMuManager.exe`
- 专属 adb v36 + 端口 5038，与 Alas（5037）隔离
- 分辨率 1280×720 横屏，截图坐标 == 点击坐标
- OCR 引擎：RapidOCR（文本）+ ddddocr（数字），自包含于 tools/

## 任务进度

| 阶段 | 状态 | 说明 |
|---|---|---|
| P0 通道打通 | ✅ | ADB 连接/截图/点击验证 |
| P1 设备层 | ✅ | `common.py` + `tools/devkit.py` |
| P2 感知层 | ✅ | OCR + 模板匹配 + 颜色匹配 |
| P3 启动与导航 | ✅ | `launch.py` + `navigate.py`（含兜底重试） |
| P4 货币战争入口 | ✅ | `navigate.py` 合并原 battle.py，段位+层级识别 |
| P4.5 界面识别改图形匹配 | ✅ | stage 3~10 全部改为图片模板匹配 |
| P4.6 词条本地字典 | 🔲 | OCR 误识别修正，待实现 |
| P4.7 BOSS 信息入库 | ✅ | `data/db.py` SQLite + `boss_info.py` 自动写入 |
| P5 决策层 | 🔲 | LLM 接入、Prompt、成本控制，待实现 |
| P6 编排与调试 | ✅ | `main.py` STAGES + 错误快照 |

## 段位词条数量映射

A0-A1:0, A2-A3:1, A4-A5:2, A6-A7:3, A8:4

## 待办

### HIGH

- [ ] **检测进入对局后是否进入 BOSS 阵营和词条界面**
  - stage 10 点击"下一步"后，图形匹配检测是否进入 BOSS 阵营和词条界面
  - 匹配成功 → 正常流程，boss_info 数据已在库
  - 匹配失败 → 判断是否未完成对局
    - 是未完成对局 → 继续使用旧数据（不重新识别）
    - 不是未完成对局 → 清理旧对局数据 + 重新载入 BOSS 阵营和词缀
  - 待用户提供：BOSS 阵营和词条界面的图形匹配坐标

### MEDIUM

- [ ] **对局结束 complete_active_game() 接入**
  - 等后续战斗流程明确后，在合适位置调用 complete_active_game() 标记对局完成

### LOW

- [ ] **stage 1/2（login/main）是否改图形匹配**
  - 暂留 OCR，待用户确认是否需要改

- [ ] **投资策略表 strategies 设计**
  - 等货币战争投资策略玩法明确后再加

- [ ] **boss_info OCR 识别改为图形匹配**
  - 用户说后面再说，暂不动

- [ ] **P4.6 词条本地字典匹配替换**

- [ ] **P5 决策层：模型接入、Prompt、成本控制**

- [ ] **失败回放**

## 约定

- 排查/修复过程写临时文件，修完即删
- 动作必须可验证（点完断言有变化）
- 优先 OCR，模板匹配仅作补充（段位徽章例外）
- 持久数据放项目 data/ 并纳入 Git，不依赖外部可清理路径