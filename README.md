# study-presence

摄像头在座学习状态监测：定时取帧 → 人脸检测 → 去抖状态机 → 在座时长入库，Tkinter 窗口实时展示。

检测后端可插拔：默认本地离线 OpenCV YuNet（画面不出本机、零调用成本），可切到百度云人脸检测 API。

## 功能

- 实时预览 + 「在座 / 离座」状态，连续 N 次观测才翻转，抑制单帧误检与短暂起身
- 今日累计在座时长：每次在座区间写入 SQLite，程序重启后仍可累加
- 后端可切换：`local`（离线 YuNet）／`baidu`（云端 detect，密钥只从 `.env` 读）
- 失败不静默：检测或相机出错时把原因显示在窗口里，不把网络错误伪装成「没人」

## 架构

```
CameraSource ──frame──▶ PresenceMonitor (worker thread)
                            │  每 N 秒
                            ▼
                     Detector (local:yunet | baidu:detect)
                            │  face_count
                            ▼
                     PresenceTracker（去抖状态机）
                            │  PresenceEvent
                            ▼
                     PresenceStore（SQLite session 表）

     FrameUpdate / StatusUpdate ──queue──▶ StudyPresenceWindow（Tk 主线程）
```

- **单写者**：相机、检测器、存储只在 worker 线程里被触碰；UI 通过 `queue` 拿结果，不阻塞、不抢锁
- **帧不排队**：帧队列容量 1，UI 落后时丢弃旧帧，只渲染最新画面
- **状态与时长分离**：`PresenceTracker` 只管去抖，`PresenceStore` 只管区间入库，跨天统计由 SQL 窗口裁剪得出
- **异常显式化**：检测后端失败抛 `DetectorError`，由 worker 转成界面上的错误文案，不做 `except: pass`

## 快速开始

```bash
uv sync
uv run study-presence          # 等价于 uv run python -m app
```

首次运行 local 后端会自动下载 YuNet 模型（约 230 KB）到 `models/`；下载失败时按提示手动放到该路径即可。

常用参数：

```bash
uv run study-presence --camera 1        # 换摄像头
uv run study-presence --interval 3      # 每 3 秒检测一次
uv run study-presence --backend baidu   # 切到云端后端（需先配 .env）
```

## 配置

复制 `.env.example` 为 `.env`（已 gitignore），或用同名环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SP_BACKEND` | `local` | `local` 或 `baidu` |
| `SP_CAMERA_INDEX` | `0` | 摄像头编号 |
| `SP_DETECT_INTERVAL_S` | `2` | 检测间隔（秒） |
| `SP_PRESENT_AFTER` | `2` | 连续几次检测到人脸才算在座 |
| `SP_ABSENT_AFTER` | `3` | 连续几次没检测到人脸才算离座 |
| `SP_BAIDU_API_KEY` | — | 百度智能云 API Key，`backend=baidu` 时必填 |
| `SP_BAIDU_SECRET_KEY` | — | 百度智能云 Secret Key，同上 |

数据落盘位置：`data/presence.db`（SQLite，`session` 表记录后端、开始、结束时间）。

## 检测后端

| 后端 | 依赖 | 网络 | 成本 | 适用 |
|---|---|---|---|---|
| `local`（YuNet ONNX） | `opencv-python` | 首次下载模型 | 无 | 日常使用，画面不出本机 |
| `baidu`（人脸检测 v3） | 百度智能云密钥 | 每次检测上传一帧 JPEG | 按调用计费 | 需要云端多属性能力的演示 |

云端后端带 token 缓存（提前 60 秒过期）与失效重取，并受 `SP_DETECT_INTERVAL_S` 节流。

## 目录结构

```
app/
├── __main__.py        # CLI 参数、依赖装配、启动
├── camera.py          # cv2.VideoCapture 的封装（唯一 open/read/close 入口）
├── frames.py          # 缩放、BGR→RGB、JPEG base64
├── pipeline.py        # worker 线程：取帧 → 检测 → 状态机 → 入库
├── config/settings.py # SP_* 环境变量 → 不可变 Settings
├── detectors/         # base 协议 + local(YuNet) + baidu(云端)
├── presence/          # tracker 状态机、store 会话存储
└── ui/window.py       # Tkinter 窗口，主线程只渲染
tests/                 # 状态机、存储、帧工具、两个后端、pipeline
```

## 质量检查

```bash
uv run ruff check .
uv run ruff format --check .
uv run basedpyright
uv run pytest
```

## 隐私

- `local` 后端全程离线：帧只在内存里，不落盘、不上传
- `baidu` 后端会把单帧 JPEG 上传到百度云；密钥只从 `.env` 读，仓库里没有任何凭据

## Roadmap

- 按天/周的专注时长报表与图表
- 托盘常驻 + 开机自启
- GitHub Actions：ruff / basedpyright / pytest
- 多目标场景下区分「本人」与他人（当前只判断人脸数量）
