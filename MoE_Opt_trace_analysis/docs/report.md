# Trace Analysis Report

## Overview

| num_instances | num_phases | num_names | num_pids | num_tids | num_core_groups | core_groups | total_wall_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 43928 | 54 | 314 | 16 | 72 | 3 | cube, vector_recv, vector_send | 336.56 |

## Visualizations

![Analysis Charts](analysis_charts.png)

## Statistical Highlights

- Trace scope: 43928 mapped intervals, 54 phases, 72 tids, core groups=cube, vector_recv, vector_send, wall=336.560 us.
- Core group wall coverage: vector_send=336.560 us (100.0%), vector_recv=328.520 us (97.6%), cube=247.740 us (73.6%).
- Top non-container categories by wall coverage: communication=335.400 us (99.7%), wait=324.700 us (96.5%), epilogue=245.500 us (72.9%), compute=215.040 us (63.9%).
- Category pie basis: non-container category event-time share uses `total_us`, so slices sum to 100%. communication=173776.020 us (31.8%), wait=172526.340 us (31.6%), epilogue=105961.280 us (19.4%), compute=45997.360 us (8.4%), quant=30061.820 us (5.5%), sync=16404.600 us (3.0%), init=1723.900 us (0.3%), cleanup=213.500 us (0.0%).
- Leading category per core group: cube: compute 200.640 us (81.0% of group); vector_recv: wait 309.420 us (94.2% of group); vector_send: communication 324.240 us (96.3% of group).
- Top non-container phases: gmm2_combine_combine=252.360 us (75.0%, communication), gmm2_combine_block_epilogue=245.500 us (72.9%, epilogue), gmm2_combine_shared_wait_combine=240.940 us (71.6%, wait), gmm2_combine_combine_wait_status=235.400 us (69.9%, wait), gmm2_combine_block_epilogue_group=156.780 us (46.6%, epilogue).

## Automatic Diagnosis

主耗时阶段是 gmm2_combine_shared_wait_combine；瓶颈类型倾向于 wait

1. [high] 主耗时阶段是 gmm2_combine_shared_wait_combine
   Evidence: union=240.940 us, 占 wall time 71.6%, category=wait.
   Action: 优先检查该阶段内部的 top raw names 和同 category 的等待/计算子阶段。
2. [high] 瓶颈类型倾向于 wait
   Evidence: wait union=324.700 us, 占 wall time 96.5%.
   Action: 若该类型是 wait/sync，优先看跨核信号与通信；若是 compute/epilogue，优先看矩阵维度、分块和核间负载。
3. [high] 存在显著等待开销
   Evidence: wait union=324.700 us, 占 wall time 96.5%; top wait=gmm2-combine combine-wait-status, gmm2-combine block-epilogue shared-wait-combine, dispatch-gmm1 shared-dispatch-swiglu wait-flag.
   Action: 重点排查 token ready、combine status、shared expert 同步和 AIC/AIV pipeline 依赖。
4. [high] 等待主要出现在 vector_recv 核组
   Evidence: vector_recv=309.420 us, vector_send=267.420 us, cube=189.640 us; vector_recv 内 wait 覆盖该核组 94.2%.
   Action: 分别查看 phase_core_group_summary.csv，确认是 cube 等 token，还是 vector_recv/vector_send 在等待 combine/status。
5. [info] dispatch_gmm1 与 gmm2_combine 有一定流水覆盖
   Evidence: overlap=103.840 us, 相对较短阶段覆盖 56.9%.
   Action: 继续看各自内部 wait 和 epilogue 是否占主导。

## Core Group Summary

| core_group | core_kind | core_type | observed_core_count | count | union_us | ratio_to_total_wall | total_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cube | cube | 0 | 24 | 9240 | 247.74 | 0.736095 | 199119.18 |
| vector_recv | vector | 1 | 24 | 19440 | 328.52 | 0.976111 | 585494.34 |
| vector_send | vector | 2 | 24 | 15248 | 336.56 | 1 | 608691.74 |

## Category By Core Group

| core_group | category | observed_core_count | count | union_us | ratio_to_core_group_wall | ratio_to_total_wall | total_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cube | container | 24 | 1920 | 247.74 | 1 | 0.736095 | 144954.6 |
| cube | compute | 24 | 3468 | 200.64 | 0.809881 | 0.596149 | 19929.2 |
| cube | wait | 24 | 2316 | 189.64 | 0.76548 | 0.563466 | 12360.2 |
| cube | sync | 24 | 1152 | 148.22 | 0.598289 | 0.440397 | 8688.98 |
| cube | communication | 24 | 384 | 41.04 | 0.165658 | 0.12194 | 13186.2 |
| vector_recv | container | 24 | 3540 | 328.52 | 1 | 0.976111 | 346532.36 |
| vector_recv | wait | 24 | 2364 | 309.42 | 0.94186 | 0.919361 | 82891.36 |
| vector_recv | epilogue | 24 | 2700 | 245.42 | 0.747047 | 0.729201 | 91931.06 |
| vector_recv | communication | 24 | 5844 | 202.34 | 0.615914 | 0.6012 | 19649.64 |
| vector_recv | quant | 24 | 2688 | 177.8 | 0.541215 | 0.528286 | 20868.58 |
| vector_recv | compute | 24 | 384 | 155.74 | 0.474066 | 0.462741 | 17452.66 |
| vector_recv | sync | 24 | 384 | 77.38 | 0.235541 | 0.229914 | 5180.8 |
| vector_recv | cleanup | 24 | 384 | 24.64 | 0.075003 | 0.073211 | 126.3 |
| vector_recv | init | 24 | 1152 | 24.02 | 0.073116 | 0.071369 | 861.58 |
| vector_send | container | 24 | 2340 | 336.56 | 1 | 1 | 355153.48 |
| vector_send | communication | 24 | 3492 | 324.24 | 0.963394 | 0.963394 | 140940.18 |
| vector_send | wait | 24 | 2812 | 267.42 | 0.794569 | 0.794569 | 77274.78 |
| vector_send | epilogue | 24 | 1996 | 158.38 | 0.470585 | 0.470585 | 14030.22 |
| vector_send | quant | 24 | 2304 | 124.24 | 0.369147 | 0.369147 | 9193.24 |
| vector_send | compute | 24 | 384 | 116.96 | 0.347516 | 0.347516 | 8615.5 |
| vector_send | sync | 24 | 384 | 58.68 | 0.174352 | 0.174352 | 2534.82 |
| vector_send | init | 24 | 1152 | 23.98 | 0.07125 | 0.07125 | 862.32 |
| vector_send | cleanup | 24 | 384 | 10.44 | 0.03102 | 0.03102 | 87.2 |

## Phase By Core Group

| core_group | phase | category | observed_core_count | count | union_us | ratio_to_core_group_wall | total_us |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cube | processing | container | 24 | 384 | 247.74 | 1 | 50323.66 |
| cube | dispatch_gmm1 | container | 24 | 384 | 174.22 | 0.703237 | 35787.16 |
| cube | dispatch_gmm1_aic | container | 24 | 384 | 173.84 | 0.701703 | 35630.36 |
| cube | gmm2_combine | container | 24 | 384 | 164.36 | 0.663437 | 11866.08 |
| cube | gmm2_combine_aic | container | 24 | 384 | 163.24 | 0.658917 | 11347.34 |
| cube | dispatch_gmm1_moe_process | compute | 24 | 1152 | 130.9 | 0.528377 | 13236.1 |
| cube | gmm2_combine_block_mmad_copy_out | compute | 24 | 780 | 120.2 | 0.485186 | 819.78 |
| cube | gmm2_combine_block_mmad_waiting | wait | 24 | 780 | 117.04 | 0.472431 | 785.5 |
| cube | gmm2_combine_moe_gmm2 | compute | 24 | 1152 | 110.04 | 0.444175 | 2345.02 |
| cube | dispatch_gmm1_wait_moe_token | wait | 24 | 1152 | 100.72 | 0.406555 | 7761.3 |
| cube | dispatch_gmm1_sync | sync | 24 | 384 | 92.62 | 0.37386 | 7096.26 |
| cube | gmm2_combine_shared_gmm2 | compute | 24 | 384 | 85.98 | 0.347057 | 3528.3 |
| cube | gmm2_combine_sync_gmm2 | sync | 24 | 384 | 76.62 | 0.309276 | 988.8 |
| cube | dispatch_gmm1_sync_block_mmad | sync | 24 | 384 | 53.48 | 0.215871 | 603.92 |
| cube | dispatch_gmm1_shared_process | communication | 24 | 384 | 41.04 | 0.165658 | 13186.2 |
| cube | dispatch_gmm1_wait_shared_token | wait | 24 | 384 | 15.74 | 0.063534 | 3813.4 |
| vector_recv | processing | container | 24 | 384 | 328.52 | 1 | 116900 |
| vector_recv | gmm2_combine | container | 24 | 2004 | 248.04 | 0.755023 | 78538.2 |
| vector_recv | gmm2_combine_aiv | container | 24 | 384 | 246.1 | 0.749117 | 77177.24 |
| vector_recv | gmm2_combine_block_epilogue | epilogue | 24 | 384 | 245.42 | 0.747047 | 76975.9 |
| vector_recv | gmm2_combine_shared_wait_combine | wait | 24 | 384 | 240.94 | 0.73341 | 65808.34 |
| vector_recv | dispatch_gmm1 | container | 24 | 384 | 182.5 | 0.555522 | 37059.36 |
| vector_recv | dispatch_gmm1_aiv | container | 24 | 384 | 182.02 | 0.554061 | 36857.56 |
| vector_recv | dispatch_gmm1_comp_core | compute | 24 | 384 | 155.74 | 0.474066 | 17452.66 |
| vector_recv | gmm2_combine_block_epilogue_group | epilogue | 24 | 1152 | 153.52 | 0.467308 | 5965.46 |
| vector_recv | gmm2_combine_block_epilogue_calc | epilogue | 24 | 460 | 137.22 | 0.417691 | 3185.98 |
| vector_recv | dispatch_gmm1_moe_dispatch_swiglu | quant | 24 | 1152 | 132.88 | 0.404481 | 7975 |
| vector_recv | dispatch_gmm1_moe_dispatch_swiglu_wait_flag | wait | 24 | 432 | 125.58 | 0.38226 | 5124.12 |
| vector_recv | dispatch_gmm1_recv_core | communication | 24 | 384 | 124.62 | 0.379338 | 9332.04 |
| vector_recv | dispatch_gmm1_recv_token | communication | 24 | 1152 | 116.98 | 0.356082 | 2029.28 |
| vector_recv | dispatch_gmm1_recv_token_calc | communication | 24 | 1152 | 116.18 | 0.353647 | 1737.96 |
| vector_recv | gmm2_combine_send_calc | communication | 24 | 1620 | 115.14 | 0.350481 | 482.46 |
| vector_recv | gmm2_combine_block_epilogue_shared_group | epilogue | 24 | 384 | 97.46 | 0.296664 | 4173.38 |
| vector_recv | gmm2_combine_block_epilogue_waiting | wait | 24 | 460 | 97.12 | 0.295629 | 2599.84 |
| vector_recv | dispatch_gmm1_shared_dispatch_swiglu | quant | 24 | 384 | 96.32 | 0.293194 | 9012.52 |
| vector_recv | gmm2_combine_block_epilogue_shared_calc | epilogue | 24 | 320 | 79.38 | 0.241629 | 1630.34 |
| vector_recv | dispatch_gmm1_sync_aiv | sync | 24 | 384 | 77.38 | 0.235541 | 5180.8 |
| vector_recv | gmm2_combine_block_epilogue_shared_waiting | wait | 24 | 320 | 73.12 | 0.222574 | 2497.16 |
| vector_recv | dispatch_gmm1_get_cum_sum | communication | 24 | 1152 | 72.46 | 0.220565 | 1626.78 |
| vector_recv | dispatch_gmm1_shared_dispatch_swiglu_wait_flag | wait | 24 | 768 | 64.34 | 0.195848 | 6861.9 |
| vector_recv | dispatch_gmm1_moe_quant | quant | 24 | 384 | 40.98 | 0.124741 | 418.26 |
| vector_recv | dispatch_gmm1_shared_quant | quant | 24 | 384 | 37.46 | 0.114027 | 516.9 |
| vector_recv | dispatch_gmm1_recv_count | communication | 24 | 384 | 27.18 | 0.082735 | 4441.12 |
| vector_recv | dispatch_gmm1_update_clean_info | cleanup | 24 | 384 | 24.64 | 0.075003 | 126.3 |
| vector_recv | combine_init | init | 24 | 384 | 17.96 | 0.054669 | 171.8 |
| vector_recv | dispatch_gmm1_share_quant_core | quant | 24 | 384 | 14.7 | 0.044746 | 2945.9 |
| vector_recv | dispatch_gmm1_aiv_init_state | init | 24 | 384 | 5.74 | 0.017472 | 294.8 |
| vector_recv | dispatch_gmm1_aiv_init_params | init | 24 | 384 | 4.74 | 0.014428 | 394.98 |
| vector_send | processing | container | 24 | 384 | 336.56 | 1 | 119678.28 |
| vector_send | gmm2_combine | container | 24 | 804 | 256.92 | 0.763371 | 81295.62 |
| vector_send | gmm2_combine_aiv | container | 24 | 384 | 255.82 | 0.760102 | 80409.38 |
| vector_send | gmm2_combine_combine | communication | 24 | 384 | 252.36 | 0.749822 | 73891.34 |
| vector_send | gmm2_combine_combine_wait_status | wait | 24 | 384 | 235.4 | 0.69943 | 66034.24 |
| vector_send | dispatch_gmm1 | container | 24 | 384 | 182.38 | 0.541894 | 36991.52 |
| vector_send | dispatch_gmm1_aiv | container | 24 | 384 | 181.94 | 0.540587 | 36778.68 |
| vector_send | gmm2_combine_block_epilogue | epilogue | 24 | 384 | 158.38 | 0.470585 | 6459.6 |
| vector_send | gmm2_combine_block_epilogue_group | epilogue | 24 | 1152 | 156.24 | 0.464226 | 5340.96 |
| vector_send | gmm2_combine_block_epilogue_calc | epilogue | 24 | 460 | 137.54 | 0.408664 | 2229.66 |
| vector_send | dispatch_gmm1_comp_core | compute | 24 | 384 | 116.96 | 0.347516 | 8615.5 |
| vector_send | dispatch_gmm1_moe_dispatch_swiglu | quant | 24 | 1152 | 111.36 | 0.330877 | 5860.74 |

## Category Summary

| category | count | union_us | ratio_to_total_wall | total_us | tid_nunique |
| --- | --- | --- | --- | --- | --- |
| container | 7800 | 336.56 | 1 | 846640.44 | 72 |
| communication | 9720 | 335.4 | 0.996553 | 173776.02 | 72 |
| wait | 7492 | 324.7 | 0.964761 | 172526.34 | 72 |
| epilogue | 4696 | 245.5 | 0.729439 | 105961.28 | 48 |
| compute | 4236 | 215.04 | 0.638935 | 45997.36 | 72 |
| quant | 4992 | 178.44 | 0.530188 | 30061.82 | 48 |
| sync | 1920 | 149.9 | 0.445389 | 16404.6 | 72 |
| init | 2304 | 24.96 | 0.074162 | 1723.9 | 48 |
| cleanup | 768 | 24.68 | 0.07333 | 213.5 | 48 |

## Phase Summary

| phase | category | count | union_us | ratio_to_total_wall | total_us | tid_nunique |
| --- | --- | --- | --- | --- | --- | --- |
| processing | container | 1152 | 336.56 | 1 | 286901.94 | 72 |
| gmm2_combine | container | 3192 | 257.7 | 0.765688 | 171699.9 | 72 |
| gmm2_combine_aiv | container | 768 | 255.82 | 0.760102 | 157586.62 | 48 |
| gmm2_combine_combine | communication | 384 | 252.36 | 0.749822 | 73891.34 | 24 |
| gmm2_combine_block_epilogue | epilogue | 768 | 245.5 | 0.729439 | 83435.5 | 48 |
| gmm2_combine_shared_wait_combine | wait | 384 | 240.94 | 0.71589 | 65808.34 | 24 |
| gmm2_combine_combine_wait_status | wait | 384 | 235.4 | 0.69943 | 66034.24 | 24 |
| dispatch_gmm1 | container | 1152 | 182.58 | 0.542489 | 109838.04 | 72 |
| dispatch_gmm1_aiv | container | 768 | 182.06 | 0.540944 | 73636.24 | 48 |
| dispatch_gmm1_aic | container | 384 | 173.84 | 0.51652 | 35630.36 | 24 |
| gmm2_combine_aic | container | 384 | 163.24 | 0.485025 | 11347.34 | 24 |
| gmm2_combine_block_epilogue_group | epilogue | 2304 | 156.78 | 0.465831 | 11306.42 | 48 |
| dispatch_gmm1_comp_core | compute | 768 | 156.4 | 0.464702 | 26068.16 | 48 |
| gmm2_combine_block_epilogue_calc | epilogue | 920 | 140.36 | 0.417043 | 5415.64 | 48 |
| dispatch_gmm1_moe_dispatch_swiglu | quant | 2304 | 133.52 | 0.39672 | 13835.74 | 48 |
| gmm2_combine_send_calc | communication | 2040 | 131.1 | 0.389529 | 727.26 | 48 |
| dispatch_gmm1_moe_process | compute | 1152 | 130.9 | 0.388935 | 13236.1 | 24 |
| dispatch_gmm1_moe_dispatch_swiglu_wait_flag | wait | 864 | 126.16 | 0.374851 | 9481.72 | 48 |
| dispatch_gmm1_recv_core | communication | 384 | 124.62 | 0.370276 | 9332.04 | 24 |
| gmm2_combine_block_mmad_copy_out | compute | 780 | 120.2 | 0.357143 | 819.78 | 24 |

## Bubble Summary

| parent_phase | parent_union_us | child_covered_us | bubble_us | bubble_ratio | gap_count | max_gap_us |
| --- | --- | --- | --- | --- | --- | --- |
| gmm2_combine | 257.7 | 257.14 | 0.56 | 0.002173 | 2 | 0.52 |
| dispatch_gmm1 | 182.58 | 182.22 | 0.36 | 0.001972 | 2 | 0.32 |
| processing | 336.56 | 336.44 | 0.12 | 0.000357 | 2 | 0.08 |

## Top Raw Names

| name | phase | category | count | total_us | union_us | tid_nunique |
| --- | --- | --- | --- | --- | --- | --- |
| processing [extra:0] #0 | processing | container | 1152 | 286901.94 | 336.56 | 72 |
| gmm2-combine [extra:0] #0 | gmm2_combine | container | 1152 | 171281.94 | 257.7 | 72 |
| gmm2-combine aiv [extra:0] #0 | gmm2_combine_aiv | container | 768 | 157586.62 | 255.82 | 48 |
| dispatch-gmm1 [extra:0] #0 | dispatch_gmm1 | container | 1152 | 109838.04 | 182.58 | 72 |
| gmm2-combine block-epilogue [extra:0] #0 | gmm2_combine_block_epilogue | epilogue | 768 | 83435.5 | 245.5 | 48 |
| gmm2-combine combine [extra:0] #0 | gmm2_combine_combine | communication | 384 | 73891.34 | 252.36 | 24 |
| dispatch-gmm1 aiv [extra:0] #0 | dispatch_gmm1_aiv | container | 768 | 73636.24 | 182.06 | 48 |
| gmm2-combine combine-wait-status [extra:0] #0 | gmm2_combine_combine_wait_status | wait | 384 | 66034.24 | 235.4 | 24 |
| gmm2-combine block-epilogue shared-wait-combine [extra:0] #0 | gmm2_combine_shared_wait_combine | wait | 384 | 65808.34 | 240.94 | 24 |
| dispatch-gmm1 aic [extra:0] #0 | dispatch_gmm1_aic | container | 384 | 35630.36 | 173.84 | 24 |
| dispatch-gmm1 CompCoreFunc [extra:0] #0 | dispatch_gmm1_comp_core | compute | 768 | 26068.16 | 156.4 | 48 |
| dispatch-gmm1 SendCoreFunc [extra:0] #0 | dispatch_gmm1_send_core | communication | 384 | 23709.1 | 71.88 | 24 |
| dispatch-gmm1 dispatch-send [extra:0] #0 | dispatch_gmm1_dispatch_send | communication | 384 | 21962.64 | 69.06 | 24 |
| dispatch-gmm1 shared-process [extra:0] #0 | dispatch_gmm1_shared_process | communication | 384 | 13186.2 | 41.04 | 24 |
| dispatch-gmm1 moe-dispatch-send [extra:0] #1 | dispatch_gmm1_moe_dispatch_send | communication | 384 | 12265.46 | 54.82 | 24 |
| dispatch-gmm1 shared-dispatch-swiglu [extra:0] #0 | dispatch_gmm1_shared_dispatch_swiglu | quant | 768 | 11445.54 | 96.32 | 48 |
| gmm2-combine aic [extra:0] #0 | gmm2_combine_aic | container | 384 | 11347.34 | 163.24 | 24 |
| dispatch-gmm1 moe-dispatch-swiglu [extra:0] #0 | dispatch_gmm1_moe_dispatch_swiglu | quant | 768 | 9395.74 | 102 | 48 |
| dispatch-gmm1 RecvCoreFunc [extra:0] #0 | dispatch_gmm1_recv_core | communication | 384 | 9332.04 | 124.62 | 24 |
| dispatch-gmm1 sync-aiv [extra:0] #0 | dispatch_gmm1_sync_aiv | sync | 768 | 7715.62 | 79.86 | 48 |

## High Overlap Pairs

| phase_a | phase_b | overlap_us | overlap_ratio_a | overlap_ratio_b | union_us_a | union_us_b |
| --- | --- | --- | --- | --- | --- | --- |
| processing | gmm2_combine | 257.7 | 0.765688 | 1 | 336.56 | 257.7 |
| gmm2_combine | gmm2_combine_aiv | 255.82 | 0.992705 | 1 | 257.7 | 255.82 |
| processing | gmm2_combine_aiv | 255.82 | 0.760102 | 1 | 336.56 | 255.82 |
| gmm2_combine_aiv | gmm2_combine_combine | 252.36 | 0.986475 | 1 | 255.82 | 252.36 |
| gmm2_combine | gmm2_combine_combine | 252.36 | 0.979278 | 1 | 257.7 | 252.36 |
| processing | gmm2_combine_combine | 252.36 | 0.749822 | 1 | 336.56 | 252.36 |
| gmm2_combine_aiv | gmm2_combine_block_epilogue | 245.5 | 0.959659 | 1 | 255.82 | 245.5 |
| gmm2_combine | gmm2_combine_block_epilogue | 245.5 | 0.952658 | 1 | 257.7 | 245.5 |
| processing | gmm2_combine_block_epilogue | 245.5 | 0.729439 | 1 | 336.56 | 245.5 |
| gmm2_combine_block_epilogue | gmm2_combine_combine | 242.1 | 0.986151 | 0.959344 | 245.5 | 252.36 |
| gmm2_combine_shared_wait_combine | gmm2_combine_combine | 240.94 | 1 | 0.954747 | 240.94 | 252.36 |
| gmm2_combine_block_epilogue | gmm2_combine_shared_wait_combine | 240.94 | 0.981426 | 1 | 245.5 | 240.94 |
| gmm2_combine_aiv | gmm2_combine_shared_wait_combine | 240.94 | 0.941834 | 1 | 255.82 | 240.94 |
| gmm2_combine | gmm2_combine_shared_wait_combine | 240.94 | 0.934963 | 1 | 257.7 | 240.94 |
| processing | gmm2_combine_shared_wait_combine | 240.94 | 0.71589 | 1 | 336.56 | 240.94 |
| gmm2_combine_shared_wait_combine | gmm2_combine_combine_wait_status | 235.4 | 0.977007 | 1 | 240.94 | 235.4 |
| gmm2_combine_block_epilogue | gmm2_combine_combine_wait_status | 235.4 | 0.958859 | 1 | 245.5 | 235.4 |
| gmm2_combine_combine | gmm2_combine_combine_wait_status | 235.4 | 0.932794 | 1 | 252.36 | 235.4 |
| gmm2_combine_aiv | gmm2_combine_combine_wait_status | 235.4 | 0.920178 | 1 | 255.82 | 235.4 |
| gmm2_combine | gmm2_combine_combine_wait_status | 235.4 | 0.913465 | 1 | 257.7 | 235.4 |

## Low Overlap Pairs

| phase_a | phase_b | overlap_us | overlap_ratio_min | union_us_a | union_us_b |
| --- | --- | --- | --- | --- | --- |
| dispatch_gmm1_sync_aiv | gmm2_combine_block_epilogue_shared_calc | 14.84 | 0.186949 | 79.86 | 79.38 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue_shared_calc | 5.64 | 0.077836 | 72.46 | 79.38 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_send_calc | 5.64 | 0.077836 | 72.46 | 131.1 |
| gmm2_combine_block_mmad_copy_out | dispatch_gmm1_get_cum_sum | 6.96 | 0.096053 | 120.2 | 72.46 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_combine_wait_status | 7.1 | 0.097985 | 72.46 | 235.4 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue_calc | 7.12 | 0.098261 | 72.46 | 140.36 |
| gmm2_combine_sync_gmm2 | dispatch_gmm1_get_cum_sum | 8.1 | 0.111786 | 76.62 | 72.46 |
| gmm2_combine_block_mmad_waiting | dispatch_gmm1_get_cum_sum | 8.48 | 0.11703 | 117.04 | 72.46 |
| gmm2_combine_moe_gmm2 | dispatch_gmm1_get_cum_sum | 8.76 | 0.120894 | 110.04 | 72.46 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue_waiting | 9.08 | 0.125311 | 72.46 | 119.28 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_shared_wait_combine | 10.14 | 0.139939 | 72.46 | 240.94 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue_shared_waiting | 10.2 | 0.140767 | 72.46 | 73.12 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue_shared_group | 10.2 | 0.140767 | 72.46 | 97.46 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_combine_wait_send | 10.2 | 0.140767 | 72.46 | 107.12 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue_group | 10.2 | 0.140767 | 72.46 | 156.78 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_block_epilogue | 10.2 | 0.140767 | 72.46 | 245.5 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_combine | 10.2 | 0.140767 | 72.46 | 252.36 |
| dispatch_gmm1_get_cum_sum | gmm2_combine_aiv | 10.2 | 0.140767 | 72.46 | 255.82 |
| gmm2_combine_shared_gmm2 | dispatch_gmm1_get_cum_sum | 10.2 | 0.140767 | 85.98 | 72.46 |
| gmm2_combine_aic | dispatch_gmm1_get_cum_sum | 10.2 | 0.140767 | 163.24 | 72.46 |
