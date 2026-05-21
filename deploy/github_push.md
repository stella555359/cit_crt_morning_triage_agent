# GitHub 推送与克隆记录

## 目的

本文档用于记录本项目在本地 Windows 和 Debian 服务器上的 Git / GitHub 操作。

项目仓库地址：

```text
https://github.com/stella555359/cit_crt_morning_triage_agent
```

后续凡是和本项目相关的 Git 操作，包括本地提交、推送、服务器克隆、服务器拉取、代理参数等，都统一记录到这个文件。

## Windows 本地首次推送

以下命令在 Windows PowerShell 中执行。

```powershell
cd C:\TA\cit_crt_morning_triage_agent

git init
git status
git add .
git commit -m "Initial CIT CRT morning triage agent MVP"

git branch -M main
git remote add origin https://github.com/stella555359/cit_crt_morning_triage_agent.git
git push -u origin main
```

## 如果远端 origin 已存在

如果下面命令报错：

```powershell
git remote add origin https://github.com/stella555359/cit_crt_morning_triage_agent.git
```

错误类似：

```text
remote origin already exists
```

改用下面命令：

```powershell
git remote set-url origin https://github.com/stella555359/cit_crt_morning_triage_agent.git
git push -u origin main
```

## Debian 服务器带代理克隆

以下命令在 Debian 服务器上执行，当前服务器代理为：

```text
http://10.144.1.10:8080
```

推荐优先使用单次命令代理参数：

```bash
sudo mkdir -p /opt/cit_crt_morning_triage_agent
sudo chown -R ute:ute /opt/cit_crt_morning_triage_agent

git -c http.proxy=http://10.144.1.10:8080 \
    -c https.proxy=http://10.144.1.10:8080 \
    clone https://github.com/stella555359/cit_crt_morning_triage_agent.git \
    /opt/cit_crt_morning_triage_agent
```

这样不会把代理写入服务器全局 Git 配置，后续排查更清楚。

## 如果服务器目录已存在

如果服务器上已经有项目目录，不要覆盖 clone，进入目录后执行拉取：

```bash
cd /opt/cit_crt_morning_triage_agent

git -c http.proxy=http://10.144.1.10:8080 \
    -c https.proxy=http://10.144.1.10:8080 \
    pull --ff-only
```

`--ff-only` 的作用是只允许快进更新，避免在服务器上意外产生 merge commit。

## 预期结果

本地首次 push 成功后：

```text
main 分支已推送到 origin/main
GitHub 仓库页面能看到项目文件
后续在本地可以直接使用 git push
```

服务器 clone 成功后：

```text
/opt/cit_crt_morning_triage_agent 目录存在
git remote -v 指向 GitHub 仓库
git status 显示 working tree clean
```

## 常见失败模式

### 需要 GitHub 认证

现象：

```text
git push 要求登录 GitHub 或输入 token
```

处理：

```text
按提示在浏览器或凭据窗口完成 GitHub 认证。
```

### 没有可提交内容

现象：

```text
nothing to commit, working tree clean
```

处理：

```text
说明文件可能已经提交过。可以继续执行设置分支、设置远端和 push 的命令。
```

### origin 已存在

现象：

```text
error: remote origin already exists.
```

处理：

```powershell
git remote set-url origin https://github.com/stella555359/cit_crt_morning_triage_agent.git
git push -u origin main
```

### 远端已有提交导致 push 被拒绝

现象：

```text
Updates were rejected because the remote contains work that you do not have locally.
```

处理：

```text
先停止操作并检查远端仓库内容。除非明确要覆盖远端，否则不要 force push。
```

### 服务器代理连接失败

现象：

```text
Failed to connect to github.com
Could not resolve proxy
Received HTTP code 407 from proxy after CONNECT
```

处理：

```text
确认代理地址、端口、是否需要认证，以及 Debian 服务器是否允许通过该代理访问 GitHub。
```

### /opt 目录权限不足

现象：

```text
Permission denied
could not create work tree dir
```

处理：

```bash
sudo mkdir -p /opt/cit_crt_morning_triage_agent
sudo chown -R ute:ute /opt/cit_crt_morning_triage_agent
```

## 学习记录

### 本步解决的问题

新建的 Morning Triage Agent 项目需要一个统一的 Git 操作文档，用来记录：

```text
Windows 本地首次推送
Debian 服务器通过代理克隆
后续本地和服务器 Git 操作
```

### 修改的文件

```text
deploy/github_push.md
.cursor/rules/git-operations-documentation.mdc
```

`deploy/github_push.md` 替代原来的 `deploy/github-initial-push.md`，作为本项目唯一的 Git 操作记录文档。

### 核心流程

```text
本地项目目录
-> git init
-> git add / git commit
-> 设置 main 分支
-> 添加 GitHub origin
-> push 到 GitHub
-> Debian 服务器在 /opt 下通过单次代理参数 git clone
```

### 验证命令

Windows 本地：

```powershell
git status
git remote -v
```

Debian 服务器：

```bash
cd /opt/cit_crt_morning_triage_agent
git status
git remote -v
```

预期结果：

```text
working tree clean
origin 指向 https://github.com/stella555359/cit_crt_morning_triage_agent.git
```

### 复查问题

- GitHub 仓库页面是否能看到所有项目文件？
- 本地和服务器上的 `git status` 是否都是 clean？
- `git remote -v` 是否指向预期 GitHub 仓库？
- Debian 服务器是否能通过代理正常 clone 和 pull GitHub 仓库？
