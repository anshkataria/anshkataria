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
"""

import os
import re
import sys
import requests

GITHUB_API = "https://api.github.com/graphql"

# Templates keep every {{PLACEHOLDER}} token intact so this script can be run
# repeatedly (each run reads the template fresh and writes a resolved copy).
# Fill in your personal info (NAME, ROLE, BIO, TOOLCHAIN_LINE_1, etc.) directly
# inside the *.template.svg files once - only the GitHub-stat placeholders
# below get replaced automatically on every run.
TEMPLATE_TO_OUTPUT = {
    "templates/dark.template.svg": "dark.svg",
    "templates/light.template.svg": "light.svg",
}

# Placeholders that will be substituted inside the SVG files.
# Add or remove entries here to match what you display in your template.
PLACEHOLDERS = [
    "USERNAME",
    "REPOS",
    "STARS",
    "FOLLOWERS",
    "COMMITS",
    "LOC",
]


def graphql_query(token: str, username: str) -> dict:
    query = """
    query($login: String!) {
      user(login: $login) {
        login
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes {
            stargazerCount
          }
        }
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
        }
      }
    }
    """
    headers = {"Authorization": f"bearer {token}"}
    resp = requests.post(
        GITHUB_API,
        json={"query": query, "variables": {"login": username}},
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def estimate_loc(token: str, username: str) -> str:
    """
    GitHub's API doesn't expose a direct 'lines of code' metric.
    This is a lightweight estimate based on total additions across the
    user's own repos via the REST search API. For a more accurate number,
    consider swapping in a dedicated LOC-counting action.
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
    user = graphql_query(token, username)
    repos = user["repositories"]
    total_stars = sum(node["stargazerCount"] for node in repos["nodes"])
    contrib = user["contributionsCollection"]
    total_commits = contrib["totalCommitContributions"] + contrib["restrictedContributionsCount"]

    return {
        "USERNAME": user["login"],
        "REPOS": str(repos["totalCount"]),
        "STARS": str(total_stars),
        "FOLLOWERS": str(user["followers"]["totalCount"]),
        "COMMITS": str(total_commits),
        "LOC": estimate_loc(token, username),
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

        remaining = re.findall(r"\{\{[A-Z_]+\}\}", updated)
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
