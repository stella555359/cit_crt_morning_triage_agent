# CIT/CRT Morning Triage Agent 初始计划与验证记录

## 一句话定位

`CIT/CRT Morning Triage Agent` 是一个部署在 Debian 13 服务器上的浏览器自动化 + AI 辅助分析工具，用于每天早上自动进入 `reporting_portal`，筛选昨晚指定软件包 / testline 下的 CIT/CRT Robot case，找出黄色 `not analyzed` 结果，打开 `Test Logs` 对应的 `log.html`，提取每个 failed case 内部的失败信息，并生成 Web Morning Report 供测试工程师在 Windows 本机浏览器中复核。

## 真实人工流程

当前人工流程是：

```text
每天早上打开 reporting_portal
-> 按软件包 / testline / CIT robotcase 过滤昨晚结果
-> 找黄色 not analyzed
-> 点击 Log 列下面的 Test Logs
-> 进入 log.html
-> 查看每个 failed case 的失败 Message 和失败 step
-> 如果是 gNB 软件问题，人工报 PR，并把 not analyzed 改为 failed
-> 如果是环境 / UE / 非 gNB 软件问题，人工建 ticket，并把 not analyzed 改为 passed
```

Agent 第一版只覆盖“收集 + 解析 + 初步归因 + 报告展示”，不覆盖报 PR、建 ticket、修改 `reporting_portal` 状态。

## Agent 边界

Agent 负责：

- 使用 Playwright 复用 `reporting_portal` 登录态。
- 打开带 query 参数的 filtered `test-runs` URL。
- 找到目标 testline 下的 `not analyzed` / `origin result = failed` 行。
- 提取每行的 `Test Logs` URL。
- 打开 `log.html`。
- 提取 failed case 内部的 case-level message 和 failed keyword 证据。
- 用规则做第一层分类。
- 用 LLM 做解释增强，但不能替代人工结论。
- 存储分析结果并通过 Web 前端展示 Morning Report。

Agent 不负责：

- 不直接使用 Jenkins API 或 Jenkins token。
- 不自动报 PR。
- 不自动建 ticket。
- 不自动修改 `reporting_portal` 里的结果状态。
- 不绕过权限，只自动化测试工程师本人已经能在页面上完成的读取和分析动作。

## 已验证可行性

### 1. Debian 服务器可以访问 `reporting_portal`

在 Debian 13 服务器上用 Playwright headless 访问：

```text
https://rep-portal.ext.net.nokia.com/reports/test-runs/
```

结果：

```text
title: Reporting Portal
url: https://rep-portal.ext.net.nokia.com/login/?next=%2Freports%2Ftest-runs%2F
text sample: Reporting Portal / Log in / Waiting for Microsoft Azure / SSO LOG IN
```

结论：

```text
服务器网络和 Playwright 基础访问可行，页面跳转到 SSO 登录页。
```

### 2. Playwright persistent profile 可以复用登录态

使用 profile：

```text
/home/ute/reporting-portal-profile
```

先用 `headless=False` 手工登录一次，再用 `headless=True` 复用 profile 验证。

结果：

```text
title: Test Runs
url: https://rep-portal.ext.net.nokia.com/reports/test-runs/?columns=...&limit=25
text length: 5034
```

结论：

```text
persistent login session 可用，headless 模式能进入 /reports/test-runs/，不再跳回 login 页面。
```

补充发现：

```text
persistent profile 不是永久凭据，只在 SSO/MSAL session 有效时可用。
后续重新验证时出现 "No active accounts found. Trying to login silently..."，
页面停留在 Loading... + footer，所有 filtered URL 都无法加载 Test Runs 表格。
```

因此 Agent 每次扫描前必须先做登录健康检查，不能把 `Loading...` 误判为“没有数据”。

健康检查规则：

```text
if console contains "No active accounts found"
or body text is only "Loading..." + footer
or body contains "SSO LOG IN"
or "Test Runs" table is not loaded within 30 seconds:
    mark session_expired
    stop scan
    show re-login handoff
```

Web UI / 日志中应显示：

```text
reporting_portal login expired, manual re-login required
```

### 3. URL query 参数过滤 testline 可行

验证 URL：

```text
https://rep-portal.ext.net.nokia.com/reports/test-runs/?columns=%3Ahash%3Abd74cf67846066c9841ec0ee24147833&limit=100&test_line=7_5_UTE5G402T820
```

结果：

```text
Filtered by:
Test Line:
7_5_UTE5G402T820
contains target: True
```

页面文本中能看到：

```text
Test Logs
https://10.70.226.9/logs/WebTrigger/SBTS00/SBTS00_ENB_9999_260518_000007/4807/CRT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-0/ca_cases/log.html
...
not analyzed
failed
...
```

结论：

```text
Agent 不需要模拟 UI 输入过滤框，优先直接拼 filtered URL，更稳定。
```

### 4. filtered page 可以提取 `Test Logs` 和 `details/test-report` 链接

已验证 headless Playwright 能读取 `<a>` 链接。

示例输出：

```text
TEXT= Test Logs
HREF= https://10.70.226.9/logs/WebTrigger/SBTS00/SBTS00_ENB_9999_260518_000007/4807/CRT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-0/ca_cases/log.html

TEXT= 8639a104cfc63bc4b6e26db71dba2877
HREF= /details/test-report/45872365/
```

结论：

```text
每条 row 的 log.html URL 和 report detail URL 都能从页面链接中提取。
```

### 5. 直接打开 `log.html` 并读取页面文本可行

验证 URL：

```text
https://10.70.226.9/logs/WebTrigger/SBTS00/SBTS00_ENB_9999_260518_000007/4807/CRT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-0/ca_cases/log.html
```

结果：

```text
title: Ca Cases Log
text length: 54064
contains Test Execution Errors: True
contains ERROR: True
```

结论：

```text
Agent 能通过 Playwright 直接读取 log.html 文本。
```

注意：脚本示例中只打印了 `text[:5000]`，不是只能读取前 5000 字符。实际已读取到 54064 字符。

### 6. `Download zip` 也可通过 reporting_portal 登录态触发

已验证 report detail 的下载 URL 能触发下载：

```text
https://rep-portal.ext.net.nokia.com/at/test-reports/45873334/download/
```

结果：

```text
suggested filename: robot_report.zip
saved as: /home/ute/test-report-45873334.zip
```

但该 zip 解压后可能只有 JSON，是否包含 `log.html` / `output.xml` 取决于具体 report。第一版不依赖 zip，保留为 fallback。

## 关键设计修正

### 不使用 `Test Execution Errors` 作为主要证据

页面顶部的 `Test Execution Errors` 不作为 triage 主证据。原因：

- 里面可能包含 import warning、deprecation warning、初始化变量错误。
- 它不一定等于最终 Robot case 的失败原因。
- 日常人工分析真正关注的是 failed case 内部的 `Message` 和 failed step。

第一版明确忽略：

```text
Test Execution Errors
WARN
import warning
deprecated warning
library contains no keywords
Robot 初始化阶段 ERROR
```

### 正确解析目标

Agent 应优先解析每个 failed test case 内部：

```text
TEST 节点
-> Full Name
-> Tags
-> Status: FAIL
-> Message
-> failed keyword
-> failed keyword 下的 FAIL / traceback
-> parent keyword chain
```

示例有效证据：

```text
Status: FAIL
Message:
CannotAttachError: Cell id is not changed for UE: 6306e004
Check UE logs if proper serving cell is being heard.
```

failed keyword 示例：

```text
KEYWORD Ue attach UE ${ue_index}
FAIL CannotAttachError: Cell id is not changed for UE: 6306e004
```

这类证据用于分类和报告，不使用页面顶部 `Test Execution Errors`。

## 解析策略

### 第一版文本解析

先不强依赖 Robot `output.xml`，因为实际工作中直接可访问的是 `log.html`。

第一版可以基于 `body.inner_text()` 做文本解析：

```text
找到 "Status:\nFAIL"
向上提取 TEST name / Full Name / Tags
向下提取 Message
继续向下找第一个 FAIL 行
提取 failed keyword 附近上下文
```

### 后续增强 DOM 解析

如果文本规则不稳定，再用 Playwright 定位 Robot log 的 DOM 节点：

```text
展开 failed TEST
展开 failed keyword
读取该节点下 FAIL message 和 traceback
```

### fallback

如果 `log.html` 信息不足：

```text
进入 /details/test-report/<id>/
-> Download zip
-> 解压
-> 尝试解析 output.xml / JSON / report files
```

## 初始分类规则

第一版分类不要太多：

```text
product_bug_candidate
ue_or_radio_issue
environment_issue
testline_config_issue
robot_script_issue
jenkins_or_infra_issue
known_issue
need_manual_check
```

规则示例：

```text
CannotAttachError / UE logs / serving cell is being heard
-> ue_or_radio_issue

Variable not found / Keyword not found / library contains no keywords
-> robot_script_issue 或 testline_config_issue

NoneType default_ssh_connection_details / tl.attenuator / tl.test_pcs
-> testline_config_issue

No route to host / connection refused / ssh timeout
-> environment_issue

Jenkins workspace / checkout / permission / disk full
-> jenkins_or_infra_issue

Assertion failed / KPI below threshold / unexpected gNB response
-> product_bug_candidate
```

## Morning Report Web 展示

最终报告不要求用户下载 HTML 文件，而是展示在 Web 前端。

建议页面：

```text
https://<debian-server>/triage/
```

### Summary 区域

```text
Date
Build / Load
Testline scope
Total not analyzed
Parsed successfully
Suspected product bug
Suspected UE / environment issue
Suspected script / config issue
Need manual check
```

### Case 列表

每行显示：

```text
testline
robotcase
build
run type: CIT / CRT / CDRT
original result
reporting status: not analyzed
suggested category
confidence
case message summary
log.html link
```

### Case 详情

```text
Full Name
Tags
Status
Case Message
Failed Keyword
Failure Text
Keyword Chain
Suggested Category
Evidence
Suggested Next Action
Human Review Fields
```

### 人工复核字段

第一版只记录，不回写 `reporting_portal`：

```text
human_final_category
PR ID
ticket ID
review note
reviewed_at
```

这些字段后续可形成评测集和训练/微调数据。

## 推荐技术架构

```text
systemd timer / manual trigger
-> Playwright persistent profile
-> login health check
-> reporting_portal filtered URL
-> extract not analyzed rows
-> open log.html
-> parse failed case message and failed keyword
-> rule-based classifier
-> optional LLM explanation
-> SQLite
-> FastAPI
-> React Morning Report dashboard
-> Nginx HTTPS
-> Windows browser
```

## MVP 分阶段

### Phase 0：可行性验证（已完成大部分）

- [x] Playwright 能打开 reporting_portal。
- [x] persistent profile 能复用登录态。
- [x] 已确认 persistent profile 依赖有效 SSO/MSAL session，session 可能过期。
- [x] filtered URL 能按 testline 过滤。
- [x] 能提取 `Test Logs` 链接。
- [x] 能打开 `log.html` 并读取文本。
- [x] 能触发 `Download zip`，但暂不作为主路径。
- [ ] 实现扫描前登录健康检查和重新登录交接提示。
- [ ] 验证从 `log.html` 中稳定提取 case-level `Status: FAIL` / `Message` / failed keyword。

### Phase 1：离线脚本 MVP

目标：

```text
输入 filtered URL
输出 JSON triage result
```

功能：

- 提取 not analyzed rows。
- 提取 `log.html`。
- 解析 failed case message。
- 规则分类。
- 输出 `triage_result.json`。

### Phase 2：Web Report MVP

目标：

```text
FastAPI + SQLite + React 展示 Morning Report
```

功能：

- 手动触发一次 triage run。
- 存储 triage cases。
- 展示 summary 和 case list。
- 展示 case detail。
- 支持人工复核字段。

### Phase 3：定时 Agent

目标：

```text
每天早上自动运行
```

功能：

- systemd timer 或 cron。
- 多 testline / 多 build 配置。
- 登录态过期检测。
- 失败时在 Web 页面显示 `login expired` 或 `portal unavailable`。

### Phase 4：LLM 增强

目标：

```text
规则先分类，LLM 只做解释增强
```

功能：

- 输入结构化 evidence。
- 输出自然语言解释和 next action。
- 不给确定 root cause。
- 输出需带 confidence 和 need_manual_check。

## 风险与应对

| 风险 | 应对 |
|---|---|
| `reporting_portal` 登录态过期 | 每次扫描前做 login health check；Web 页面显示 `login expired`，人工用 persistent browser 重新登录 |
| 页面 URL 参数变化 | 保存手工过滤后的 URL 模板，优先配置化 |
| `log.html` DOM 结构变化 | 第一版使用文本解析，后续再补 DOM parser |
| `Test Logs` URL 无法访问 | 使用 report detail 的 download zip fallback |
| AI 过度判断 root cause | 规则先分类，LLM 只解释证据，并输出 `need_manual_check` |
| 误报 product bug | 不自动报 PR，不自动改状态，人工复核后再行动 |

## 面试表达

可以这样描述：

```text
我把每天 CIT/CRT 回归分析流程抽象成 Morning Triage Agent。它部署在 Debian 服务器上，通过 Playwright 复用 reporting_portal 登录态，自动打开按 testline / build 过滤后的 test-runs 页面，抓取黄色 not analyzed 的 Robot case，进入 Test Logs 的 log.html 页面，提取 failed case 内部的 Message 和 failed keyword，再用规则和 LLM 做初步归因，最后通过 Web dashboard 展示给测试工程师复核。

这个 Agent 不自动报 PR、不自动建 ticket、不自动修改 reporting_portal 状态，只负责收集、解析、初步分类和证据整理。这样既符合权限边界，也能减少每天人工逐个点 log.html 查失败点的重复劳动。
```

## 下一步最小任务

下一步应先实现 `log.html` failed case extractor 的原型：

```text
输入：单个 log.html URL
输出：
- full_name
- tags
- status
- case_message
- failed_keyword
- failure_text
- keyword_chain
```

完成后再接入 filtered reporting portal row extraction.
