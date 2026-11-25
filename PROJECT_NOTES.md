# 智报（zhibaozb.top）项目交接备忘

> 本文档用于换电脑 / 新会话后快速恢复上下文。最后更新：2026-11-24。

## 产品定位

智报 = AI 写周报（日报 / 周报 / 月报 / 季度总结），聚焦「写汇报」这一个垂直场景，不是泛 AI 聊天工具。

**付费理由（与免费大模型的差异）**：不拼"谁写得好"，拼"谁记得你、谁替你干活"——
确定性（不编数据）、岗位贴合（13 岗位话术）、成品交付（导出 Word）、记忆连续性（历史报告衔接）。

## 技术架构

- 后端：FastAPI，入口 `webapp/main.py`；营销页为静态 HTML，在 `docs/`（`docs/index.html` 是官网首页）
- 模型：OpenAI 兼容接口，线上用智谱 `glm-4-flash`（见 `render.yaml`），可换成 deepseek / 千问 / kimi / 豆包
- 语音识别：智谱 `glm-asr-2512`，复用 `LLM_API_KEY`（`LLM_BASE_URL` 为智谱时自动生效，无需单独配 `ASR_API_KEY`）
- 核心壁垒：`core/prompts.py`（13 岗位四维话术 focus/style/vocab/avoid + 四模块结构 + 不编数据【待补充】约束）
- 账号体系：兑换码 `code` 就是账号；`reports` 表已按 `code` 存历史报告（`core/store.py`）
- 生成接口：`webapp/main.py` 的 `api_generate`；微调 `api_refine`；语音 `api_transcribe`

## 已完成（截至 2026-11-25）

- 语音输入：按住说话转文字，含采样率优化（16kHz）、提示音 + 振动、识别后自动生成开关、按钮 UI 升级（更大/光泽/动画）
- 首页「特点与优势」模块（精简为一行图标 + 短词）
- 全站标题字体统一（字重 700 / 字距 -0.018em）
- 记忆衔接：写周报自动衔接上一期计划（`link_prev` + `plan_section_of`），报告页一键汇总月报 / 季度总结（`/api/aggregate`）
- 文件上传提炼：Word / Excel / PPT / PDF / 截图 / 网页链接 → 自动转成素材写入输入框（`core/extract.py`、`/api/extract`、`/api/extract-url`）
  - 导入前可选「提炼字数」：精简 200 / 标准 400 / 详细 800 / 不提炼，服务端用 `build_summarize_prompt` 按字数上限归纳成要点清单
  - 导入后先进预览框（可编辑），再选择「采用并填入 / 按当前字数重试（`/api/summarize`）/ 取消」，不会直接污染输入框

## 待办（下一步，按优先级）

1. **第三方集成**：飞书 / 钉钉 / 企业微信群机器人推送（需要用户提供 webhook 地址；个人微信 / QQ 无官方接口，不做）
2. 继续 SEO 长尾页与收录观察


## 部署要点

- 平台：Render，serviceId `srv-dc1vvbks728c73djvie0`，域名 zhibaozb.top，GitHub 仓库 `babawang1234/workreport`
- 改代码后流程：`git push` → Render 后台 → Manual Deploy → Deploy latest commit（手动部署，push 不自动触发）
- 线上依赖以 `requirements-web.txt` 为准（`render.yaml` 的 buildCommand），本地依赖见 `requirements.txt`；新增服务端依赖两个文件都要补
- 语音录音仅在 HTTPS 下可用；iOS 微信内核不支持 Web 录音，需提示用户改用系统浏览器
