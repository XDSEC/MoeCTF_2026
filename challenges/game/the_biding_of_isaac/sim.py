import random
import math
from collections import defaultdict

# 策略: 输入上一轮平均值 prev(首轮为 None)，输出 (0,100) 的数
# 简单起见每个策略实例可带随机种子/参数

def strategy_fixed(value):
    def f(prev, rng):
        return value
    return f

def strategy_follow_two_thirds(initial=50.0):
    def f(prev, rng):
        if prev is None:
            return initial
        return max(0.001, min(99.999, 2.0/3.0 * prev))
    return f

def strategy_best_response_to_prev(n, initial=50.0):
    # 假设其他人上一轮的平均值等于 prev，推导对当前均值的“有限人数最优回应”
    # z = 2(n-1)/(3n-2) * prev
    coef = 2.0 * (n - 1) / (3.0 * n - 2.0)
    def f(prev, rng):
        if prev is None:
            return initial
        return max(0.001, min(99.999, coef * prev))
    return f

def strategy_random_uniform():
    def f(prev, rng):
        return rng.uniform(0.001, 99.999)
    return f

def strategy_noisy_target(initial=50.0, noise=5.0):
    def f(prev, rng):
        target = initial if prev is None else 2.0/3.0 * prev
        return max(0.001, min(99.999, target + rng.gauss(0, noise)))
    return f

def strategy_high_anchor(value=95.0):
    def f(prev, rng):
        return value
    return f

def strategy_low_anchor(value=1.0):
    def f(prev, rng):
        return value
    return f

def strategy_cooperate(value=3.0):
    def f(prev, rng):
        return value
    return f

# 简单自适应：如果上一轮自己得分高就靠近上一轮目标，否则向均值靠拢? 这里只做占位
def strategy_prev_avg():
    def f(prev, rng):
        if prev is None:
            return 50.0
        return max(0.001, min(99.999, prev))
    return f

STRATEGIES = {
    "fixed50": [strategy_fixed(50.0) for _ in range(3)],
    "fixed33": [strategy_fixed(33.333) for _ in range(3)],
    "follow23": [strategy_follow_two_thirds() for _ in range(3)],
    "bestResp": [strategy_best_response_to_prev(12) for _ in range(3)],  # n=总bot数, 占位后面替换
    "random": [strategy_random_uniform() for _ in range(3)],
    "noisyTarget": [strategy_noisy_target() for _ in range(3)],
    "high95": [strategy_high_anchor(95.0) for _ in range(3)],
    "low1": [strategy_low_anchor(1.0) for _ in range(3)],
    "coop3": [strategy_cooperate(3.0) for _ in range(3)],
    "prevAvg": [strategy_prev_avg() for _ in range(3)],
}

def run_tournament(bot_strategies, rounds=30, seed=1, verbose=True):
    rng = random.Random(seed)
    # bot_strategies: list of (label, function)
    labels = [label for label, _ in bot_strategies]
    totals = {label: 0.0 for label in labels}
    prev = None
    history = []
    for r in range(1, rounds+1):
        outputs = []
        for label, f in bot_strategies:
            # each bot may have separate rng? We'll pass same rng sequentially; okay for stateless
            x = f(prev, rng)
            x = max(0.001, min(99.999, x))
            outputs.append(x)
        avg = sum(outputs) / len(outputs)
        target = 2.0/3.0 * avg
        round_scores = []
        for label, x in zip(labels, outputs):
            c = math.exp(-abs(x - target))
            score = c * avg
            round_scores.append(score)
            totals[label] += score
        history.append((r, avg, target, outputs, round_scores))
        if verbose:
            top = sorted(zip(labels, round_scores), key=lambda t: -t[1])[:5]
            topstr = ", ".join(f"{lb}:{sc:.3f}" for lb, sc in top)
            print(f"Round {r:2d} avg={avg:7.3f} target={target:7.3f} top: {topstr}")
        prev = avg
    return totals, history

def summarize(totals):
    print("\n===== 总排名 =====")
    for label, total in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"{label:12s} {total:10.3f}")

def scenario(name, bot_strategies, rounds=30, seed=1):
    print("\n" + "="*70)
    print("场景:", name)
    print("="*70)
    totals, hist = run_tournament(bot_strategies, rounds=rounds, seed=seed, verbose=True)
    summarize(totals)
    return totals, hist

if __name__ == "__main__":
    # 场景1: 全是一样的“跟随2/3上轮”
    bots1 = [("follow23_%d"%i, strategy_follow_two_thirds()) for i in range(12)]
    scenario("全部跟随2/3上轮", bots1, rounds=20)

    # 场景2: 混合基础策略, 每类3个
    bots2 = []
    for label, makers in [
        ("fixed50", [strategy_fixed(50.0)]),
        ("fixed33", [strategy_fixed(33.333)]),
        ("follow23", [strategy_follow_two_thirds()]),
        ("bestResp", [strategy_best_response_to_prev(30)]),
        ("random", [strategy_random_uniform()]),
        ("noisyTarget", [strategy_noisy_target()]),
        ("high95", [strategy_high_anchor(95.0)]),
        ("low1", [strategy_low_anchor(1.0)]),
        ("coop3", [strategy_cooperate(3.0)]),
        ("prevAvg", [strategy_prev_avg()]),
    ]:
        for i in range(3):
            bots2.append((f"{label}_{i}", makers[0]))
    scenario("10种基础策略各3个", bots2, rounds=40)
