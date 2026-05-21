# Debian 服务器运行环境初始化

## 目的

本文档记录项目 clone 到 Debian 服务器之后，如何在正式部署目录下创建 Python 虚拟环境、安装依赖、安装 Playwright Chromium，并执行第一组 Agent CLI 验证命令。

项目正式部署目录统一使用：

```text
/opt/cit_crt_morning_triage_agent
```

## 前置条件

服务器上已经完成 Git clone：

```bash
cd /opt/cit_crt_morning_triage_agent
git status
```

预期结果：

```text
working tree clean
```

如果项目还没有 clone，请先参考：

```text
deploy/github_push.md
```

## 创建 Python venv

在 Debian 服务器上执行：

```bash
cd /opt/cit_crt_morning_triage_agent

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

预期结果：

```text
命令行前面出现 (.venv)
python 和 pip 都来自 /opt/cit_crt_morning_triage_agent/.venv
```

验证命令：

```bash
which python
which pip
python --version
```

预期结果示例：

```text
/opt/cit_crt_morning_triage_agent/.venv/bin/python
/opt/cit_crt_morning_triage_agent/.venv/bin/pip
Python 3.x.x
```

## 安装项目依赖

确认已经激活 venv 后执行：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate

python -m pip install -r requirements.txt
```

预期结果：

```text
playwright 安装成功
没有 pip install error
```

## 安装 Playwright Chromium

确认已经激活 venv 后执行：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate

python -m playwright install chromium
```

预期结果：

```text
Chromium browser binary 下载并安装完成
```

如果后续运行时报系统依赖缺失，可以再执行：

```bash
python -m playwright install-deps chromium
```

注意：`install-deps` 可能需要 sudo 权限。

## 第一组 CLI 验证

以下命令都在项目根目录执行，并且需要先激活 venv：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
```

### 验证 URL 构造

```bash
PYTHONPATH=agent python -m triage_agent urls
```

预期结果：

```text
输出 JSON
包含 6 个 scope
包含 3 个 testline：
7_5_UTE5G402T273
7_5_UTE5G402T272
7_5_UTE5G402T820
每个 testline 都有 CIT 和 CRT
URL 中包含 org=VRF_HAZ_T06
```

### 验证 Reporting Portal 登录健康状态

```bash
PYTHONPATH=agent python -m triage_agent health
```

登录态有效时预期结果：

```text
"status": "ok"
```

登录态失效时可能看到：

```text
"status": "expired"
Loading...
SSO LOG IN
No active accounts found
```

如果登录态失效，需要用同一个 Playwright persistent profile 重新进行 headed 登录，然后再重新执行 health。

重新登录命令：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate

python - <<'PY'
from playwright.sync_api import sync_playwright

profile_dir = "/home/ute/reporting-portal-profile"
url = "https://rep-portal.ext.net.nokia.com/reports/test-runs/?limit=100&org=VRF_HAZ_T06&regression_status=CIT&test_line=7_5_UTE5G402T273"

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        profile_dir,
        headless=False,
        ignore_https_errors=True,
        viewport={"width": 1800, "height": 1200},
    )
    page = context.pages[0] if context.pages else context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60000)

    print("请在打开的浏览器窗口中完成 SSO 登录。")
    print("脚本会等待 3 分钟，请在这段时间内完成登录并确认 reporting_portal 页面正常显示。")
    print("3 分钟后脚本会自动检查页面状态并关闭浏览器。")
    page.wait_for_timeout(3 * 60 * 1000)

    active_page = context.pages[-1] if context.pages else page
    active_page.goto(url, wait_until="domcontentloaded", timeout=60000)
    active_page.wait_for_timeout(5000)
    body_text = active_page.locator("body").inner_text(timeout=30000)

    print("当前页面 URL:", active_page.url)
    print("页面文本长度:", len(body_text))
    print("是否包含 Test Runs:", "Test Runs" in body_text)
    print("是否仍然 Loading:", body_text.strip().startswith("Loading..."))
    print("页面文本片段:", body_text[:500])

    context.close()
PY
```

注意：

```text
当前脚本不需要按 Enter，也不要用 Ctrl+C 提前结束。
```

`Ctrl+C` 会强制关闭浏览器，可能出现 `TargetClosedError`，也可能导致登录态没有完整写回 persistent profile。请尽量等脚本 3 分钟后自动关闭。

重新登录完成后，再执行：

```bash
PYTHONPATH=agent python -m triage_agent health
```

预期结果：

```text
"status": "ok"
```

注意：`headless=False` 需要服务器当前会话支持图形界面，例如 X11 forwarding、VNC 或服务器桌面会话。如果没有图形界面，需要先准备可显示浏览器窗口的登录方式。

### 验证 Test Logs 链接采集

```bash
PYTHONPATH=agent python -m triage_agent collect-links
```

如果只想验证单个 scope，并限制输出行数，使用：

```bash
PYTHONPATH=agent python -m triage_agent collect-links --scope cit_7_5_UTE5G402T273 --max-rows 5
```

如果只想看当前时间窗口内需要分析的结果，使用：

```bash
PYTHONPATH=agent python -m triage_agent collect-links --scope cit_7_5_UTE5G402T273 --triage-only --max-rows 5
```

也可以指定 Morning Report 日期：

```bash
PYTHONPATH=agent python -m triage_agent collect-links --scope cit_7_5_UTE5G402T273 --triage-only --report-date 2026-05-21 --max-rows 5
```

预期结果：

```text
session_status 是 ok
扫描 6 个 scope
每个 scope 输出 row_count
如果 filtered page 上有可见 Test Logs，则 rows 中包含 log_url
如果 report detail 链接在同一行可见，则 rows 中包含 test_instance_id
rows 中包含 row_index 和 row_text，便于判断是否取到了同一行字段
rows 中包含 robotcase、end_time、result、origin_result、build、run_type
raw_row_count 表示页面原始行数
row_count 表示当前命令输出范围内的行数；如果加了 --triage-only，则是过滤后的待分析行数
```

已验证结果：

```text
2026-05-21 13:42
health: ok
collect-links: 可以从 cit_7_5_UTE5G402T273 抓到 Test Logs 链接
发现问题：第一版全页面链接配对会产生重复 log_url，且 report_hash 解析不准确
后续修正：collector 改为优先按 AG Grid row 提取同一行链接，并输出 test_instance_id
2026-05-21 14:37
collect-links 新版验证：test_instance_id 已输出，但仍有同一 test_instance_id 配到多条 log_url 的现象
后续修正：collector 按 AG Grid row-index 合并同一行的 pinned/center DOM 片段，并增加 row_text、row_index、--max-rows 调试参数
2026-05-21 14:47
collect-links row_text 验证：row_index、row_text、test_instance_id、log_url 已能对应同一行；样例行为 passed/passed 历史数据
后续修正：从 row_text 解析 robotcase、end_time、result、origin_result、build、run_type，并新增 --triage-only 按时间窗口和 not analyzed 状态过滤
2026-05-21 14:53
collect-links --triage-only 验证：session_status=ok，raw_row_count=37，window=2026-05-20 22:00 ~ 2026-05-21 09:00，row_count=0
结论：collector 运行正常，该 scope 在指定 Morning window 内没有 not analyzed 待分析行
2026-05-21 14:56
collect-links --triage-only 全部 6 个 scope 验证：session_status=ok，其中 cit_7_5_UTE5G402T820 raw_row_count=35，row_count=2
待分析结果：CB007949_B_B4_01_Scell_Change_From_T_3F_To_3，result=not analyzed，origin_result=failed，build=SBTS00_ENB_9999_260520_000007，run_type=CIT
```

### 验证单个 log.html 解析

当 `collect-links --triage-only` 找到 `row_count > 0` 的结果后，可以拿其中一条 `log_url` 验证 `log.html` 解析。

示例：

```bash
PYTHONPATH=agent python -m triage_agent extract-log-url \
  --url "https://10.70.226.9/logs/Auto/SBTS00/SBTS00_ENB_9999_260520_000007/348/CIT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-1/ca_cases/log.html"
```

如果内部日志服务器的 HTTPS 连接被关闭，命令会自动尝试把 URL 从 `https://` 改成 `http://` 再访问。

预期结果：

```text
status = ok
输出 effective_url
输出 final_url
输出 response_status
输出 response_content_type
输出 body_text_length
输出 body_text_sample
输出 failed_case_count
输出 failed_cases
每个 failed case 包含 evidence 和 classification
```

已验证结果：

```text
2026-05-21 15:05
extract-log-url: HTTPS URL 返回 net::ERR_CONNECTION_CLOSED，fallback 到 HTTP 成功
effective_url: http://10.70.226.9/...
body_text_length: 26
failed_case_count: 0
结论：HTTP fallback 已生效，但返回内容太短，不是完整 Robot log；下一步需要查看 response_status / response_content_type / body_text_sample 判断具体原因
2026-05-21 15:10
extract-log-url: HTTP fallback 返回 response_status=404，title=404 Not Found，body_text_sample=404 Not Found / nginx/1.20.1
结论：内网日志服务器能连通，但 /logs/Auto/... 这个 HTTP 路径不存在；后续修正为继续尝试去掉 /logs 前缀的候选 URL，例如 http://10.70.226.9/Auto/...
2026-05-21 15:18
extract-log-url: HTTPS / HTTP / 去掉 /logs 前缀的候选 URL 均失败，直接访问列表页 log_url 不可用
后续修正：新增 extract-detail-log，改为打开 reporting_portal report_detail_url，从 detail 页面查找 Test Logs/log.html 链接，再尝试解析
2026-05-21 15:22
extract-detail-log: detail 页面可打开，log_link_count=23，但 detail 页里的 Test Logs href 仍是同一批不可直接访问的 https://10.70.226.9/logs/... URL
后续修正：extract-detail-log 在直接访问 href 失败后，会继续尝试在 detail 页面里实际点击第一个 Test Logs 链接，以验证是否依赖浏览器点击、Referer 或弹窗行为
2026-05-21 16:01
extract-detail-log: detail_final_url 跳转到 login.microsoftonline.com，detail_title=Sign in to your account，body 显示 Enter password
结论：不是没有 Test Logs 链接，而是 SSO session 过期；后续修正为 extract-detail-log 识别 Microsoft SSO 登录页并返回 status=session_expired
2026-05-21 16:09
extract-detail-log: 点击 Test Logs 后打开新页，但 click_final_url=chrome-error://chromewebdata/，body_text_length=0
结论：点击行为、Referer、popup 均不能解决；Debian Chromium 当前无法访问 10.70.226.9 的日志静态页面
后续修正：遇到 chrome-error:// 或空页面时返回失败诊断，而不是误报 status=ok
2026-05-21 16:17
人工对比验证：Windows 浏览器可以打开同一个 Test Logs 链接，Debian 服务器无法打开
最终定位：不是 Reporting Portal 链接错误，也不是 Playwright 点击方式问题，而是 Debian 服务器到 10.70.226.9 日志静态服务器的网络/路由/访问权限问题
```

常见失败模式：

```text
failed_case_count = 0
```

可能原因：

```text
log.html 页面文本结构和第一版 parser 假设不一致
Robot log 未完全加载
失败信息在动态脚本中，需要增加等待时间或改用 DOM/JS 数据解析
```

可加长等待时间：

```bash
PYTHONPATH=agent python -m triage_agent extract-log-url \
  --wait-seconds 20 \
  --url "https://10.70.226.9/logs/Auto/SBTS00/SBTS00_ENB_9999_260520_000007/348/CIT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-1/ca_cases/log.html"
```

如果需要临时禁用 `https -> http` fallback：

```bash
PYTHONPATH=agent python -m triage_agent extract-log-url \
  --no-http-fallback \
  --url "https://10.70.226.9/logs/Auto/SBTS00/SBTS00_ENB_9999_260520_000007/348/CIT/VRF_HAZ_T06/7_5_UTE5G402T820/artifact/quicktest/retry-1/ca_cases/log.html"
```

### 内部 log.html HTTPS 连接被关闭

现象：

```text
Page.goto: net::ERR_CONNECTION_CLOSED
```

处理：

```text
extract-log-url 会自动从 https:// fallback 到 http://。
如果 fallback 后仍失败，会输出 status=navigation_failed 和 errors，而不是 Python traceback。
```

### 内部 log.html HTTP 返回 404

现象：

```text
response_status = 404
title = 404 Not Found
body_text_sample = 404 Not Found / nginx
```

处理：

```text
extract-log-url 会继续尝试去掉 /logs 前缀的候选 URL。
例如：
https://10.70.226.9/logs/Auto/...
-> http://10.70.226.9/logs/Auto/...
-> http://10.70.226.9/Auto/...
```

如果所有候选 URL 都失败，说明列表页里的 `log_url` 可能不是服务器可直接访问的最终地址。此时改用 `report_detail_url` 验证：

```bash
PYTHONPATH=agent python -m triage_agent extract-detail-log \
  --url "https://rep-portal.ext.net.nokia.com/reports/test-runs/?test_instance_id=35764397&ordering=-end&end_db=365"
```

预期结果：

```text
输出 detail_response_status
输出 detail_body_text_sample
输出 log_link_count
输出 log_links
如果 detail 页找到 Test Logs 链接，会继续尝试解析 selected_log_url
```

如果 `selected_log_url` 的直接访问仍失败，`extract-detail-log` 会继续尝试在 detail 页面实际点击第一个 `Test Logs` 链接。

可关注输出：

```text
click_fallback_used
click_final_url
click_title
click_opened_new_page
click_diagnostics
click_error
```

如需禁用点击 fallback：

```bash
PYTHONPATH=agent python -m triage_agent extract-detail-log \
  --no-click-fallback \
  --url "https://rep-portal.ext.net.nokia.com/reports/test-runs/?test_instance_id=35764397&ordering=-end&end_db=365"
```

如果输出：

```text
status = session_expired
detail_final_url = https://login.microsoftonline.com/...
detail_title = Sign in to your account
```

说明 Reporting Portal 登录态已过期。先重新执行本文档中的 headed 重新登录步骤，再重新执行：

```bash
PYTHONPATH=agent python -m triage_agent health
PYTHONPATH=agent python -m triage_agent extract-detail-log \
  --url "https://rep-portal.ext.net.nokia.com/reports/test-runs/?test_instance_id=35764397&ordering=-end&end_db=365"
```

如果输出：

```text
click_final_url = chrome-error://chromewebdata/
body_text_length = 0
```

说明浏览器点击也无法打开日志页面。此时问题不在 Reporting Portal 链接提取，而在 Debian 到内部日志静态服务器的访问路径或日志服务器映射。

下一步排查方向：

```text
1. 在服务器 headed Chromium 手工打开同一个 Test Logs 链接，确认是否同样是 Chrome error page
2. 在 Windows 浏览器手工打开同一个 Test Logs 链接，确认是否 Windows 可访问但 Debian 不可访问
3. 向团队确认 10.70.226.9 的日志服务是否需要特定网络、DNS、代理、VPN 或只允许某些来源访问
4. 如果直接 log.html 访问无法解决，转向 Reporting Portal 可用的 download zip / artifact download 路径
```

当前验证结论：

```text
Windows 可以打开同一个 Test Logs 链接
Debian 服务器不能打开同一个 Test Logs 链接
```

因此后续实现分为两条路线：

```text
路线 A：解决 Debian 服务器到 10.70.226.9 的网络访问
- 适合继续沿用当前 log.html 直接解析方案
- 需要网络/路由/代理/访问权限支持

路线 B：不依赖 10.70.226.9 直接访问
- 改为寻找 Reporting Portal detail 页或后端能触发的 download zip / artifact download 路径
- Agent 下载 zip 后在服务器本地解压 log.html 或 output.xml
- 这条路线更符合“部署在 Debian 上自动运行”的约束
```

### Plan B：验证 Reporting Portal 下载入口

当 Debian 无法直接打开 `10.70.226.9` 的 `log.html` 时，改为验证 Reporting Portal detail 页面是否提供可下载的 zip / artifact / output 文件入口。

早期头脑风暴验证记录中已经确认过 Reporting Portal 的 report download 入口：

```text
https://rep-portal.ext.net.nokia.com/at/test-reports/45873334/download/
```

曾成功下载：

```text
suggested filename: robot_report.zip
saved as: /home/ute/test-report-45873334.zip
```

因此 Plan B 的方向是直接构造 `/at/test-reports/<report_id>/download/`，不再维护“从 detail 页 DOM 里找下载按钮”的探索代码。

如果已知 test report id，可以直接尝试下载：

```bash
PYTHONPATH=agent python -m triage_agent download-report-zip --report-id 45873334
```

也可以从 URL 中提取 report id：

```bash
PYTHONPATH=agent python -m triage_agent download-report-zip \
  --url "https://rep-portal.ext.net.nokia.com/details/test-report/45873334/"
```

下载默认保存目录：

```text
/tmp/cit_crt_morning_triage_agent_downloads
```

预期成功输出：

```text
status = ok
results.status = downloaded
results.suggested_filename = robot_report.zip
results.saved_path = /tmp/cit_crt_morning_triage_agent_downloads/robot_report.zip
```

如果下载解压后只有 `reporting_portal.json`，可以先解析这个 JSON：

```bash
PYTHONPATH=agent python -m triage_agent extract-report-json \
  --file /tmp/cit_crt_morning_triage_agent_downloads/robot_report.zip
```

也可以解析已解压的文件：

```bash
PYTHONPATH=agent python -m triage_agent extract-report-json \
  --file docs/reporting_portal.json
```

预期输出：

```text
suite_count
test_case_count
failed_case_count
failed_cases
```

说明：

```text
reporting_portal.json 是 Reporting Portal 上传用的结构化结果摘要，不是完整 raw log.html。
如果 failed case 中包含 fail_message、steps、test_exception_message 等字段，可以作为 Plan B 的解析来源。
如果 failed_case_count=0，说明该 zip 对应的 report 没有失败 case，或 JSON 中没有失败细节。
```

已验证结果：

```text
2026-05-21 16:27
废弃方向：从 detail 页 DOM 中寻找下载按钮，曾误把 Test Logs 链接当成下载候选
2026-05-21 16:32
废弃方向验证：detail 页面没有可见 zip/download/artifact 按钮
补充发现：初始计划文档中记录过 /at/test-reports/<report_id>/download/ 曾成功下载 robot_report.zip
最终修正：移除 inspect-detail-assets 相关代码，仅保留 download-report-zip 命令，直接构造并验证 Reporting Portal report zip 下载入口
2026-05-21 16:41
download-report-zip 首次验证：Playwright 返回 Page.goto: Download is starting
结论：这不是下载失败，而是下载型 URL 触发浏览器下载时的正常行为；代码已改为忽略该异常并继续读取 download_info.value 保存文件
2026-05-21
下载解压结果：zip 中只有 reporting_portal.json
结论：Plan B 下载到的是结构化 Reporting Portal JSON 摘要，不是完整 log.html/output.xml；新增 extract-report-json 命令，用于判断该 JSON 是否包含 failed case 的 fail_message/steps/exception 证据
2026-05-21 16:54
extract-report-json 验证 docs/reporting_portal.json：suite_count=1，test_case_count=22，failed_case_count=0
结论：当前样例 zip/report JSON 是全 passed 摘要，不能验证失败证据解析；需要用实际 not analyzed/failed 行对应的 report id 下载 zip 再验证
```

## 常见失败模式

### venv 没有激活

现象：

```text
playwright 找不到
pip 安装到了系统 Python
which python 不是 .venv/bin/python
```

处理：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
which python
```

### 没有安装 Chromium

现象：

```text
BrowserType.launch: Executable doesn't exist
```

处理：

```bash
source .venv/bin/activate
python -m playwright install chromium
```

### 缺少系统依赖

现象：

```text
Host system is missing dependencies
```

处理：

```bash
source .venv/bin/activate
python -m playwright install-deps chromium
```

### Python 模块找不到

现象：

```text
ModuleNotFoundError: No module named 'triage_agent'
```

处理：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
PYTHONPATH=agent python -m triage_agent urls
```

第一版还没有做 Python package install，所以需要先使用 `PYTHONPATH=agent`。

### SSO 登录态过期

现象：

```text
"status": "expired"
Loading...
SSO LOG IN
No active accounts found
MSAL reports no active account in the persistent browser profile
```

处理：

```text
用同一个 persistent profile 重新登录 reporting_portal，然后重新执行 health。
```

如果已经重新登录但 `health` 仍然返回 `No active accounts found`，优先检查：

```text
1. 重新登录脚本是否使用了同一个 profile：/home/ute/reporting-portal-profile
2. 登录完成后是否真的进入 reporting_portal 的 Test Runs 页面，而不只是完成了公司 SSO 页面
3. 是否用 Ctrl+C 强制结束了登录脚本。如果是，请改用文档中的 Enter 方式正常关闭
4. 执行 health 的 Linux 用户是否还是 ute，同一个 profile 目录是否对 ute 可读写
5. 是否有另一个 Chromium/Playwright 进程还占用同一个 profile
```

可检查 profile 权限：

```bash
ls -ld /home/ute/reporting-portal-profile
ls -la /home/ute/reporting-portal-profile | head
```

预期结果：

```text
目录 owner 是 ute
当前 ute 用户可以读写
```

### EOFError: EOF when reading a line

现象：

```text
EOFError: EOF when reading a line
```

原因：

```text
只有自定义脚本里使用 input() 时才会遇到这个问题。
用 python - <<'PY' 运行带 input() 的脚本时，heredoc 会占用标准输入，导致 input() 无法读取终端输入。
```

处理：

```text
本文档当前的重新登录脚本已经不再使用 input()，而是自动等待 3 分钟后关闭浏览器，因此不会再触发这个问题。
```

## 学习记录

### 本步解决的问题

明确服务器 clone 完成后的下一步不是直接运行 Agent，而是先在 `/opt/cit_crt_morning_triage_agent` 下创建独立 venv，确保 Python 依赖、Playwright 和 Chromium 都安装在项目自己的运行环境中。

### 修改的文件

```text
deploy/server_runtime_setup.md
```

### 核心流程

```text
/opt/cit_crt_morning_triage_agent
-> python3 -m venv .venv
-> source .venv/bin/activate
-> pip install -r requirements.txt
-> playwright install chromium
-> triage_agent urls
-> triage_agent health
-> triage_agent collect-links
```

### 关键字段和路径

```text
项目路径：/opt/cit_crt_morning_triage_agent
虚拟环境：/opt/cit_crt_morning_triage_agent/.venv
Python 包路径：agent/triage_agent
配置文件：config/triage_config.json
Playwright profile：/home/ute/reporting-portal-profile
```

### 验证命令汇总

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
which python
python -m pip install -r requirements.txt
python -m playwright install chromium
PYTHONPATH=agent python -m triage_agent urls
PYTHONPATH=agent python -m triage_agent health
PYTHONPATH=agent python -m triage_agent collect-links
```

### 复查问题

- `which python` 是否指向项目 `.venv`？
- `PYTHONPATH=agent python -m triage_agent urls` 是否输出 6 个 scope？
- `health` 是否能识别当前 SSO 登录态？
- `collect-links` 是否能从 filtered page 取到 `Test Logs` 链接？

## 邮件结果源验证

如果 Reporting Portal SSO 登录态频繁失效，或 Debian 服务器无法打开 `log.html`，优先验证 nightly 结果邮件里的下载链接。

先把一封真实结果邮件导出为 `.eml`，放到：

```text
/opt/cit_crt_morning_triage_agent/samples/result-mail.eml
```

解析邮件链接：

```bash
cd /opt/cit_crt_morning_triage_agent
source .venv/bin/activate
PYTHONPATH=agent python -m triage_agent extract-email-links \
  --file samples/result-mail.eml \
  --include-all-links
```

预期结果：

```text
subject 不为空
link_count > 0
download_candidates / portal_links / jenkins_links 至少有一个不为空
如果是 Outlook Safe Links，normalized_url 应显示真实目标 URL
```

尝试从邮件链接下载 report/log 包，并解析 `reporting_portal.json`：

```bash
PYTHONPATH=agent python -m triage_agent download-email-reports \
  --file samples/result-mail.eml \
  --max-downloads 1 \
  --extract-json
```

预期结果：

```text
download_url_count > 0
results.status = downloaded
results.saved_path 位于 /tmp/cit_crt_morning_triage_agent_downloads
如果下载包里有 reporting_portal.json，report_json_results 会输出 suite_count / test_case_count / failed_case_count
```

常见失败：

```text
download_candidates = []
```

邮件里可能没有直接下载链接，先查看 `all_links`。

```text
results.status = failed
```

下载链接可能已过期、需要交互式 SSO，或 Debian 服务器无法访问目标地址。

```text
failed_case_count = 0
```

样例邮件对应的结果可能全 passed，需要换实际 `not analyzed / failed` 结果邮件验证。
