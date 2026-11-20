# 第 53 组 · A053 音频数字水印复现

复现目标是实现论文 *An efficient watermarking algorithm for digital audio data in security applications*（Scientific Reports，2023）中的水印嵌入、盲提取和 MPI 并行处理。论文 DOI 为 [10.1038/s41598-023-45619-w](https://doi.org/10.1038/s41598-023-45619-w)。

方法 ID 为 `group_53_a053_audio_watermark`。

## 代码目录

| 路径 | 用途 |
| --- | --- |
| `src/` | Henon 映射、DTCWT、FrCT、能量量化、水印嵌入与盲提取 |
| `tests/` | 变换参考矩阵、正逆变换与无攻击 WAV 水印闭环测试 |
| `requirements.txt` | 单核算法的 Python 依赖 |
| `run_experiments.py` | 批量运行 SNR、BER 与三项鲁棒性对照 |
| `src/mpi_watermark.py` | MPI 分帧嵌入、盲提取与计时 |
| `api.py` | 接收平台请求，返回生成的 WAV 与 JSON 报告 |

## 单核模块验证

在本目录下使用 Python 3.12 创建虚拟环境并运行测试：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

- `src/henon.py` 按论文第 5 页式（7）及式（9）至（11）计算 modified Henon 序列，以整段水印对应的序列均值为阈值，再执行 XOR。实现将 `x0, y0` 视为首次更新前的种子，余弦索引从 0 开始。论文给出了控制参数范围，未给出实验使用的六个密钥值。测试使用明确指定的参数。
- `src/dtcwt_transform.py` 使用 `dtcwt` 的 `near_sym_a` 和 `qshift_a` 滤波器，将 486 点实数帧两端各对称扩展 13 点，做五层变换，重建后裁回原长度。按第 4 页式（5）的形式，将库输出的交错低频行配对为 16 个复数，再将修改后的实部和虚部交错写回供逆变换使用。第 5 页给出了滤波器参考文献，具体滤波器组、两树相位约定和边界规则仍需与作者实现核对。
- `src/quantization.py` 用平方能量 `E = sum(|c|²)` 验证候选量化规则。PDF 第 9 页式（17）的区间起点缺少步长因子，式（16）给出的比例为原能量除以目标能量。为满足式（21）的余量判决，采用 `E' = Δ × (floor(E / Δ) + q)`，其中比特 0 对应 `q = 0.25`、比特 1 对应 `q = 0.75`，再以 `sqrt(E' / E)` 缩放系数。测试验证了目标能量和比特恢复。全零系数无法靠缩放达到正能量目标，当前模块会报告错误。平方能量定义仍需与前置论文核对。

## FrCT 构造

2023 年论文第 4 页的式（2）重复了式（1）。`src/frct.py` 采用 [2020 年 FrCT 前置论文](https://doi.org/10.1016/j.sigpro.2020.107509)式（9）、（10）的加权 Charlier 递推，以及式（37）、（41）、（42）的交替正负特征空间和分数阶相位。

前置论文表 2 的 Gram–Schmidt 结果与 QR 计算一致，但在矩阵尺寸大于 2 时可见非对称项。为满足后续对称正交投影的前提，本实现对 QR 结果的对称部分做谱分解，将特征值分别投影为 +1 和 −1，再用带列主元的 QR 为各特征空间选择一组基。重根空间内的基依赖这一选择。音频实验采用 `a1 = 0.16`，由表 2 中 `a1 = 0.01 × N` 的示例外推至 `N = 16`。这两项是复现实现的选择，2023 年论文未给出对应的原代码或实验设置。

## 单核 WAV 验证

`src/watermark.py` 接收 44.1 kHz 单声道 PCM16 WAV，每 486 点承载 1 bit，提取只需要带水印文件、位数和相同参数。输入可用容量为 `floor(采样点数 / 486)` 位，未用于嵌入的尾部样本保持原值。全零载体帧和可能溢出的 PCM16 输出会报告错误。

在本目录运行 Python，可用以下代码检查自己的 WAV。测试密钥用于实验复现。

```python
from src.henon import HenonKey
from src.watermark import embed_wav, extract_wav

bits = [0, 1, 1, 0, 1, 1, 0, 0]
key = HenonKey(a=1.4, b=0.3, c=0.2, d=0.4, x0=0.3, y0=0.5)
embed_wav("original.wav", "marked.wav", bits, key)
recovered = extract_wav("marked.wav", len(bits), key)
ber = (recovered != bits).mean()
print(f"BER = {ber:.2%}")
```

使用随机种子 53 的合成 WAV 做首次无攻击验证。SNR 按输入与写盘后重新读出的 PCM16 样本计算。

| 音频 | 错误比特 | BER | SNR |
| --- | ---: | ---: | ---: |
| 双音加低幅噪声 | 0 / 128 | 0% | 58.88 dB |
| 均匀噪声 | 0 / 128 | 0% | 47.81 dB |

当前候选规则对完整 FrCT 向量计算平方能量，并用同一倍数缩放所有系数。酉变换保持全向量能量，逆变换也保留该缩放，因此改变 FrCT 阶数不会改变这条流程的水印结果。两段合成音频在 `alpha = 0` 和 `alpha = 0.2` 下得到相同的 PCM16 样本。[2022 年前置论文](https://doi.org/10.1016/j.eswa.2022.117325)的第 5.1 节也使用平方二范数，但在 FrCT 前将低频向量分为四组，每组单独变换和量化。该流程与 2023 年的逐帧流程有差异。全组平方能量仍有酉不变性，论文所述的阶数效应仍待解释。

### 真实音乐与重建后校准

用 Kimiko Ishizaka 演奏的《Open Goldberg Variations》01 Aria 的 1.05–61.05 秒作为 CC0 替代样本。在 44.1 kHz 单声道 PCM16 下测量，使用随机种子 53 生成 5,444 位水印，固定 `alpha = 0.2`、`delta = 0.2` 和 `a1 = 0.16`。[录音来源及许可](https://archive.org/details/OpenGoldbergVariations)

默认嵌入在逆变换前设定目标能量。重新分析浮点重建帧时，原先的 67 个错误中有 29 个在保留完整 512 点时仍会出现，裁回 486 点再补边时有 67 个。可选的 `embed_wav(..., calibrate=True)` 保持高频细节系数固定，按重建后重新分析的能量选择低频增益。候选区间保留 0.025 个量化步长的余量，候选帧舍入为 PCM16 后再次验证目标比特。如果当前帧已经在有余量的正确区间，可以直接保留。无法使用可行的低频增益时，嵌入会报告帧号。

| 同一段 Aria，无攻击 | 错误比特 | BER | SNR |
| --- | ---: | ---: | ---: |
| 默认嵌入 | 67 / 5,444 | 1.23% | 14.51 dB |
| 加入重建后校准 | 0 / 5,444 | 0% | 17.91 dB |

校准是工程修正，提取仍调用原有的 `extract_wav`。虽然整段 SNR 提升，原先 67 个错误帧合计的平方失真有所增加。

对同一音乐样本做三项鲁棒性初测。高斯白噪声的随机种子为 532，MP3 使用 FFmpeg 和 libmp3lame 编解码，移位在开头补 5 个零并截去尾部 5 点。

| 处理条件 | 默认嵌入 BER | 校准后 BER |
| --- | ---: | ---: |
| 高斯白噪声，30 dB | 1.25% | 0.15% |
| MP3，128 kbps | 18.75% | 45.65% |
| 向右移位 5 个采样点 | 5.99% | 18.15% |

校准改善了此段音乐的无攻击提取和加噪结果，MP3 和移位后的误码上升。

### 多曲目对照

输入使用 44.1 kHz 单声道 PCM16 WAV。按统一的水印种子和密钥比较默认嵌入、0.025 步长余量和 0.20 步长余量。每个输入在同一进程内完成 WAV 嵌入和提取，`--workers` 只并行运行不同实验，正式计时请使用 MPI 入口。MP3 重编码需要安装带 `libmp3lame` 的 FFmpeg。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python run_experiments.py \
  --workers 4 --output /tmp/a053-comparison path/to/jazz.wav path/to/rock.wav
```

输出目录包含带水印 WAV 和 `results.json`，记录每种设置的无攻击 BER、SNR 与处理后的 BER。输入源如果是 MP3，WAV 已经带有一次有损编码的影响，因此 MP3 测试表示再次编码。

本次对照使用五首 CC BY 4.0 曲目，每首裁剪 60 秒，转为 44.1 kHz 单声道 PCM16。每首嵌入 5,444 位，表中 BER 为五首的平均值。

| 风格 | 曲目来源 | 裁剪起点 |
| --- | --- | ---: |
| 爵士 | Ignacio Tapia Carmagnani · [Anticipating Gold](https://freemusicarchive.org/music/ignacio-tapia-carmagnani/summer-is-on-its-way/anticipating-gold/) | 0 秒 |
| 流行 | JMHBM · [Afterglow](https://freemusicarchive.org/music/beat-mekanik/euphoria/afterglow-3/) | 0.52 秒 |
| 嘻哈伴奏 | 1000 Handz · [Final Chapter](https://freemusicarchive.org/music/1000-handz/cc-by-free-to-use-melodic-rap-instrumentals-vol-2/final-chapter/) | 0 秒 |
| 摇滚 | Kevin MacLeod · [Take the Lead](https://incompetech.com/music/royalty-free/index.html?isrc=USUAN1100695) | 0 秒 |
| 电子舞曲 | 1000 Handz · [Dance Dance](https://freemusicarchive.org/music/1000-handz/cc-by-free-to-use-dancehouse-instrumentals/dance-dance/) | 0 秒 |

| 设置 | 无攻击 BER | SNR 范围 | 30 dB 白噪声 BER | 128 kbps MP3 BER | 右移 5 点 BER |
| --- | ---: | ---: | ---: | ---: | ---: |
| 默认嵌入 | 0.19% | 33.09–47.10 dB | 9.96% | 47.55% | 39.98% |
| 校准余量 0.025 | 0.00% | 36.16–56.89 dB | 28.95% | 50.04% | 44.06% |
| 校准余量 0.20 | 0.00% | 33.41–50.41 dB | 10.45% | 47.42% | 40.10% |

0.20 余量在两种校准设置中保留了较低的加噪和移位误码。2023 年论文表 12 的 128 kbps MP3 BER 为 0%，目前的替代音乐和实现仍与该结果有明显差距。[2023 年论文](https://doi.org/10.1038/s41598-023-45619-w)

### MPI 实验

在已有 Open MPI 的 CPU 机上启用 Python 虚拟环境，并安装 MPI 绑定：

```bash
python -m pip install -r requirements.txt -r requirements-mpi.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 mpirun -np 4 \
  python -m src.mpi_watermark path/to/source.wav \
  --calibration-margin 0.025 --output-wav /tmp/a053-mpi-4.wav
```

所有进程共用同一水印序列，主进程先生成完整 Henon 掩码，再分发连续帧和对应比特。各进程使用与串行实现相同的帧处理函数。计时包含 MPI 分发和收集，WAV 读写在计时区间外。程序输出嵌入与提取耗时、无攻击 BER 和输出 WAV 的 SHA-256。比较不同进程数前，先核对哈希和误码结果一致。省略 `--calibration-margin` 可测默认嵌入。

在 CPU 配额为 4 核的 Codex 云实例上，使用 Open MPI 5.0.7 对 60 秒爵士片段做了单次计时，校准余量为 0.20。

| MPI 进程数 | 嵌入耗时 | 提取耗时 | 嵌入加速比 | 提取加速比 |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 36.84 s | 9.22 s | 1.00× | 1.00× |
| 2 | 20.32 s | 5.06 s | 1.81× | 1.82× |
| 4 | 10.69 s | 2.74 s | 3.45× | 3.37× |

三次运行都恢复了 5,444 位，输出 WAV 也与串行校准版本逐字节一致。华为云的 8、16 进程及重复计时仍待测量。

## 平台接入

方法已登记到平台目录。算法服务接收 `POST /process`，配置指向 `http://127.0.0.1:8000/process`。启动命令、素材限制、结果保留时间和样例出处见[根目录 README](../../README.md#本机运行)。请求和结果格式见[算法接入规范](../../docs/算法接入规范.md)。
