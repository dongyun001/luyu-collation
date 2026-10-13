# 评测工具（eval/）

> 这套脚本是 **`docs/EVAL.md` 的可执行版本**。它**不定义口径**——口径在 `docs/EVAL.md`，
> 这里只负责按口径算、按口径出报告。两边冲突时以 `docs/EVAL.md` 为准，并**先改文档再改代码**。
>
> 目录位置的规矩见 `docs/EVAL.md §8.1`：**脚本与标注集进仓库**（`eval/`），
> **问卷原始答卷留 `docs/eval/survey/`**（含个人信息风险，不入仓库）。

## 一句话职责

| 文件 | 干什么 | 什么时候用 |
|---|---|---|
| `mark_to_labels.py` | 标记文本 → 标注 JSON：`[[原文\|权威写法\|类型\|来源\|备注]]`，**索引由脚本算** | 标注时（先标后写） |
| `self_check.py` | 标注自检：区间错位、id 缺失/重复、类型/来源非法、GT 重叠、五类配额、few-shot 污染 | **标完就跑**，不通过就别往下走 |
| `run_compare.py` | 对比实验：走真实 HTTP 跑全量用例，产出 `*.raw.json` | 要出数字时 |
| `judge.py` | 判定：区间匹配、检出/分类分离、存疑、双 precision、分层；产出 `*.points.csv` 与复核清单 | 跑完实验后 |
| `report.py` | 汇总成 Markdown / JSON / CSV（可进佐证材料） | 判定之后 |
| `survey_stats.py` | 问卷统计：正向比例（4–5 计正向）、NPS、选项分布、开放题原话；逐题缺失剔除不填补 | 问卷回收后 |
| `timing_stats.py` | 效率实验：两组均值、效率倍数 = 人工均值 ÷ 辅助均值、**Bootstrap 95% 置信区间** | 计时表填完后 |

## 完整流程

```bash
# 0) 标注（人工）：先标后写，索引别手数
python -m eval.mark_to_labels docs/eval/annotate/case-001.marked.txt   # 人眼核对区间
python -m eval.mark_to_labels docs/eval/annotate/*.marked.txt --write  # 写进 eval/dataset/

# 0b) 标注自检（EVAL §9 前三条）
python -m eval.self_check eval/dataset/

# 1) 起后端（.env 里要有真实密钥）
npm run dev:server

# 2) 跑对象（每个供应商/配置一个 --label；--base-url 指向该配置的后端）
python -m eval.run_compare --label mimo        --base-url http://localhost:3001
python -m eval.run_compare --label siliconflow --base-url http://localhost:3001
# 消融对照：把后端以 COLLATE_RULES_ENABLED=false 起一次，再跑一个 label
python -m eval.run_compare --label ablate-rules --base-url http://localhost:3001

# 3) 判定（会顺便写出复核清单）
python -m eval.judge --dataset eval/dataset/ --results eval/results/

# 4) 人工裁决 GT 之外的建议（EVAL §3.4：这一步**必须人做**）
#    编辑 eval/results/review.csv，把 verdict 填成 extra-valid / extra-invalid / duplicate / out-of-scope
python -m eval.judge --dataset eval/dataset/ --results eval/results/ --review eval/results/review.csv

# 5) 出报告
python -m eval.report --results eval/results/ --out docs/eval/report

# 6) 问卷与效率实验（口径见 SURVEY §5；只在试点之后才有数据）
python -m eval.survey_stats docs/eval/survey/post.csv --issued 20 \
    --likert q1,q2,q3,q4,q5,q6,q7 --nps q8 --single q9 --multi q10 --open q11 \
    --out docs/eval/survey/post_stats.md --open-out docs/eval/survey/open_answers.csv
python -m eval.timing_stats docs/eval/survey/timing.csv --out docs/eval/survey/timing_stats.md
```

## 问卷与计时口径（两个统计脚本）

- **正向 = 4–5 分**（3 分不算正向）；**有效份数 = 填齐全部量表题**；量表题缺失按「未作答」
  **逐题剔除，不填补**。脚本会在这些地方打印提醒（样本量不足、回收率偏低、各题作答数不一致）。
- **必须给区间**。人少时均值极不稳——3 人组的 Bootstrap 区间能宽到跨过 3 倍这条线，
  脚本默认输出 95% 区间就是为了让报告不能只写点估计。种子固定（`BOOTSTRAP_SEED`），
  换机器跑出的区间一致，这才谈得上复现。
- **开放题只导出原话**，不做情绪打分、不替团队归纳主题——主观解读不能当数据。
- 列名不猜：用 `--likert/--nps/--single/--multi/--open` 显式指定（问卷平台导出的表头千奇百怪）。

## 几条不能忘的纪律

1. **不要在判定器里"补"口径**。口径只有 `docs/EVAL.md` 一处；要改先改那儿。
2. **GT 之外的建议必须人工裁决**（`review.csv`）。没裁决的**保守计入 FP**——
   绝不自动算成"正确"，那等于自己给自己发分。
3. **结果要能追溯**：`run_compare` 会在每次运行前读 `/health`，把当前生效的
   Prompt 版本、规则开关、温度写进 `*.raw.json`，`judge` 再带进 `*.points.csv`。
   不要手写这些字段。
4. **限流要等，不要跳过**：命中 429 时执行器等一个窗口（61s）再继续；跳过会让样本不齐。
5. **报告不要手改**：数字对不上时，回到 `eval/results/*.points.csv` 找原因。

## 实测经验（2026-10-13，冒烟）

- **消融开关的效果只体现在"高置信层"的指标上**。规则（形近/通假字表 +0.1）只改
  `confidence`，不改检出集合，所以"全部返回"层的 P/R 在开/关下**完全一样**；
  它改变的是条目**是否越过 0.7 这条线**，从而影响高置信层的数字。
  看消融是否真的起作用，**要比高置信层**，并核对 `rulesEnabled` 列与 `confidence` 列
  （同一点开/关分别是 1.0 / 0.95）。
- 冒烟用的假模型夹具在 `eval/tests/fixtures/smoke_dataset/`，**只用于验证脚本链路**；
  它过不了 `self_check` 的配额检查（只有 4 个点），这是预期的——真基准在 `eval/dataset/`。
