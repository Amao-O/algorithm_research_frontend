# 第 53 组 · A053 音频数字水印复现

复现目标是实现论文 *An efficient watermarking algorithm for digital audio data in security applications*（Scientific Reports，2023）中的水印嵌入、盲提取和 MPI 并行处理。论文 DOI 为 [10.1038/s41598-023-45619-w](https://doi.org/10.1038/s41598-023-45619-w)。

方法 ID 为 `group_53_a053_audio_watermark`。

## 代码目录

| 路径 | 用途 |
| --- | --- |
| `src/` | Henon 映射、DTCWT、FrCT、能量量化、水印嵌入与盲提取 |
| `tests/` | 变换参考矩阵、正逆变换与无攻击 WAV 水印闭环测试 |
| `requirements.txt` | 单核算法的 Python 依赖 |
| `run_experiments.py` | 后续运行 SNR、BER、鲁棒性与 MPI 性能实验 |
| `api.py` | 后续提供前端调用的 HTTP 接口 |

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

当前候选规则对完整 FrCT 向量计算平方能量，并用同一倍数缩放所有系数。酉变换保持全向量能量，逆变换也保留该缩放，因此改变 FrCT 阶数不会改变这条流程的水印结果。两段合成音频在 `alpha = 0` 和 `alpha = 0.2` 下得到相同的 PCM16 样本。论文所述的阶数效应仍待核对 2022 年音频水印前置论文中的量化定义和系数选择。上述 BER 和 SNR 只对应合成音频，尚未测量音乐、鲁棒性和 MPI 性能。

## 平台接入

算法可运行后，将方法配置放入 `public/methods/group_53_a053_audio_watermark.json`，并更新 `public/methods/index.json`。真实输入和输出样例放入 `public/samples/group_53_a053_audio_watermark/`。请求和结果格式见[算法接入规范](../../docs/算法接入规范.md)。
