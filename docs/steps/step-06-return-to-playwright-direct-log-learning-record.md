# Step 06 回到 Playwright 直读 log.html 学习记录

## 日期

2026-05-21

## 本步骤解决的问题

之前在原 Debian 服务器上验证时，`Test Logs` 对应的 `log.html` 出现：

```text
Windows 可以打开
Debian 服务器无法打开
```

这曾导致项目临时转向 Plan B 和邮件结果源。但新的验证发现，换到 `10.57.159.149`（`tl813-agent`，之前 `jenkins_robotframework` 项目的服务器）后，Debian 浏览器可以直接打开同类 `log.html`。

因此当前结论调整为：

```text
Playwright 直读 log.html 方案仍然可行。
部署服务器应优先选择 10.57.159.149 / tl813-agent。
邮件结果源暂时放弃，不作为主路线。
```

## 修改的文件及原因

```text
README.md
```

恢复主路线描述为 Reporting Portal + Playwright + `log.html`。

```text
docs/overview/roadmap.md
```

将当前主路线从“邮件结果源优先”改回“Playwright 直读 `log.html` 优先”，并记录 `10.57.159.149` / `tl813-agent` 的服务器选择依据。

```text
docs/overview/initial-plan-and-validation.md
```

补充 `tl813-agent` 可打开 `log.html`、手工 Chrome 会遇到证书告警、Playwright 使用 `ignore_https_errors=True` 的设计说明。

```text
deploy/server_runtime_setup.md
```

补充在 `tl813-agent` 上验证 `extract-log-url` 的命令、预期结果和失败模式。

```text
docs/steps/step-06-return-to-playwright-direct-log-learning-record.md
```

记录本次路线回切的原因、核心流程、验证命令和复查问题。

## 核心调用流程

```text
Reporting Portal filtered URL
-> collect Test Logs links
-> log.html URL
-> Playwright launch_persistent_context(ignore_https_errors=True)
-> read body.inner_text()
-> extract failed case message / failed keyword / failure text
-> rule classifier
-> Morning Report
```

## 关键字段

```text
server = 10.57.159.149 / tl813-agent
log_url
response_status
body_text_length
body_text_sample
failed_case_count
failed_cases
classification
```

## 服务器端验证命令

在 `10.57.159.149` / `tl813-agent` 上执行：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
PYTHONPATH=agent python -m triage_agent extract-log-url \
  --url "https://10.70.226.9/logs/WebTrigger/SBTS26R2/SBTS26R2_ENB_0000_000406_000000/4654/CRT/VRF_HAZ_T06/7_5_UTE5G402T273/artifact/quicktest/retry-0/ca_cases/log.html"
```

预期结果：

```text
status = ok
response_status = 200
body_text_length > 0
failed_case_count 有输出
failed_cases 在日志存在 failed case 时不为空
```

如果先验证 Reporting Portal 到 log URL 的完整链路：

```bash
PYTHONPATH=agent python -m triage_agent health
PYTHONPATH=agent python -m triage_agent collect-links \
  --scope cit_7_5_UTE5G402T820 \
  --triage-only \
  --report-date 2026-05-21 \
  --max-rows 5
```

再从输出中选择一条 `log_url` 执行 `extract-log-url`。

## 常见失败模式

```text
Your connection is not private
NET::ERR_CERT_AUTHORITY_INVALID
```

手工 Chrome 会看到该隐私告警。这是内部日志服务器证书问题。项目内 Playwright context 已使用 `ignore_https_errors=True`，CLI 正常情况下应绕过该告警。

```text
status = navigation_failed
net::ERR_CONNECTION_CLOSED
chrome-error://chromewebdata/
```

当前服务器仍无法访问目标日志静态服务器。确认是否在 `10.57.159.149` / `tl813-agent` 上运行，而不是原来不可访问的 Debian 服务器。

```text
status = session_expired
```

Reporting Portal 登录态过期。重新用同一个 Playwright persistent profile 做 headed 登录，然后执行 `health`。

```text
failed_case_count = 0
```

该 `log.html` 可能是全 passed，或当前文本解析规则未覆盖该 Robot log 的失败结构。换实际 failed/not analyzed 的 `log_url` 验证。

## 给用户的复盘问题

```text
1. Agent 后续是否统一部署到 10.57.159.149 / tl813-agent？
2. tl813-agent 上的 Playwright headless 是否能像手工 Chrome 一样打开 log.html？
3. extract-log-url 是否能输出 body_text_length 和 failed_case_count？
4. 如果可以，下一步是否回到 collector -> log extractor -> classifier 的完整 Morning Triage 链路？
```
