"""补充课：weights @ V 到底在做什么

目标：证明 weights @ V 就是"每个词、每个维度，各做一次加权平均"。
方法：先用最笨的手写循环算一遍，再用矩阵乘法算一遍，比对结果是否完全相同。
"""

import torch

torch.set_printoptions(precision=3, sci_mode=False)

words = ["猫", "狗", "石头", "跑"]
V = torch.tensor([
    [0.9, 0.10],   # 猫
    [0.8, 0.20],   # 狗
    [0.1, 0.05],   # 石头
    [0.1, 0.90],   # 跑
])

# 上一课算出来的权重（"猫"那一行：猫对各个词的注意力）
w_cat = torch.tensor([0.341, 0.315, 0.165, 0.180])

print("=" * 60)
print("【笨办法】手写循环：对每个维度，做一次加权平均")
print("=" * 60)

new_cat_manual = []
for dim in range(2):                       # 维度 0 = 生物性, 维度 1 = 动作性
    dim_name = "生物性" if dim == 0 else "动作性"
    total = 0.0
    print(f"\n--- 第 {dim} 个数字（{dim_name}）---")
    for j, w in enumerate(words):
        contrib = w_cat[j].item() * V[j, dim].item()
        total += contrib
        print(f"  {w_cat[j]:.3f} × {w}的{dim_name}{V[j, dim]:.2f} = {contrib:.4f}")
    print(f"  ── 相加 = {total:.4f}  ← 这就是新猫的第 {dim} 个数字")
    new_cat_manual.append(total)

print("\n手写循环得到的「新猫」:", [round(x, 4) for x in new_cat_manual])

print("\n" + "=" * 60)
print("【矩阵写法】weights @ V")
print("=" * 60)
new_cat_matmul = w_cat @ V
print("w_cat @ V =", new_cat_matmul)

print("\n" + "=" * 60)
print("【结论】两者是否相同？")
print("=" * 60)
same = torch.allclose(torch.tensor(new_cat_manual), new_cat_matmul, atol=1e-6)
print("手写循环结果 :", [round(x, 4) for x in new_cat_manual])
print("矩阵乘法结果 :", [round(x, 4) for x in new_cat_matmul.tolist()])
print("完全相同吗？ :", same)
print("\n→ 是的。weights @ V 就是把这些小加法一次性全部算完，没有任何新魔法。")

# ============ 一次算完所有词 ============
print("\n" + "=" * 60)
print("【扩展】所有词一起算（weights 是 4×4，每行一个词）")
print("=" * 60)
X = V
weights_all = torch.softmax(X @ X.T, dim=-1)
out_all = weights_all @ V
for i, w in enumerate(words):
    print(f"  {w}: 原始 {V[i].tolist()} → 新 {[round(x,3) for x in out_all[i].tolist()]}")
print("\n每一行都是同样的操作：拿这一行的 4 个权重，去混合 V 的 4 行。")
