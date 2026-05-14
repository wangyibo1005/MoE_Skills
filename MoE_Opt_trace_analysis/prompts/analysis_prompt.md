请根据给出的算子 trace 统计表分析性能表现。分析对象是 `trace.json` 中的事件统计，而不是某个固定算子；如果用户提供了算子名、源码目录或 phase map，请结合这些上下文解释 phase/category 的业务含义。

重点关注：

1. 哪些 phase 占总 wall time 比例最高。
2. 主瓶颈更偏 wait、sync、compute、epilogue、communication、quant 还是其他 category。
3. 耗时主要集中在哪些 core group、tid 或 raw name。
4. 关键 phase 之间 overlap 是否偏低，是否可能存在串行化或流水不足。
5. 外层阶段内是否存在明显 bubble 或未归因时间。
6. 如果提供了源码上下文，哪些 raw name 或 phase 应优先回查源码打点位置。
7. 输出简洁、专业、可执行的诊断结论。

要求：

- 不要虚构原始 trace 中没有的事实。
- 结论必须基于统计表。
- 优先指出 1~3 个最关键的问题。
- 优先引用 phase/name/category/core group 的 `union_us` 和 `ratio_to_total_wall`。
- 明确区分 `union_us` 与 `total_us`：`union_us` 更接近 wall time 覆盖，`total_us` 会重复累计并行事件。
- 如果当前 phase map 或诊断规则明显偏某个算子，请说明这些结论的适用边界。
