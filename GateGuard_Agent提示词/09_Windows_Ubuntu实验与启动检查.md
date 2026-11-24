# Windows VS Code 与 Ubuntu 实验约定

文档版本 3.1，2026-11-24。目标是保持 Windows 开发习惯，先在 Ubuntu 验证 Linux 能力，再验证 openEuler。这里只提供后续实施步骤，文档更新不会自动安装软件、启动 VM 或修改内核。

## 推荐环境

Windows 安装 VS Code、Python 扩展、Remote-SSH 和独立 Python 3.12。Ubuntu 24.04 LTS 虚拟机建立独立 Python 3.12 venv，安装按实际版本固定的 Git、OpenSSH、clang/LLVM、libbpf、bpftool、编译依赖和 btrfs-progs。具体包名、内核和版本由 A/C 在 VM 中验证后冻结；不能把当前在线内核文档的新接口当作 Ubuntu 现有能力。

2026-11-23 的历史只读核查发现本地 Python 指向 3.9.4，VS Code 和上述扩展已安装，VMware 已有 Ubuntu 和 openEuler 登记。Ubuntu VM 配置为 2 vCPU、4 GB RAM；这些是核查时的配置及缓存信息，不是 guest 内实际验证结果。可以先用现有 VM 做功能测试；稳定性能测试应单独记录 CPU/内存/磁盘和背景负载。

## 两类 VS Code 窗口

| 窗口 | 打开的目录与解释器 | 适合任务 |
|---|---|---|
| Windows 本地 | 本地代码仓库、Windows 的 .venv/Scripts/python.exe | DEF 数据清洗/质检，组长离线策略学习与结果分析，B 的纯 Python 测试 |
| Remote-SSH 到 Ubuntu | VM 的 Linux 仓库、Linux 的 .venv/bin/python | ABC 系统构建、DEF 真实采集、策略安装与恢复实验 |

VS Code 在 Windows 显示，但 Remote-SSH 窗口的终端、调试与 Python 实际运行于 Ubuntu。点击运行前查看远程标志和选中的解释器。Windows 与 VM 的 venv 不互拷，不混用 pip；使用对应解释器的 `python -m pip`。需要特权的动作由受控助手或明确实验命令完成，不把整个 IDE 长期作为 root 运行。

## 源码、文件系统与传输

建议 Windows 和 VM 各自 Git 工作副本；按同一提交联调，变更由作者保存并审查后同步。共享工作树不擅自切分支或覆盖他人。VM 实验代码和目标文件放在 Linux 原生文件系统中；保护数据使用登记 loop 文件内的专用 Btrfs 子卷。Windows 共享文件夹不承担 BPF/权限/快照文件语义验收。

数据包与高层 profile 通过 SSH/SFTP 或显式复制交换，校验和通过后使用；不传旧 PID/cgroup/inode 当新环境绑定。不要在运行中的审计 DB 上直接复制单个 SQLite 文件；采用 B 的一致导出或封包接口。Windows 浏览器通过 SSH 端口转发访问 VM 回环面板，默认不向公网开放。

## 首次环境验证由 A/C 完成

1. SSH 连通，记录发行版、uname、Python、CPU/内存和包版本；这些只读检查先行。
2. 检查 BTF、BPF/LSM 配置、`/sys/kernel/security/lsm`、cgroup v2 和权限，报告 supported/unsupported/unverified。
3. 构建受限目标的最小采集与 LSM 测试。libbpf-bootstrap 的原始 lsm 示例会拒绝 bpf()，不能直接当作文件守护运行；先改成只作用于登记实验主体的测试。
4. 检查 Btrfs 支持，用本次登记的实验 loop 文件和专用挂载验证快照/恢复；不格式化 VM 系统盘或 Windows 分区。
5. 验证 Windows 离线模块可导入、读取 VM 数据、生成 profile；Linux-only 子命令在 Windows 返回明确不支持。

需要修改启动参数、重启或调整内核时，先记录现状、必要性和回退办法，由组长确认具体环境操作。保留现有安全模块，不为让 demo 通过而关闭 AppArmor/SELinux 或全局安全机制。BPF LSM 不可用时报告原因，不能无声改成 fanotify 并沿用精细权限承诺。

## Ubuntu 到 openEuler

Ubuntu 用于首轮开发与完整闭环；openEuler 单独记录内核、BTF、LSM、工具链、Python 和文件系统能力，再重编译、重新绑定资源、重跑能力矩阵和核心用例。CO-RE 能帮助字段适配，但不保证所有 hook/helper 可用。最终报告分别列出两平台实测范围，禁止把 Ubuntu 通过写成 openEuler 已通过。

## 参考

- [VS Code Remote-SSH](https://code.visualstudio.com/docs/remote/ssh)
- [VS Code Python 解释器](https://code.visualstudio.com/docs/python/environments)
- [Python venv](https://docs.python.org/3.12/library/venv.html)
- [Linux BPF LSM](https://docs.kernel.org/bpf/prog_lsm.html)
- [Linux LSM 配置](https://docs.kernel.org/admin-guide/LSM/index.html)

## 规范化与路径检查

B 本机指定工作副本为 `C:\Users\cm191\Documents\GitHub\GateGuard`；后续本机修改在此进行，其他成员与 VM 各用自己的副本，软件不写死此路径。离线加工按 08/12 保留 Linux 原始路径、对象和时钟语义；Windows realpath 不能验证 Linux 链接与对象身份。正式数据以契约 3.1 封包，完整 specs 与 run 载荷随包校验。
