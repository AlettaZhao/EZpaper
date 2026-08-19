from env import load_env_file
import os
import sys


def has_value(key: str) -> bool:
    value = os.environ.get(key, "").strip()
    return bool(value) and "你的" not in value and "xxxx" not in value.lower()


def main() -> None:
    load_env_file()

    checks = [
        ("FEISHU_APP_ID", "optional", "Feishu app ID; required when FEISHU_OPEN_IDS is set"),
        ("FEISHU_APP_SECRET", "optional", "Feishu app secret; required when FEISHU_OPEN_IDS is set"),
        ("FEISHU_OPEN_IDS", "optional", "Comma-separated Feishu open_id list"),
        ("FEISHU_WEBHOOKS", "optional", "Comma-separated Feishu group webhook URLs"),
        ("FEISHU_WEBHOOK_SECRET", "optional", "Webhook signing secret if the bot enables signature verification"),
    ]

    missing_required = []
    for key, level, note in checks:
        status = "OK" if has_value(key) else "MISSING"
        print(f"{key}: {status} ({level}) - {note}")

    app_targets_ok = has_value("FEISHU_OPEN_IDS")
    app_creds_missing = [
        key for key in ["FEISHU_APP_ID", "FEISHU_APP_SECRET"]
        if not has_value(key)
    ]
    app_channel_ok = app_targets_ok and not app_creds_missing
    webhooks_ok = has_value("FEISHU_WEBHOOKS")

    if app_targets_ok and app_creds_missing:
        print("Feishu app channel is incomplete and will fail: " + ", ".join(app_creds_missing))
        missing_required.extend(app_creds_missing)

    if not app_channel_ok and not webhooks_ok:
        if not app_targets_ok:
            missing_required.append("FEISHU_OPEN_IDS or FEISHU_WEBHOOKS")
        print("Missing complete Feishu delivery channel: set FEISHU_OPEN_IDS with app credentials, or FEISHU_WEBHOOKS")

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
