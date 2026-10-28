"""第 1 课：注意力就是"加权平均"

三个最小工具：
  向量    —— 一串数字，表示一个词的特征（比如 2 个数字：生物性、动作性）
  点积    —— 两个向量逐位相乘再相加，越大说明越"像"（越相关）
  softmax —— 把一串数字变成"都为正、加起来等于 1"的权重

这一课先用最简版本：Q = K = V = 词的原始向量（不做任何变换）。
先搞懂"加权平均"这一步，下一课再讲为什么要做 Q/K/V 三个投影。
"""

import torch

torch.set_printoptions(precision=3, sci_mode=False)

# ============ 1. 四个词，每个词用 2 个数字表示 ============
#    第 0 个数字 = "生物性"，第 1 个数字 = "动作性"
words = ["猫", "狗", "石头", "跑"]
X = torch.tensor([
    [0.9, 0.10],   # 猫   —— 生物性强，动作性弱
    [0.8, 0.20],   # 狗   —— 生物性强，动作性弱
    [0.1, 0.05],   # 石头 —— 两个都弱
    [0.1, 0.90],   # 跑   —— 生物性弱，动作性强
])
print("每个词的向量:")
for w, v in zip(words, X):
    print(f"  {w}: {v.tolist()}")

# ============ 2. 相似度打分 ============
# 点积：Q @ K.T 得到 4x4 矩阵，第 i 行第 j 列 = "第 i 个词和第 j 个词有多像"

Q, K, V = X, X, X
scores = Q @ K.T
print("\n[步骤1] 相似度矩阵 scores（越大越像）:")
print(scores)

# ============ 3. 变成权重（softmax）============
# 对每一行做 softmax：这一行的 4 个数 → 4 个正数、加起来 = 1
weights = torch.softmax(scores, dim=-1)
print("\n[步骤2] 权重矩阵 weights（每行加起来 = 1）:")
print(weights)
print("检查每行之和:", weights.sum(dim=-1))

# ============ 4. 加权平均 V ============
# 每个词的新表示 = 所有词表示的加权平均（权重就是上面算出来的）
out = weights @ V
print("\n[步骤3] 每个词的新表示:")
for w, o in zip(words, out):
    print(f"  {w}: {o.tolist()}")

# ============ 5. 看清楚"猫"发生了什么 ============
i = 0  # "猫"
print(f"\n[拆解] 「{words[i]}」的新表示是怎么来的:")
for j, w in enumerate(words):
    contribution = weights[i, j] * V[j]
    print(f"  {weights[i, j]:.3f} × {words[j]}的向量 {V[j].tolist()} = {contribution.tolist()}")
print("  全部相加 =", out[i].tolist())
print(f"\n  原始「猫」= {X[i].tolist()}  →  新「猫」= {out[i].tolist()}")
print("  注意：新表示是 4 个词的混合，权重大的（猫、狗）影响更大 —— 这就是'注意力'")
