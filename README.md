# EvoMap MCP Server for Codex

本地 STDIO MCP Server，把 EvoMap 知识图谱 API 暴露给 Codex CLI 与 VS Code Codex 扩展。

## 工具

| MCP 工具 | EvoMap API | 费用 |
| --- | --- | --- |
| `evomap_query` | `POST /kg/query` | 消耗 credits |
| `evomap_ingest` | `POST /kg/ingest` | 消耗 credits |
| `evomap_status` | `GET /kg/status` | 免费 |
| `evomap_my_graph` | `GET /kg/my-graph` | 免费 |

API Key 只从 `EVOMAP_API_KEY` 环境变量读取，并作为 Bearer token 发送。当前官方 KG API Key 格式为 `ek_` 加 48 位十六进制字符；其他类型的 EvoMap 凭据不能用于这些 `/kg/*` 端点。项目不会读取 `.env`，以避免 VS Code 与终端使用不同的密钥来源。

## macOS 安装

当前机器上的项目已完成依赖安装、编译和 Codex 注册。配置位置为 `~/.codex/config.toml`，入口为：

```toml
[mcp_servers.evomap]
command = "node"
args = ["/Users/lirc/VSCode/EvoMap/dist/index.js"]
cwd = "/Users/lirc/VSCode/EvoMap"
env_vars = ["EVOMAP_API_KEY"]
startup_timeout_sec = 20
tool_timeout_sec = 60
enabled = true
```

为从终端启动的 VS Code 设置当前会话变量：

```bash
export EVOMAP_API_KEY="ek_your_key"
code /Users/lirc/VSCode/EvoMap
```

如果从 Dock/Finder 启动 VS Code，可把变量加入当前 macOS GUI 登录会话：

```bash
launchctl setenv EVOMAP_API_KEY "ek_your_key"
npm run diagnose
```

设置后完全退出并重新打开 VS Code，让 Codex 扩展继承该变量。`config.toml` 只声明转发变量名，不保存 API Key。

## 可选：Windows 安装

如需把项目迁移到 Windows，可在 PowerShell 中运行：

```powershell
cd C:\path\to\EvoMap
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\setup-windows.ps1
[Environment]::SetEnvironmentVariable("EVOMAP_API_KEY", "ek_your_key", "User")
```

脚本会安装依赖、编译项目、备份已有配置为 `config.toml.bak`，并只追加 `evomap` MCP 配置；如果已存在同名配置，脚本会停止而不覆盖。

脚本写入 `%USERPROFILE%\.codex\config.toml` 的配置等价于以下内容（路径按实际位置生成）：

```toml
[mcp_servers.evomap]
command = "node"
args = ["C:\\path\\to\\EvoMap\\dist\\index.js"]
env_vars = ["EVOMAP_API_KEY"]
startup_timeout_sec = 20
tool_timeout_sec = 60
enabled = true
```

`env_vars` 只声明转发变量名，不会把 API Key 写进 `config.toml`。

## 验证

```powershell
npm test
codex mcp list
codex mcp get evomap
```

重启 VS Code Codex 扩展后，先让 Codex 调用：

```text
调用 evomap_status，原样总结账户的 KG 权限、余额和用量。
```

再做一次免费读取：

```text
调用 evomap_my_graph，告诉我返回了多少节点和关系，不要修改任何数据。
```

`evomap_query` 与 `evomap_ingest` 会消耗 credits。首次测试写入前，建议先用 `evomap_status` 确认权限与余额。

## 可选环境变量

- `EVOMAP_BASE_URL`：默认 `https://evomap.ai`。
- `EVOMAP_TIMEOUT_MS`：默认 `30000`。

## 官方文档

- EvoMap API：<https://evomap.ai/api/docs/dev-full?lang=zh>
- EvoMap API Key：<https://evomap.ai/zh/wiki/28-api-access>
- Codex MCP：<https://developers.openai.com/zh-Hans/docs/extend/mcp>
