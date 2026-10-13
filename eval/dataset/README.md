# 评测基准数据集（待填）

> **当前状态：空**（`cases.json` 与 `labels.json` 都是 `[]`）。
> 这份数据集是 `docs/ROADMAP.md §4` 的"证据基准"，也是 PRD §6 那四项指标的**唯一**来源。
> 规格在 `docs/EVAL.md §2`，本文件只讲"怎么填、填完怎么验"。

## 两个文件

| 文件 | 内容 |
|---|---|
| `cases.json` | 语料：`[{ "id": "case-001", "source": "选段原文", "origin": "《XX》XX篇（版本）" }]` |
| `labels.json` | 标注：`docs/EVAL.md §2.3` 的字段，一个错误点一条 |

`origin`（版本出处）不是可选项——`docs/EVAL.md §2.1` 要求来源清单进附录，合规要用。

## 填的时候按这个顺序

1. **选段**：公共版权古籍通行本，每段 **200–500 字**，共 **10 段**（v1）。
   - **避开《论语》学而篇**：它是校勘 Prompt 的 few-shot 示例，放进来会污染评测。
     `self_check` 会认出 few-shot 片段并报错。
   - **体裁分散**（史书 / 诸子 / 骈文 / 笔记各来几段）：10 段同一部书，指标只反映一种文体。
   - **保持一整行**：换行符也按 1 个字计入，多行会高估字数、也让选段不再是一段连续的文。
2. **每段同时具备两类错误**：天然 OCR 错误（真实分布）+ 人工注入错误（保证五类都有样本）。
   - 讹字：形近替换（`伐`→`代`）　衍文：误重一字（`舍去`→`舍舍去`）　脱文：脱虚实字（`其名为鲲`→`其名鲲`）
   - **通假不注入**：通假不是错误而是用字现象，样本取自原文本身（`source` 填 `inherent`）
   - 异文：换成**有版本依据的**他本写法，并在 `note` 里注明依据
3. **不要手数索引**——这是标注里唯一的系统性错误来源。把选段存成**标记文件**
   （放 `docs/eval/annotate/`，过程材料不入库），用 `[[原文|权威写法|类型|来源|备注]]` 标出每个点，
   索引由 `eval/mark_to_labels.py` 算：

```bash
python -m eval.mark_to_labels docs/eval/annotate/case-001.marked.txt    # 先人眼核对区间，不写盘
python -m eval.mark_to_labels docs/eval/annotate/*.marked.txt --write   # 确认后写进数据集
```

   标记文件顶部可写元信息（`# caseId: case-001` / `# origin: 《左传·庄公十年》（杨伯峻注本）`），
   `caseId` 也能从文件名推断（`case-001.marked.txt`）。后三段可省：只写 `[[原|改]]` 时类型留作
   「待定」——脚本**不猜类型**（猜错会污染逐类指标，而自检查不出来）；`来源` 默认 `injected`；
   **异文没写备注时 `hasEditionEvidence` 自动为 `false`**（没给别本依据就等于没有依据）。
4. **配额**：五类各 **≥10**，总量 **≥60**。
5. **标注 `start`/`end` 用左闭右开区间**，且必须满足 `source[start:end] == original`。
   上面那条命令保证了这一点，但仍要跑自检兜底：

```bash
python -m eval.self_check eval/dataset/     # 不通过就别往下走
```

6. **异文类的 `expectedSuggestion` 必须填别本写法**，不能与 `original` 相同
   （与 `docs/API.md §2` 的契约同一条；`self_check` 会拦）。
7. **`hasEditionEvidence`**：该点能否凭版本判定。异文类填 `false` 时，模型报它按**存疑**处理
   （既不算检出也不算误报，见 `docs/EVAL.md §3.5`）。
8. **两人复核**：标注人自检后，第二人至少抽 **20%** 复核。
   这一步机器验不了，请在报告里写明复核人编号与抽样比例。

## 填完怎么确认

```bash
python -m eval.self_check eval/dataset/            # 必须 0 error
python -m eval.self_check eval/dataset/ --json     # 机器可读，供脚本/CI 调用
```

输出里会带逐类配额与总量；只有 `warn`（复核比例提醒）是正常的。

## 不许做的事

- **不许把测试夹具当基准**：`eval/tests/fixtures/` 下的东西只用于验证脚本，不是证据。
- **不许为了指标好看而删难例**：漏报的点要留着，它就是召回率的分母。
- **不许改口径来迁就结果**：口径改动只走 `docs/EVAL.md`，并说明理由与影响。
