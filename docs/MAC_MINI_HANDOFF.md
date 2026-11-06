# Short-Drama-Bench：Mac mini / Codex 交接文档

更新日期：2026-11-06（Asia/Shanghai）。本文记录已验证状态，不代表两个 baseline 已达到正式评测要求。

## 1. 给接手 Codex 的任务说明

先阅读本文件、各仓库的 `AGENTS.md`（如存在）和 `LOCAL_SETUP.md`，检查实际代码与当前分支，再继续部署。

任务：在 Mac mini 上部署 ViMax、CineCrew 的 API 适配版本，先完成第 1 条 prompt 的小样验证，再准备 Short-Drama-Bench 的 10 条正式测试。

必须遵守：

- 使用 uv 管理 Python 环境和启动，不依赖原电脑的 `.venv`。
- 保留 baseline 原有的规划、选图、首尾帧、审查、拼接流程。适配默认限制在 provider/client/独立 gateway 边界。
- 不因为模型接口报错就删除尾帧、改分镜、改人物名、关闭质量审查或发明后处理流程。
- 用户给的提示词原样输入，不加入“已授权”“保留流程”“失败后报告”等执行层说明。
- 密钥只留在本机忽略文件中，不进入对话、日志、测试、提交或公开仓库。
- 付费测试先单条、有限重试。遇到确定性的欠费、权限或参数错误，应报告并停止重复提交。
- 进程存活、HTTP health 成功、`exit 0`，都不能单独证明任务成功；必须核对最新产物、实际调用结果和成片。
- 先解决已知兼容性问题并验收 prompt 1，不直接批量跑 10 条。
- 不覆盖用户在 Mac mini 上已经配置的密钥、结果或其他改动。

## 2. 仓库与版本

| 项目 | Fork | 工作分支 | 本次交接的适配代码提交 |
| --- | --- | --- | --- |
| ViMax | https://github.com/hit-cxf/ViMax | `api-adapter` | `0d68f0fcd42a25454ac1c82cd8f9d7a8513c4845` |
| CineCrew | https://github.com/hit-cxf/CineCrew | `api-adapter` | `003a4202c24efe5cd6ec6d4f065baf6e4c204fd9` |

本文件的文档提交晚于表中代码提交。记录正式实验时，应另记实际运行的完整 commit SHA。

两个 fork 为公开仓库。`main` 保持上游版本，适配在 `api-adapter`，不要默认拉 `main`。

原机远端已整理为：`origin` 指向用户 fork，`upstream` 指向原作者仓库。

未上传：密钥、本机配置、视频、图片缓存、运行日志、实验结果，以及 CineCrew `data/` 下的临时测试脚本。

## 3. 公共环境

API 模型在远端运行，Mac mini 不需要本地加载视频模型或 CUDA。需要稳定网络、有效账户余额和所选模型的调用权限。

```bash
brew install uv ffmpeg node
mkdir -p ~/Project
cd ~/Project
git clone --branch api-adapter https://github.com/hit-cxf/ViMax.git
git clone --branch api-adapter https://github.com/hit-cxf/CineCrew.git
```

Python 使用 3.12；原机验证版本为 3.12.11。以 `uv.lock` 锁定依赖，不要无理由升级依赖。

先检查端口，避免覆盖其他服务：ViMax Web 为 4173，CineCrew 本地媒体 gateway 为 8766。

## 4. 实际模型配置

| 用途 | 当前采用配置 |
| --- | --- |
| 文本规划、智能体调度 | `qwen3.5-plus`，关闭思考模式 |
| 视觉理解、选图或视觉审查 | 同一个 `qwen3.5-plus`，关闭思考模式 |
| 图片生成、编辑 | `wan2.7-image-pro` |
| 视频生成 | `happyhorse-1.0-i2v`，但见 ViMax 的重要限制 |
| 输出目标 | 9:16，720P；关键帧 900×1600，预期视频 720×1280 |

用户最早要求过 `deepseek-v4-pro` 文本 + Qwen 视觉，后来明确接受本次两个项目都用 Qwen，不要自行切回 DeepSeek。

文本接口使用 DashScope 的 OpenAI-compatible 地址；媒体接口使用 DashScope 原生地址。以仓库模板为准，注意地域与密钥必须匹配。

关闭思考的原因已真实复现：原 ViMax 4096 token 输出预算被 Qwen 思考消耗，正式内容为空，导致人物 JSON 解析失败。关闭后，同一故事成功返回 3 个人物。不要通过修改用户提示词规避。

## 5. ViMax 部署

在 `~/Project/ViMax` 中执行：

```bash
uv sync --python 3.12 --locked
cp configs/agent.dashscope.example.yaml configs/agent.local.yaml
chmod 600 configs/agent.local.yaml
npm --prefix web ci
npm --prefix web run build
```

在本机填写 `configs/agent.local.yaml` 中三个 `api_key`，不要把填写后的文件提交。然后：

```bash
./start-local.sh
```

浏览器打开 http://127.0.0.1:4173。原项目提供 WebUI，可从 Settings 修改本机模型配置。

适配内容：

- `tools/dashscope_generators.py`：图片与视频 provider adapter。
- `agent_runtime/config.py`、`vimax_adapters.py`：provider 选择与工厂接入。
- `agent_runtime/llm.py`、`vimax_adapters.py`：Qwen 请求关闭思考。
- 人物参考图提示、关键帧尺寸与候选图检查：统一为 9:16。
- 参考图上传前生成唯一文件名的临时副本，避免不同人物的 `front.png` 被 SDK 上传到同一个 OSS key；原文件和引用顺序不变。
- I2V 不发送不支持的 `ratio` 参数；分辨率 720P，比例随关键帧。

### ViMax 阻塞点：HappyHorse 不接受尾帧

真实接口多次返回：

```text
InvalidParameter: Input should be 'first_frame': input.media.1.type
```

当前 DashScope HappyHorse I2V 只接受单张首帧，而 ViMax 的部分镜头需要首尾帧。适配分支现在会在本地提前拒绝两帧 HappyHorse 请求，不丢尾帧、不继续付费重试。

`wan2.7-i2v` 的官方接口明确支持 `first_frame` + `last_frame`，请求形状可由当前 adapter 传递，但此配置尚未在本项目端到端验证。是否改用它，先与用户确认模型选择及对比口径，不自动混用模型。

如继续使用 HappyHorse：不要声称 ViMax 已能完整跑通；只应验证单帧请求并保留阻塞报告。

离线回归命令（不生成付费内容）：

```bash
env TMPDIR=/private/tmp uv run --locked python -m pytest \
  tests/test_agent_llm.py tests/test_agent_config.py tests/test_vimax_adapters.py \
  tests/test_dashscope_generators.py tests/test_image_selection.py \
  tests/test_provider_presets.py -q
```

已在无本机密钥配置的干净副本通过：88 tests、23 subtests。前端构建通过。

产物位置：`.vimax/`、`.working_dir/`。仅 Web 服务存活不表示后台 agent 正在生成。

## 6. CineCrew 部署

在 `~/Project/CineCrew` 中执行：

```bash
uv sync --python 3.12 --locked
cp .env.dashscope.example .env
chmod 600 .env
```

本机配置 `.env`：

- `LLM_API_KEY`、`DASHSCOPE_MEDIA_API_KEY`：本机填写 DashScope 密钥。
- `MEDIA_GATEWAY_TOKEN`、`T2I_API_KEY`、`VIDEO_API_KEY`：三者填写同一个随机的本地 token，不使用上游密钥充当本地 token。
- `T2I_BASE_URL`、`VIDEO_BASE_URL`：指向本机 gateway，模板默认 8766。
- 可用 `uv run --locked python -c 'import secrets; print(secrets.token_urlsafe(32))'` 在本机生成 token，勿粘贴到公开记录。

终端 A：

```bash
uv run --locked uvicorn local_media_gateway:app --host 127.0.0.1 --port 8766
```

该地址是 API 服务，不是 WebUI。CineCrew 原生使用命令行，未额外制作前端。

终端 B，先验证环境：

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked python -c 'import src.pipeline, src.adapters; print("Imports OK")'
uv run --locked python run_dataset_story.py --help
```

已在无本机 `.env` 的干净副本通过 6 项测试。测试 mock provider，不产生生成费用。

原生规划入口（付费 LLM，但不生成媒体）：

```bash
uv run --locked python run_dataset_story.py configs/local_examples/wedding_investor
```

原生端到端入口（付费 LLM、生图、视频和审查）：

```bash
uv run --locked python run_dataset_story.py configs/local_examples/wedding_investor --execute
```

注意：第二个命令会重新跑规划，不是从上一个规划断点继续。不要未经判断就重复运行。

适配方式：原生 `T2IClient` / `VideoClient` 不改，用独立 `local_media_gateway.py` 转译 OpenAI 形状的图片/视频请求。参考图以 Base64 保序传递，避免同名 OSS 上传问题；媒体下载不向第三方媒体域转发 provider 密钥。

原生流程：ArtDepartment → StoryEditor → Cinematographer → DSLValidator → VODirector → TechnicalDirector → DailiesReviewer → ProductionOperator。

保留默认审查和一次额外重试。`generate_references` 仍为上游默认 `false`，不要默默打开或假设已启用人物参考图生成。

### CineCrew 当前验收缺口

1. **时长**：原始短 prompt 被规划为 6 镜头、28 秒，成片 28.95 秒，不满足 180 秒。CineCrew 是剧本到影片框架，不能假设一句创作灵感会自动扩展成三分钟。应先查原生时长控制及剧本输入约定，与用户确认处理方式；不要复制镜头或拉伸补时长。
2. **中文对白导出**：最终蓝图中三个镜头有中文台词，但对应 VideoJob 都标为 `prelude`，`dialogue` 字段为空。重点检查 `src/agents/production_operator/production_operator_agent.py` 中 `_split_dialogue_shot_duration` 的单段返回与 `segment_roles` 的对应关系。这是已观察到的数据不一致，尚未修复；不能据此宣布中文对白已经通过验收，也不要在没有回归测试时大改原项目。
3. **模型最小时长**：HappyHorse 接受整数 3–15 秒；原生客户端会 round job duration。少于 3 秒的任务被 gateway 本地拒绝，未自动延长、裁剪、改切段。
4. **声音控制**：独立 voice preset、FPS/frame_num 不是当前 HappyHorse 的原生控制参数。不要把 FilmDSL 内的设定等同于模型实际执行；声音、台词、身份必须实际检查。
5. **质检失败仍出片**：原生框架在一次重试后可能保留未通过视觉审查的片段并拼接。`6/6 completed` 只说明生成成功，不代表六段都通过质检。
6. **成片帧率异常**：本次 FFprobe 显示视频流 `r_frame_rate=384/1`，源自未修改的拼接流程，原因尚未排查。应检查实际时间戳、avg_frame_rate、播放和音画同步，不要当作 384 FPS 实验设置或无证据地修改。

已生成样片有 720×1280 视频流和音频流，不能据此保证中文台词、时长和质量合格。

产物：`data/runs/dataset/<story>/<run_id>/` 下的 `assets/`、`shots/`、`media/`、`logs/`；成片通常为 `media/film.mp4`。

## 7. 第一个 prompt 与输入原则

只输入以下文字，不额外混入执行指令：

```text
在婚礼上被遗弃后，她以能够收购新郎帝国的投资者身份回归。 要求：总时长为3分钟，对白、台词使用中文。
```

CineCrew 已提交相同文字的输入文件：`configs/local_examples/wedding_investor/script_synopsis.json`。

如果要显式选择 ViMax 的 idea2video 模式，优先使用原项目已有的入口/工具，不把调度细节堆进创作提示词。不要假设上述短 prompt 在不同框架中有相同的扩写行为。

## 8. Short-Drama-Bench 的 10 条创作灵感

原机文件：`Short-Drama-Bench/docs/prompts.txt`。以下为该文件内容，不代表已存在统一的三分钟生成脚本：

1. 在婚礼上被遗弃后，她以能够收购新郎帝国的投资者身份回归
2. 因怀孕而被解雇的女员工重新成为公司的大客户
3. 连环杀手一直潜伏在他们的群聊中
4. 现代医科学生穿越回汉末行医
5. 她为了签证与室友假结婚，然后就不再是假结婚了
6. 在上班的第一天，她发现公司最大的企业间谍竟然是自己的导师
7. 设计师妻子被指偷窃老板的手稿，却被秘密结婚的丈夫撞见。只需一个电话，首席执行官就会被召来。
8. 被同学嘲笑的转校生，父亲是学校董事长
9. 全家人凑钱让哥哥出国留学，妹妹却自己考上了更好的学校
10. 被合作伙伴踢出局的创始人带着核心技术重新创业

各 prompt 的附加时长和语言要求须一致、独立留档，不得偷偷给某个 baseline 更多剧情信息。

## 9. 正式测试与评估约定

现有方法包括 VideoClaw、ScriptAgent、MM-StoryAgent、Anim-director，计划新增 ViMax、CineCrew。正式比较前需冻结并记录：

- commit、输入原文、provider、实际模型 ID/版本/地域、思考开关。
- 各框架的原生选图、质检、重试预算及是否生成参考图。
- 目标/规划/实际时长、分辨率、宽高比、音频流、台词语言、失败次数与费用。
- 模型是否混用、是否人工修改、是否补时长、是否存在不合格片段回退。
- 每条任务的最新状态、最终输出路径和原始日志。失败和缺失不能记作 0 分或悄悄剔除。

跨框架用同一组模型有利于控制变量，但不能为了表面一致而破坏 baseline 原生能力。当前 ViMax-HappyHorse 的首尾帧冲突须先明确解决方案。

人工评测：0–4 Likert，九个指标：创意/剧情核心贴合度、故事完整性与因果连贯、人物核心特征一致性、服装与造型合理性、场景与背景连续性、角色动作与互动正确性、视觉美感与成像质量、运动与时间稳定性、短剧节奏与可看性。

人物核心特征与服装必须分开：面部和永久性特征要稳定，服装允许随剧情合理变化。

人工 WebUI：私有仓库 https://github.com/hit-cxf/short-drama-human-eval-webui 。原配置尚未加入这两个新 baseline；添加后验证同主题方法顺序打乱。只有点击 Save 才回传，Evaluator 必填。

统一归档约定可沿用 `videos/<method>/1.mp4` 至 `10.mp4`，保留中间产物但不混入正式视频目录。

VBench 已交由另一个 agent / GPU 环境运行，不要在 Mac mini 未评估计算需求就重新跑。已有自动指标为 imaging_quality、aesthetic_quality、background_consistency、subject_consistency、motion_smoothness；新增模型必须复用同样的抽帧和长视频处理口径。

原机 Short-Drama-Bench 根目录不是 Git 仓库，两个 fork 不包含该目录的完整脚本、结果或已有 baseline 视频；需要另行传输，不假设 clone 后就有全部 benchmark 数据。

## 10. 建议接手顺序与验收

1. 确认本机分支、版本、磁盘、网络、FFmpeg、端口和凭证忽略规则；不输出密钥。
2. `uv sync --locked`，运行离线测试和模块导入，不先调用付费生成。
3. 与用户确认 ViMax 首尾帧视频模型选择；保留尾帧，不静默降级。
4. 针对 CineCrew 28 秒规划、对白任务导出及拼接 FPS 做定位；先给证据和最小改法，避免改变 baseline 的实验含义。
5. 冻结方案后，用 prompt 1 做有限的小样：校验真实尺寸、音画同步、中文台词、时长、人物、接口错误和审查结果。
6. 原生流程能正确产出且满足实验约定后，再启动 10 条；明确目标时长容差，由用户决定，不擅自设阈值。
7. 最后接入统一目录与评测工具，汇总成功率、时间、费用、自动分数与人工评分。

建议成片检查：

```bash
ffprobe -v error \
  -show_entries format=duration:stream=codec_type,width,height,r_frame_rate,avg_frame_rate \
  -of json PATH_TO_FINAL_VIDEO
```

已有实验仅供定位接口，不应不加说明地纳入正式结果。当前没有任何一个新 baseline 被验收为“三分钟、中文对白、质量合格”的完整正式样本。
