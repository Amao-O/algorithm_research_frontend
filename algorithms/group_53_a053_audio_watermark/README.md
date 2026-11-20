# 第 53 组 · A053 音频数字水印复现

复现目标是实现论文 *An efficient watermarking algorithm for digital audio data in security applications*（Scientific Reports，2023）中的水印嵌入、盲提取和 MPI 并行处理。论文 DOI 为 [10.1038/s41598-023-45619-w](https://doi.org/10.1038/s41598-023-45619-w)。

方法 ID 为 `group_53_a053_audio_watermark`。

## 代码目录

| 路径 | 用途 |
| --- | --- |
| `src/` | Henon 映射、DTCWT、FrCT、能量量化、水印嵌入与盲提取，以及后续的 MPI 实现 |
| `tests/` | 正逆变换、无攻击水印闭环与串行和并行结果一致性的测试 |
| `requirements.txt` | 后续记录实际使用的 Python 依赖 |
| `run_experiments.py` | 后续运行 SNR、BER、鲁棒性与 MPI 性能实验 |
| `api.py` | 后续提供前端调用的 HTTP 接口 |

当前已建立源码和测试目录。先核对 FrCT 矩阵构造、DTCWT 低频系数与帧边界处理，以及能量量化公式。单进程无攻击条件下的 BER 达到 0 后，再用华为云 CPU 资源验证 MPI 并行效果。

## 平台接入

算法可运行后，将方法配置放入 `public/methods/group_53_a053_audio_watermark.json`，并更新 `public/methods/index.json`。真实输入和输出样例放入 `public/samples/group_53_a053_audio_watermark/`。请求和结果格式见[算法接入规范](../../docs/算法接入规范.md)。
