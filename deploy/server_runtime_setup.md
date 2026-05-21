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
