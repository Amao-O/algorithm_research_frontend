# 第 53 组 · A053 音频数字水印复现

本组根据 Yamni 等人在 *Scientific Reports*（2023）发表的论文实现了 WAV 水印嵌入、盲提取和 MPI 分帧处理，并接入老师提供的算法研究平台。方法 ID 为 `group_53_a053_audio_watermark`。成员姓名与分工待本组确认后补齐。[论文](https://doi.org/10.1038/s41598-023-45619-w) · [本组 Fork 与提交分支](https://github.com/Amao-O/algorithm_research_frontend/tree/group_53_submission)

## 复现内容

算法使用 modified Henon 掩码、五层 DTCWT、FrCT 和平方能量量化。基矩阵构造参考 2020 年 FrCT 论文，量化推导对照 2022 年音频水印论文。代码使用 `dtcwt 0.14.0` 提供的 1D 滤波器，并记录了滤波器组、FrCT 对称化与参数外推的选择。平台演示启用重建后校准，使用 0.20 个量化步长的余量。该校准属于本组为 PCM16 写盘和重新分析引入的工程修正。[算法实现与差异说明](algorithms/group_53_a053_audio_watermark/README.md) · [2020 年 FrCT 论文](https://doi.org/10.1016/j.sigpro.2020.107509) · [2022 年音频前置论文](https://doi.org/10.1016/j.eswa.2022.117325) · [dtcwt 项目及许可证](https://github.com/rjw57/dtcwt)

## 本机运行

使用 Python 3.12、Node.js 24 和 pnpm。演示服务在 CPU 上处理音频。先在一个终端启动后端：

```bash
cd algorithms/group_53_a053_audio_watermark
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt -r requirements-api.txt
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

另开终端，在仓库根目录启动前端：

```bash
pnpm install --frozen-lockfile --ignore-scripts
npm run dev -- --port 5173 --strictPort
```

打开 `http://127.0.0.1:5173/#/methods/group_53_a053_audio_watermark`。选择「用样例试一试」，使用默认的 `A053` 文字开始处理。下载生成的 WAV 后，切换到「盲提取水印」并上传该 WAV，位数填 `32`。下载 JSON 报告可查看恢复的文字和比特。

当前方法配置指向同一台机器上的 HTTP 服务。公开部署时，将配置里的 `adapter.endpoint` 改为可访问的 HTTPS 接口，并通过后端的 `A053_ALLOWED_ORIGINS` 设置实际前端来源。该变量接受逗号分隔的来源，默认允许本机 5173 和 4173 端口。[方法配置](public/methods/group_53_a053_audio_watermark.json) · [平台接口规范](docs/算法接入规范.md)

## 输入与结果

| 字段或结果 | 说明 |
| --- | --- |
| `audio` | 44.1 kHz 单声道 PCM16 WAV，最多 6 MiB。每 486 个采样点承载一位。 |
| `mode` | `embed` 嵌入短文字，`extract` 从带水印 WAV 提取比特。 |
| `watermark` | 嵌入时使用，默认 `A053`。文字最多 16 字符，按 UTF-8 转为比特。 |
| `bit_count` | 提取时使用，默认 32。填写嵌入报告中的实际位数，范围 1–5,444，并受素材容量限制。 |
| `watermarked.wav` | 嵌入操作生成的 WAV，采样率、声道和时长与输入一致。 |
| `report.json` | 嵌入报告记录位数。提取报告记录位数、比特和可从整字节 UTF-8 解码的文字。 |

服务使用公开的演示密钥参数。结果存于临时目录，下载有效期为一小时，到期目录会在后续请求时清理，服务退出时也会清理。服务同时处理一个任务。浏览器取消等待后，已开始的后端计算仍可能完成。

## 样例与实验结果

- **平台样例**使用 Ignacio Tapia Carmagnani 的 *Anticipating Gold* 录音 0–8 秒。源文件为 MP3，裁剪后转成 44.1 kHz 单声道 PCM16，并对输出嵌入了 32 位 `A053`。实测 32 位全部正确恢复。前 32 个承载帧的 SNR 为 18.88 dB，其余样本逐点一致。[原始 WAV](public/samples/group_53_a053_audio_watermark/input.wav) · [带水印 WAV](public/samples/group_53_a053_audio_watermark/output.wav) · [录音来源](https://freemusicarchive.org/music/ignacio-tapia-carmagnani/summer-is-on-its-way/anticipating-gold/) · [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
- **五首音乐替代样本**每首嵌入 5,444 位，0.20 余量校准的无攻击 BER 均为 0%，SNR 范围为 33.41–50.41 dB。128 kbps MP3 重编码和右移 5 点的平均 BER 分别为 47.42% 和 40.10%，论文的鲁棒性结果仍待复现。[逐曲目明细 CSV](algorithms/group_53_a053_audio_watermark/results/five_music_results.csv) · [实验方法与摘要](algorithms/group_53_a053_audio_watermark/README.md#多曲目对照)
- **华为云 MPI 实测**在 Ubuntu 24.04.4 LTS、4 vCPU 的同一台 ECS 上完成。使用同一段 60 秒爵士样本，1、2、4 进程各测 3 次。9 次均恢复全部 5,444 位，输出 WAV 的 SHA-256 一致。以 1 进程的中位耗时为基线，4 进程嵌入从 54.38 秒降到 14.15 秒（3.84×），提取从 14.27 秒降到 3.79 秒（3.77×）。目前华为云计时覆盖 1、2、4 进程。[9 次原始计时 JSON](algorithms/group_53_a053_audio_watermark/results/a053-huawei-mpi-summary.json) · [完整计时、ETIR 与复现条件](algorithms/group_53_a053_audio_watermark/README.md#华为云-ecs-重复计时)

## 验证

已在本地 Vite 和 Python 服务上验证样例加载、嵌入、音频下载、盲提取和报告下载。在华为云 ECS 上，也已通过本机 HTTP 接口完成样例上传、嵌入、下载 WAV 和盲提取，恢复全部 32 位并得到文本 `A053`。当前接口供同一台机器访问，也可通过 SSH 端口转发进行验证。

```bash
# 仓库根目录
npm test
npm run build

# Python 虚拟环境在算法目录下建立后运行
cd algorithms/group_53_a053_audio_watermark
.venv/bin/python -m unittest discover -s tests -v
```

[算法与接口代码](algorithms/group_53_a053_audio_watermark/) · [批量实验入口](algorithms/group_53_a053_audio_watermark/run_experiments.py) · [MPI 入口](algorithms/group_53_a053_audio_watermark/src/mpi_watermark.py) · [老师提供的平台仓库](https://github.com/lym-lab/algorithm_research_frontend)
