# 入口场景来源与许可边界

现有 `entry-scene.js`、`entry-math-atlas.svg` 与 `entry-fallback.webp` 由本仓库提交 `1f88c781ddf71eb85fe7048d622da83de559a2a0` 在 2026-09-30 引入。提交及同期任务记录称其来自 Gravity Journey 参考站，但没有记录可核实的参考站 URL 或独立场景授权。本次保留资源，不据文件名或公开可访问性推断授权。

JS 内嵌 Three.js 的运行时版本标记 `revision:184`，对应官方 three 0.184.0。`entry-scene-THREE-LICENSE` 是该固定版本官方 npm 包中的完整 MIT 许可，仅说明 Three.js 组件的许可；没有把整个混合压缩场景包声明为 MIT。`entry-scene.manifest.json` 记录版本证据、固定 npm 包来源及本地文件 SHA256。

参考站独立场景、公式 atlas 与降级图片的确切来源和授权仍待核实。该限制保留在清单的 `reference_scene_authorization`，不通过修改运行资源、换图或升级 Three.js 掩盖。
