/*
 * SPDX-License-Identifier: MIT
 * Copyright (c) Huawei Technologies Co., Ltd. 2025-2025. All rights reserved.
 * Description: FusedDeepMoe operator kernel function implementation file
 * Create: 2025-07-19
 * Note:
 * History: 2025-07-19 create FusedDeepMoe operator kernel function implementation file
 */
#include "fused_deep_moe.h"
#include <kernel_operator.h>
#include "lib/matmul_intf.h"

__aicore__ inline void SetMoeProfilePtr(int64_t *profilePtr)
{
#if __CCE_AICORE__ == 220 || defined(__DAV_C310__) || defined(__DAV_310R6__)
#ifdef SPLIT_CORE_CUBE // 编译期宏，用于区分不同的核类型
    g_moeProfilePtrCube = profilePtr;
#elif defined(SPLIT_CORE_VEC) // 编译期宏，用于区分不同的核类型
    g_moeProfilePtrVec = profilePtr;
#else
    g_moeProfilePtr = profilePtr;
#endif
#else
    g_moeProfilePtr = profilePtr;
#endif
}

__aicore__ inline void SetMoeDebugInfoPtr(int64_t *debugInfoPtr)
{
#if __CCE_AICORE__ == 220 || defined(__DAV_C310__) || defined(__DAV_310R6__)
#ifdef SPLIT_CORE_CUBE
    g_moeDebugInfoPtrCube = debugInfoPtr;
#elif defined(SPLIT_CORE_VEC)
    g_moeDebugInfoPtrVec = debugInfoPtr;
#else
    g_moeDebugInfoPtr = debugInfoPtr;
#endif
#else
    g_moeDebugInfoPtr = debugInfoPtr;
#endif
}

extern "C" __global__ __aicore__ void fused_deep_moe(
    // input
    GM_ADDR x, GM_ADDR expert_ids, GM_ADDR gmm1_permuted_weight, GM_ADDR gmm1_permuted_weight_scale,
    GM_ADDR gmm2_weight, GM_ADDR gmm2_weight_scale, GM_ADDR expert_scales,
    GM_ADDR share_gmm1_permuted_weight, GM_ADDR share_gmm1_permuted_weight_scale,
    GM_ADDR share_gmm2_weight, GM_ADDR share_gmm2_weight_scale,
    GM_ADDR expert_smooth_scales, GM_ADDR share_smooth_scales, GM_ADDR x_active_mask,
    GM_ADDR comm_args,
    // output
    GM_ADDR output, GM_ADDR share_output, GM_ADDR expertTokenNums,
    // system
    GM_ADDR workspace, GM_ADDR tiling)
{
    icache_preload(8);
#if ENABLE_MOE_DEBUG_INFO
    int64_t debugInfo[DEBUG_INFO_COUNT];
    SetMoeDebugInfoPtr(&debugInfo[0]);
#endif
#if ENABLE_MOE_PROFILING
    AscendC::PipeBarrier<PIPE_ALL>();
    Arch::CrossCoreFlag gmm1AivFinished{0};
    if constexpr (g_coreType == AscendC::AIV) {
        Arch::CrossCoreBarrier<0x0, PIPE_MTE3>();
        Arch::CrossCoreSetFlag<0x2, PIPE_MTE3>(gmm1AivFinished);
    } else {
        Arch::CrossCoreWaitFlag(gmm1AivFinished);
    }
    int64_t profData[PROF_SIZE_PER_CORE]; // 长度为2048，但是一前一后往里写事件id和时间戳，所以实际记录数为1024 - 1 = 1023
    profData[0] = 1;
    profData[PROF_SIZE_PER_CORE - 1] = AscendC::GetSystemCycle();
    SetMoeProfilePtr(&profData[0]);
#endif
    // New output recvCount
    REGISTER_TILING_DEFAULT(FusedDeepMoeTilingData);
    KERNEL_TASK_TYPE_DEFAULT(KERNEL_TYPE_MIX_AIC_1_2);  // 1C2V
    GET_TILING_DATA(tiling_data, tiling);
    // return;
    if constexpr (TILING_KEY_IS(0) || TILING_KEY_IS(1) || TILING_KEY_IS(2) || TILING_KEY_IS(3) ||
                TILING_KEY_IS(4) || TILING_KEY_IS(5) || TILING_KEY_IS(6) || TILING_KEY_IS(7)) {
        FusedDeepMoe<DTYPE_X, DTYPE_GMM1_WEIGHT_SCALE, DTYPE_GMM2_WEIGHT_SCALE, int32_t, false, TILING_KEY_VAR> op;
        op.Init(x, expert_ids, gmm1_permuted_weight, gmm1_permuted_weight_scale, gmm2_weight, gmm2_weight_scale,
                expert_scales, share_gmm1_permuted_weight, share_gmm1_permuted_weight_scale,
                share_gmm2_weight, share_gmm2_weight_scale, expert_smooth_scales, share_smooth_scales, x_active_mask, comm_args,
                output, share_output, expertTokenNums,
                workspace, nullptr, &tiling_data);
        op.Process();
    }
    else if constexpr (TILING_KEY_IS(8) || TILING_KEY_IS(9) || TILING_KEY_IS(10) || TILING_KEY_IS(11) ||
                TILING_KEY_IS(12) || TILING_KEY_IS(13) || TILING_KEY_IS(14) || TILING_KEY_IS(15)) {
        FusedDeepMoe<DTYPE_X, DTYPE_GMM1_WEIGHT_SCALE, DTYPE_GMM2_WEIGHT_SCALE, int32_t, false, TILING_KEY_VAR> op;
        op.Init(x, expert_ids, gmm1_permuted_weight, gmm1_permuted_weight_scale, gmm2_weight, gmm2_weight_scale,
                expert_scales, share_gmm1_permuted_weight, share_gmm1_permuted_weight_scale,
                share_gmm2_weight, share_gmm2_weight_scale, expert_smooth_scales, share_smooth_scales, x_active_mask, comm_args,
                output, share_output, expertTokenNums,
                workspace, nullptr, &tiling_data);
        op.Process();
    }
// 把“当前核本地栈上的 profiling 数据 profData”拷回到 GM 里，作为后续离线收集 trace 的原始数据。
#if ENABLE_MOE_PROFILING
    if (share_smooth_scales && (MOE_PROFILING_THRESHOLD == 0 || DEBUG_INFO_ENABLE_PROFILING != 0)) {
        AscendC::GlobalTensor<int64_t> initGlobal = {};
        initGlobal.SetGlobalBuffer((__gm__ int64_t *)(share_smooth_scales));
        AscendC::GlobalTensor<int64_t> coreGlobal;
        if (g_coreType == AscendC::AIC) {
            coreGlobal = initGlobal[AscendC::GetBlockIdx() * PROF_SIZE_PER_CORE]; // (0 ~ 23) * 2048
        } else {
            coreGlobal = initGlobal[(AscendC::GetBlockNum() + AscendC::GetBlockIdx()) * PROF_SIZE_PER_CORE]; // (24 + 0 ~ 47) * 2048
        }

        MOE_LOG_DEBUG("YHB: coreGlobal %p profData[0] = %u", coreGlobal.GetPhyAddr(), profData[0]);
        for (unsigned i = 0; i < profData[0]; ++i) { // profData[0] 记录着当前buffer的实际记录数
            coreGlobal(i) = profData[i];
            coreGlobal(PROF_SIZE_PER_CORE - i - 1) = profData[PROF_SIZE_PER_CORE - i - 1];
#if ENABLE_MOE_PROFILING_DETAIL
            MOE_LOG_DETAIL("YHB: i %u coreGlobal %p profData[0] = %u", i, coreGlobal[i].GetPhyAddr(), profData[i]);
            MOE_LOG_DETAIL("YHB: i %u coreGlobal %p profData[0] = %u", PROF_SIZE_PER_CORE - i - 1,
                           coreGlobal[PROF_SIZE_PER_CORE - i - 1].GetPhyAddr(), profData[PROF_SIZE_PER_CORE - i - 1]);
#endif
        }
        for (unsigned i = 0; i < profData[0]; ++i) { // profData[0] 记录着当前buffer的实际记录数  这个循环做cache刷新，关键位置刷新缓存
            if (i == 0 || (((uint64_t)coreGlobal[i].GetPhyAddr()) & 63) == 0) {
                __asm__ __volatile__("");
                AscendC::DataCacheCleanAndInvalid<int64_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                                AscendC::DcciDst::CACHELINE_OUT>(coreGlobal[i]);
                __asm__ __volatile__("");
            }
            if (i == profData[PROF_SIZE_PER_CORE - 1] - 1 || (((uint64_t)coreGlobal[i].GetPhyAddr()) & 63) == 0) {
                __asm__ __volatile__("");
                AscendC::DataCacheCleanAndInvalid<int64_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                                AscendC::DcciDst::CACHELINE_OUT>(coreGlobal[i]);
                __asm__ __volatile__("");
            }
        }
    }
#endif
}
