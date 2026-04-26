"""教育学知识库（Educational Knowledge Base）模块。

POC 阶段：纯 JSON 文件存储 + 静态加载（``poc_loader``）。
正式版（L3）将迁移到 SQLite + Chroma 双存储 + 进化 pipeline。

主要导出：

- ``poc_loader.load_theories()`` — 加载 ``data/edu_theories/*.json`` 全部卡片
- ``poc_loader.resolve_persona_anchors(persona)`` — 把 persona 的 theory_anchors
  解析为 ``ResolvedTheory`` 列表，可直接喂给 Jinja 模板渲染
"""
