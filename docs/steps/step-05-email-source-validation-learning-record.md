# Step 05 邮件结果源验证学习记录

## 日期

2026-05-21

## 本步骤解决的问题

Reporting Portal 页面路线在服务器上遇到两个实际阻碍：

```text
1. SSO/MSAL 登录态几个小时后可能失效，Playwright persistent profile 需要人工重新 headed 登录。
2. Windows 能打开的 10.70.226.9 log.html，Debian 服务器无法稳定访问。
```

因此本步骤新增“结果邮件源”作为优先数据入口：先解析 nightly 结果邮件中的下载链接，再复用现有 report zip / `reporting_portal.json` 解析能力。

## 修改的文件及原因

```text
agent/triage_agent/models.py
```

新增邮件解析结果的数据结构：

```text
EmailLinkCandidate
EmailAttachmentSummary
EmailParseResult
```

```text
agent/triage_agent/email_collector.py
```

新增本地邮件文件解析器：

```text
.eml 标准解析
.msg best-effort 解析
邮件正文和 HTML href 链接提取
Outlook Safe Links url 参数展开
download / portal / jenkins / other 链接分类
附件摘要提取
```

```text
agent/triage_agent/cli.py
```

新增命令：

```text
extract-email-links
download-email-reports
```

并复用已有能力：

```text
download-report-zip
extract-report-json
```

```text
docs/overview/roadmap.md
docs/overview/initial-plan-and-validation.md
docs/steps/step-05-email-source-validation-learning-record.md
```

记录路线切换原因、核心流程、验证命令、预期结果和常见失败模式。

## 核心调用流程

```text
samples/result-mail.eml
-> parse_email_file()
-> extract body text, href links, plain URLs, attachments
-> unwrap Outlook Safe Links
-> classify URLs into download_candidates / portal_links / jenkins_links
-> JSON output
```

如果需要继续下载：

```text
samples/result-mail.eml
-> download-email-reports
-> collect download candidate URLs
-> if URL contains Reporting Portal report id:
      build /at/test-reports/<id>/download/
   else:
      keep original candidate URL
-> Playwright persistent profile
-> save downloaded file under /tmp/cit_crt_morning_triage_agent_downloads
-> optional extract-report-json
```

## 关键字段

```text
subject
from_address
to_addresses
sent_at
body_text_length
body_text_sample
link_count
download_candidates
portal_links
jenkins_links
all_links
attachments
download_urls
results.saved_path
report_json_results
```

## 服务器端验证命令

先把一封真实 nightly 结果邮件导出为 `.eml`，放到项目目录：

```text
samples/result-mail.eml
```

只验证邮件解析：

```bash
PYTHONPATH=agent python -m triage_agent extract-email-links \
  --file samples/result-mail.eml \
  --include-all-links
```

预期结果：

```text
subject 不为空
sent_at 能识别或保留原始 Date 字符串
link_count > 0
download_candidates / portal_links / jenkins_links 至少有一个不为空
如果邮件链接是 Outlook Safe Links，normalized_url 应展开为真实目标 URL
```

继续尝试下载并解析 JSON：

```bash
PYTHONPATH=agent python -m triage_agent download-email-reports \
  --file samples/result-mail.eml \
  --extract-json
```

预期结果：

```text
download_url_count > 0
results 至少有一条 status = downloaded
saved_path 指向 /tmp/cit_crt_morning_triage_agent_downloads
如果下载文件是 robot_report.zip 或 reporting_portal.json，report_json_results 中能看到 suite_count / test_case_count / failed_case_count
```

调试时限制下载数量：

```bash
PYTHONPATH=agent python -m triage_agent download-email-reports \
  --file samples/result-mail.eml \
  --max-downloads 1 \
  --extract-json
```

## 常见失败模式

```text
download_candidates = []
```

邮件里可能只有普通 Portal 页面链接，或下载入口隐藏在需要登录后点击的页面里。先查看 `--include-all-links` 输出。

```text
results.status = failed
```

下载链接可能需要交互式 SSO、已经过期，或 Debian 服务器网络无法访问目标地址。

```text
report_json_results.status = failed
```

下载文件不是 zip/json，或 zip 中没有 `reporting_portal.json`。

```text
failed_case_count = 0
```

该邮件对应的结果可能全 passed，或 `reporting_portal.json` 只有摘要字段，不包含 failed case 证据。需要换实际 `not analyzed / failed` 结果邮件验证。

```text
.msg 解析出的 body_text_length 很小或 link_count = 0
```

当前 `.msg` 支持是 best-effort。如果 `.msg` 无法解析，优先从 Outlook 导出 `.eml`；后续再评估是否安装 optional `extract_msg` 依赖。

## 给用户的复盘问题

```text
1. 真实 nightly 邮件里的下载链接是否能被 extract-email-links 抓到？
2. normalized_url 是否已经从 Outlook Safe Links 展开为真实下载地址？
3. Debian 服务器能否直接下载邮件里的 report/log 包？
4. 下载包里是否包含 failed/not analyzed case 所需的 fail_message、steps 或 exception 字段？
5. 如果邮件源可行，后续邮箱自动接入应选择 Microsoft Graph、IMAP，还是邮件转发到专用邮箱？
```
