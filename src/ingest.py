import os
import json
import time
import logging
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
from typing import Any, Dict, Optional, List

import requests

base_dir = Path(__file__).resolve().parent.parent
env_path = base_dir / '.env'
load_dotenv(dotenv_path=env_path)

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"

ROLES = ["SDE", "Data Scientist", "ML Engineer", "Data Analyst"]
CITIES = ["Bangalore", "Hyderabad", "Pune", "Delhi"]

# ---------------------------------------------------------------------------
# Logging setup — logs to both console and a daily log file so you can debug
# gaps (e.g. "why did Pune return 0 results yesterday?") without re-running.
# ---------------------------------------------------------------------------
log_dir = base_dir / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_filename = log_dir / f"ingest_{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("ingest")


def build_request_params(
    *,
    app_id: str,
    app_key: str,
    what: Optional[str] = None,
    where: Optional[str] = None,
    results_per_page: int = 20,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": results_per_page,
    }
    if what:
        params["what"] = what
    if where:
        params["where"] = where
    return params


def fetch_jobs(
    *,
    app_id: Optional[str] = None,
    app_key: Optional[str] = None,
    what: Optional[str] = None,
    where: Optional[str] = None,
    country: str = "in",
    results_per_page: int = 20,
    page: int = 1,
) -> Dict[str, Any]:

    app_id = app_id or os.environ.get("ADZUNA_APP_ID")
    app_key = app_key or os.environ.get("ADZUNA_APP_KEY")

    if not app_id or not app_key:
        raise ValueError("Set ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables first.")

    params = build_request_params(
        app_id=app_id,
        app_key=app_key,
        what=what,
        where=where,
        results_per_page=results_per_page,
    )

    url = f"{ADZUNA_BASE_URL}/{country}/search/{page}"
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all_combinations(
    roles: List[str] = ROLES,
    cities: List[str] = CITIES,
    pages_per_query: int = 3,
    results_per_page: int = 20,
    sleep_seconds: float = 1.0,
) -> List[Dict[str, Any]]:
    """Loop over every (role, city) combination and pull up to `pages_per_query`
    pages for each. Logs a per-combo summary and continues past individual
    failures instead of aborting the whole run.
    """
    all_results: List[Dict[str, Any]] = []
    summary = {"combos_run": 0, "combos_failed": 0, "combos_empty": 0, "total_jobs": 0}

    total_combos = len(roles) * len(cities)
    combo_num = 0

    for role in roles:
        for city in cities:
            combo_num += 1
            combo_label = f"[{combo_num}/{total_combos}] what='{role}' where='{city}'"
            combo_job_count = 0

            for page_num in range(1, pages_per_query + 1):
                try:
                    data = fetch_jobs(
                        what=role,
                        where=city,
                        country="in",
                        results_per_page=results_per_page,
                        page=page_num,
                    )
                except requests.exceptions.HTTPError as e:
                    logger.error(f"{combo_label} page={page_num} -> HTTP error: {e}")
                    summary["combos_failed"] += 1
                    break
                except requests.exceptions.RequestException as e:
                    logger.error(f"{combo_label} page={page_num} -> request failed: {e}")
                    summary["combos_failed"] += 1
                    break

                results = data.get("results", [])
                if not results:
                    logger.info(f"{combo_label} page={page_num} -> no more results, stopping pagination")
                    break

                for r in results:
                    r["_query_role"] = role
                    r["_query_city"] = city

                all_results.extend(results)
                combo_job_count += len(results)
                time.sleep(sleep_seconds)  # respect rate limit (1 call/sec on free tier)

            if combo_job_count == 0:
                logger.warning(f"{combo_label} -> 0 total jobs collected")
                summary["combos_empty"] += 1
            else:
                logger.info(f"{combo_label} -> {combo_job_count} jobs collected")

            summary["combos_run"] += 1
            summary["total_jobs"] += combo_job_count

    logger.info(
        f"RUN SUMMARY: {summary['combos_run']} combos run, "
        f"{summary['combos_empty']} returned 0 results, "
        f"{summary['combos_failed']} failed outright, "
        f"{summary['total_jobs']} total jobs collected"
    )
    return all_results


def save_data_to_file(data: Dict[str, Any], prefix: str = "jobs") -> Path:
    output_dir = base_dir / "data" / "raw"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.json"
    output_path = output_dir / filename

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4, ensure_ascii=False)

    logger.info(f"Raw API response stored successfully at: {output_path}")
    return output_path


if __name__ == "__main__":
    logger.info("Starting daily ingestion run")
    all_results = fetch_all_combinations()
    save_data_to_file({"results": all_results}, prefix="daily_pull")
    logger.info("Ingestion run complete")