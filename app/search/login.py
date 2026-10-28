import logging

from ..config import config
from .instagram import Instagram


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not (config.ig_username and config.ig_password):
        raise SystemExit("В .env нужны IG_USERNAME и IG_PASSWORD")
    ig = Instagram(config.ig_settings, config.ig_username, config.ig_password, proxy=config.ig_proxy, interactive=True)
    cl = ig.connect()
    print(f"\nВход выполнен: {cl.username}. Сессия сохранена в {config.ig_settings}")


if __name__ == "__main__":
    main()