import os
import re
import torch
from typing import List, Callable

def get_define_value_from_file(filepath, macro_name):
    """
    从单个头文件中提取 #define 宏的值，并尝试用 eval 计算表达式
    :param filepath: 头文件的完整路径
    :param macro_name: 宏名称，如 "PROF_SIZE_PER_CORE"
    :return: 计算后的数值（int/float），未找到则返回 None
    """
    if not os.path.isfile(filepath):
        print(f"文件不存在: {filepath}")
        return None

    # 匹配 #define 宏定义的正则（忽略注释）
    pattern = re.compile(r'^\s*#\s*define\s+' + re.escape(macro_name) + r'\s+([^\\/].*?)(?:\s*//.*|$)', re.IGNORECASE)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # 跳过纯注释行
                if line.startswith('//') or line.startswith('/*'):
                    continue

                match = pattern.match(line)
                if match:
                    value_expr = match.group(1).strip()
                    # 去除可能的括号，如 (1024) 或 (1024 * 2)
                    value_expr = value_expr.strip()
                    if value_expr.startswith('(') and value_expr.endswith(')'):
                        value_expr = value_expr[1:-1].strip()

                    print(f"找到宏定义: {macro_name} = {value_expr} (在 {filepath} 第 {line_num} 行)")

                    # 使用 eval 安全计算表达式
                    try:
                        # 构建安全的命名空间（只允许基本数学常量和操作）
                        safe_namespace = {
                            '__builtins__': {},
                            'True': True,
                            'False': False,
                        }
                        result = eval(value_expr, safe_namespace)
                        print(f"计算结果: {result}")
                        return result
                    except Exception as e:
                        print(f"eval 计算失败: {e}")
                        return None
    except Exception as e:
        print(f"读取文件出错: {e}")
        return None

    return None  # 未找到

def get_script_base_dir() -> str:
    """返回当前脚本（trace_utils.py）所在目录，处理 __file__ 为空的情况"""
    script_dir = os.path.dirname(__file__)
    return script_dir if script_dir else os.getcwd()

def get_define_value(relative_dir: str, filename: str, macro_name: str):
    # 解析相对路径
    base = get_script_base_dir()
    filepath = os.path.join(base, relative_dir, filename)
    return get_define_value_from_file(filepath, macro_name)

def get_define_value_from_base(macro_name):
    """从固定头文件中读取宏定义的值，并打印结果"""
    relative_dir = "../../../src/cam/comm_operator/ascend_kernels/fused_deep_moe/op_kernel"
    filename = "fused_deep_moe_base.h"
    value = get_define_value(relative_dir, filename, macro_name)
    if value is not None:
        print(f"🎉 最终结果: {macro_name} = {value}")
    else:
        print(f"❌ 未找到宏 {macro_name}，请检查路径和文件内容。")
    return value

def get_prof_size_per_core():
    """获取 PROF_SIZE_PER_CORE 宏的值（整数）"""
    return get_define_value_from_base("PROF_SIZE_PER_CORE")

def get_enable_moe_profiling():
    """获取 ENABLE_MOE_PROFILING 宏的布尔值（非0即启用）"""
    val = get_define_value_from_base("ENABLE_MOE_PROFILING")
    # 如果未找到宏，默认返回 False；否则根据值是否为0判断
    return False if val is None else val != 0

def get_core_num_list():
    use_1c2v = os.environ.get('MOE_USE_1C2V', '0')
    if use_1c2v == '1':
        return [24, 24, 24]
    else:
        return [24, 48]


def mapping_with_1c2v(gid, idx):
    if not hasattr(mapping_with_1c2v, "aic_offset"):
        core_num_list = get_core_num_list()
        mapping_with_1c2v.aic_offset = core_num_list[0]
    if gid == 0:
        return idx
    elif gid == 1:
        return mapping_with_1c2v.aic_offset + 2 * idx
    elif gid == 2:
        return mapping_with_1c2v.aic_offset + 2 * idx + 1
    else:
        raise ValueError("Invalid group id")

def mapping_with_sequance(gid, idx):
    if not hasattr(mapping_with_sequance, "sequance_mapping"):
        core_num_list = get_core_num_list()
        mapping_with_sequance.base_mapping = [sum(core_num_list[:i]) for i in range(len(core_num_list))]
    return mapping_with_sequance.base_mapping[gid] + idx

def group_by_mapping(profiling: torch.Tensor, group_sizes: List[int],   # 按照aic 偶数aiv 和 奇数aiv 把原始的（72, 2048） 拆分成（24, 2048）和（48, 2048）分成三组
                     mapping_func: Callable[[int, int], int] = mapping_with_sequance) -> List[torch.Tensor]:
    """通过映射函数将 profiling 数据分组。"""
    total_cores = profiling.size(0)
    groups = []
    for gid, size in enumerate(group_sizes):
        indices = [mapping_func(gid, i) for i in range(size)]
        # 索引越界检查
        if max(indices) >= total_cores or min(indices) < 0:
            raise ValueError(f"Mapping out of range: group {gid} indices {indices}")
        groups.append(profiling[indices])
    return groups

def save_profiling_data(profiling_raw: torch.Tensor, rank_id: int, output_dir: str = "../../../output/cam/profiling_data"):
    """从原始 tensor 提取 MoE profiling 数据，按核心类型拆分并保存为 .pt 文件。"""
    if not get_enable_moe_profiling():
        return

    core_num_list = get_core_num_list()
    prof_size_per_core = get_prof_size_per_core()
    total_cores = sum(core_num_list)
    required_len = total_cores * prof_size_per_core

    # 切片并重塑
    profiling = profiling_raw.view(torch.int64).flatten()[:required_len].view(total_cores, prof_size_per_core)
    # kernel里 coreGlobal = initGlobal[AscendC::GetBlockIdx() * PROF_SIZE_PER_CORE]; 
    # coreGlobal = initGlobal[(AscendC::GetBlockNum() + AscendC::GetBlockIdx()) * PROF_SIZE_PER_CORE];
    # 保证了数据都是连续紧凑排列的，确保这个裁剪语义的正确性
    if len(core_num_list) == 3:
        group_mapping = mapping_with_1c2v
    else:
        group_mapping = mapping_with_sequance
    split_tensors = group_by_mapping(profiling, core_num_list, group_mapping)

    # 确定输出绝对路径（相对路径基于脚本目录）
    base = get_script_base_dir()
    out_dir = output_dir if os.path.isabs(output_dir) else os.path.join(base, output_dir)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"rank{rank_id:03d}.pt")
    torch.save(split_tensors, out_path)
    print(f"Saved: {out_path} ({len(split_tensors)} types)")