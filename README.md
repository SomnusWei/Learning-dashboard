# 学习工作台（Learning Dashboard）

一个面向中医学习者的个人学习工作台，支持错题本管理、FSRS 间隔重复复习、方歌库记忆、待办事项、学习计划、知识库等功能。提供 PWA + 桌面端（Tauri）多端访问，所有业务数据集中存储在 NAS 后端，确保多端数据一致。

## 功能特性

### 核心模块
- **🏠 首页 Dashboard**：今日学习统计、复习进度、待办概览
- **📝 错题本**：截图 OCR 一键录入（蓝基因等 App）、FSRS 智能复习队列、重复错题检测（相似度 > 95%）
- **📅 学习计划**：今日/本周计划，快速模板（复习错题库、手动添加待办）
- **✅ 待办事项**：方歌复习联动、扩展剪藏、优先级/截止时间/标签
- **📚 学习中心**：知识库（卡片浏览）、🎵 方歌库（批量导入、关联待办）、今日复习
- **⚙️ 设置**：主题切换、桌面端连接路径切换（内网 IP / 域名）、打开日志目录

### OCR 错题录入
- **桌面端**：`Alt+Q` 全局快捷键截图指定 App 窗口（蓝基因等）
- **图像处理**：Rust 调用 Python 脚本截图 → PP-OCR 文本识别 → 后端结构化解析（科目/题型/题干/答案）→ 弹窗编辑确认 → 落库
- **PWA 端**：上传图片 → 后端 OCR 服务识别 → 同样结构化解析
- **解析规则**：支持 A1/A2 型题（题干在前）、B1/B2 型题（选项在前）两种形态自动识别
- **语义修复**：内置常见 OCR 漏识模式修复表

### FSRS 间隔重复算法
- 采用 fsrs 1.1.0 库的 `FSRS` 类（基于 Free Spaced Repetition Scheduler）
- 4 档评分：Again / Hard / Good / Easy
- 评分按钮显示**实际下次复习时间**（动态预览，非硬编码）
- 自动判定掌握：reps >= 8 且 scheduled_days >= 21
- 数据存储：`wrong_questions.fsrs_state` JSONB 字段

### 桌面端特性（Tauri 2 + Rust）
- 全局快捷键 `Alt+Q` 触发截图 OCR
- 系统托盘：左键切换显示/隐藏、右键菜单（显示/退出）
- 关闭窗口最小化到托盘（不退出）
- `Ctrl+F` 应用内搜索（拦截 WebView2 原生搜索框）
- 日志：tauri-plugin-log 同时输出到 stdout / LogDir / Webview 控制台
- 隐藏 cmd 窗口（CREATE_NO_WINDOW + windows_subsystem）
- 桌面端连接路径切换：内网 IP（高速） / 域名（外网）

## 技术栈

### 前端
- Vue 3 + Vite + TypeScript
- vite-plugin-pwa（仅缓存静态资源，不缓存业务数据）
- Pinia（状态管理）
- Vue Router

### 桌面端
- Tauri 2 + Rust
- tauri-plugin-log、tauri-plugin-global-shortcut、tauri-plugin-notification
- reqwest（HTTP 请求，OCR 后直接调 backend 保存错题）

### 后端
- FastAPI (Python) + PostgreSQL
- JWT 认证
- fsrs 1.1.0（间隔重复算法）
- difflib.SequenceMatcher（错题相似度检测）

### OCR 服务
- RapidOCR (PP-OCRv3) + ONNX Runtime
- 兼容无 AVX 指令集的 CPU（如 Intel Celeron N5095）

### 部署
- Docker Compose：postgres / backend / ocr / nginx 四服务
- Nginx 反向代理 + HTTPS（8443 端口）
- 速率限制：登录 10 次/分钟、OCR 5 次/分钟、通用 API 20 次/秒

## 项目结构

```
Learning dashboard/
├── backend/                # FastAPI 后端
│   └── app/
│       ├── api/            # HTTP 客户端
│       ├── core/           # 数据库、认证
│       ├── models/         # SQLAlchemy 模型
│       ├── routers/        # API 路由（auth/dashboard/wrong-questions/
│       │                   #   todos/formula-songs/search/...）
│       └── services/       # OCR 服务封装
├── frontend/               # Vue 3 PWA 前端
│   └── src/
│       ├── api/            # API 客户端
│       ├── components/     # AppLayout、GlobalSearch
│       ├── views/          # Home/WrongQuestions/Plans/Todos/Study/Settings
│       ├── stores/         # Pinia stores（auth/theme）
│       └── router/         # Vue Router
├── src-tauri/              # Tauri 桌面端
│   ├── src/main.rs         # Rust 主程序（截图 OCR、托盘、快捷键）
│   ├── capabilities/       # Tauri ACL 权限
│   ├── tauri.conf.json     # Tauri 配置
│   └── Cargo.toml
├── ocr-service/            # OCR 微服务（FastAPI + RapidOCR）
├── nginx/                  # Nginx 配置
├── tools/                  # 工具脚本
│   ├── grab_window.py      # 窗口截图（含图像预处理）
│   └── aliyun_ddns.py      # DDNS 脚本（IPv6 公网 IP 变更自动更新）
├── deploy/                 # 部署脚本和资源
├── docker-compose.yml      # 容器编排
└── .env.example            # 环境变量示例（无敏感信息）
```

## 部署指南

### 前置要求
- Docker + Docker Compose
- NAS 或 Linux 服务器（推荐飞牛 OS / Debian 系）
- 域名 + SSL 证书（可选，用于 HTTPS 外网访问）
- IPv6 公网地址（可选，用于外网访问）

### 步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/SomnusWei/Learning-dashboard.git
   cd Learning-dashboard
   ```

2. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env，填入你的配置（数据库密码、JWT 密钥、域名等）
   ```

3. **构建并启动服务**
   ```bash
   docker compose up -d --build
   ```

4. **数据库初始化**
   ```bash
   docker exec ld-backend python -m app.core.database
   ```

5. **访问**
   - 本机：`https://<your-ip>:8443`
   - 域名（需 DNS 解析 + SSL）：`https://your-domain:8443`

### 桌面端构建

```bash
cd src-tauri
cargo build --release
# 或安装 tauri-cli 后：
cargo tauri build
```

生成的 NSIS 安装包位于 `src-tauri/target/release/bundle/nsis/`。

### OCR 服务部署

OCR 服务默认包含在 docker-compose.yml 中。如需独立部署：

```bash
cd ocr-service
docker build -t learning-ocr .
docker run -d --name ocr -p 8866:8866 learning-ocr
```

## 安全说明

- **本仓库不含任何敏感信息**：IP、账号、密码、SSH 凭证、SSL 私钥均通过 `.env` 注入或本地配置
- **NAS IPv6 防火墙**：通过本机 ip6tables 仅放行 8443 端口，拒绝所有外网入站
- **速率限制**：Nginx 层面对登录、OCR、通用 API 分别限流
- **JWT 认证**：所有业务接口需登录
- **单用户架构**：所有表保留 user_id 字段，便于未来扩展

## 截图（待补充）

- 首页 Dashboard
- 错题本截图 OCR 录入流程
- 复习卡片评分界面
- 方歌库批量导入

## 开发计划

- [ ] 错题本 OCR 准确率进一步提升（PaddleOCR 升级）
- [ ] 学习计划智能推荐（基于 FSRS 复习进度）
- [ ] 知识库卡片 Anki 同步
- [ ] 移动端适配优化

## License

MIT
