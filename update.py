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
# Fill in your personal info (NAME, ROLE, BIO, TYPE_1..TYPE_6, EMAIL,
# PORTFOLIO) directly inside the *.template.svg files once - only the
# GitHub-stat placeholders below get replaced automatically on every run.
TEMPLATE_TO_OUTPUT = {
    "templates/dark.template.svg": "dark.svg",
    "templates/light.template.svg": "light.svg",
}

# Placeholders that will be substituted inside the SVG files.
# Add or remove entries here to match what you display in your template.
# (STARS/FOLLOWERS/REPOS are still computed and available below even though
# the default template no longer displays them - add {{STARS}} / {{FOLLOWERS}}
# / {{REPOS}} back into your template if you want them.)
PLACEHOLDERS = [
    "USERNAME",
    "REPOS",
    "STARS",
    "FOLLOWERS",
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


def build_stats(token: str, username: str) -> dict:
    profile = get_profile_summary(token, username)
    repos = profile["repositories"]
    total_stars = sum(node["stargazerCount"] for node in repos["nodes"])

    return {
        "USERNAME": profile["login"],
        "REPOS": str(repos["totalCount"]),
        "STARS": str(total_stars),
        "FOLLOWERS": str(profile["followers"]["totalCount"]),
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
