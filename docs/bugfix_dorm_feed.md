# Fix: 宿舍喂食复用旧截图导致填充值不更新

文件：`module/dorm/dorm.py` → `RewardDorm.dorm_feed_once()`
分支：`bug_fix`

## 根因

`dorm_feed_once()` 的采样循环用的是 `for _ in self.loop():`，而 `ModuleBase.loop()` 默认 `skip_first=True`，首帧不截图；该循环一读到有食物就 `break`，函数体内也没有任何主动截图。

`_dorm_feed_click()` 在 `count > 3` 时走 `multi_click` 分支并设置 `skip_first_screenshot = True`，随后的等待循环同样跳过首帧；它判断的 `DORM_FEED_CHECK` 用的正是进入喂食界面那张旧图，必然匹配成功并立即退出，依旧没有产生新帧。

两者叠加，`dorm_feed()` 的 10 轮循环共用进入喂食界面那一刻的画面，`fill` 恒定、`count` 恒定，填充计算被架空。该问题由 `877ce02b9` (#2707) 把原本无条件的 `self.device.screenshot()` 改成跳过首帧的循环引入，`632b06780` 改写为 `loop()` 后一直保留。

## 前后对比

| 项目 | 修复前 | 修复后 |
|---|---|---|
| 每轮截图 | 0 次 | 1 次 |
| 读数 | 10 轮全是 `0/40000` | 每轮随实际填充变化 |
| 喂食次数 | 每轮固定 `40000//2000=20` | `fill//feed`，逐轮递减 |
| 结束方式 | `Dorm feed run count reached` | `Dorm feed finished` |

## 对应日志

修复前：

```
09:13:00.485 [OCR_DORM_FILL] 0/40000
09:13:00.488 Dorm feed FOOD_1_0 x 20
09:13:03.474 [OCR_DORM_FILL] 0/40000
09:13:03.476 Dorm feed FOOD_1_0 x 20
...
09:13:28.934 [OCR_DORM_FILL] 0/40000
09:13:28.936 Dorm feed FOOD_1_0 x 20
09:13:32.058 Dorm feed run count reached
```

修复后：

```
09:43:33.702 [OCR_DORM_FILL 0.025s] 45858/50000
09:43:33.703 Dorm food: [21226, 10547, 0, 0, 0, 0], to fill: 4142
09:43:33.704 Dorm feed FOOD_1_0 x 2
09:43:35.709 [OCR_DORM_FILL 0.021s] 49858/50000
09:43:35.710 Dorm food: [...], to fill: 142
09:43:35.710 Dorm feed finished
```

## 复现对照

用 `git show HEAD:module/dorm/dorm.py` 的旧代码与当前代码，在 mock 环境下按 `0/40000`、`11245/40000`、`15224/40000`、`16555/40000` 逐轮读数对照：

| 轮次 | 旧版读数 | 旧 count | 新版读数 | 新 count | 截图 旧/新 |
|---|---|---|---|---|---|
| 1 | 0/40000 | 20 | 0/40000 | 20 | 0 / 1 |
| 2 | 0/40000 | 20 | 11245/40000 | 14 | 0 / 1 |
| 3 | 0/40000 | 20 | 15224/40000 | 12 | 0 / 1 |
| 4 | 0/40000 | 20 | 16555/40000 | 11 | 0 / 1 |

旧版四轮截图调用 0 次，始终读初始帧；新版每轮 1 帧，次数随剩余空间递减。