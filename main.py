# Copyright (c) 2026 eele14. All Rights Reserved.
import argparse
import logging
import sys

from config import Config
from bot import SelfBot, _BOT_MODE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default=".env", help="Path to .env file (default: .env)")
    args = parser.parse_args()

    try:
        config = Config(args.env)
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
        print(f"Check your {args.env} file.")
        sys.exit(1)

    mode = "BOT" if _BOT_MODE else "SELFBOT"
    logging.getLogger(__name__).info(f"Starting in {mode} mode")

    bot = SelfBot(config)
    bot.run(config.discord_token)
