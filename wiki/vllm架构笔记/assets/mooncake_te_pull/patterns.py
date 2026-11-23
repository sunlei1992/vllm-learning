def make_pattern(seed: int, block: int, size: int) -> bytes:
    cycle = bytes(((j * (31 + seed) + block * (17 + seed) + seed) & 0xFF) for j in range(256))
    return (cycle * (size // 256 + 1))[:size]
