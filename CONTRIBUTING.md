# 贡献指南

## 协作流程

1. 在 Issues 里认领模块 / 功能（或新建 Issue 说明要做的事）
2. 从 `main` 拉出分支：`feat/<模块名>`、`fix/<问题>`、`docs/<文档>`
3. 开发 + 自测：`python -m pytest tests/`
4. 提 PR，描述改动与影响面，至少 1 人 review 后合并

## 提交信息约定

| 前缀 | 用途 |
| --- | --- |
| `feat` | 新功能 |
| `fix` | 修复缺陷 |
| `docs` | 文档 |
| `refactor` | 重构（不改变行为） |
| `test` | 测试 |
| `chore` | 杂项（配置、依赖等） |

示例：`feat(punctuation): 接入 LLM 自动标点`

## 代码约定

- 注释与文档用中文，便于全员理解；代码标识符用英文
- 公开函数标注参数与返回值类型（type hints）
- 数据结构改动必须同步 [docs/data-spec.md](docs/data-spec.md)
- 新增模块放在 `src/guji_collate/modules/`，实现 `run()` 方法并在 `pipeline.py` 中注册
- 不把真实古籍数据、密钥、本地配置提交入库（见 `.gitignore`）

## 密钥与敏感信息

- 密钥一律放本地 `.env`（复制 `.env.example` 改名填入），**严禁提交**；`.env` 与 `configs/local.yaml` 已在 `.gitignore` 中
- 密钥名约定：LLM 接口密钥用 `GUJI_LLM_API_KEY`（与 `configs/default.yaml` 的 `llm.api_key_env` 对应）
- CI 里有敏感文件入库检查（`.github/workflows/ci.yml`），提交了 `.env` 会直接变红
- 需要在 CI 里用共享密钥时，走 GitHub 仓库 Settings → Secrets and variables → Actions，用 `${{ secrets.XXX }}` 注入

## 目录职责

| 目录 | 职责 |
| --- | --- |
| `src/guji_collate/` | 核心代码 |
| `docs/` | 设计与规范文档 |
| `tests/` | 单元测试 |
| `configs/` | 配置文件（`default.yaml` 入库，`local.yaml` 忽略） |
| `data/` | 数据（原始影像/文本默认不入库） |

## 认领清单（建议的第一批任务）

- [ ] `modules/ocr.py`：接入 PaddleOCR 或 OCR 服务
- [ ] `modules/segmentation.py`：文言断句（规则 / LLM）
- [ ] `modules/punctuation.py`：自动标点
- [ ] `modules/collation.py`：异文比对与校勘记生成
- [ ] `modules/translation.py`：文白翻译
- [ ] `api/main.py`：补齐 REST 路由，落地 `docs/api.md`
