import argparse
from pathlib import Path

from src.model_client import ModelClient


ROOT = Path(__file__).resolve().parent
AGENT_FILE = ROOT / "AGENT.md"


def is_bullet_only(text: str) -> bool:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]
    return bool(lines) and all(line.startswith("- ") for line in lines)


def print_stats(client: ModelClient, history) -> None:
    stats = client.stats(history)

    print("\n--- Statistics ---")
    print(f"Turn count: {stats['turn_count']}")
    print(
        "Cumulative input tokens: "
        f"{stats['cumulative_input_tokens']}"
    )
    print(
        "Cumulative output tokens: "
        f"{stats['cumulative_output_tokens']}"
    )
    print(
        "Cumulative total tokens: "
        f"{stats['cumulative_total_tokens']}"
    )
    print(
        "Serialized conversation-history length: "
        f"{stats['serialized_history_length']} characters"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    system_prompt = AGENT_FILE.read_text(encoding="utf-8").strip()

    client = ModelClient(
        model=args.model,
        temperature=args.temperature,
    )

    history = [
        {
            "role": "system",
            "content": system_prompt,
        }
    ]

    print("Code-review client ready.")
    print("Enter code or a review request.")
    print("Commands: /stats, /exit")

    try:
        while True:
            user_input = input("\nYou: ").strip()

            if user_input.lower() in {"/exit", "/quit"}:
                break

            if user_input.lower() == "/stats":
                print_stats(client, history)
                continue

            if not user_input:
                continue

            history.append({
                "role": "user",
                "content": user_input,
            })

            try:
                result = client.complete(history)
            except Exception as error:
                history.pop()
                print(f"Model error: {error}")
                continue

            history.append({
                "role": "assistant",
                "content": result.content,
            })

            print(f"\nAssistant:\n{result.content}")
            print(
                "\nTurn tokens: "
                f"input={result.input_tokens}, "
                f"output={result.output_tokens}, "
                f"total={result.total_tokens}"
            )
            print(
                "Bullet-only format check: "
                f"{'PASS' if is_bullet_only(result.content) else 'FAIL'}"
            )

    except (EOFError, KeyboardInterrupt):
        print()

    finally:
        stats = client.stats(history)
        print("\n--- Exit totals ---")
        print(f"Turn count: {stats['turn_count']}")
        print(
            "Cumulative input tokens: "
            f"{stats['cumulative_input_tokens']}"
        )
        print(
            "Cumulative output tokens: "
            f"{stats['cumulative_output_tokens']}"
        )
        print(
            "Cumulative total tokens: "
            f"{stats['cumulative_total_tokens']}"
        )


if __name__ == "__main__":
    main()