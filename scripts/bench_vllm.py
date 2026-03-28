#!/usr/bin/env python3
"""Benchmark vLLM throughput for conwai workloads.

Usage:
    python scripts/bench_vllm.py http://HOST:PORT/v1

Simulates 24 agents making 3 concurrent calls each (72 total) and measures
tokens/second, time-to-first-token, and per-request latency.
"""

import argparse
import asyncio
import statistics
import time

from openai import AsyncOpenAI

SYSTEM_PROMPT = (
    "You are an agent in a simulated economy. You forage for resources, "
    "craft bread, and trade with other agents. Respond with your next action."
)

USER_PROMPT = (
    "You have 3 flour and 2 water in your inventory. The market price for "
    "bread is 5 coins. Another agent offered to trade 2 flour for 1 water. "
    "There are 6 other agents in the world. What do you do next? Think step "
    "by step about your strategy, then decide on a single action."
)

# Roughly matches conwai workload: ~200 prompt tokens, ~200 completion tokens
MAX_TOKENS = 512


async def single_request(client: AsyncOpenAI, model: str, request_id: int) -> dict:
    """Make one chat completion and return timing stats."""
    start = time.perf_counter()
    first_token_time = None
    completion_tokens = 0
    prompt_tokens = 0

    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            max_tokens=MAX_TOKENS,
            temperature=0.7,
            stream=True,
            stream_options={"include_usage": True},
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        token_count = 0
        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    token_count += 1
                    if first_token_time is None:
                        first_token_time = time.perf_counter()
            if chunk.usage:
                prompt_tokens = chunk.usage.prompt_tokens
                completion_tokens = chunk.usage.completion_tokens
        if completion_tokens == 0:
            completion_tokens = token_count

        end = time.perf_counter()
        total = end - start
        ttft = (first_token_time - start) if first_token_time else total

        return {
            "request_id": request_id,
            "ok": True,
            "total_s": total,
            "ttft_s": ttft,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "tok_per_s": completion_tokens / total if total > 0 else 0,
        }
    except Exception as e:
        return {
            "request_id": request_id,
            "ok": False,
            "error": str(e),
            "total_s": time.perf_counter() - start,
        }


async def run_batch(
    client: AsyncOpenAI, model: str, concurrency: int, label: str
) -> list[dict]:
    """Fire `concurrency` requests simultaneously and collect results."""
    print(f"\n--- {label}: {concurrency} concurrent requests ---")
    tasks = [
        asyncio.create_task(single_request(client, model, i))
        for i in range(concurrency)
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


def print_stats(results: list[dict]) -> None:
    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    if failed:
        print(f"  FAILED: {len(failed)} requests")
        for f in failed[:3]:
            print(f"    #{f['request_id']}: {f.get('error', 'unknown')}")

    if not ok:
        print("  No successful requests.")
        return

    totals = [r["total_s"] for r in ok]
    ttfts = [r["ttft_s"] for r in ok]
    toks = [r["completion_tokens"] for r in ok]
    per_req_tps = [r["tok_per_s"] for r in ok]

    wall_time = max(totals)
    total_completion_tokens = sum(toks)
    total_prompt_tokens = sum(r["prompt_tokens"] for r in ok)
    aggregate_tps = total_completion_tokens / wall_time

    print(f"  Requests:     {len(ok)} ok, {len(failed)} failed")
    print(f"  Wall time:    {wall_time:.2f}s")
    print(f"  Prompt tok:   {total_prompt_tokens} total")
    print(f"  Compl. tok:   {total_completion_tokens} total")
    print(f"  Aggregate:    {aggregate_tps:.1f} tok/s (completion)")
    print(f"  Per-request:  {statistics.mean(per_req_tps):.1f} tok/s mean")
    print(
        f"  TTFT:         p50={statistics.median(ttfts):.3f}s  "
        f"p95={sorted(ttfts)[int(len(ttfts) * 0.95)]:.3f}s  "
        f"max={max(ttfts):.3f}s"
    )
    print(
        f"  Latency:      p50={statistics.median(totals):.2f}s  "
        f"p95={sorted(totals)[int(len(totals) * 0.95)]:.2f}s  "
        f"max={max(totals):.2f}s"
    )


async def main():
    parser = argparse.ArgumentParser(description="Benchmark vLLM for conwai")
    parser.add_argument("base_url", help="vLLM base URL (e.g. http://host:8000/v1)")
    parser.add_argument(
        "--model", default=None, help="Model name (auto-detected if omitted)"
    )
    parser.add_argument("--warmup", type=int, default=2, help="Warmup requests")
    args = parser.parse_args()

    client = AsyncOpenAI(base_url=args.base_url, api_key="none")

    # Auto-detect model
    model = args.model
    if not model:
        models = await client.models.list()
        model = models.data[0].id
        print(f"Detected model: {model}")

    # Warmup
    if args.warmup:
        print(f"Warming up with {args.warmup} requests...")
        await run_batch(client, model, args.warmup, "Warmup")

    # Benchmark at different concurrency levels matching conwai workload
    for concurrency, label in [
        (1, "Baseline (single request)"),
        (12, "4 agents × 3 calls"),
        (24, "8 agents × 3 calls"),
        (48, "16 agents × 3 calls"),
        (72, "24 agents × 3 calls"),
    ]:
        results = await run_batch(client, model, concurrency, label)
        print_stats(results)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
