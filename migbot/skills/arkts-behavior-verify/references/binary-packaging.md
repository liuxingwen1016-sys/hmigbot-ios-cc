# 二进制发布适配

源码在本 MySkills 仓库维护，Core 的构建流水线负责 Nuitka 编译。
`scripts/`、`engines/setting/scripts/`、`engines/interaction/scripts/` 各自编译为独立模块根。
开发时仍可直接运行 Python；发布后原脚本路径对应薄启动器，库逻辑编入二进制。
跨引擎进程通过 behavior_runtime 与固定 behavior_bridge 命令通信，不能把冻结可执行文件当作 Python 解释器执行 -c。

Core 生成 scripts/schema-hints.json 供二进制审阅入口读取枚举，并生成 binary-package-manifest.json 校验实际发布字节。
原 package-manifest.json 与 source-provenance.json 保留源码和上游证据；不得使用原源码 SHA 校验转换后的启动器。
`package_skill.py verify --root <发布技能目录>` 自动识别源码包或二进制包。
源码修改后重新生成源码清单、更新对应 Core，再重新构建。二进制包不可反向打包为源码。

测试与 fixtures 留在开发仓库，发布时排除。不要把 .git、缓存或本地构建目录复制到 Core 技能目录。
这里不需要额外同步器或 core-sync-manifest.json。发布完整性通过不等于应用行为验证通过。
