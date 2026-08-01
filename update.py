"""
update.py

Fetches live GitHub statistics for a user via the GitHub GraphQL API and
writes them into the placeholder tokens inside dark.svg / light.svg.

Required environment variables (set as GitHub Actions secrets, or export
locally before running):
    ACCESS_TOKEN - a GitHub Personal Access Token
                   (Contents: Read and write, Metadata: Read only)
    USER_NAME    - the GitHub username to fetch stats for

Run locally:
    export ACCESS_TOKEN=ghp_xxxxxxxxxxxx
    export USER_NAME=your-username
    python update.py

Note on commit counts: we do NOT display a single lifetime commit number.
GitHub's contributionsCollection only covers 1 year per query, so a lifetime
total requires summing across years - which is exactly the kind of derived
number that's easy to get subtly wrong (double-counting restricted/private
contribution types, year-boundary edge cases, etc). Instead, ACTIVITY_GRID
renders the actual last-52-weeks contribution calendar as a heatmap, the
same underlying per-day counts GitHub's own graph uses, so there's no
computed total to be wrong.
"""

import os
import re
import sys
from datetime import datetime, timezone
import requests

GITHUB_API = "https://api.github.com/graphql"

# Templates keep every {{PLACEHOLDER}} token intact so this script can be run
# repeatedly (each run reads the template fresh and writes a resolved copy).
# Fill in your personal info (NAME, ROLE, BIO, TYPE_1..TYPE_6, EMAIL,
# PORTFOLIO) directly inside the *.template.svg files once - only the
# GitHub-stat placeholders below get replaced automatically on every run.
TEMPLATE_TO_OUTPUT = {
    "templates/dark.template.svg": "dark.svg",
    "templates/light.template.svg": "light.svg",
}

# Placeholders that will be substituted inside the SVG files.
# Add or remove entries here to match what you display in your template.
# (STARS/FOLLOWERS are still computed and available below even though the
# default template no longer displays them - add {{STARS}} / {{FOLLOWERS}}
# back into your template if you want them.)
PLACEHOLDERS = [
    "USERNAME",
    "REPOS",
    "STARS",
    "FOLLOWERS",
    "LOC",
    "STREAK",
    "ACTIVITY_GRID",
]


def gql(token: str, query: str, variables: dict) -> dict:
    headers = {"Authorization": f"bearer {token}"}
    resp = requests.post(
        GITHUB_API,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]


def get_profile_summary(token: str, username: str) -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        login
        createdAt
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes {
            stargazerCount
          }
        }
      }
    }
    """
    data = gql(token, query, {"login": username})
    return data["user"]


def fetch_contribution_weeks(token: str, username: str) -> list:
    """
    Returns the last ~52 weeks of the contribution calendar as GitHub groups
    it: a list of weeks, each with 7 contributionDays (Sun-Sat), in
    chronological order. Used to derive both STREAK and ACTIVITY_GRID from a
    single API call instead of querying twice.
    """
    now = datetime.now(timezone.utc)
    try:
        one_year_ago = now.replace(year=now.year - 1)
    except ValueError:
        one_year_ago = now.replace(year=now.year - 1, day=28)

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """
    variables = {
        "login": username,
        "from": one_year_ago.isoformat(),
        "to": now.isoformat(),
    }
    data = gql(token, query, variables)
    return data["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]


def current_streak(weeks: list) -> int:
    """
    Counts consecutive days (ending today) with at least one contribution.
    Today is allowed to have zero contributions without breaking the streak,
    since the day isn't over yet.
    """
    days = sorted(
        (d for week in weeks for d in week["contributionDays"]),
        key=lambda d: d["date"],
    )
    today_str = datetime.now(timezone.utc).date().isoformat()

    streak = 0
    for day in reversed(days):
        if day["date"] == today_str and day["contributionCount"] == 0:
            continue
        if day["contributionCount"] > 0:
            streak += 1
        else:
            break

    return streak


# Fixed contribution-count -> color thresholds, in ascending order of upper
# bound (inclusive). The heatmap sits directly under the STREAK row, so the
# palette is a warm-to-flame gradient rather than GitHub's green.
_HEATMAP_LEVELS = [
    (0, "#e2d9c3"),
    (2, "#FFC98B"),
    (5, "#FF9F4A"),
    (9, "#EE8130"),
]
_HEATMAP_MAX_COLOR = "#C1121F"


def _heatmap_color(count: int) -> str:
    for upper, color in _HEATMAP_LEVELS:
        if count <= upper:
            return color
    return _HEATMAP_MAX_COLOR


def build_activity_heatmap(weeks: list, x: int = 436, y: int = 442, cell: int = 6, gap: int = 1) -> str:
    """
    Renders the last 52 weeks of contributionDays as a grid of <rect> cells
    (columns = weeks, rows = day-of-week), positioned to match the fixed
    ACTIVITY block coordinates in templates/*.template.svg.
    """
    pitch = cell + gap
    rects = []
    for col, week in enumerate(weeks[-52:]):
        for row, day in enumerate(week["contributionDays"]):
            cx = x + col * pitch
            cy = y + row * pitch
            fill = _heatmap_color(day["contributionCount"])
            rects.append(
                f'<rect x="{cx}" y="{cy}" width="{cell}" height="{cell}" rx="1" '
                f'fill="{fill}" stroke="#1a1a1a" stroke-width="0.4"/>'
            )
    return "".join(rects)


def estimate_loc(token: str, username: str) -> str:
    """
    GitHub's API doesn't expose a direct 'lines of code' metric.
    This is a lightweight estimate based on total repo size via the REST
    search API. For a more precise number, consider swapping in a
    dedicated LOC-counting action (e.g. github-readme-stats' LOC add-on,
    or a tool like `cloc` run against clones of your repos in the workflow).
    """
    headers = {"Authorization": f"token {token}"}
    resp = requests.get(
        f"https://api.github.com/search/repositories?q=user:{username}",
        headers=headers,
        timeout=30,
    )
    if resp.status_code != 200:
        return "N/A"
    total_size_kb = sum(repo.get("size", 0) for repo in resp.json().get("items", []))
    # 'size' from the API is in KB of the repo (not exact LOC), used here as a rough proxy.
    estimated_loc = total_size_kb * 20  # rough heuristic multiplier
    return f"{estimated_loc:,}+"


def build_stats(token: str, username: str) -> dict:
    profile = get_profile_summary(token, username)
    repos = profile["repositories"]
    total_stars = sum(node["stargazerCount"] for node in repos["nodes"])
    weeks = fetch_contribution_weeks(token, username)

    return {
        "USERNAME": profile["login"],
        "REPOS": str(repos["totalCount"]),
        "STARS": str(total_stars),
        "FOLLOWERS": str(profile["followers"]["totalCount"]),
        "LOC": estimate_loc(token, username),
        "STREAK": str(current_streak(weeks)),
        "ACTIVITY_GRID": build_activity_heatmap(weeks),
    }


def apply_placeholders(svg_text: str, stats: dict) -> str:
    for key in PLACEHOLDERS:
        token = "{{" + key + "}}"
        if key in stats:
            svg_text = svg_text.replace(token, stats[key])
    return svg_text


def update_svg_files(stats: dict) -> None:
    for template_path, output_path in TEMPLATE_TO_OUTPUT.items():
        if not os.path.exists(template_path):
            print(f"Skipping {template_path} (not found).")
            continue
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        updated = apply_placeholders(content, stats)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(updated)

        remaining = re.findall(r"\{\{[A-Z_0-9]+\}\}", updated)
        note = f" (remaining placeholders: {remaining} - fill these in the template)" if remaining else ""
        print(f"Generated {output_path} from {template_path}{note}")


def main() -> None:
    token = os.environ.get("ACCESS_TOKEN")
    username = os.environ.get("USER_NAME")

    if not token or not username:
        print("ERROR: ACCESS_TOKEN and USER_NAME environment variables are required.")
        sys.exit(1)

    stats = build_stats(token, username)
    print("Fetched stats:", stats)
    update_svg_files(stats)


if __name__ == "__main__":
    main()
