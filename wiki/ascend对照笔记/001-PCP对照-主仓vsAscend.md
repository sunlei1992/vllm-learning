# 001 PCP 对照：vLLM 主仓 vs vllm-ascend

> 对照结论：**vllm-ascend 重新实现了 PCP**（非复用主仓代码）。
> 算法思想同源（DualChunkSwap + all_gather 还原），但载体（V1 runner）和配套（投机解码/多模态/NPU 注意力）完全不同。
> 日期：2026-08-28 ｜ 基线：vllm v0.28.0 @ `../vllm-src/`、vllm-ascend v0.23.0 @ `../vllm-ascend-src/`

---

## 1. 一句话结论

> 主仓 PCP 只挂在 **Model Runner V2 (MRV2)** 上；ascend 的 NPUModelRunner 继承 **V1 runner**，
> 用不了主仓实现，于是在 V1 上自研了一套 **2387 行** 的 PCPManager +
> **5000+ 行** 的 CP 注意力栈（按 NPU 的 MLA/DSA/SFA 注意力各写一份）。

## 2. 为什么必须重写（架构根源，先理解这个）

```
vllm 主仓:  PCP → v1/worker/gpu/pcp_manager.py → 只被 MRV2 使用
            config/vllm.py:620:
            "PCP runtime support is implemented only by the V2 model runner"

vllm-ascend: NPUModelRunner(GPUModelRunner)
            model_runner_v1.py:268 + :97
            （继承 vllm.v1.worker.gpu_model_runner.GPUModelRunner = V1 系）
```

Ascend NPU 平台还在 V1 runner 上（未迁移 MRV2）→ V1 上没有主仓 PCP → 自研。
> 这也是"插件为什么可以差这么多"的典型案例：插件可以**替换/重写**主仓的任意层。

## 3. 同源部分（算法与抽象没变）

| 方面 | 主仓 | vllm-ascend | 同源点 |
|---|---|---|---|
| 切分算法 | DualChunkSwap（pcp_manager.py:195-208，2×PCP 块、rank 拿 r + 2P-1-r） | pcp_utils.py 注释自述 *"DualChunkSwap style... 2 * pcp_world_size chunks"* | 算法一致（都是为了因果负载均衡） |
| 进程组 | `get_pcp_group()`（vllm.distributed.parallel_state:1445） | 同样 import vllm 的 `get_pcp_group/get_dcp_group` | **复用主仓**，没自己建 |
| 执行模式 | 本地化 batch → all_gather KV → 注意力 → all_gather + `hidden_restore_idx` 还原 | all_gather KV → 注意力 → all_gather + `pcp_allgather_restore_idx` 还原 | 思路一致（索引还原是同一招） |

## 4. 区别对照表（精读重点）

| 维度 | vllm 主仓（MRV2） | vllm-ascend | 看代码 |
|---|---|---|---|
| PCPManager | 682 行 | **2387 行** | 主仓 `pcp_manager.py` vs ascend `worker/pcp_utils.py` |
| 载体 runner | MRV2（`v1/worker/gpu/model_runner.py`） | V1（`NPUModelRunner(GPUModelRunner)`） | `model_runner_v1.py:268` |
| 投机解码 | ❌ `NotImplementedError: MRV2 PCP does not support spec decode yet`（pcp_manager.py:323） | ✅ PCP+spec decode+MTP（`PCPSpecDecodeMTPInputs` 等） | ascend `pcp_utils.py:46-68` |
| 多模态 | 无专门处理 | ✅ `build_local_mm_schedule`(400) / `gather_mm_embeddings_for_pcp`(454) | ascend `pcp_utils.py` |
| 注意力侧 | 共用 ~100 行 `attention/pcp.py`（MLA latent gather） | 每种注意力重写：`attention_cp.py`(1073) + `mla_cp.py`(855) + `dsa_cp.py`(1671) + `sfa_cp.py`(1312) | ascend `attention/context_parallel/` |
| 还原索引 | `hidden_restore_idx` / `padded_gather_idx` | `pcp_allgather_restore_idx`（all_gather 后 `index_select`） | attention_cp.py:836-838 |
| 算子对齐 | 通用 CUDA | NPU FA 对齐 → `_build_fa_padding_restore_idx`(236) | ascend `pcp_utils.py` |
| 310P 特化 | — | `_310p/model_runner_310p.py`（hybrid attn 等） | ascend `_310p/` |

## 5. 注意力通信模式对照（深入线索）

主仓 MLA：`attention/pcp.py:26` —— 只对 **latent** 做 pcp all_gather（decode 本地 + prefill gather）。

ascend：`attention/context_parallel/attention_cp.py` 里 pcp/dcp 双 group 混合：
- `:578` `get_dcp_group().all_gather(query, 1)` —— query 沿**头维**走 dcp
- `:725-730` prefill query 按 pcp/dcp 分别 all_gather
- `:836-838` `all_kv = get_pcp_group().all_gather(...)` + `index_select(pcp_allgather_restore_idx)` —— KV 沿 token 维走 pcp

> 线索：ascend 的 CP 通信比主仓复杂在 **DCP×PCP 同时生效**的组合路径。

## 6. 彩蛋：DSA 的 CP 实现

`dsa_cp.py`（1671 行）实现了 **DSA（dual chunk attention，GLM-5.2 的稀疏注意力）的 context parallel**。
我们在 CPU 上遇到"稀疏注意力 NotImplemented"（`platforms/cpu.py:89`）——同一个特性在 ascend 的
NPU 生态是**完整实现**的。对照学习价值极高：同一个 vLLM 特性，CPU 砍掉、NPU 实现。

## 7. 代码对照阅读路线（建议顺序）

1. 先读主仓 `pcp_manager.py:195-310`（DualChunkSwap + 索引构建）—— 建立基准
2. 再读 ascend `pcp_utils.py:663+ update_tokens_for_pcp` 的 DualChunkSwap 实现 —— 看差异（padding、MM、spec decode 分支）
3. 对比两个还原索引：`hidden_restore_idx` vs `pcp_allgather_restore_idx`
4. 挑 `mla_cp.py` 的 `AscendMlaCPImpl(AscendMLAImpl)` 和主仓 MLA CPU 实现对照（我们刚学过 CPU 版）
5. git 考古：`git log --oneline -- vllm_ascend/worker/pcp_utils.py` 看它怎么跟进主仓

## 8. 疑问清单（待解决）

- [ ] ascend 为什么不迁移到 MRV2？（V1 有 PCP 自研成本，MRV2 迁移成本更高？还是 MRV2 的 PCP 不支持 Ascend 算子？）
- [ ] ascend 的 spec decode + PCP 怎么和 MTP 的 multiple tokens 对齐？（`PCPSpecDecodeMTPInputs` 的语义）
- [ ] DSA-CP 在 NPU 上用的什么通信/调度模式？（1671 行值得专篇精读）

## 9. 学习方法收获

1. **插件可以重写主仓任意层**：看到"主仓 PCP 是 V2-only"，就明白 ascend 为什么自研——版本架构差异是重写的第一原因
2. **算法 vs 实现的分离**：DualChunkSwap 思想通用，但 runner 载体、注意力后端、算子对齐都是平台相关的
3. **对照阅读的锚点**：先找主仓"基准实现"，再找插件的对应文件 diff——比单独读插件快得多
