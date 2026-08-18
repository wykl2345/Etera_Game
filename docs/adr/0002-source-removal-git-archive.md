# ADR-0002: 源码删除 + git tag 留档

v1 的 PySide6 源码（Core/、tests/）在迁移到前后端分离架构后删除，仅以 git tag `pre-web-refactor` 留档。原因是该仓库常被 LLM 辅助开发，大量旧源码会污染上下文、拖慢每次会话；而架构与 API 语义已由文档（architecture/requirements/references + DSL.txt）完整记录，重写时有据可依。

**Consequences**: 需要代码示例时用 `git show pre-web-refactor:<path>` 查阅；`docs/references.md` §四 收录了常用文件的查阅命令。
