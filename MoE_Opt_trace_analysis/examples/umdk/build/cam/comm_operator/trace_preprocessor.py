#!/usr/bin/env python3
"""
C代码追踪点预处理工具 - 保持原始事件类型
"""

import re
import json
import os
import sys
from collections import defaultdict, deque
from typing import List, Dict, Tuple
# point_id：唯一对应一个源码里的具体调用点 MoeTracing(TRACE_POINT("processing", "B")); 和 MoeTracing(TRACE_POINT("processing", "E"))； 是两个point 有两个point_id
# event_id：唯一对应一个事件类型， 同一个 label 共用一个 ID ，上面的例子 这个是一个event_id
class TracePreprocessor:
    def __init__(self):
        self.next_event_id = 1  # 事件ID计数器
        self.next_point_id = 1  # 位置ID计数器

        # 检查点：确保point_id不超过32位范围
        self.MAX_BASE_POINT_ID = 0xFFFFFFFF  # 2^32 - 1
        
        # 映射表
        self.event_map = {}      # label -> event_id
        self.point_map = {}      # point_id -> 位置信息
        self.point_to_event = {} # point_id -> event_id
        
    def process_file(self, filepath: str, modify: bool = False) -> List[Dict]:  # BE闭合必须在同一个文件，这是一个限制
        """处理单个文件"""
        print(f"处理: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找所有TRACE_POINT调用
        pattern = r'TRACE_POINT\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)'
        matches = list(re.finditer(pattern, content))
        
        if not matches:
            print("  未找到TRACE_POINT调用")
            return []
        
        # 按行号排序处理（确保顺序正确）
        matches_with_lines = []
        for match in matches:
            label = match.group(1)   # processing 
            event_type = match.group(2)  # 原始事件类型（保持大小写） B
            line_num = content[:match.start()].count('\n') + 1 # 代码中的原始行号
            
            matches_with_lines.append({
                'match': match,
                'label': label,
                'event_type': event_type,
                'line': line_num,
                'start': match.start(),
                'end': match.end()
            })
        
        # 按行号排序
        matches_with_lines.sort(key=lambda x: x['line'])
        
        # 第一遍：分配ID
        points = []
        for match_info in matches_with_lines:
            label = match_info['label']
            event_type = match_info['event_type']
            line_num = match_info['line']
            
            # 分配事件ID（相同label相同event_id）
            if label not in self.event_map:
                self.event_map[label] = self.next_event_id
                self.next_event_id += 1
            
            event_id = self.event_map[label]
            
            # 分配位置ID（每个调用位置唯一）
            point_id = self.next_point_id
            if point_id > self.MAX_BASE_POINT_ID:
                print(f"    ⚠️ 错误: point_id {point_id} 超出32位范围 (最大: {self.MAX_BASE_POINT_ID})")
                print(f"      请减少追踪点数量或调整ID分配策略")
                return []

            self.next_point_id += 1
            
            # 记录映射
            self.point_map[point_id] = {
                'label': label,
                'file': filepath,
                'line': line_num,
                'event_type': event_type,  # 保持原始大小写
                'original': match_info['match'].group(0)
            }
            self.point_to_event[point_id] = event_id
            
            points.append({
                'point_id': point_id, # point是唯一的，每个point_id对应一个源码里的具体调用点
                'event_id': event_id, # event_id不唯一，B和E对应的同一个event_id
                'label': label,
                'line': line_num,
                'event_type': event_type,
                'start': match_info['start'],
                'end': match_info['end']
            })
        
        # 第二遍：仅对大写事件进行嵌套检查
        print("  嵌套检查（仅大写事件）:")
        event_stack = deque()  # 存储 (label, event_id, line, point_id) 检查括号表达式是否正确闭合
        
        for point in points:
            event_type_upper = point['event_type'].upper()  # 转为大写用于检查
            event_type_raw = point['event_type']  # 原始事件类型
            label = point['label']
            event_id = point['event_id']
            line_num = point['line']
            point_id = point['point_id']
            
            # 仅对大写事件进行嵌套检查
            if event_type_upper == 'B':  # 大写开始事件 大B压入栈
                # 只有原始是大写时才检查
                if event_type_raw == 'B':
                    event_stack.append((label, event_id, line_num, point_id))
                    print(f"    行{line_num}: 事件 '{label}' 开始（大写B，进行嵌套检查）")
                else:
                    print(f"    行{line_num}: 事件 '{label}' 开始（小写b，跳过嵌套检查）")
                
            elif event_type_upper == 'E':  # 大写结束事件
                if event_type_raw == 'E':  # 大写结束事件
                    if not event_stack:
                        print(f"    ⚠️ 行{line_num}: 事件 '{label}' 的大写结束没有匹配的开始")
                    else:
                        stack_label, stack_event_id, stack_line, stack_point_id = event_stack[-1]
                        if stack_label != label or stack_event_id != event_id:
                            print(f"    ⚠️ 行{line_num}: 事件 '{label}' 的大写结束与 '{stack_label}' (行{stack_line}) 的开始不匹配")
                        else:
                            event_stack.pop()
                            print(f"    行{line_num}: 事件 '{label}' 结束（大写E，正确匹配）")
                else:
                    print(f"    行{line_num}: 事件 '{label}' 结束（小写e，跳过嵌套检查）")
            else:
                # 其他事件类型（I, C, S, F等）
                if event_type_raw.isupper():
                    print(f"    行{line_num}: 事件 '{label}' 类型 '{event_type_raw}'")
                else:
                    print(f"    行{line_num}: 事件 '{label}' 类型 '{event_type_raw}'（小写）")
        
        # 检查未闭合的事件（仅大写）
        if event_stack:
            print(f"    ⚠️ 有未闭合的大写事件:")
            for label, event_id, line, point_id in reversed(event_stack):
                print(f"      事件 '{label}' (ID:{point_id}) 在行 {line} 开始但未结束")
        else:
            print(f"    ✓ 所有大写事件都正确闭合")
        
        # 执行替换（如果开启modify）
        if modify and points:
            # 按位置从后向前替换，避免位置偏移
            points.sort(key=lambda x: x['start'], reverse=True) # 反着替换，避免位置偏移
            new_content = content
            
            for point in points:
                new_content = new_content[:point['start']] + str(point['point_id']) + new_content[point['end']:]
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            print(f"  已替换 {len(points)} 个追踪点")
            
            # 显示详细信息
            for point in sorted(points, key=lambda x: x['line']):
                print(f"    行 {point['line']}: '{point['label']}' [{point['event_type']}] -> 位置ID:{point['point_id']} (事件ID:{point['event_id']})")
        
        return points
    
    def process_directory(self, src_path: str, modify: bool = False) -> List[Dict]:
        """处理目录"""
        print(f"扫描目录: {src_path}")
        
        all_points = []
        
        for root, dirs, files in os.walk(src_path):
            for file in files:
                if file.endswith(('.c', '.cpp', '.cc', '.h', '.hpp')):
                    filepath = os.path.join(root, file)
                    points = self.process_file(filepath, modify)
                    all_points.extend(points)
        
        return all_points
    
    def save_mappings(self, output_dir: str):
        """保存映射表"""
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. 位置映射表 (point_id -> 详细信息)
        point_map_data = {}
        for point_id, info in self.point_map.items():
            # 使用相对路径
            rel_path = os.path.relpath(info['file'], output_dir) if output_dir else info['file']
            
            point_map_data[str(point_id)] = {
                'label': info['label'],
                'file': rel_path,
                'line': info['line'],
                'event_type': info['event_type'],  # 保持原始大小写
                'event_id': self.point_to_event[point_id]
            }
        
        with open(os.path.join(output_dir, "point_map.json"), 'w', encoding='utf-8') as f:
            json.dump(point_map_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n映射表已保存至: {output_dir}/point_map.json")
        print(f"  总追踪点: {len(self.point_map)}")
        print(f"  总事件类型: {len(self.event_map)}")
    
    def print_statistics(self):
        """打印统计信息"""
        print("\n" + "=" * 60)
        print("统计信息:")
        print(f"  总追踪点数量: {len(self.point_map)}")
        print(f"  总事件类型数: {len(self.event_map)}")
        
        # 显示事件统计
        print("\n  事件标签统计:")
        for label, event_id in sorted(self.event_map.items(), key=lambda x: x[1]):
            point_count = len([pid for pid, eid in self.point_to_event.items() if eid == event_id])
            print(f"    事件ID:{event_id:3d} - '{label}' - {point_count}个调用点")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='C代码追踪点预处理工具 - 保持原始事件类型')
    parser.add_argument('src', help='源文件或源目录路径')
    parser.add_argument('output', help='输出目录路径')
    parser.add_argument('--modify', action='store_true', help='开启后原地修改源文件，默认仅检查')
    
    args = parser.parse_args()
    
    preprocessor = TracePreprocessor()
    
    if os.path.isfile(args.src):
        # 处理单个文件
        print("=" * 60)
        points = preprocessor.process_file(args.src, args.modify)
        
        # 保存映射表
        if points:
            preprocessor.save_mappings(args.output)
            preprocessor.print_statistics()
    elif os.path.isdir(args.src):
        # 处理目录
        print("=" * 60)
        points = preprocessor.process_directory(args.src, args.modify)
        
        if points:
            preprocessor.save_mappings(args.output)
            preprocessor.print_statistics()
    else:
        print(f"错误: 路径不存在: {args.src}")
        sys.exit(1)

if __name__ == "__main__":
    main()