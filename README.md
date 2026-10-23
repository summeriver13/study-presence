# study-presence

摄像头在座学习状态监测：合格人脸 → 时间窗去抖 → 键鼠交互证据 → 三态（离座 / 在座无交互 / 在座有交互），区间写入 SQLite，Tk 窗口实时显示，可按天出报表。

检测后端可插拔：默认本地离线 OpenCV YuNet（画面不出本机、零调用成本），可切到百度云人脸检测 API。

![study-presence 运行截图](docs/screenshot.png)

## 判定逻辑

「这个人正在学习」不是人脸检测器能回答的问题。所以这里不宣称测量专注度，只输出两个可观测、可复核的量：**在座时长**与**有交互时长**。

| 状态 | 判据 |
|---|---|
| 离座 | 画面中央区域内没有面积达标的人脸 |
| 在座 · 无交互 | 有合格人脸，但最近 `SP_ACTIVITY_IDLE_S` 秒内没有键鼠输入 |
| 在座 · 有交互 | 有合格人脸，且有近期键鼠输入 |

三步链：

1. **合格人脸**（`app/presence/criteria.py`）：人脸框中心落在画面中央 ROI（默认横向 0.2–0.8、纵向 0.05–0.95），且面积占整帧 ≥ `SP_MIN_FACE_AREA`（默认 2%）。海报、路人、远处室友都在这一步被过滤掉。
2. **时间窗去抖**（`app/presence/tracker.py`）：占据状态要连续满足阈值秒数才翻转（`SP_PRESENT_AFTER_S` / `SP_ABSENT_AFTER_S`）。单位是秒不是检测次数，改 `--interval` 不会改变判定的时间尺度。
3. **交互证据**（`app/activity.py`）：Windows 下读 `GetLastInputInfo` 的空闲时长，只取秒数、不取任何输入内容；其他平台降级为纯视觉，界面显示「交互检测不可用」。

由此得到两个数字：**在座时长**（全部区间合计）与**有交互时长**（只算 active 区间）。

### 已知局限

- 低头看书、大幅侧脸可能检测不到人脸 → 会被判成离座。这是正脸检测模型的固有限制，不引入更重的头部姿态模型就解决不了
- 键鼠在动说明不了在学；在座无交互也可能是在看书。两个数字都以「可观测证据」命名，不叫「专注度」
- 多人同框只判断「有没有合格人脸」，不区分是不是本人；室友坐在同一位置会共享这份时长
- 交互证据只有 Windows 实现，其他平台退化为「在座即有交互」

## 架构

```
FrameSource ──frame──▶ PresenceMonitor (worker thread)
                          │  每 N 秒检测
                          ▼
                  Detector (local:yunet | baidu:detect)
                          │  DetectionResult（归一化人脸框）
                          ▼
                  PresenceCriteria（ROI + 面积过滤）
                          │  occupied
                          ▼
                  PresenceTracker（秒级去抖）◀── ActivitySource（键鼠空闲时长）
                          │  PresenceEvent（absent | idle | active）
                          ▼
                  PresenceStore（SQLite session 表，按 state 区分区间）

   FrameUpdate / StatusUpdate ──queue──▶ StudyPresenceWindow（Tk 主线程）
```

- **单写者**：相机、检测器、存储只在 worker 线程里被触碰；UI 通过两个队列拿结果，不阻塞、不抢锁
- **帧不排队**：帧队列容量 1，UI 落后时丢弃旧帧，只渲染最新画面
- **判定与统计分离**：`criteria` 决定「算不算在座」，`tracker` 决定「什么时候翻转」，`store` 只管区间入库；报表与评估复用同一套纯函数
- **异常显式化**：检测后端失败抛 `DetectorError`，由 worker 转成界面上的错误文案，不做 `except: pass`

## 快速开始

```bash
uv sync
uv run study-presence          # 等价于 uv run python -m app
```

首次运行 local 后端会自动下载 YuNet 模型（约 230 KB）到 `models/`；下载失败时按提示手动放到该路径即可。

```bash
uv run study-presence --camera 1        # 换摄像头
uv run study-presence --interval 3      # 每 3 秒检测一次
uv run study-presence --backend baidu   # 切到云端后端（需先配 .env）
uv run study-presence --source demo.mp4 # 无摄像头：用视频/图片文件当输入（视频循环播放）
```

## 在座时长报表

```bash
uv run study-presence --report        # 今天
uv run study-presence --report 7      # 近 7 天
uv run study-presence --report 30 --csv out/month.csv
```

按天切分（跨午夜的会话会拆到两天），每行给出在座与有交互两个时长，末尾是合计与有记录天数的日均。报表只读 SQLite，不打开摄像头、不需要检测模型。

```
在座 / 有交互时长（近 7 天）
2026-10-18  在座 00:30:00  有交互 00:12:00
2026-10-19  在座 00:55:00  有交互 00:41:00
...
合计: 在座 06:30:00  有交互 03:05:00
有记录: 5 天，日均在座 01:18:00
```

## 判定质量评估

阈值不该靠猜。准备一段标注好「何时有人、何时无人」的视频，用回放算出指标：

标注 CSV（`label` 取 `absent` / `idle` / `active`；评估只判在座与否，所以 idle 与 active 都按在座计）：

```csv
start_s,end_s,label
0,12,absent
12,95,present
```

```bash
uv run study-presence --evaluate demo.mp4 --labels demo.csv --stride 0.5
uv run study-presence --evaluate demo.mp4 --labels demo.csv --sweep 0.005,0.01,0.02,0.05
```

输出（下列数字来自 12 秒合成视频：前 6 秒无人、后 6 秒有人，仅用于验证链路，不代表真实场景精度）：

```
在座判定：precision 1.000  recall 0.750  F1 0.857  准确率 0.880
混淆矩阵：TP 9  FP 0  FN 3  TN 13

最小人脸面积占比    precision  recall  F1
0.005                  1.000   0.750  0.857
0.020                  1.000   0.750  0.857
0.200                  0.000   0.000  0.000
```

recall 0.75 来自 1 秒去抖延迟（人出现的瞬间不能立刻算在座），不是漏检。真实数值需要你用真实场景的视频标注后跑出来，`--sweep` 就是用来选阈值的。

## 配置

复制 `.env.example` 为 `.env`（已 gitignore），或用同名环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SP_BACKEND` | `local` | `local` 或 `baidu` |
| `SP_CAMERA_INDEX` | `0` | 摄像头编号 |
| `SP_SOURCE` | — | 视频或图片文件路径；设置后忽略摄像头 |
| `SP_DETECT_INTERVAL_S` | `2` | 检测间隔（秒） |
| `SP_PRESENT_AFTER_S` | `4` | 连续有人多少秒才算在座 |
| `SP_ABSENT_AFTER_S` | `6` | 连续无人多少秒才算离座 |
| `SP_MIN_FACE_AREA` | `0.02` | 人脸框面积占整帧的下限，低于视为远处的脸 |
| `SP_TRACK_INPUT` | `1` | 是否读取键鼠空闲时长（仅 Windows 生效，`0` 关闭） |
| `SP_ACTIVITY_IDLE_S` | `60` | 空闲超过多少秒算「无交互」 |
| `SP_DB_PATH` | `data/presence.db` | SQLite 落盘位置，窗口与报表共用 |
| `SP_BAIDU_API_KEY` | — | 百度智能云 API Key，`backend=baidu` 时必填 |
| `SP_BAIDU_SECRET_KEY` | — | 百度智能云 Secret Key，同上 |

数据落盘在 `SP_DB_PATH` 指向的 SQLite：`session` 表按 `state`（`active` / `idle`）记录每段区间的后端与起止时间。旧库打开时会自动补 `state` 列。

## 检测后端

| 后端 | 依赖 | 网络 | 成本 | 适用 |
|---|---|---|---|---|
| `local`（YuNet ONNX） | `opencv-python-headless` | 首次下载模型 | 无 | 日常使用，画面不出本机 |
| `baidu`（人脸检测 v3） | 百度智能云密钥 | 每次检测上传一帧 JPEG | 按调用计费 | 需要云端多属性能力的演示 |

两个后端都返回归一化人脸框，判定链完全一致；云端后端带 token 缓存（提前 60 秒过期）与失效重取，并受 `SP_DETECT_INTERVAL_S` 节流。

## 目录结构

```
app/
├── __main__.py        # CLI 参数、依赖装配：窗口 / 报表 / 评估
├── sources.py         # 帧来源协议：摄像头 / 视频与图片文件
├── camera.py          # cv2.VideoCapture 的封装（唯一 open/read/close 入口）
├── frames.py          # 缩放、BGR→RGB、JPEG base64
├── activity.py        # 交互证据：GetLastInputInfo 空闲时长（含降级实现）
├── pipeline.py        # worker 线程：取帧 → 检测 → 判据 → 状态机 → 入库
├── report.py          # 会话区间按天切分，渲染报表与 CSV
├── evaluation.py      # 回放标注视频，算 precision / recall / F1 与阈值曲线
├── config/settings.py # SP_* 环境变量 → 不可变 Settings
├── detectors/         # base 协议（人脸框）+ local(YuNet) + baidu(云端)
├── presence/          # criteria 判据、tracker 状态机、store 会话存储
└── ui/                # window.py 窗口（主线程只渲染）、format.py 纯展示格式化
tests/                 # 判据、状态机、存储、两个后端、pipeline、报表、评估
```

## 质量检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest
```

与 `.github/workflows/ci.yml` 完全一致：push 与 PR 都会在 Ubuntu 上跑一遍。

## 设计取舍

| 决定 | 理由 | 代价 |
|---|---|---|
| 只统计 ROI 内、面积达标的人脸 | 旧实现「画面里有任意一张脸就算在座」，海报、路人、室友都能刷时长 | 需要标定 ROI，人坐得太偏会漏判 |
| 去抖阈值用秒而不是观测次数 | 次数阈值与 `--interval` 耦合，改采样率等于改判定标准 | 阈值要按时间理解，配置项变多 |
| 输出「在座」与「有交互」两个时长，不叫专注度 | 人脸存在性证明不了在学习，键鼠活动也证明不了；只报告能复核的量 | 界面与报表各多一列 |
| 交互证据缺失时不惩罚（在座即有交互） | 不为没有证据的结论编造数据，同时在界面标注「交互检测不可用」 | 非 Windows 平台无法区分 idle / active |
| 阈值来源是 `--sweep` 曲线 | 拍脑袋的阈值无法解释，也无法随场景调整 | 评估需要一段标注视频 |
| 采集/检测/入库全在 worker 线程，UI 只消费队列 | 旧版在 Tk 主线程 `while True` + `sleep`，检测期间窗口冻结 | 跨线程只靠队列，关闭要处理 join 时序 |
| 帧队列容量 1，满了丢旧帧 | 预览延迟比丢帧更影响观感；积压会让画面越来越落后 | 极端卡顿时会跳帧 |
| 存区间而不是存累计秒数 | 累计值无法回溯校验，也不能按任意窗口重算 | 查询要按天切分并裁剪边界 |
| 未结束的会话查询时裁到 `now` | 崩溃或强退不会丢掉当前这段在座 | 查询多一个 `ended_at IS NULL` 分支 |
| 后端失败抛 `DetectorError` 并显示在窗口 | 旧版 `except: return False` 把网络/鉴权故障伪装成「没人学习」 | 界面多一行错误文案 |

## 隐私

- `local` 后端全程离线：帧只在内存里，不落盘、不上传
- 交互证据只读「距上次输入多少秒」，不读键值、不留输入历史
- `baidu` 后端会把单帧 JPEG 上传到百度云；密钥只从 `.env` 读，仓库里没有任何凭据

## Roadmap

- 头部姿态/视线方向，缓解「低头看书被判离座」
- 托盘常驻 + 开机自启
- 多目标场景下区分「本人」与他人（当前只判断有没有合格人脸）

## 许可

MIT，见 [LICENSE](LICENSE)。
