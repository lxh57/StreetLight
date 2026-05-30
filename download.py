import argparse
import json

import requests
# python download.py --limit 2650 --offset 0 --output streetlights_new2000.json --timeout 180

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download streetlights JSON from API")
    parser.add_argument(
        "--url",
        default="https://nervous-commotion-countdown.ngrok-free.dev/api/streetlights",
        help="API endpoint",
    )
    parser.add_argument("--limit", type=int, default=1000, help="Number of records to fetch")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--sequence-id", default=None, help="Filter by sequence id")
    parser.add_argument("--output", default="streetlights.json", help="Output JSON file")
    parser.add_argument("--timeout", type=int, default=60, help="Request timeout (seconds)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = {
        "limit": args.limit,
        "offset": args.offset,
        "sequence_id": args.sequence_id,
    }
    params = {key: value for key, value in params.items() if value is not None}

    response = requests.get(args.url, params=params, timeout=args.timeout)
    response.raise_for_status()
    data = response.json()

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print("Da luu JSON!")
    print(f"File: {args.output}")


if __name__ == "__main__":
    main()