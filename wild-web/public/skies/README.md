# 全景天空资产

这些是 Poly Haven 实际资产下载中的 8K Tonemapped JPG，转换为 8192 × 4096、quality=95 的 WebP，保留完整全景。不是网站缩略图或案例渲染图。

所有源资产采用 [CC0-1.0](https://polyhaven.com/license)，可商用、修改和随产品分发。源文件 URL、MD5、处理后尺寸和大小记录在 `sources.json`。

| 时段 | 资产 | 作者 |
| --- | --- | --- |
| 白天 | [Kloofendal 48d Partly Cloudy Pure Sky](https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky) | Greg Zaal、Jarod Guest |
| 清晨 | [Qwantani Dawn Pure Sky](https://polyhaven.com/a/qwantani_dawn_puresky) | Greg Zaal、Jarod Guest |
| 黄昏 | [Belfast Sunset Pure Sky](https://polyhaven.com/a/belfast_sunset_puresky) | Dimitrios Savva、Greg Zaal、Jarod Guest |
| 夜晚 | [Qwantani Night Pure Sky](https://polyhaven.com/a/qwantani_night_puresky) | Greg Zaal、Jarod Guest |

运行时使用项目内的资源，只按需加载当前时段，并只常驻当前全景纹理。天空与环境反射使用同一份图和朝向；加载失败时使用现有程序化天空。
