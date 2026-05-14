/*
 * SPDX-License-Identifier: MIT
 * Copyright (c) Huawei Technologies Co., Ltd. 2025-2025. All rights reserved.
 * Description: FusedDeepMoe operator kernel function implementation file
 * Create: 2025-07-19
 * Note:
 * History: 2025-07-19 create FusedDeepMoe operator kernel function implementation file
 */
#ifndef ACT_GEMM_KERNEL_GROUPED_MATMUL_M_PER_TOKEN_DEQUANT_MULTISTAGE_WORKSPACE_HPP
#define ACT_GEMM_KERNEL_GROUPED_MATMUL_M_PER_TOKEN_DEQUANT_MULTISTAGE_WORKSPACE_HPP

#include "ascendc/basic_api/interface/kernel_operator_list_tensor_intf.h"
#include "../../raw_distributed/cam_moe_distribute_combine.h"
#include "catlass/catlass.hpp"
#include "catlass/arch/cross_core_sync.hpp"
#include "catlass/arch/resource.hpp"
#include "catlass/coord.hpp"
#include "catlass/detail/callback.hpp"
#include "catlass/gemm_coord.hpp"
#include "catlass/matrix_coord.hpp"

// Use this to make a callback
template <typename Func>
CATLASS_DEVICE
Callback MakeCallbackWithCall(Func *func)
{
    Callback callback;
    callback.func = func;
    callback.caller = [](void const *f) {
        static_cast<Func const *>(f)->Call();
    };
    return callback;
}
#define ENABLE_GMM2_MOVING_FORWARD 1

#if ENABLE_GMM2_MOVING_FORWARD
struct MoeCallback {
    void const *func{nullptr};
    void (*caller)(void const *, int32_t){nullptr};
    int32_t index{0};
    MoeCallback() = default;

    CATLASS_DEVICE
    void operator()() const
    {
        if (caller) {
            caller(func, index);
        }
    }

    CATLASS_DEVICE
    operator bool() const
    {
        return func != nullptr;
    }
};

template <typename Func>
CATLASS_DEVICE
MoeCallback MakeCallbackWithValue(Func *func, int32_t value)
{
    MoeCallback callback;
    callback.index = value;
    callback.func = func;
    callback.caller = [](void const *f, int32_t idx) {
        static_cast<Func const *>(f)->CallWithValue(idx);
    };
    return callback;
}

#endif

template <typename Func>
CATLASS_DEVICE
Callback MakeCallbackWithCall2(Func *func)
{
    Callback callback;
    callback.func = func;
    callback.caller = [](void const *f) {
        static_cast<Func const *>(f)->Call2();
    };
    return callback;
}

#define ENABLE_TENSOR_LIST

namespace Catlass::Gemm::Kernel {
namespace GMM2 {
    constexpr uint32_t SOFT_SYNC_SPACE_SIZE = 512;
    constexpr uint64_t SOFT_SYNC_OFFSET = 1024 * 1024; // len: 24 * 4 * 512 = 48KB
    constexpr uint64_t NOTIFY_GMM2_SOFT_SYNC_OFFSET = 1072 * 1024; // len: group_count * 512 = (group_count / 2)KB
}

template <TemplateMC2TypeClass, class BlockMmad_, class BlockEpilogue_, class BlockScheduler_,
          uint32_t WORKSPACE_STAGES_, class ElementGroupList_>
class GroupedMatmulSliceMPerTokenDequantMultiStageWorkspace {
public:
    using BlockMmad = BlockMmad_;
    using ArchTag = typename BlockMmad::ArchTag;
    using L1TileShape = typename BlockMmad::L1TileShape;
    using ElementA = typename BlockMmad::ElementA;
    using LayoutA = typename BlockMmad::LayoutA;
    using ElementB = typename BlockMmad::ElementB;
    using LayoutB = typename BlockMmad::LayoutB;
    using ElementC = typename BlockMmad::ElementC;
    using LayoutC = typename BlockMmad::LayoutC;
    using ElementAccumulator = typename BlockMmad::ElementAccumulator;

    using BlockEpilogue = BlockEpilogue_;
    using ElementScale = typename BlockEpilogue::ElementRawScale;
    using LayoutScale = typename BlockEpilogue::LayoutScale;
    using ElementPerTokenScale = typename BlockEpilogue::ElementPerTokenScale;
    using LayoutPerTokenScale = typename BlockEpilogue::LayoutPerTokenScale;
    using ElementD = typename BlockEpilogue::ElementD;
    using LayoutD = typename BlockEpilogue::LayoutD;
    using EpilogueParams = typename BlockEpilogue::Params;

    using BlockScheduler = BlockScheduler_;
    static constexpr uint32_t WORKSPACE_STAGES = WORKSPACE_STAGES_;
    using ElementGroupList = ElementGroupList_;

    /// Parameters structure
    struct Params {
        // Data members
        GemmCoord problemShape;
        uint32_t problemCount;
        __gm__ ElementGroupList_ *ptrGroupList;
        __gm__ ElementA *ptrA;
        LayoutA layoutA;
        __gm__ ElementB *ptrB;
        LayoutB layoutB;
        __gm__ ElementScale *ptrScale;
        LayoutScale layoutScale;
        __gm__ ElementPerTokenScale *ptrPerTokenScale;
        LayoutPerTokenScale layoutPerTokenScale;
        __gm__ ElementD *ptrD;
        LayoutD layoutD;
        __gm__ ElementC *ptrC;
        LayoutC layoutC;
        uint32_t batchSize;
        GemmCoord sharedGmm2ProblemShape;
        __gm__ ElementA * ptrSharedA;
        __gm__ ElementB * ptrSharedB;
        __gm__ ElementD *ptrSharedD;
        __gm__ ElementC *ptrSharedC;
        __gm__ ElementScale *ptrSharedScale;
        __gm__ ElementPerTokenScale *ptrSharedPtrPerTokenScale;
        LayoutA sharedLayoutA;
        LayoutB sharedLayoutB;
        LayoutPerTokenScale sharedLayoutPerTokenScale;
        LayoutD sharedLayoutD;
        LayoutC sharedLayoutC;
        GM_ADDR ptrWorkspace;
        void *combiner;
        uint32_t epRankSize;

        // Methods
        CATLASS_DEVICE
        Params() {}

        CATLASS_DEVICE
        Params(GemmCoord problemShape_, uint32_t problemCount_, GM_ADDR ptrGroupList_, GM_ADDR ptrA_, LayoutA layoutA_,
               GM_ADDR ptrB_, LayoutB layoutB_, GM_ADDR ptrScale_, LayoutScale layoutScale_, GM_ADDR ptrPerTokenScale_,
               LayoutPerTokenScale layoutPerTokenScale_, GM_ADDR ptrD_, LayoutD layoutD_, GM_ADDR ptrC_, LayoutC layoutC_, uint32_t batchSize_,
               GemmCoord sharedGmm2ProblemShape_, GM_ADDR ptrSharedA_, GM_ADDR ptrSharedB_, GM_ADDR ptrSharedD_, GM_ADDR ptrSharedC_,
               GM_ADDR ptrSharedScale_, GM_ADDR ptrSharedPtrPerTokenScale_, LayoutA sharedLayoutA_,
               LayoutB sharedLayoutB_,
               LayoutPerTokenScale sharedLayoutPerTokenScale_, LayoutD sharedLayoutD_, LayoutC sharedLayoutC_,
               GM_ADDR ptrWorkspace_, void *combiner_, uint32_t epRankSize_)
            : problemShape(problemShape_),
              problemCount(problemCount_),
              ptrGroupList(reinterpret_cast<__gm__ ElementGroupList *>(ptrGroupList_)),
              ptrA(reinterpret_cast<__gm__ ElementA *>(ptrA_)),
              layoutA(layoutA_),
              ptrB(reinterpret_cast<__gm__ ElementB *>(ptrB_)),
              layoutB(layoutB_),
              ptrScale(reinterpret_cast<__gm__ ElementScale *>(ptrScale_)),
              layoutScale(layoutScale_),
              ptrPerTokenScale(reinterpret_cast<__gm__ ElementPerTokenScale *>(ptrPerTokenScale_)),
              layoutPerTokenScale(layoutPerTokenScale_),
              ptrD(reinterpret_cast<__gm__ ElementD *>(ptrD_)),
              layoutD(layoutD_),
              ptrC(reinterpret_cast<__gm__ ElementC *>(ptrC_)),
              layoutC(layoutC_),
              batchSize(batchSize_),
              sharedGmm2ProblemShape(sharedGmm2ProblemShape_),
              ptrSharedB(reinterpret_cast<__gm__ ElementB *>(ptrSharedB_)),
              ptrSharedScale(reinterpret_cast<__gm__ ElementScale *>(ptrSharedScale_)),
              ptrSharedD(reinterpret_cast<__gm__ ElementD *>(ptrSharedD_)),
              ptrSharedC(reinterpret_cast<__gm__ ElementC *>(ptrSharedC_)),
              ptrSharedA(reinterpret_cast<__gm__ ElementA *>(ptrSharedA_)),
              ptrSharedPtrPerTokenScale(reinterpret_cast<__gm__ ElementPerTokenScale *>(ptrSharedPtrPerTokenScale_)),
              sharedLayoutA(sharedLayoutA_),
              sharedLayoutB(sharedLayoutB_),
              sharedLayoutPerTokenScale(sharedLayoutPerTokenScale_),
              sharedLayoutD(sharedLayoutD_),
              sharedLayoutC(sharedLayoutC_),
              ptrWorkspace(ptrWorkspace_),
              combiner(combiner_),
              epRankSize(epRankSize_)
        {}
    };

    // Methods
    CATLASS_DEVICE
    GroupedMatmulSliceMPerTokenDequantMultiStageWorkspace(GM_ADDR commArgs = nullptr, uint32_t epRankId = 0)
    {
        Arch::FlagID flagId = 0;
        GM_ADDR syncGmAddrBase = nullptr;
        if (commArgs) {
            epRankId_ = epRankId;
            epWinContext_.SetGlobalBuffer(&(reinterpret_cast<__gm__ Moe::CommArgs *>(commArgs))->peerMems[0],
                                          Moe::CAM_MAX_RANK_SIZE);
            syncGmAddrBase = ((GM_ADDR)epWinContext_.GetValue(epRankId));
        } else {
            winContext_ = (__gm__ HcclOpResParam *)AscendC::GetHcclContext<AscendC::HCCL_GROUP_ID_0>();
            syncGmAddrBase = (GM_ADDR)((winContext_)->localWindowsExp);
        }

        GM_ADDR prevSyncGmAddr = syncGmAddrBase + GMM2::NOTIFY_GMM2_SOFT_SYNC_OFFSET;
        prevWaitFunc = {this, prevSyncGmAddr, 0};
        prevSetFunc = {this, prevSyncGmAddr, 0};

        GM_ADDR syncGmAddr =
            syncGmAddrBase + +GMM2::SOFT_SYNC_OFFSET + AscendC::GetBlockIdx() / AscendC::GetSubBlockNum() * WORKSPACE_STAGES * GMM2::SOFT_SYNC_SPACE_SIZE;
        for (uint32_t stageId = 0; stageId < WORKSPACE_STAGES; ++stageId) {
            flagAicFinishStoreList[stageId] = Arch::CrossCoreFlag(flagId++);
            flagAivFinishComputeList[stageId] = Arch::CrossCoreFlag(flagId++);
            aicWaitFuncList[stageId] = {this, syncGmAddr, stageId};
            aicSetFuncList[stageId] = {this, syncGmAddr, stageId};
        }
    }

    template <int32_t CORE_TYPE = g_coreType>
    CATLASS_DEVICE void operator()(Params const &params);

    template <>
    CATLASS_DEVICE void operator()<AscendC::AIC>(Params const &params)
    {
        MoeTracing(TRACE_POINT("gmm2-combine aic", "B"));
        BlockScheduler blockScheduler;
        BlockMmad blockMmad(resource);

        // Represent the full gm
        AscendC::GlobalTensor<ElementA> gmA;
        gmA.SetGlobalBuffer(params.ptrA);
        AscendC::GlobalTensor<ElementB> gmB;
        AscendC::ListTensorDesc gmBlistTensorDesc(reinterpret_cast<__gm__ void *>(params.ptrB));
        if constexpr (!(EXEC_FLAG & EXEC_FLAG_TENSOR_LIST)) {
            gmB.SetGlobalBuffer(reinterpret_cast<__gm__ ElementB *>(gmBlistTensorDesc.GetDataPtr<int32_t>(0)));
        }
        AscendC::GlobalTensor<ElementGroupList> groupList;
        groupList.SetGlobalBuffer(params.ptrGroupList);

        uint32_t coreIdx = AscendC::GetBlockIdx();
        uint32_t coreNum = AscendC::GetBlockNum();
        int64_t gmGroupOffsetA = 0;
        int64_t gmGroupOffsetB = 0;
        int64_t gmGroupOffsetC = 0;

        AscendC::GlobalTensor<ElementC> gmC;
        gmC.SetGlobalBuffer(params.ptrC);
#if !ENABLE_GMM2_MOVING_FORWARD
        auto layoutC = layout::RowMajor{L1TileShape::M * coreNum * WORKSPACE_STAGES, L1TileShape::N};
#endif

        uint32_t stageId = 0;
        uint32_t stageUsed = 0;
        uint32_t startCoreIdx = 0;
#if ENABLE_GMM2_MOVING_FORWARD
        int32_t callIdx = 1;
#endif

        uint32_t tracingIdx = 0;
        for (uint32_t groupIdx = 0; groupIdx < params.problemCount; ++groupIdx) {
            uint32_t groupTracingIdx = tracingIdx++;
            MoeTracing(TRACE_POINT("gmm2-combine moe-gmm2", "B"), 0, groupTracingIdx);
            MoeTracing(TRACE_POINT("gmm2-combine wait quant", "B"), 0, groupTracingIdx);
            prevWaitFunc.CallWithAll(groupIdx, 48);
            MoeTracing(TRACE_POINT("gmm2-combine wait quant", "E"), 0, groupTracingIdx);
            if constexpr (EXEC_FLAG & EXEC_FLAG_TENSOR_LIST) {
                gmB.SetGlobalBuffer(reinterpret_cast<__gm__ ElementB *>(
                        gmBlistTensorDesc.GetDataPtr<int32_t>(groupIdx)));
            }
            uint32_t currentM = (groupIdx == 0) ? groupList.GetValue(params.epRankSize - 1)
                                                : (groupList.GetValue((groupIdx + 1) * params.epRankSize - 1) -
                                                   groupList.GetValue(groupIdx * params.epRankSize - 1));
            GemmCoord inGroupProblemShape{currentM, params.problemShape.n(), params.problemShape.k()};

            LayoutA layoutA = params.layoutA.GetTileLayout(inGroupProblemShape.GetCoordMK());
            LayoutB layoutB = params.layoutB;

            blockScheduler.Update(inGroupProblemShape, MakeCoord(L1TileShape::M, L1TileShape::N));
            uint32_t coreLoops = blockScheduler.GetCoreLoops();
#if ENABLE_GMM2_MOVING_FORWARD
            auto layoutC = params.layoutC.GetTileLayout(inGroupProblemShape.GetCoordMN());
#endif

            // Determine the starting loopIdx of the current core under the current
            // groupIdx
            uint32_t startLoopIdx = ((coreIdx < startCoreIdx) ? (coreIdx + coreNum) : coreIdx) - startCoreIdx;
            // Loop through the matmul of each groupIdx
            for (uint32_t loopIdx = startLoopIdx; loopIdx < coreLoops; loopIdx += coreNum) {
                // Compute block location
                GemmCoord blockCoord = blockScheduler.GetBlockCoord(loopIdx);
                GemmCoord actualBlockShape = blockScheduler.GetActualBlockShape(blockCoord);

                Callback callbackBeforeFixpipe{};
#if ENABLE_GMM2_MOVING_FORWARD
                MoeCallback callbackAfterFixpipe = MakeCallbackWithValue(&aicSetFuncList[stageId], callIdx);
#else
                if (stageUsed == WORKSPACE_STAGES) {
                    callbackBeforeFixpipe = MakeCallbackWithCall2(&aicWaitFuncList[stageId]);
                } else {
                    ++stageUsed;
                }
                Callback callbackAfterFixpipe = MakeCallback(&aicSetFuncList[stageId]);
#endif

                // Compute initial location in logical coordinates
                MatrixCoord offsetA{blockCoord.m() * L1TileShape::M, blockCoord.k() * L1TileShape::K};
                MatrixCoord offsetB{blockCoord.k() * L1TileShape::K, blockCoord.n() * L1TileShape::N};
#if ENABLE_GMM2_MOVING_FORWARD
                MatrixCoord offsetC{blockCoord.m() * L1TileShape::M, blockCoord.n() * L1TileShape::N};
#else
                MatrixCoord offsetC{(stageId * coreNum + coreIdx) * L1TileShape::M, 0};
#endif
                int64_t gmOffsetA = layoutA.GetOffset(offsetA);
                int64_t gmOffsetB = layoutB.GetOffset(offsetB);
                int64_t gmOffsetC = layoutC.GetOffset(offsetC);

                // Compute block-scoped matrix multiply-add
                if constexpr (BlockMmad::DispatchPolicy::ASYNC) {
                    blockMmad(gmA[gmGroupOffsetA + gmOffsetA], layoutA, gmB[gmGroupOffsetB + gmOffsetB], layoutB,
                              gmC[gmGroupOffsetC + gmOffsetC], layoutC, actualBlockShape, callbackBeforeFixpipe,
                              callbackAfterFixpipe, stageId, tracingIdx++);
                } else {
                    callbackBeforeFixpipe();
                    blockMmad(gmA[gmGroupOffsetA + gmOffsetA], layoutA, gmB[gmGroupOffsetB + gmOffsetB], layoutB,
                              gmC[gmGroupOffsetC + gmOffsetC], layoutC, actualBlockShape);
                    callbackAfterFixpipe();
                }

                if (++stageId == WORKSPACE_STAGES) {
                    stageId = 0;
#if ENABLE_GMM2_MOVING_FORWARD
                    ++callIdx;
#endif
                }
            }

            gmGroupOffsetA += inGroupProblemShape.m() * inGroupProblemShape.k();
            if constexpr (!(EXEC_FLAG & EXEC_FLAG_TENSOR_LIST)) {
            gmGroupOffsetB += inGroupProblemShape.k() * inGroupProblemShape.n();
            }
#if ENABLE_GMM2_MOVING_FORWARD
            gmGroupOffsetC += inGroupProblemShape.m() * inGroupProblemShape.n();
#endif
            startCoreIdx = (startCoreIdx + coreLoops) % coreNum;
            MoeTracing(TRACE_POINT("gmm2-combine moe-gmm2", "E"), 0, groupTracingIdx);
        }
        
        bool skipWithSoft[WORKSPACE_STAGES] = {};
        if constexpr (EXEC_FLAG & EXEC_FLAG_SHARED_EXPERT) {
            MoeTracing(TRACE_POINT("gmm2-combine shared-gmm2", "B"));
            gmA.SetGlobalBuffer(params.ptrSharedA);
            gmB.SetGlobalBuffer(params.ptrSharedB);
#if ENABLE_GMM2_MOVING_FORWARD
            gmC.SetGlobalBuffer(params.ptrSharedC);
            auto layoutC = params.sharedLayoutC;
#endif
            uint32_t softStageUsed = 0;
            GemmCoord inGroupProblemShape = params.sharedGmm2ProblemShape;

            LayoutA layoutA = params.sharedLayoutA;
            LayoutB layoutB = params.sharedLayoutB;

            blockScheduler.Update(inGroupProblemShape, MakeCoord(L1TileShape::M, L1TileShape::N));
            uint32_t coreLoops = blockScheduler.GetCoreLoops();

            // Determine the starting loopIdx of the current core under the current groupIdx
            uint32_t startLoopIdx = ((coreIdx < startCoreIdx) ? (coreIdx + coreNum) : coreIdx) - startCoreIdx;
            // Loop through the matmul of each groupIdx
            uint32_t tracingIdx = 0;
            for (uint32_t loopIdx = startLoopIdx; loopIdx < coreLoops; loopIdx += coreNum) {
                // Compute block location
                GemmCoord blockCoord = blockScheduler.GetBlockCoord(loopIdx);
                GemmCoord actualBlockShape = blockScheduler.GetActualBlockShape(blockCoord);

                Callback callbackBeforeFixpipe{};
#if ENABLE_GMM2_MOVING_FORWARD
                MoeCallback callbackAfterFixpipe = MakeCallbackWithValue(&aicSetFuncList[stageId], callIdx);
#else
                if (softStageUsed == WORKSPACE_STAGES) {
                    callbackBeforeFixpipe = MakeCallbackWithCall(&aicWaitFuncList[stageId]);
                } else {
                    if (stageUsed == WORKSPACE_STAGES) {
                        callbackBeforeFixpipe = MakeCallbackWithCall2(&aicWaitFuncList[stageId]);
                    } else {
                        ++stageUsed;
                    }
                    ++softStageUsed;
                    skipWithSoft[stageId] = true;
                }
                Callback callbackAfterFixpipe = MakeCallbackWithCall(&aicSetFuncList[stageId]);
#endif

                // Compute initial location in logical coordinates
                MatrixCoord offsetA{blockCoord.m() * L1TileShape::M, blockCoord.k() * L1TileShape::K};
                MatrixCoord offsetB{blockCoord.k() * L1TileShape::K, blockCoord.n() * L1TileShape::N};
#if ENABLE_GMM2_MOVING_FORWARD
                MatrixCoord offsetC{blockCoord.m() * L1TileShape::M, blockCoord.n() * L1TileShape::N};
#else
                MatrixCoord offsetC{(stageId * coreNum + coreIdx) * L1TileShape::M, 0};
#endif
                int64_t gmOffsetA = layoutA.GetOffset(offsetA);
                int64_t gmOffsetB = layoutB.GetOffset(offsetB);
                int64_t gmOffsetC = layoutC.GetOffset(offsetC);

                // Compute block-scoped matrix multiply-add
                if constexpr (BlockMmad::DispatchPolicy::ASYNC) {
                    blockMmad(
                        gmA[gmOffsetA], layoutA,
                        gmB[gmOffsetB], layoutB,
                        gmC[gmOffsetC], layoutC,
                        actualBlockShape,
                        callbackBeforeFixpipe, callbackAfterFixpipe,
                        stageId, tracingIdx++
                    );
                } else {
                    callbackBeforeFixpipe();
                    blockMmad(
                        gmA[gmOffsetA], layoutA,
                        gmB[gmOffsetB], layoutB,
                        gmC[gmOffsetC], layoutC,
                        actualBlockShape
                    );
                    callbackAfterFixpipe();
                }

                if (++stageId == WORKSPACE_STAGES) {
                    stageId = 0;
#if ENABLE_GMM2_MOVING_FORWARD
                    ++callIdx;
#endif
                }
            }
            MoeTracing(TRACE_POINT("gmm2-combine shared-gmm2", "E"));
        }

        if constexpr (BlockMmad::DispatchPolicy::ASYNC) {
            MoeTracing(TRACE_POINT("gmm2-combine sync-gmm2", "B"));
            blockMmad.SynchronizeBlock();
            MoeTracing(TRACE_POINT("gmm2-combine sync-gmm2", "E"));
        }


#if !ENABLE_GMM2_MOVING_FORWARD
        while (stageUsed > 0) {
            uint32_t aivComputeStageId = (stageId >= stageUsed) ?
                (stageId - stageUsed) : (stageId + WORKSPACE_STAGES - stageUsed);
            if (skipWithSoft[aivComputeStageId]) {
                Callback callbackBeforeFixpipe = MakeCallbackWithCall(&aicWaitFuncList[aivComputeStageId]);
                callbackBeforeFixpipe();
            } else {
                Callback callbackBeforeFixpipe = MakeCallbackWithCall2(&aicWaitFuncList[aivComputeStageId]);
                callbackBeforeFixpipe();
            }
            --stageUsed;
        }
#endif
        MoeTracing(TRACE_POINT("gmm2-combine aic", "E"));
    }

    template <>
    CATLASS_DEVICE void operator()<AscendC::AIV>(Params const &params)
    {
        MoeTracing(TRACE_POINT("gmm2-combine aiv", "B"));
        auto *combiner = (MoeDistributeCombineImpl::CamMoeDistributeCombine<TemplateMC2TypeFunc> *)params.combiner;
        do {
            MoeTracing(TRACE_POINT("gmm2-combine block-epilogue", "B"));
            if constexpr (EXEC_FLAG & EXEC_FLAG_DEEP_FUSE) {
                if (AscendC::GetSubBlockIdx() == 0) {
                    AscendC::CrossCoreSetFlag<0x0, PIPE_MTE3>(MoeDistributeCombineImpl::RECV_SYNC_EVENT_ID);
                }
            }
            BlockScheduler blockScheduler;
            BlockEpilogue blockEpilogue(resource, combiner->GetCalcInfo());

            uint32_t coreIdx = AscendC::GetBlockIdx() / AscendC::GetSubBlockNum();
            uint32_t coreNum = AscendC::GetBlockNum();
            int64_t gmGroupOffsetScale = 0;
            int64_t gmGroupOffsetPerTokenScale = 0;
            int64_t gmGroupOffsetD = 0;
            AscendC::GlobalTensor<ElementGroupList> groupList;
            groupList.SetGlobalBuffer(params.ptrGroupList);

            AscendC::GlobalTensor<ElementC> gmC;
            gmC.SetGlobalBuffer(params.ptrC);
#if !ENABLE_GMM2_MOVING_FORWARD
            auto layoutC = layout::RowMajor{L1TileShape::M * coreNum * WORKSPACE_STAGES, L1TileShape::N};
#endif

            uint32_t stageId = 0;
            uint32_t startCoreIdx = 0;
            int64_t gmGroupOffsetC = 0;
#if ENABLE_GMM2_MOVING_FORWARD
            int32_t callIdx = 1;
#endif
            AscendC::ListTensorDesc gmScaleListTensor;
            gmScaleListTensor = AscendC::ListTensorDesc(reinterpret_cast<__gm__ void *>(params.ptrScale));
            __gm__ ElementScale* gmScalePtr;
            if constexpr (!(EXEC_FLAG & EXEC_FLAG_TENSOR_LIST)) {
                gmScalePtr = reinterpret_cast<__gm__ ElementScale*>(gmScaleListTensor.GetDataPtr<int32_t>(0));
            }
            uint32_t tracingIdx = 0;
            for (uint32_t groupIdx = 0; groupIdx < params.problemCount; ++groupIdx) {
                uint32_t groupTracingIdx = tracingIdx++;
                MoeTracing(TRACE_POINT("gmm2-combine block-epilogue group", "B"), 0, groupTracingIdx);
                uint32_t currentM = (groupIdx == 0) ? groupList.GetValue(params.epRankSize - 1)
                                                    : (groupList.GetValue((groupIdx + 1) * params.epRankSize - 1) -
                                                       groupList.GetValue(groupIdx * params.epRankSize - 1));
                GemmCoord inGroupProblemShape{currentM, params.problemShape.n(), params.problemShape.k()};
#if ENABLE_GMM2_MOVING_FORWARD
                auto layoutC = params.layoutC.GetTileLayout(inGroupProblemShape.GetCoordMN());
#endif

                LayoutScale layoutScale = params.layoutScale;
                LayoutPerTokenScale layoutPerTokenScale =
                    params.layoutPerTokenScale.GetTileLayout(inGroupProblemShape.template GetCoordByAxis<0>());
                LayoutD layoutD = params.layoutD.GetTileLayout(inGroupProblemShape.GetCoordMN());
                EpilogueParams epilogueParams;
                if constexpr (EXEC_FLAG & EXEC_FLAG_TENSOR_LIST) {
                    gmScalePtr = reinterpret_cast<__gm__ ElementScale*>(
                                        gmScaleListTensor.GetDataPtr<int32_t>(groupIdx));
                    epilogueParams = EpilogueParams {
                        gmScalePtr, layoutScale,
                        params.ptrPerTokenScale + gmGroupOffsetPerTokenScale, layoutPerTokenScale,
                            params.ptrD + gmGroupOffsetD, layoutD};
                } else {
                    epilogueParams = EpilogueParams{gmScalePtr + gmGroupOffsetScale,
                                              layoutScale,
                                              params.ptrPerTokenScale + gmGroupOffsetPerTokenScale,
                                              layoutPerTokenScale,
                                              params.ptrD + gmGroupOffsetD,
                                              layoutD};
                }
                blockScheduler.Update(inGroupProblemShape, L1TileShape::ToCoordMN());
                blockEpilogue.UpdateParams(epilogueParams);
                uint32_t coreLoops = blockScheduler.GetCoreLoops();

                GemmCoord blockShapeMNK = L1TileShape::ToCoord();
                uint32_t startLoopIdx = ((coreIdx < startCoreIdx) ? (coreIdx + coreNum) : coreIdx) - startCoreIdx;
                for (uint32_t loopIdx = startLoopIdx; loopIdx < coreLoops; loopIdx += coreNum) {
                    GemmCoord blockCoordMNK = blockScheduler.GetBlockCoord(loopIdx);
                    GemmCoord actualBlockShapeMNK = blockScheduler.GetActualBlockShape(blockCoordMNK);

#if ENABLE_GMM2_MOVING_FORWARD
                    MatrixCoord offsetC{blockCoordMNK.m() * L1TileShape::M, blockCoordMNK.n() * L1TileShape::N};
#else
                    MatrixCoord offsetC{(stageId * coreNum + coreIdx) * L1TileShape::M, 0};
#endif
                    int64_t gmOffsetC = layoutC.GetOffset(offsetC);
                    auto gmBlockC = gmC[gmGroupOffsetC + gmOffsetC];
                    auto layoutBlockC = layoutC.GetTileLayout(actualBlockShapeMNK.GetCoordMN());

                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue waiting", "B"), stageId, tracingIdx);
#if ENABLE_GMM2_MOVING_FORWARD
                    aicWaitFuncList[stageId].CallWithValue(callIdx);
#else
                    Arch::CrossCoreWaitFlag(flagAicFinishStoreList[stageId]);
#endif
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue waiting", "E"), stageId, tracingIdx);
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue calc", "B"), stageId, tracingIdx);
                    blockEpilogue(gmGroupOffsetD, groupIdx, blockShapeMNK, blockCoordMNK, actualBlockShapeMNK, gmBlockC,
                                  layoutBlockC);
#if !ENABLE_GMM2_MOVING_FORWARD
                    Arch::CrossCoreSetFlag<0x2, PIPE_MTE3>(flagAivFinishComputeList[stageId]);
#endif
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue calc", "E"), stageId, tracingIdx++);
                    if (++stageId == WORKSPACE_STAGES) {
                        stageId = 0;
#if ENABLE_GMM2_MOVING_FORWARD
                        ++callIdx;
#endif
                    }
                }

                if constexpr (!(EXEC_FLAG & EXEC_FLAG_TENSOR_LIST)) {
                gmGroupOffsetScale += inGroupProblemShape.n();
                }
                gmGroupOffsetPerTokenScale += inGroupProblemShape.m();
                gmGroupOffsetD += inGroupProblemShape.m() * inGroupProblemShape.n();
#if ENABLE_GMM2_MOVING_FORWARD
                gmGroupOffsetC += inGroupProblemShape.m() * inGroupProblemShape.n();
#endif

                startCoreIdx = (startCoreIdx + coreLoops) % coreNum;
                MoeTracing(TRACE_POINT("gmm2-combine block-epilogue group", "E"), 0, groupTracingIdx);
            }
            if constexpr (EXEC_FLAG & EXEC_FLAG_SHARED_EXPERT) {
                if (AscendC::GetSubBlockIdx() == 0) {
                    uint32_t tracingIdx = 0;
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-group", "B"));
#if ENABLE_GMM2_MOVING_FORWARD
                    gmC.SetGlobalBuffer(params.ptrSharedC);
                    auto layoutC = params.sharedLayoutC;
#endif
                    AscendC::CrossCoreSetFlag<0x0, PIPE_MTE3>(MoeDistributeCombineImpl::SEND_SYNC_EVENT_ID);
                    if constexpr ((EXEC_FLAG & EXEC_FLAG_DEEP_FUSE) == 0) {
                        AscendC::CrossCoreSetFlag<0x0, PIPE_MTE3>(MoeDistributeCombineImpl::RECV_SYNC_EVENT_ID);
                    }
                    GemmCoord inGroupProblemShape = params.sharedGmm2ProblemShape;

                    LayoutScale layoutScale = params.layoutScale;
                    LayoutPerTokenScale layoutPerTokenScale =
                        params.sharedLayoutPerTokenScale.GetTileLayout(inGroupProblemShape.template GetCoordByAxis<0>());
                    LayoutD layoutD = params.sharedLayoutD.GetTileLayout(inGroupProblemShape.GetCoordMN());

                    EpilogueParams epilogueParams{
                        params.ptrSharedScale, layoutScale,
                        params.ptrSharedPtrPerTokenScale, layoutPerTokenScale,
                        params.ptrSharedD, layoutD
                    };

                    blockScheduler.Update(inGroupProblemShape, L1TileShape::ToCoordMN());
                    blockEpilogue.UpdateParams(epilogueParams);
                    uint32_t coreLoops = blockScheduler.GetCoreLoops();

                    GemmCoord blockShapeMNK = L1TileShape::ToCoord();
                    uint32_t startLoopIdx = ((coreIdx < startCoreIdx) ? (coreIdx + coreNum) : coreIdx) - startCoreIdx;
                    for (uint32_t loopIdx = startLoopIdx; loopIdx < coreLoops; loopIdx += coreNum) {
                        GemmCoord blockCoordMNK = blockScheduler.GetBlockCoord(loopIdx);
                        GemmCoord actualBlockShapeMNK = blockScheduler.GetActualBlockShape(blockCoordMNK);

#if ENABLE_GMM2_MOVING_FORWARD
                        MatrixCoord offsetC{blockCoordMNK.m() * L1TileShape::M, blockCoordMNK.n() * L1TileShape::N};
#else
                        MatrixCoord offsetC{(stageId * coreNum + coreIdx) * L1TileShape::M, 0};
#endif
                        int64_t gmOffsetC = layoutC.GetOffset(offsetC);
                        auto gmBlockC = gmC[gmOffsetC];
                        auto layoutBlockC = layoutC.GetTileLayout(actualBlockShapeMNK.GetCoordMN());
#if ENABLE_GMM2_MOVING_FORWARD
                        MoeCallback callbackBeforeBlockEpilogue = MakeCallbackWithValue(&aicWaitFuncList[stageId], callIdx);
#else
                        Callback callbackBeforeBlockEpilogue = MakeCallbackWithCall(&aicWaitFuncList[stageId]);
                        Callback callbackAfterBlockEpilogue = MakeCallbackWithCall(&aicSetFuncList[stageId]);
#endif

                        MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-waiting", "B"), stageId, tracingIdx);
                        callbackBeforeBlockEpilogue();
                        MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-waiting", "E"), stageId, tracingIdx);
                        MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-calc", "B"), stageId, tracingIdx);
                        blockEpilogue(0, UINT32_MAX, blockShapeMNK, blockCoordMNK, actualBlockShapeMNK,
                            gmBlockC, layoutBlockC);
#if !ENABLE_GMM2_MOVING_FORWARD
                        callbackAfterBlockEpilogue();
#endif
                        MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-calc", "E"), stageId, tracingIdx++);

                        if (++stageId == WORKSPACE_STAGES) {
                            stageId = 0;
#if ENABLE_GMM2_MOVING_FORWARD
                            ++callIdx;
#endif
                        }
                    }
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-group", "E"));
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-wait-combine", "B"));
                    AscendC::CrossCoreWaitFlag(MoeDistributeCombineImpl::SEND_SYNC_EVENT_ID);
                    AscendC::CrossCoreWaitFlag(MoeDistributeCombineImpl::RECV_SYNC_EVENT_ID);
                    MoeTracing(TRACE_POINT("gmm2-combine block-epilogue shared-wait-combine", "E"));
                }
            }
            MoeTracing(TRACE_POINT("gmm2-combine block-epilogue", "E"));
        } while(false);

        icache_preload(4);
        if constexpr (EXEC_FLAG & EXEC_FLAG_SHARED_EXPERT) {
            if (AscendC::GetSubBlockIdx() == 1) {
                MoeTracing(TRACE_POINT("gmm2-combine combine", "B"));
                resource.pipe.Init();
                combiner->TPipeSet(&resource.pipe);
                combiner->ProcessCombine();
                combiner->TPipeSet(nullptr);
                resource.pipe.Destroy();
                MoeTracing(TRACE_POINT("gmm2-combine combine", "E"));
            }
        } else if constexpr (EXEC_FLAG & EXEC_FLAG_DEEP_FUSE) {
            if (AscendC::GetSubBlockIdx() == 0) {
                MoeTracing(TRACE_POINT("gmm2-combine combine-send", "B"));
                resource.pipe.Init();
                combiner->TPipeSet(&resource.pipe);
                combiner->AllToAllSend();
                combiner->TPipeSet(nullptr);
                resource.pipe.Destroy();
                MoeTracing(TRACE_POINT("gmm2-combine combine-send", "E"));
            } else {
                MoeTracing(TRACE_POINT("gmm2-combine combine-recv", "B"));
                resource.pipe.Init();
                combiner->TPipeSet(&resource.pipe);
                combiner->ReducePermute();
                combiner->TPipeSet(nullptr);
                resource.pipe.Destroy();
                MoeTracing(TRACE_POINT("gmm2-combine combine-recv", "E"));
            }
        } else {
            MoeTracing(TRACE_POINT("gmm2-combine combine", "B"));
            resource.pipe.Init();
            combiner->TPipeSet(&resource.pipe);
            combiner->Process();
            combiner->TPipeSet(nullptr);
            resource.pipe.Destroy();
            MoeTracing(TRACE_POINT("gmm2-combine combine", "E"));
        }

#if ENABLE_GMM2_MOVING_FORWARD
        if (AscendC::GetSubBlockIdx() == 0) {
            MoeTracing(TRACE_POINT("gmm2-combine clean-flags", "B"));
            for (uint32_t i = 0; i < WORKSPACE_STAGES; ++i) {
                aicSetFuncList[i].CallWithValue(0);
            }
            for (uint32_t i = (AscendC::GetBlockIdx() / AscendC::GetSubBlockNum()); i < params.problemCount; i += AscendC::GetBlockNum()) {
                prevSetFunc.CallWithAll(i, 0);
            }
            MoeTracing(TRACE_POINT("gmm2-combine clean-flags", "E"));
        }
#endif
        MoeTracing(TRACE_POINT("gmm2-combine aiv", "E"));
    }

private:
    friend struct AicWaitFunc;
    friend struct AicSetFunc;

    struct AicWaitFunc {
        using MatmulKernel =
            GroupedMatmulSliceMPerTokenDequantMultiStageWorkspace<TemplateMC2TypeFunc, BlockMmad, BlockEpilogue,
                                                                  BlockScheduler, WORKSPACE_STAGES, ElementGroupList>;

        CATLASS_DEVICE
        AicWaitFunc() = default;

        CATLASS_DEVICE
        void Call() const {
            constexpr uint32_t waitValue = g_coreType == AscendC::AIC ? 0 : 1;
            // 查看flag，类似wait flag
            AscendC::PipeBarrier<PIPE_ALL>();
            AscendC::GlobalTensor<int32_t> global;
            global.SetGlobalBuffer((__gm__ int32_t *)(syncAddr + stageId * GMM2::SOFT_SYNC_SPACE_SIZE));
            while (true){
                __asm__ __volatile__("");
                AscendC::DataCacheCleanAndInvalid<int32_t,
                            AscendC::CacheLine::SINGLE_CACHE_LINE, AscendC::DcciDst::CACHELINE_OUT>(global);
                __asm__ __volatile__("");
                int32_t value = global.GetValue(0);
                if (value == waitValue) {
                    __asm__ __volatile__("");
                    AscendC::DataCacheCleanAndInvalid<int32_t,
                            AscendC::CacheLine::SINGLE_CACHE_LINE, AscendC::DcciDst::CACHELINE_OUT>(global);
                    __asm__ __volatile__("");
                    break;
                }
            }
            AscendC::PipeBarrier<PIPE_ALL>();
        }

        CATLASS_DEVICE
        void CallWithValue(int32_t waitValue) const
        {
            CallWithAll(stageId, waitValue);
        }

        CATLASS_DEVICE
        void CallWithAll(int32_t index, int32_t waitValue) const
        {
#define YHB_ENABLE_SOFTSYNC_TIMEOUT 0
#if YHB_ENABLE_SOFTSYNC_TIMEOUT
            int64_t timeout = AscendC::GetSystemCycle() + 50 * 1000 * 100;
#endif
            AscendC::GlobalTensor<int32_t> global;
            global.SetGlobalBuffer((__gm__ int32_t *)(syncAddr + index * GMM2::SOFT_SYNC_SPACE_SIZE));
            while (true) {
                __asm__ __volatile__("");
                AscendC::DataCacheCleanAndInvalid<int32_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                                  AscendC::DcciDst::CACHELINE_OUT>(global);
                __asm__ __volatile__("");
                int32_t value = global.GetValue(0);
                if (value >= waitValue) {
                    __asm__ __volatile__("");
                    AscendC::DataCacheCleanAndInvalid<int32_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                                      AscendC::DcciDst::CACHELINE_OUT>(global);
                    __asm__ __volatile__("");
#if MOE_ENABLE_SOFTSYNC_TIMEOUT
                    MOE_LOG_DETAIL("YHB: sync waited, index(%u) waitValue(%u) value(%u)", index, waitValue, value);
#endif
                    break;
                }
#if YHB_ENABLE_SOFTSYNC_TIMEOUT
                if (AscendC::GetSystemCycle() - timeout > 0) {
                    MOE_LOG_WARNING("YHB: sync timeout, index(%u) waitValue(%u) value(%u)", index, waitValue, value);
                    break;
                }
#endif
            }
        }

        CATLASS_DEVICE
        void operator()() const
        {
            Arch::CrossCoreWaitFlag(ptr->flagAivFinishComputeList[stageId]);
        }

        MatmulKernel *ptr{nullptr};
        GM_ADDR syncAddr;
        uint32_t stageId;
    };

    struct AicSetFunc {
        using MatmulKernel =
            GroupedMatmulSliceMPerTokenDequantMultiStageWorkspace<TemplateMC2TypeFunc, BlockMmad, BlockEpilogue,
                                                                  BlockScheduler, WORKSPACE_STAGES, ElementGroupList>;

        CATLASS_DEVICE
        AicSetFunc() = default;

        CATLASS_DEVICE
        void Call() const {
            constexpr uint32_t setValue = g_coreType == AscendC::AIC ? 1 : 0;
            AscendC::PipeBarrier<PIPE_ALL>();
            AscendC::GlobalTensor<int32_t> global;
            global.SetGlobalBuffer((__gm__ int32_t *)(syncAddr + stageId * GMM2::SOFT_SYNC_SPACE_SIZE));
            __asm__ __volatile__("");
            AscendC::DataCacheCleanAndInvalid<int32_t,
                            AscendC::CacheLine::SINGLE_CACHE_LINE, AscendC::DcciDst::CACHELINE_OUT>(global);
            __asm__ __volatile__("");
            global.SetValue(0, setValue);
            __asm__ __volatile__("");
            AscendC::DataCacheCleanAndInvalid<int32_t,
                            AscendC::CacheLine::SINGLE_CACHE_LINE, AscendC::DcciDst::CACHELINE_OUT>(global);
            __asm__ __volatile__("");
            AscendC::PipeBarrier<PIPE_ALL>();
        }

        CATLASS_DEVICE
        void CallWithValue(int32_t setValue) const
        {
            CallWithAll(stageId, setValue);
        }

        CATLASS_DEVICE
        void CallWithAll(uint32_t index, int32_t setValue) const
        {
            AscendC::PipeBarrier<PIPE_ALL>();
            AscendC::GlobalTensor<int32_t> global;
            global.SetGlobalBuffer((__gm__ int32_t *)(syncAddr + index * GMM2::SOFT_SYNC_SPACE_SIZE));
            __asm__ __volatile__("");
            AscendC::DataCacheCleanAndInvalid<int32_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                              AscendC::DcciDst::CACHELINE_OUT>(global);
            __asm__ __volatile__("");
            global.SetValue(0, setValue);
            __asm__ __volatile__("");
            AscendC::DataCacheCleanAndInvalid<int32_t, AscendC::CacheLine::SINGLE_CACHE_LINE,
                                              AscendC::DcciDst::CACHELINE_OUT>(global);
            __asm__ __volatile__("");
            AscendC::PipeBarrier<PIPE_ALL>();
        }

        CATLASS_DEVICE
        void operator()() const
        {
            Arch::CrossCoreSetFlag<0x2, PIPE_FIX>(ptr->flagAicFinishStoreList[stageId]);
        }

        MatmulKernel *ptr{nullptr};
        GM_ADDR syncAddr;
        uint32_t stageId;
    };

    Arch::CrossCoreFlag flagAicFinishStoreList[WORKSPACE_STAGES];
    Arch::CrossCoreFlag flagAivFinishComputeList[WORKSPACE_STAGES];

    AicWaitFunc aicWaitFuncList[WORKSPACE_STAGES];
    AicSetFunc aicSetFuncList[WORKSPACE_STAGES];
    AicWaitFunc prevWaitFunc;
    AicSetFunc prevSetFunc;
    AscendC::GlobalTensor<GM_ADDR> epWinContext_;
    __gm__ HcclOpResParam *winContext_;
    uint32_t epRankId_{0};
    Arch::Resource<ArchTag> resource;
};

}  // namespace Catlass::Gemm::Kernel

#endif  // ACT_GEMM_KERNEL_GROUPED_MATMUL_M_PER_TOKEN_DEQUANT_MULTISTAGE_WORKSPACE_HPP
