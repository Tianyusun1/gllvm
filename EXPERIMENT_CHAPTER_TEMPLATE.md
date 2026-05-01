# 实验章节模板（可直接改写到论文）

## 4.1 实验环境与设置
- 硬件平台：CPU/GPU 型号、内存、操作系统。
- 编译器与版本：LLVM 版本、Python 版本。
- 基准输入：`dag_data.json`。
- 算法集合：baseline、GA、ACO。
- 参数网格：seed 与 budget 配置（见 `phase3_config.json`）。

## 4.2 评价指标
- 编译时间（compile_time_ms）
- 关键路径估计（critical_path_est）
- 资源冲突代理（resource_conflict_proxy）
- 寄存器压力代理（reg_pressure_proxy）

## 4.3 实验流程
1. 运行 Phase-2 对比实验，得到各配置原始结果。
2. 运行 Phase-3 聚合统计，产出 `aggregate.csv` 与 `report.md`。
3. 运行 `plot_results.py` 生成图表。

## 4.4 结果与分析
- 图1：compile time vs budget
- 图2：resource conflict vs budget
- 图3：reg pressure vs budget
- 图4：critical path vs budget

分析建议：
- 比较不同 budget 下 GA/ACO 的收益稳定性（均值与方差）。
- 讨论编译时间开销与调度质量之间的权衡。
- 给出推荐预算区间与算法选择建议。

## 4.5 小结
- 总结：在可接受编译开销下，哪类算法在哪些指标上更优。
- 局限：代理指标与真实运行时性能差异。
- 下一步：接入 LLVM 真实 MachineScheduler 进行端到端验证。
