# 全景天空资产

这些是 Poly Haven 实际资产下载中的 8K Tonemapped JPG，转换为 8192 × 4096、quality=95 的 WebP，保留完整全景。不是网站缩略图或案例渲染图。

所有源资产采用 [CC0-1.0](https://polyhaven.com/license)，可商用、修改和随产品分发。源文件 URL、MD5、处理后尺寸和大小记录在 `sources.json`。

| 时段 | 资产 | 作者 |
| --- | --- | --- |
| 白天 | [Kloofendal 48d Partly Cloudy Pure Sky](https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky) | Greg Zaal、Jarod Guest |
| 清晨 | [Qwantani Dawn Pure Sky](https://polyhaven.com/a/qwantani_dawn_puresky) | Greg Zaal、Jarod Guest |
| 黄昏 | [Belfast Sunset Pure Sky](https://polyhaven.com/a/belfast_sunset_puresky) | Dimitrios Savva、Greg Zaal、Jarod Guest |
| 夜晚 | [Qwantani Night Pure Sky](https://polyhaven.com/a/qwantani_night_puresky) | Greg Zaal、Jarod Guest |

运行时按需并行加载当前时段的 `*.preview.webp`（1024 × 512、约 6–27 KB）和完整 8K 图。预览仅用于尽早显示背景；完整图就绪后替换预览，并更新环境反射。完整图加载失败时回退程序化天空，不把预览当作最终画质。

完整 8K 文件未缩小或重新压缩。预览由对应 WebP 用 Lanczos 缩小、quality=85 编码；来源与对应关系见 `sources.json`。

页面内复用压缩字节与进行中的下载；解码使用异步 ImageBitmap，旧纹理释放时关闭解码图。每个天空实例只常驻当前一张纹理；预览阶段不额外构建 PMREM。天空与反射使用同一份完整图和朝向。保存截图会等待完整资源或程序化回退就绪，不导出临时预览。

全景采样显式修正经度接缝的梯度，保留 mip 过滤；照片已有云层，天气雾化只由实际雨、雪、雾和沙尘驱动。ImageBitmap 翻转和色彩处理遵循 [Three.js 的加载约定](https://threejs.org/docs/pages/ImageBitmapLoader.html)。
