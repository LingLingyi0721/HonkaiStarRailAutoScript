# HonkaiStarRailAutoScript

崩坏：星穹铁道「货币战争」玩法 AI Agent 自动化脚本。

核心思路：感知层先把画面结构化为 JSON，LLM 只看结构化数据做决策——不把原始像素喂给模型，省 token 且稳定。

## 架构

```
编排层   main.py
决策层   LLM（待实现）
感知层   OCR + 模板匹配 → 结构化 JSON
设备层   ADB / 模拟器 IPC
```

## 项目结构

```
├── main.py          # 编排层，STAGES 注册表
├── launch.py        # 启动游戏 → 登录 → 主界面
├── navigate.py      # 导航 → 货币战争入口
├── boss_info.py     # BOSS 信息识别
├── gameplay.py      # 对局内操作（投资环境选择）
├── common.py        # 公共基础设施
├── perception/      # 感知层（OCR/模板匹配/颜色匹配）
├── tools/           # 设备层（ADB封装/OCR引擎）
├── data/            # 数据层（CSV + db.py 查询接口）
├── image/           # 模板图片
└── log/             # 运行日志
```

## 使用

```bash
python main.py                  # 全流程
python main.py --from navigate  # 从指定阶段开始
python main.py --only gameplay  # 只运行某个阶段
```

## 环境

- MuMu 模拟器 1280×720 横屏
- 专属 ADB v36（端口 5038）
- RapidOCR（文本）+ ddddocr（数字）