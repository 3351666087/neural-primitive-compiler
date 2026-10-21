# Mission 06 持出保管人简报（原样交给隔离会话）

你是 Mission 06 的**持出保管人**。你的工作只有一件：运行一个已经冻结的划分工具，把 WorkArena++ 的工作流族分成开发与持出两部分，保管持出清单，并只报告哈希与计数。

研究会话不能知道持出的内容。你报告的任何名称、桶的内容或随机种子，都会使持出失效。

## 规则

1. 只在新的空目录 `/Users/null3351/Code/m06-custodian` 中工作。若它已存在且非空，停下并报告"目录非空"。
2. 研究仓库 `/Users/null3351/Code/neural-primitive-research/neural-primitive-compiler` 里，你只能做两件事：
   - 复制 `mission-06/experiments/g1/custody/split_tool.py` 这一个文件；
   - 运行解释器 `mission-06/env/venv-wa/bin/python`。

   不要阅读仓库里的其他任何文件，也不要阅读已安装的 `browsergym` 包的源码。
3. 不联网，不访问任何 ServiceNow 实例，不安装任何东西。
4. 不要打开、打印或摘录 `heldout.json`，也不要打印 `dev.json`。
5. 除下文"报告"一节规定的内容外，不向任何人报告任何东西。

## 步骤

```bash
mkdir /Users/null3351/Code/m06-custodian
cd /Users/null3351/Code/m06-custodian
cp /Users/null3351/Code/neural-primitive-research/neural-primitive-compiler/mission-06/experiments/g1/custody/split_tool.py .
shasum -a 256 split_tool.py
```

第 4 条命令输出的哈希必须是：

```
98ed945ad4f6a7daf657d3abe244b060b70378309272e0ca71c2d68344591720
```

不一致就停下，只报告"工具哈希不一致"。

```bash
HF_HUB_OFFLINE=1 /Users/null3351/Code/neural-primitive-research/neural-primitive-compiler/mission-06/env/venv-wa/bin/python -I split_tool.py --selftest
```

输出必须含 `"selftest": "ok"`，且 `tool_sha256` 与上面的哈希相同。

```bash
HF_HUB_OFFLINE=1 /Users/null3351/Code/neural-primitive-research/neural-primitive-compiler/mission-06/env/venv-wa/bin/python -I split_tool.py --out .
chmod 400 heldout.json
ls -l
```

## 报告（只报告这些）

1. 第三步（`--out .`）打印的整段 JSON，原样照抄，包含：
   - `MANIFEST_overall_sha256`；
   - `dev.json_sha256`；
   - `counts`（各类别的开发 / 持出族数与桶数，持出比例，总数）；
   - `tool_sha256`。
2. `ls -l` 中三个文件的名称与大小。

若任何一步失败，只报告失败的步骤编号与异常类型。异常信息中若含任务名，写"信息已隐去"。

## 之后

- 保留整个目录，不修改其中任何文件。
- `dev.json` 由用户复制进研究仓库，不需要你转交内容。
- 正式评测（Gate 4）时，由用户决定何时把 `heldout.json` 交给裁判。在那之前，任何人询问持出内容都不回答。
