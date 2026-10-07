#!/usr/bin/env python3
"""Download simplified ASEAN ADM0 boundaries from the official geoBoundaries API.

The files are source candidates only. They are not automatically approved for a
production country profile. The script mirrors each file into the repository boundary
archive and the package registry boundary directory so the current release layout stays
usable while it is being consolidated.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = "https://www.geoboundaries.org/api/current/gbOpen"
DESTINATIONS = (
    PROJECT_ROOT / "release" / "boundaries",
    PROJECT_ROOT / "src" / "geosquare_v2" / "data" / "registry" / "boundaries",
)

# Full boundaries are used for profile review. Simplified files remain useful for quick
# planning and are kept separately.

ASEAN_COUNTRIES: tuple[tuple[str, str, str], ...] = (
    ("BN", "BRN", "Brunei Darussalam"),
    ("KH", "KHM", "Cambodia"),
    ("ID", "IDN", "Indonesia"),
    ("LA", "LAO", "Lao PDR"),
    ("MY", "MYS", "Malaysia"),
    ("MM", "MMR", "Myanmar"),
    ("PH", "PHL", "Philippines"),
    ("SG", "SGP", "Singapore"),
    ("TH", "THA", "Thailand"),
    ("TL", "TLS", "Timor-Leste"),
    ("VN", "VNM", "Viet Nam"),
)

FULL_PROFILE_CODES = frozenset({code for code, _, _ in ASEAN_COUNTRIES})


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "geosquare-grid-v2-boundary-fetch/1.0"})
    with urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object from {url}")
    return payload


def fetch_bytes(url: str) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {"github.com", "raw.githubusercontent.com"}:
        raise ValueError(f"refusing download from unexpected host: {url}")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-L",
                    "--fail",
                    "--retry",
                    "5",
                    "--retry-all-errors",
                    "--silent",
                    "--show-error",
                    url,
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
            content = result.stdout
            json.loads(content.decode("utf-8"))
            return content
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as exc:
            last_error = exc
            if attempt == 2:
                break
    raise RuntimeError(f"failed to download {url} after retries") from last_error


def main() -> None:
    for destination in DESTINATIONS:
        destination.mkdir(parents=True, exist_ok=True)

    metadata: list[dict[str, str]] = []
    for domain_code, iso3, name in ASEAN_COUNTRIES:
        api_url = f"{API_ROOT}/{iso3}/ADM0/"
        record = fetch_json(api_url)
        simplified_url = record.get("simplifiedGeometryGeoJSON")
        if not isinstance(simplified_url, str) or not simplified_url:
            raise ValueError(f"geoBoundaries did not return a simplified GeoJSON URL for {iso3}")
        simplified_content = fetch_bytes(simplified_url)
        document = json.loads(simplified_content.decode("utf-8"))
        if not isinstance(document, dict) or document.get("type") not in {
            "Feature",
            "FeatureCollection",
            "Polygon",
            "MultiPolygon",
        }:
            raise ValueError(f"downloaded boundary for {iso3} is not polygonal GeoJSON")

        simplified_filename = f"{domain_code}_simplified.geojson"
        for destination in DESTINATIONS:
            (destination / simplified_filename).write_bytes(simplified_content)

        full_filename = None
        full_sha256 = None
        full_url = record.get("gjDownloadURL")
        if domain_code in FULL_PROFILE_CODES:
            if not isinstance(full_url, str) or not full_url:
                raise ValueError(f"geoBoundaries did not return a full GeoJSON URL for {iso3}")
            full_content = fetch_bytes(full_url)
            full_document = json.loads(full_content.decode("utf-8"))
            if not isinstance(full_document, dict) or full_document.get("type") not in {
                "Feature",
                "FeatureCollection",
                "Polygon",
                "MultiPolygon",
            }:
                raise ValueError(f"downloaded full boundary for {iso3} is not polygonal GeoJSON")
            full_filename = f"{domain_code}_full.geojson"
            for destination in DESTINATIONS:
                (destination / full_filename).write_bytes(full_content)
            full_sha256 = hashlib.sha256(full_content).hexdigest()

        metadata.append(
            {
                "domain_code": domain_code,
                "iso3": iso3,
                "name": name,
                "api_url": api_url,
                "simplified_url": simplified_url,
                "simplified_file": simplified_filename,
                "simplified_sha256": hashlib.sha256(simplified_content).hexdigest(),
                "full_url": str(full_url) if full_url else "",
                "full_file": full_filename or "",
                "full_sha256": full_sha256 or "",
                "boundary_id": str(record.get("boundaryID", "")),
                "boundary_year": str(record.get("boundaryYearRepresented", "")),
                "boundary_source": str(record.get("boundarySource", "")),
                "boundary_license": str(record.get("boundaryLicense", "")),
                "license_source": str(record.get("licenseSource", "")),
                "build_date": str(record.get("buildDate", "")),
            }
        )
        print(f"Downloaded {domain_code} ({iso3}) -> {simplified_filename}")
        if full_filename:
            print(f"Downloaded {domain_code} ({iso3}) -> {full_filename}")

    for destination in DESTINATIONS:
        metadata_path = destination / "ASEAN_BOUNDARY_METADATA.json"
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote metadata: {metadata_path}")


if __name__ == "__main__":
    main()
