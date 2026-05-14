#!/usr/bin/env python3
"""
增强版追踪数据收集器 - 支持64位组合ID（微秒时间戳，名称带seq，队列匹配，rank排序，两种extra_id模式）
支持按从叶子向上的层数过滤事件（--depth），1=所有叶子，2=叶子+父层，依此类推。
使用整型时间戳（cycles）进行区间包含判断，避免浮点误差。
"""

import json
import os
import glob
import torch
from collections import deque, defaultdict
from typing import List, Dict, Any, Tuple, Optional

CLOCK_DIVISOR = 50.0  # 时钟频率 (MHz)，用于将时钟周期转换为微秒

def extract_point_id_parts(combined_id: int) -> Tuple[int, int]:
    base_point_id = combined_id & 0xFFFFFFFF
    extra_id = (combined_id >> 32) & 0xFFFFFFFF
    if base_point_id >= 0x80000000:
        base_point_id = base_point_id - 0x100000000
    if extra_id >= 0x80000000:
        extra_id = extra_id - 0x100000000
    return int(base_point_id), int(extra_id)

def parse_profiling_data(profiling_tensor: torch.Tensor, core_type: int = 0, core_id: int = 0, debug: bool = False) -> List[Dict]: # 它对每个 core 的一行 buffer处理
    prof_size_per_core = profiling_tensor.shape[1]
    raw_count = int(profiling_tensor[core_id][0].item())
    record_count = raw_count - 1
    if debug:
        print(f"  Core {core_id}: raw_count={raw_count}, 实际记录数={record_count}, Profiling大小={prof_size_per_core}")
    if record_count <= 0:
        return []
    initial_timestamp = profiling_tensor[core_id][-1].item()
    if debug:
        print(f"  初始时间戳: {initial_timestamp} (索引-1)")
    records = []
    max_records = min(record_count, (prof_size_per_core - 2) // 2)
    if debug and record_count > max_records:
        print(f"  警告: 记录数量({record_count})超过可用存储空间，仅解析前{max_records}条")
    for i in range(max_records):
        combined_id = profiling_tensor[core_id][1 + i].item()
        raw_timestamp = profiling_tensor[core_id][-2 - i].item()
        diff = (raw_timestamp - initial_timestamp) & 0xFFFFFFFFFFFFFFFF
        timestamp_us = diff / CLOCK_DIVISOR # 50个cycle是一个us
        base_point_id, extra_id = extract_point_id_parts(combined_id)
        if debug:
            print(f"  记录{i}: 组合ID={combined_id:#x} (索引{1+i}), 时间戳={raw_timestamp} (索引{-2-i}), 差值={diff}, 时间戳_us={timestamp_us:.2f}")
        records.append({
            'timestamp_us': timestamp_us,
            'timestamp_cycles': diff,              # 整型差值，用于比较
            'raw_timestamp': raw_timestamp,
            'initial_timestamp': initial_timestamp,
            'combined_id': int(combined_id),
            'base_point_id': base_point_id,
            'extra_id': extra_id,
            'core_type': core_type,
            'core_id': core_id,
            'record_idx': i
        })
    return records

def load_all_ranks(data_dir: str = "profiling_data", debug_core: Optional[Tuple[int, int, int]] = None) -> Dict[int, Dict]:
    all_data = {} # 所有卡所有核解析出来的数据
    pt_files = sorted(glob.glob(os.path.join(data_dir, "rank*.pt")))
    for pt_file in pt_files: # 遍历各个卡
        basename = os.path.basename(pt_file) # basename是文件本身的名字
        rank_id = int(basename.split('.')[0][4:]) # 比如 “003”
        try:
            split_tensors = torch.load(pt_file, map_location='cpu')
            rank_records = [] # 所有核解析出来的数据
            for type_idx, tensor in enumerate(split_tensors): # 遍历各个组 
                core_num = tensor.shape[0]
                for core_id in range(core_num): # 遍历各个核
                    debug = (debug_core is not None and
                            debug_core[0] == rank_id and
                            debug_core[1] == type_idx and
                            debug_core[2] == core_id)
                    if debug:
                        print(f"\n调试核心 - Rank {rank_id}, 类型 {type_idx}, 核心 {core_id}:")
                        print(f"Tensor形状: {tensor.shape}")
                    records = parse_profiling_data(tensor, type_idx, core_id, debug) # 单个核解析出来的数据
                    for record in records:
                        record['rank_id'] = rank_id
                    rank_records.extend(records) 
            all_data[rank_id] = {
                'records': rank_records,
                'tensor_count': len(split_tensors)
            }
            print(f"Rank {rank_id}: {len(rank_records)} 条记录, {len(split_tensors)} 种核心类型")
        except Exception as e:
            print(f"加载 {pt_file} 失败: {e}")
    return all_data

    '''
        统一包成这样返回
        {
        "points": {
            "1": {...},
            "2": {...}
        }
        }
    '''
def load_mapping(mapping_file: str = "trace_mapping.json") -> Dict:
    if os.path.exists(mapping_file):
        with open(mapping_file, 'r') as f:
            data = json.load(f)
        if "points" in data:
            return data
        else:
            return {"points": data}
    return {"points": {}}

def convert_to_chrome_event_type(event_type: str) -> Tuple[str, str]:
    event_upper = event_type.upper()
    display_map = {
        'B': 'Begin',
        'E': 'End',
        'I': 'Instant',
        'C': 'Counter',
        'S': 'Async Start',
        'F': 'Async End',
        'M': 'Marker',
    }
    display_name = display_map.get(event_upper, 'Unknown')
    return event_upper, display_name

def build_interval_tree(intervals, debug=False):
    """
    构建区间树，使用整型 cycles 比较，计算每个区间到最深叶子的深度（叶子深度=1）。
    intervals: 列表，每个元素为 {'start_cycles', 'end_cycles', 'interval_obj'}
    """
    if not intervals:
        return

    # 按开始时间排序
    intervals_sorted = sorted(intervals, key=lambda x: x['start_cycles'])

    n = len(intervals_sorted)
    parent = [None] * n

    # 为每个区间寻找直接父节点（包含它的最小区间）
    for i in range(n):
        cur = intervals_sorted[i]
        best_parent = None
        best_parent_end = float('inf')
        for j in range(n):
            if i == j:
                continue
            other = intervals_sorted[j]
            # 严格包含：other.start <= cur.start and other.end >= cur.end
            if other['start_cycles'] <= cur['start_cycles'] and other['end_cycles'] >= cur['end_cycles']:
                # 确保严格包含（长度更大）
                if other['end_cycles'] - other['start_cycles'] > cur['end_cycles'] - cur['start_cycles']:
                    if other['end_cycles'] < best_parent_end: # 寻找“直接父节点”：最小包围区间
                        best_parent_end = other['end_cycles']
                        best_parent = j
        parent[i] = best_parent

    # 构建子节点列表
    children = [[] for _ in range(n)]
    for i, p in enumerate(parent):
        if p is not None:
            children[p].append(i)

    # 后序遍历计算深度
    depth = [0] * n
    def dfs(node):
        if not children[node]:
            depth[node] = 1
        else:
            max_child_depth = 0
            for child in children[node]:
                dfs(child)
                max_child_depth = max(max_child_depth, depth[child])
            depth[node] = max_child_depth + 1

    for i in range(n):
        if parent[i] is None:  # 根节点
            dfs(i)
    # 区间最小的是叶子结点，深度（其实是高度）为1
    # 将深度赋值给原始区间对象
    for i, interval in enumerate(intervals_sorted):
        interval['interval_obj']['depth_from_leaf'] = depth[i]

    if debug:
        print(f"区间树深度统计: 共 {n} 个区间")
        for i, interval in enumerate(intervals_sorted):
            print(f"  区间 {interval['interval_obj']['name']}: start_cycles={interval['start_cycles']}, end_cycles={interval['end_cycles']}, depth={depth[i]}")

def generate_chrome_trace(all_data: Dict[int, Dict], mapping: Dict,
                         output_file: str = "chrome_trace.json",
                         extra_mode: str = 'seq',
                         depth: int = 0,
                         debug_core: Optional[Tuple[int, int, int]] = None):
    """
    生成Chrome Tracing格式，支持按从叶子向上的层数过滤事件。
    depth: 0=全部保留，1=仅保留叶子节点，2=保留叶子及其父节点（最内两层），依此类推。
    """
    rank_to_pid = {}
    next_pid = 0
    points = mapping.get('points', {})
    skipped_count = 0

    # 收集元数据事件（进程名、线程名）
    metadata_events = []
    sorted_rank_ids = sorted(all_data.keys())
    for rank_id in sorted_rank_ids:
        pid = next_pid
        rank_to_pid[rank_id] = pid
        next_pid += 1
        metadata_events.append({
            'name': 'process_name',
            'ph': 'M',
            'pid': pid,
            'args': {'name': 'Rank'}
        })
        metadata_events.append({
            'name': 'process_sort_index',
            'ph': 'M',
            'pid': pid,
            'args': {'sort_index': rank_id}
        })

    # 按tid分组的事件列表（原始项）
    tid_events = {}  # key: (rank_id, core_type, core_id) -> list of raw item dicts
    tid_metadata_set = set()

    for rank_id in sorted_rank_ids:
        rank_data = all_data[rank_id]
        pid = rank_to_pid[rank_id]

        for record in rank_data['records']:
            base_point_id = str(record['base_point_id'])
            point_info = points.get(base_point_id, {})

            original_event_type = point_info.get('event_type')
            if not original_event_type:
                print(f"警告: 跳过记录 base_point_id={base_point_id} (rank {rank_id}, core {record['core_id']})，映射表中无 event_type")
                skipped_count += 1
                continue

            chrome_event_type, event_display_name = convert_to_chrome_event_type(original_event_type)

            label = point_info.get('label', f'point_{base_point_id}')
            raw_extra = record['extra_id']

            if extra_mode == 'legacy':
                # 模式A：extra_id整体使用
                base_name = f"{label} [extra:{raw_extra}]"
                raw_item = {
                    'event_base': {
                        'cat': 'trace',
                        'ts': record['timestamp_us'],
                        'pid': pid,
                        'tid': None,  # 稍后填充
                        'ph': chrome_event_type,
                        'args': {
                            'base_point_id': record['base_point_id'],
                            'extra_id': raw_extra,
                            'combined_id': f"0x{record['combined_id']:016x}",
                            'rank_id': rank_id,
                            'core_type': record['core_type'],
                            'core_id': record['core_id'],
                            'raw_timestamp': record['raw_timestamp'],
                            'initial_timestamp': record['initial_timestamp'],
                            'clock_divisor': CLOCK_DIVISOR,
                            'file': point_info.get('file', ''),
                            'line': point_info.get('line', 0)
                        }
                    },
                    'ph': chrome_event_type,
                    'base_name': base_name,
                    'ts': record['timestamp_us'],
                    'cycles': record['timestamp_cycles'],   # 整型时间戳差值
                    'point_info': point_info,
                    'need_seq': True
                }
            else:  # mode 'seq'
                # 模式B：拆分extra_id，高24位为seq，低8位为extra
                high24 = (raw_extra >> 8) & 0xFFFFFF
                low8 = raw_extra & 0xFF
                base_name = f"{label} [extra:{low8}]"
                full_name = f"{base_name} #{high24}"

                raw_item = {
                    'event_base': {
                        'cat': 'trace',
                        'ts': record['timestamp_us'],
                        'pid': pid,
                        'tid': None,
                        'ph': chrome_event_type,
                        'args': {
                            'base_point_id': record['base_point_id'],
                            'extra_id': low8,
                            'extra_raw': raw_extra,
                            'combined_id': f"0x{record['combined_id']:016x}",
                            'rank_id': rank_id,
                            'core_type': record['core_type'],
                            'core_id': record['core_id'],
                            'raw_timestamp': record['raw_timestamp'],
                            'initial_timestamp': record['initial_timestamp'],
                            'clock_divisor': CLOCK_DIVISOR,
                            'file': point_info.get('file', ''),
                            'line': point_info.get('line', 0)
                        }
                    },
                    'ph': chrome_event_type,
                    'base_name': base_name,
                    'full_name': full_name,
                    'ts': record['timestamp_us'],
                    'cycles': record['timestamp_cycles'],
                    'point_info': point_info,
                    'need_seq': False,
                    'seq': high24
                }

            tid_key = (rank_id, record['core_type'], record['core_id'])
            tid_str = f"type{record['core_type']}_core{record['core_id']:03d}"
            raw_item['event_base']['tid'] = tid_str

            # 添加线程元数据（每个tid一次）
            if tid_key not in tid_metadata_set:
                tid_metadata_set.add(tid_key)
                metadata_events.append({
                    'name': 'thread_name',
                    'ph': 'M',
                    'pid': pid,
                    'tid': tid_str,
                    'args': {'name': f'Core {record["core_id"]}'}
                })
                metadata_events.append({
                    'name': 'thread_sort_index',
                    'ph': 'M',
                    'pid': pid,
                    'tid': tid_str,
                    'args': {'sort_index': record['core_id']}
                })

            if 'event_id' in point_info:
                raw_item['event_base']['args']['event_id'] = point_info['event_id']

            tid_events.setdefault(tid_key, []).append(raw_item)

    # 配对阶段：收集完整区间和孤立事件
    all_intervals = []      # 每个元素: {'pid', 'tid', 'name', 'start_event', 'end_event', 'start_cycles', 'end_cycles', 'interval_obj'}
    unpaired_events = []    # 孤立事件（只有B或只有E）的最终事件对象

    b_count = 0
    e_count = 0
    unpaired_count = 0

    for tid_key, raw_items in tid_events.items():
        raw_items.sort(key=lambda x: x['ts'])
        pid = raw_items[0]['event_base']['pid']
        tid_str = raw_items[0]['event_base']['tid']

        # 按base_name分组
        groups = defaultdict(list)
        for item in raw_items:
            groups[item['base_name']].append(item)

        for base_name, group in groups.items():
            group.sort(key=lambda x: x['ts'])

            if extra_mode == 'legacy':
                # 模式A：队列匹配，分配seq
                b_queue = deque()
                seq_counter = 0
                for item in group:
                    if item['ph'] == 'B':
                        seq = seq_counter
                        seq_counter += 1
                        item['seq'] = seq
                        b_queue.append(item)
                    elif item['ph'] == 'E':
                        if b_queue:
                            b_item = b_queue.popleft()
                            seq = b_item['seq']
                            item['seq'] = seq
                            # 配对成功
                            b_file = b_item['point_info'].get('file', '')
                            b_line = b_item['point_info'].get('line', 0)
                            e_file = item['point_info'].get('file', '')
                            e_line = item['point_info'].get('line', 0)

                            full_name = f"{base_name} #{seq}"

                            b_event = b_item['event_base'].copy()
                            b_event['name'] = full_name
                            b_event['args']['begin_file'] = b_file
                            b_event['args']['begin_line'] = b_line
                            b_event['args']['end_file'] = e_file
                            b_event['args']['end_line'] = e_line

                            e_event = item['event_base'].copy()
                            e_event['name'] = full_name
                            e_event['args']['begin_file'] = b_file
                            e_event['args']['begin_line'] = b_line
                            e_event['args']['end_file'] = e_file
                            e_event['args']['end_line'] = e_line

                            interval = {
                                'pid': pid,
                                'tid': tid_str,
                                'name': full_name,
                                'start_event': b_event,
                                'end_event': e_event,
                                'start_cycles': b_item['cycles'],
                                'end_cycles': item['cycles'],
                                'interval_obj': None
                            }
                            interval['interval_obj'] = interval
                            all_intervals.append(interval)
                            b_count += 1
                            e_count += 1
                        else:
                            # 孤立E
                            print(f"警告: 孤立E事件，tid={tid_key}, base_name={base_name}, ts={item['ts']}")
                            item['seq'] = -1
                            e_event = item['event_base'].copy()
                            e_event['name'] = f"{base_name} #-1"
                            unpaired_events.append(e_event)
                            e_count += 1
                            unpaired_count += 1
                    else:
                        print(f"警告: 未知事件类型 {item['ph']}，tid={tid_key}")
                        e_event = item['event_base'].copy()
                        e_event['name'] = base_name
                        unpaired_events.append(e_event)
                        if item['ph'] == 'B':
                            b_count += 1
                        elif item['ph'] == 'E':
                            e_count += 1

                for item in b_queue:
                    print(f"警告: 孤立B事件，tid={tid_key}, base_name={base_name}, ts={item['ts']}")
                    seq = item['seq']
                    b_event = item['event_base'].copy()
                    b_event['name'] = f"{base_name} #{seq}"
                    unpaired_events.append(b_event)
                    b_count += 1
                    unpaired_count += 1

            else:  # 模式B：顺序配对，使用预定义的full_name
                i = 0
                n = len(group)
                while i < n:
                    item = group[i]
                    if item['ph'] == 'B':
                        # 寻找下一个同seq的E
                        j = i + 1
                        while j < n and (group[j]['ph'] != 'E' or group[j]['seq'] != item['seq']):
                            j += 1
                        if j < n and group[j]['ph'] == 'E':
                            b_item = item
                            e_item = group[j]
                            full_name = b_item['full_name']
                            b_file = b_item['point_info'].get('file', '')
                            b_line = b_item['point_info'].get('line', 0)
                            e_file = e_item['point_info'].get('file', '')
                            e_line = e_item['point_info'].get('line', 0)

                            b_event = b_item['event_base'].copy()
                            b_event['name'] = full_name
                            b_event['args']['begin_file'] = b_file
                            b_event['args']['begin_line'] = b_line
                            b_event['args']['end_file'] = e_file
                            b_event['args']['end_line'] = e_line

                            e_event = e_item['event_base'].copy()
                            e_event['name'] = full_name
                            e_event['args']['begin_file'] = b_file
                            e_event['args']['begin_line'] = b_line
                            e_event['args']['end_file'] = e_file
                            e_event['args']['end_line'] = e_line

                            interval = {
                                'pid': pid,
                                'tid': tid_str,
                                'name': full_name,
                                'start_event': b_event,
                                'end_event': e_event,
                                'start_cycles': b_item['cycles'],
                                'end_cycles': e_item['cycles'],
                                'interval_obj': None
                            }
                            interval['interval_obj'] = interval
                            all_intervals.append(interval)
                            b_count += 1
                            e_count += 1
                            i = j + 1
                        else:
                            print(f"警告: 孤立B事件，tid={tid_key}, base_name={base_name}, ts={item['ts']}")
                            b_event = item['event_base'].copy()
                            b_event['name'] = item['full_name']
                            unpaired_events.append(b_event)
                            b_count += 1
                            unpaired_count += 1
                            i += 1
                    elif item['ph'] == 'E':
                        print(f"警告: 孤立E事件，tid={tid_key}, base_name={base_name}, ts={item['ts']}")
                        e_event = item['event_base'].copy()
                        e_event['name'] = item['full_name']
                        unpaired_events.append(e_event)
                        e_count += 1
                        unpaired_count += 1
                        i += 1
                    else:
                        print(f"警告: 未知事件类型 {item['ph']}，tid={tid_key}")
                        e_event = item['event_base'].copy()
                        e_event['name'] = item.get('full_name', base_name)
                        unpaired_events.append(e_event)
                        i += 1

    # ========== 深度计算与过滤（从叶子向上，使用整型 cycles） ==========
    final_events = []

    if depth == 0:
        # 全部保留
        for interval in all_intervals:
            final_events.append(interval['start_event'])
            final_events.append(interval['end_event'])
    else:
        # 按线程分组
        intervals_by_thread = defaultdict(list)
        for interval in all_intervals:
            key = (interval['pid'], interval['tid'])
            intervals_by_thread[key].append(interval)

        for key, intervals in intervals_by_thread.items():
            # 判断当前线程是否需要调试
            # debug_core 格式: (rank, type, core)
            # 从 key 中提取 rank, core_type, core_id
            # 注意 key 中的 tid 是字符串，但我们可以从 interval 中获取 rank_id? interval 中没有 rank_id。
            # 从 metadata 中无法直接获得，但我们可以从 pid 映射回 rank_id，或者从 interval 的 start_event 中获取。
            # 这里简单处理：如果 debug_core 不为 None，且当前线程匹配，则启用调试输出。
            # 获取 rank_id: 可以从 interval['start_event']['args']['rank_id'] 获取
            if debug_core is not None:
                sample_interval = intervals[0]
                rank_id = sample_interval['start_event']['args'].get('rank_id')
                core_type = sample_interval['start_event']['args'].get('core_type')
                core_id = sample_interval['start_event']['args'].get('core_id')
                if (rank_id, core_type, core_id) == debug_core:
                    debug = True
                else:
                    debug = False
            else:
                debug = False

            interval_list = [{'start_cycles': iv['start_cycles'], 'end_cycles': iv['end_cycles'], 'interval_obj': iv} for iv in intervals]
            build_interval_tree(interval_list, debug=debug)

        # 过滤：保留深度 <= depth 的区间
        for interval in all_intervals:
            if interval.get('depth_from_leaf', 0) <= depth:
                final_events.append(interval['start_event'])
                final_events.append(interval['end_event'])

    # 添加所有未配对事件
    final_events.extend(unpaired_events)

    all_events = metadata_events + final_events

    trace_data = {
        "traceEvents": all_events,
        "displayTimeUnit": "us",
        "otherData": {
            "version": "1.0",
            "generator": "trace_collector_fifo_seq_sorted_us",
            "total_events": len(final_events),
            "skipped_events": skipped_count,
            "unpaired_events": unpaired_count,
            "b_events": b_count,
            "e_events": e_count,
            "total_ranks": len(all_data),
            "clock_divisor": CLOCK_DIVISOR,
            "extra_mode": extra_mode,
            "depth": depth
        }
    }

    with open(output_file, 'w') as f:
        json.dump(trace_data, f, indent=2)

    print(f"\nChrome trace已生成: {output_file}")
    print(f"有效事件数: {len(final_events)}")
    print(f"跳过事件数: {skipped_count}")
    print(f"未配对事件数: {unpaired_count}")
    print(f"B事件数: {b_count}")
    print(f"E事件数: {e_count}")
    if b_count != e_count:
        print("警告: B和E事件数量不匹配")
    print(f"总rank数: {len(all_data)}")
    print(f"时钟频率: {CLOCK_DIVISOR} MHz")
    print(f"extra_id模式: {extra_mode}")
    print(f"保留深度(从叶子向上): {depth} (0=全部保留)")

    return trace_data

def analyze_data(all_data: Dict[int, Dict], mapping: Dict):
    print("\n数据分析:")
    print("=" * 60)
    total_records = 0
    total_ranks = len(all_data)
    extra_id_stats = {}
    event_type_stats = {}
    timestamp_stats = {'min_us': float('inf'), 'max_us': float('-inf')}
    points = mapping.get('points', {})

    for rank_id, rank_data in all_data.items():
        record_count = len(rank_data['records'])
        total_records += record_count
        tensor_count = rank_data.get('tensor_count', 0)
        print(f"Rank {rank_id}: {record_count} 条记录, {tensor_count} 种核心类型")
        for record in rank_data['records']:
            extra_id = record['extra_id']
            base_point_id = str(record['base_point_id'])
            timestamp_us = record['timestamp_us']
            extra_id_stats[extra_id] = extra_id_stats.get(extra_id, 0) + 1
            point_info = points.get(base_point_id, {})
            event_type = point_info.get('event_type', 'unknown')
            event_type_stats[event_type] = event_type_stats.get(event_type, 0) + 1
            if timestamp_us < timestamp_stats['min_us']:
                timestamp_stats['min_us'] = timestamp_us
            if timestamp_us > timestamp_stats['max_us']:
                timestamp_stats['max_us'] = timestamp_us

    print(f"\n总计: {total_ranks} 个rank, {total_records} 条记录")
    if total_records > 0:
        print(f"\n时间戳范围 (微秒): 最小值={timestamp_stats['min_us']:.2f}, 最大值={timestamp_stats['max_us']:.2f}, 范围={timestamp_stats['max_us'] - timestamp_stats['min_us']:.2f}")
    if extra_id_stats:
        print(f"\nextra_id统计 (共{len(extra_id_stats)} 种):")
        sorted_extras = sorted(extra_id_stats.items(), key=lambda x: x[1], reverse=True)
        for extra_id, count in sorted_extras[:10]:
            percentage = count / total_records * 100 if total_records > 0 else 0
            print(f"  extra_id={extra_id}: {count} ({percentage:.1f}%)")
        if len(sorted_extras) > 10:
            print(f"  ... 及其他 {len(sorted_extras)-10} 种")
    if event_type_stats:
        print(f"\n事件类型统计:")
        for event_type, count in sorted(event_type_stats.items()):
            percentage = count / total_records * 100 if total_records > 0 else 0
            print(f"  '{event_type}': {count} ({percentage:.1f}%)")

def main():
    import argparse
    parser = argparse.ArgumentParser(description='追踪数据收集器 - 支持按从叶子向上的层数过滤事件')
    parser.add_argument('data_dir', help='数据目录')
    parser.add_argument('mapping_file', help='映射表文件')
    parser.add_argument('-o', '--output', default='chrome_trace.json', help='输出文件')
    parser.add_argument('--analyze', action='store_true', help='仅分析')
    parser.add_argument('--clock-divisor', type=float, default=50.0, help='时钟频率 (MHz)')
    parser.add_argument('--debug-core', type=str, default=None, help='调试核心 rank,type,core')
    parser.add_argument('--extra-mode', choices=['legacy', 'seq'], default='seq',
                        help='extra_id解析模式: legacy=整体使用, seq=高24位作seq低8位作extra (默认)')
    parser.add_argument('--depth', type=int, default=0,
                        help='保留的层数（从叶子向上计数）：0=全部保留，1=仅叶子节点，2=叶子+父层，...')
    args = parser.parse_args()

    global CLOCK_DIVISOR
    CLOCK_DIVISOR = args.clock_divisor

    debug_core = None
    if args.debug_core:
        try:
            parts = args.debug_core.split(',')
            if len(parts) == 3:
                debug_core = (int(parts[0]), int(parts[1]), int(parts[2]))
                print(f"调试核心: Rank {debug_core[0]}, Type {debug_core[1]}, Core {debug_core[2]}")
        except ValueError:
            print("无效的调试核心格式")

    print(f"收集数据 (时钟频率: {CLOCK_DIVISOR} MHz)...")
    all_data = load_all_ranks(args.data_dir, debug_core)
    if not all_data:
        print("未找到数据")
        return
    print(f"找到 {len(all_data)} 个rank")
    mapping = load_mapping(args.mapping_file)
    analyze_data(all_data, mapping)
    if not args.analyze:
        print("\n生成Chrome trace...")
        generate_chrome_trace(all_data, mapping, args.output,
                              extra_mode=args.extra_mode,
                              depth=args.depth,
                              debug_core=debug_core)

if __name__ == "__main__":
    main()