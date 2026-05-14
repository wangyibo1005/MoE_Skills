#!/usr/bin/env python3
"""加载原始 .pt 文件，调用 trace_utils.save_profiling_data 保存"""
import argparse
import torch
from trace_utils import save_profiling_data

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="原始 profiling tensor 文件 (.pt)")
    parser.add_argument("--rank", type=int, default=0, help="rank ID")
    parser.add_argument("--output", default="../../../output/cam/profiling_data", help="输出目录")
    args = parser.parse_args()

    profiling_raw = torch.load(args.input, map_location="cpu")
    save_profiling_data(profiling_raw, args.rank, args.output)
    print("Done.")

if __name__ == "__main__":
    main()