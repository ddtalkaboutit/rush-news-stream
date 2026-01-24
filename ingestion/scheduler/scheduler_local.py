#scheduler_local.py
import time
from datetime import datetime
from ingestion.shared.config import (
    X_INTERVAL_MINUTES,
    NEWS_INTERVAL_MINUTES,
    CHROME_NEWS_INTERVAL_MINUTES,
)
from ingestion.pipelines.x_pipeline import run_x_pipeline
from ingestion.pipelines.rss_pipeline import run_rss_pipeline
from ingestion.pipelines.html_pipeline import run_html_pipeline
from ingestion.pipelines.chrome_news_pipeline import run_chrome_news_pipeline


def main():
    last_x = 0
    last_news = 0
    last_chrome_news = 0

    while True:
        now = time.time()

        if now - last_x >= X_INTERVAL_MINUTES * 60:
            print(f"\n=== X pipeline run @ {datetime.utcnow().isoformat()} ===")
            run_x_pipeline()
            last_x = now

        if now - last_news >= NEWS_INTERVAL_MINUTES * 60:
            print(f"\n=== RSS + HTML news pipelines run @ {datetime.utcnow().isoformat()} ===")
            run_rss_pipeline()
            run_html_pipeline()
            last_news = now

        if now - last_chrome_news >= CHROME_NEWS_INTERVAL_MINUTES * 60:
            print(f"\n=== Chrome news pipeline run @ {datetime.utcnow().isoformat()} ===")
            run_chrome_news_pipeline()
            last_chrome_news = now

        time.sleep(10)


if __name__ == "__main__":
    main()
