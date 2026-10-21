# Claude Desktop 中文补充补丁

为 macOS Claude Desktop 补充中文界面文案，当前适配 **3.1623.0**。

这个项目来自一次实际的新版适配：直接新增中文 locale 曾使页面停在加载占位界面；改为翻译程序中的 `defaultMessage` 显示文案后，页面恢复正常并显示中文。因此，本工具沿用后者，不修改语言白名单、页面启动脚本或语言配置。

本项目为非官方工具，不包含 Claude 应用本体，也不提供账号或推理服务。

## 当前覆盖

- 新增 **953 条**中文词条，涵盖导航、项目、插件、技能、设置、权限提示、计划任务、Code 和 Cowork 常见操作。
- 允许复用当前应用自带的中文文本；只复用对应关系明确的译文。
- 在已有汉化的 3.1623.0 上，本次补充匹配 **1,182 个消息 ID、4,349 处显示位置**。这是该安装环境的静态扫描结果，不代表所有页面都已完成逐项视觉检查。
- 可以通过 `--base-translations` 读取本地已有的基础词库，扩大覆盖范围。

**这不是完整中文语言包。** 新增功能、远端内容、原生菜单和没有可识别消息描述符的硬编码文案仍可能显示英文。Cowork 和 Code 的部分入口采用中英双语；模型 ID 和技术标识保留原文。

### 常用入口示例

| 英文 | 中文 |
| --- | --- |
| Customize Cowork for me | 为我定制 Cowork |
| General | 通用 |
| Cowork | 协作（Cowork） |
| Code | 编程（Code） |
| Language | 语言 |

## 安装

需要 macOS、Python 3.9+、已安装的 `/Applications/Claude.app`，以及对应用和备份目录的写权限。工具不会自动提权。

1. 下载本仓库并解压。
2. 保存工作，按 **⌘Q 完全退出 Claude**。
3. 双击 `install.command`。如果无法双击运行，可以使用以下命令：

```sh
cd /path/to/claude-desktop-zh-cn-plus
/usr/bin/python3 patcher.py --dry-run
/usr/bin/python3 patcher.py --install --launch
```

默认只安装本仓库提供的补充词条，并复用应用自带的可用中文资源。已经汉化的文案会保留。

如果你有 [ooac/claude-desktop-zh-cn](https://github.com/ooac/claude-desktop-zh-cn) 的 `resources/frontend-zh-CN.json`，可以在全新安装时显式传入：

```sh
/usr/bin/python3 patcher.py --dry-run \
  --base-translations /path/to/frontend-zh-CN.json

/usr/bin/python3 patcher.py --install --launch \
  --base-translations /path/to/frontend-zh-CN.json
```

工具只读取该 JSON，不运行上游安装脚本，也不自动下载外部文件。

安装完成后，请确认聊天列表、输入框以及常用设置页面可以正常加载。**进程运行或签名校验通过，不等于页面加载成功。**

## 恢复

先完全退出 Claude，然后双击 `restore.command`，或运行：

```sh
/usr/bin/python3 patcher.py --restore --launch
```

备份和安装记录默认保存在：

```text
~/Library/Application Support/ClaudeZhCnPlus/
```

每次安装保留安装前的完整应用，不覆盖旧备份。恢复的是最近一次安装前的状态；如果安装前已经汉化，恢复后也会保留那一版汉化。恢复时当前应用会另存，不直接删除。

如果使用自定义 `--state-dir`，安装和恢复时必须传入同一个目录。为保证文件替换失败时能够立即回退，备份目录需与应用位于同一文件系统。

## 修改范围

补丁仅修改前端脚本中可识别的 `defaultMessage` 字符串，并对应用外层重新签名。会校验：

- JSON 字符串转义，防止译文改变 JavaScript 结构。
- ICU 变量、变量类型、复数和选择分支、富文本标签。
- 消息 ID 及显示字符串之外的脚本内容保持不变。
- `app.asar` 和页面入口 HTML 保持不变。
- 修改后的应用签名可以验证。

工具不读取或修改聊天记录、账户配置、API Key、网关地址、模型路由、权限模式或会话历史；不增加默认绕过权限行为。

重新签名会使用本机 ad-hoc 签名，保留运行和虚拟化所需权限，但不能继续声明 Anthropic 的团队身份和专属钥匙串组。因此依赖官方签名、受管身份或专属钥匙串权限的功能可能受影响。需要这些功能时，应恢复官方版本。本工具不关闭系统 Gatekeeper，也不删除应用隔离属性。

## 版本更新

Claude 更新可能覆盖补丁，也可能改变文案结构。默认安装仅接受已适配版本；遇到其他版本请先运行只读检查：

```sh
/usr/bin/python3 patcher.py --dry-run
```

`--allow-untested-version` 可以显式允许尝试其他版本，但不代表已验证兼容。不要用旧版完整应用覆盖新版；应针对新版本重新准备补丁。

语言选择器仍可能显示原语言。这是预期行为：工具翻译显示文案，不注册新的语言选项。请不要为了汉化手动改写 locale 或启动脚本。

## 参与补充

新增译文放在 `resources/supplemental-zh-CN.json`，格式为：

```json
{
  "Open {name}": "打开 {name}"
}
```

请保留变量、复数分支、富文本标签和技术标识。一个英文词条在不同场景下存在歧义时，先检查具体界面，再决定是否通用替换。

提交前运行：

```sh
python3 -m unittest discover -s tests -v
```

测试涵盖占位符、复数分支、转义、重复安装不重复修改，以及替换失败回退。CI 运行纯逻辑测试；macOS 安装和真实界面需要另外验证。

反馈遗漏文案时，请附 Claude 版本、页面位置、英文原文，以及已经遮盖个人信息的截图。不要提交账户配置、聊天日志、应用包或密钥。

## 来源与许可

最初的汉化参考来自 [ooac/claude-desktop-zh-cn](https://github.com/ooac/claude-desktop-zh-cn)。本仓库提供独立编写的显示文案安装器和新增词条，使用 [MIT License](LICENSE)。

本仓库不附带上游词库、上游安装脚本或 Claude 的应用文件；本仓库许可证不授予这些外部材料的权利。可选外部词库及应用内资源仅从用户本地文件读取，来源详见 [THIRD_PARTY.md](THIRD_PARTY.md)。
