from env import load_env_file
import os
import sys


def has_value(key: str) -> bool:
    value = os.environ.get(key, "").strip()
    return bool(value) and "你的" not in value and "xxxx" not in value.lower()


def main() -> None:
    load_env_file()

    checks = [
        ("FEISHU_APP_ID", "required", "Feishu app ID from the self-built app"),
        ("FEISHU_APP_SECRET", "required", "Feishu app secret from the same self-built app"),
        ("FEISHU_OPEN_IDS", "required", "Comma-separated Feishu open_id list"),
    ]

    missing_required = []
    for key, level, note in checks:
        status = "OK" if has_value(key) else "MISSING"
        print(f"{key}: {status} ({level}) - {note}")
        if level == "required" and status != "OK":
            missing_required.append(key)

    model_ok = has_value("OPENAI_API_KEY") or has_value("ANTHROPIC_API_KEY")
    model_status = "OK" if model_ok else "MISSING"
    print(f"MODEL_API_KEY: {model_status} (required) - Set OPENAI_API_KEY or ANTHROPIC_API_KEY")
    if not model_ok:
        missing_required.append("OPENAI_API_KEY or ANTHROPIC_API_KEY")

    if missing_required:
        print("Missing required config: " + ", ".join(missing_required))
        sys.exit(1)


if __name__ == "__main__":
    main()
