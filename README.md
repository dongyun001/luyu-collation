# 古籍智能校勘系统

面向中国古典文献学的 AI 辅助校勘工具：粘贴一段古籍原文，系统逐条给出**讹字 / 衍文 / 脱文 / 通假 / 异文**
五类校勘建议并附依据，人工逐条采纳或还原，最后导出符合传统体例的**校勘记**；另有多维度文献分析、
图表看板、知识图谱与**版本对勘**页面。

设计原则有三条，贯穿全部代码：

1. **AI 出建议，人做决定。** 每条建议都必须能给出依据（别本异文、字表通假、本书内互证），
   置信度低于阈值的一律先标"存疑"；采纳与还原都是人工动作，系统不替用户改字。
2. **模型输出必须过 schema 闸门才能进 UI。** 不合契约的单条丢弃并计入响应里的 `droppedCount`，
   整份不合契约直接降级报错——宁可不显示，也不渲染脏数据。
3. **演示主链路不含硬编码演示数据。** mock 只存在于测试与开发降级路径，且都有显式标记。

## 功能

| 页面 | 路由 | 做什么 |
|---|---|---|
| 上传古籍 | `/` | 粘贴或上传 .txt；按句读分段提交，逐段出结果 |
| 校勘工作台 | `/collation` | 逐条校勘建议 + 白话译文 + 采纳/还原/批量操作 + 筛选统计 + 导出校勘记 |
| 分析看板 | `/analysis` | 多维度文献判断、图表（类型分布、置信度、逐段命中）、知识图谱 |
| 版本对勘 | `/compare` | 底本 × 1–3 个参照本逐字对齐，列出异文与版本存缺 |
| 项目列表 | `/projects` | 本机历史项目（浏览器 `localStorage`，非服务端持久化） |
| 关于项目 | `/about` | 定位、能力边界与免责说明 |

**四法引擎的落地状态**（校勘学的对校 / 本校 / 他校 / 理校）：

- **对校**——已落地。字符级确定性对齐（`difflib`），**不调用任何模型**：同样两段文本永远得到
  同一份异文清单，可逐条核对、断网可用。
- **理校**——已落地。大模型给出五类专业判断，走完整的 schema 闸门与置信度规则修正。
- **本校**（全书用字一致性）与**他校**（他书引文核对，需本地语料与向量检索）——接口与降级分支在设计，
  尚未接入真实语料，文档中如实标注为未完成，不做"已实现"的表述。

**明确的未实现项**：图片/PDF OCR 与划词释义尚未接入，界面对这两处直接给降级提示，不假装可用；
服务端版导出校勘记同样未实现，当前由前端纯规则生成。

## 技术栈

- **前端**：Vue 3 + Vite + Pinia + vue-router；繁简转换用 opencc-js；图表用 ECharts
  （`echarts/core` 按需注册，只被 `/analysis` 懒加载路由引用，不进首屏包）。
- **后端**：Python 3.11+ + FastAPI，定位是**薄 BFF**：入参校验、Prompt 组装、限流（30 req/min/IP）、
  密钥托管。大模型密钥只存在服务端 `.env`，浏览器永远拿不到。
- **接口**：`GET /api/v1/health`（含当前生效的 Prompt 版本与规则开关）、`POST /api/v1/collate`、
  `POST /api/v1/analyze`、`POST /api/v1/compare`。统一错误体 `{ "error": { "code", "message" } }`。
- **Prompt 资产**：`server/prompts/`，按版本命名（如 `collate_v2.md`），按 `## SYSTEM` / `## USER` /
  `## FRAGMENT` 分段，用 `{{占位符}}` 注入变量；改 Prompt 一律另存新版本以留回归对比。
- **大模型客户端**：流式 + 停滞看门狗（判据是"上游是否还在产出"，不是总耗时）、段级重试、
  温度与"是否启用置信度规则修正"均可通过环境变量配置。

## 快速开始

环境要求：Node `^22.18.0` 或 `>=24.12.0`；Python `>=3.11`。

```bash
# 1) 前端依赖
npm install

# 2) 后端依赖（独立虚拟环境，不进 npm）
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt   # macOS / Linux

# 3) 配置密钥（.env 已在 .gitignore 中，永不提交）
cp .env.example .env    # 填入 LLM_API_KEY
```

启动（**后端启动前必须先激活 `.venv`**，`npm run dev:server` 依赖 PATH 上的 `uvicorn`）：

```bash
npm run dev:server   # uvicorn server.main:app --reload --port 3001
npm run dev          # Vite 开发服务器
```

前端默认连 `http://localhost:3001`，需要指向别处时用 `VITE_API_BASE` 覆盖。
后端的 CORS 允许来源是显式清单（`5173` / `4173`），这是有意为之：不让任意网页调用本地 BFF。
演示前先跑一次 `GET /api/v1/health` 确认服务可用。

## 测试与构建

```bash
npm test                                          # 前端（vitest，185）
.venv/Scripts/python -m pytest server/tests        # 后端（85）
.venv/Scripts/python -m pytest eval/tests          # 评测工具（83）
npm run build                                     # 生产构建
```

改动后这三条测试与构建都要通过才算完成；演示主链路（粘贴 → 校勘 → 采纳/还原 → 导出校勘记）
另需手动走一遍。测试规模随迭代变化，上面的数字是 2026-10-13 的快照。

后端测试不依赖真实模型：上游一律指向 `server/tests/fake_llm_provider.py` 这个本地假模型端点，
断言的是**生产代码路径**的行为（schema 校验、定位、降级分支、置信度规则），而不是模型的内容质量。
拉不到真实密钥时也能跑，方式见 `server/tests/README.md`。

## 评测工具（`eval/`）

`eval/` 是评测与统计脚本，随仓库发布，职责见 `eval/README.md`：

| 脚本 | 用途 |
|---|---|
| `self_check.py` | 标注自检：区间错位、类型/来源非法、标注区间重叠、类型配额、few-shot 污染 |
| `mark_to_labels.py` | 把人工标记文本转成标注文件，索引自动计算（手数索引是标注里最主要的系统性错误来源） |
| `run_compare.py` | 对比实验执行器：走真实 HTTP，强制关闭译文以保证可比性，自动记录 Prompt 版本与消融开关 |
| `judge.py` | 判定：区间重叠命中、检出与分类分开计分、`extra-valid` 单列、置信度分层 |
| `report.py` | 汇总成 Markdown / JSON / CSV |
| `survey_stats.py` | 问卷统计：正向比例、NPS、开放题原话（缺失逐题剔除，不填补） |
| `timing_stats.py` | 效率实验：两组均值、效率倍数、**Bootstrap 置信区间**（固定种子，可复现） |

标注集放 `eval/dataset/`、跑批结果放 `eval/results/`，目录与格式已就绪；**当前尚未跑过真实评测**，
因此本仓库不提供任何精度或效率数字——数字要等标注与跑批完成后由上述脚本产出，
不凭估计写进材料。

## 工程约定

- **不要覆盖用户数据**：任何修改都写成带时间戳的新文件。
- **样式只用 CSS 变量**：全局 token 在 `src/styles/theme.css`，纹样在 `src/styles/patterns.css`，
  新组件不写死色值。
- **尊重「减少动效」偏好**：全局有 `prefers-reduced-motion` 分支，图表动画同时关闭。
- **参赛材料匿名化**：技术方案、演示视频、PPT、佐证材料与截图一律不出现学校名称、
  校徽与真实姓名。
- 需求、架构、接口与评测口径以团队内部文档为准（`docs/` 只在本地留档，不随仓库发布）；
  仓库内的 `eval/README.md`、`server/tests/README.md` 与 `server/prompts/` 是同源的落地说明。
