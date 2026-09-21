# 古籍文献智能校勘工具

> 基于大语言模型（LLM）与自然语言处理（NLP）的古籍整理工作台，覆盖 **OCR 识别、自动标点、断句、异文校勘、文白翻译**，采用「机器初筛 + 专家复核」的人机协同模式。

**当前状态：脚手架阶段（v0.1）** —— 目录结构、核心数据结构和流水线已搭好，各 NLP 模块待实现，欢迎全员认领。

## 项目背景

古籍整理长期依赖专家逐字逐句校读，效率低、门槛高。参考「荀子」古籍大模型、AI 太炎 2.0、汉典重光等实践，本工具把古籍整理拆解为可组合的流水线：机器完成初筛与初校，专家只做复核与按语，既提升效率又保留学术严肃性。

## 核心功能

| 模块 | 说明 | 状态 |
| --- | --- | --- |
| OCR 识别 | 书页影像 → 带坐标文本行 | 待开发 |
| 文本规整 | 繁简、异体字、避讳字规范化 | 待开发 |
| 自动断句 | 文言文句子切分 | 待开发 |
| 自动标点 | 插入现代标点 | 待开发 |
| 异文校勘 | 底本 vs 参校本 → 校勘记 | 待开发 |
| 文白翻译 | 文言 → 现代汉语 | 待开发 |
| 人工审校 | 校勘记审核 / 标注接口 | 待开发 |

## 系统架构

```
书页影像 → [OCR 识别] → [文本规整] → [断句] → [自动标点] → [异文校勘] → [文白翻译] → 整理稿 + 校勘记
                                        ↓
                                  [人工审校 / 标注]
```

## 目录结构

```
guji-collation-tool/
├── src/guji_collate/          # 核心代码
│   ├── modules/               # OCR / 断句 / 标点 / 校勘 / 翻译 各阶段
│   ├── api/                   # FastAPI 服务（草案）
│   ├── config.py              # 配置加载（default.yaml + local.yaml）
│   ├── schemas.py             # 核心数据结构（Pydantic 模型）
│   ├── pipeline.py            # 流水线编排
│   └── cli.py                 # 命令行入口（dummy 空跑演示）
├── docs/                      # 需求 / 架构 / 数据 / 接口文档
├── tests/                     # 单元测试
├── configs/                   # 配置文件
├── data/                      # 数据目录（原始影像/文本默认不入库）
├── pyproject.toml
└── CONTRIBUTING.md            # 贡献指南
```

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url>
cd guji-collation-tool

# 2. 安装（Python ≥ 3.10）
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[api,llm]"

# 3. 空跑流水线（dummy 数据，无需真实模型/OCR）
python -m guji_collate.cli

# 4. 运行测试
pip install pytest
python -m pytest tests/
```

## 技术选型（草案）

- 语言：Python ≥ 3.10
- 服务：FastAPI（可选依赖）
- 配置：YAML（`configs/default.yaml` + `configs/local.yaml` 本地覆盖）
- OCR：PaddleOCR（可选）
- LLM：OpenAI 兼容接口，可指向本地 / 私有化模型（古籍数据不出域）

## 文档

- [docs/requirements.md](docs/requirements.md) 需求说明书
- [docs/architecture.md](docs/architecture.md) 架构设计
- [docs/data-spec.md](docs/data-spec.md) 数据规范
- [docs/api.md](docs/api.md) 接口设计
- [CONTRIBUTING.md](CONTRIBUTING.md) 贡献指南

## 协作方式

按 [CONTRIBUTING.md](CONTRIBUTING.md)：Issue 认领 → 分支开发 → PR review。
数据结构改动请先改 [docs/data-spec.md](docs/data-spec.md)，再同步改 `schemas.py`。

## 参考案例

- 「荀子」古籍大模型（南京农业大学 × 中华书局，开源）
- AI 太炎 2.0（北京师范大学）
- 汉典重光（北京大学，《四库全书》异文自动校勘）
- 古籍酷（OCR 与自动标点）
- 将无同：AI+文言文（华东师范大学）

## License

[MIT](LICENSE)
