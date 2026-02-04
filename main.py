import collections
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

from google.cloud import bigquery
import jinja2

PYPI_URL = "https://pypi.org/pypi/{name}/json"
PYTHON_RELEASES_URL = "https://peps.python.org/api/python-releases.json"

Status = collections.namedtuple(
    "Status", ("dying", "eol", "dev", "alpha", "beta", "rc"), defaults=(False,) * 6
)


def get_prerelease_phase(releases: list[dict]) -> str | None:
    """Determine the current pre-release phase (dev, alpha, beta, rc) from releases."""
    actual = [r for r in releases if r.get("state") == "actual"]
    if not actual:
        return "dev"
    stage = actual[-1].get("stage", "").lower()
    if "alpha" in stage:
        return "alpha"
    if "beta" in stage:
        return "beta"
    if "candidate" in stage:
        return "rc"
    return None  # Final release


def build_majors() -> dict[str, Status]:
    """Build the MAJORS dict from PEP API data."""
    with urllib.request.urlopen(PYTHON_RELEASES_URL) as response:
        data = json.loads(response.read())

    metadata = data["metadata"]
    releases = data["releases"]
    majors = {}
    today = dt.date.today()

    for version, info in metadata.items():
        # Include all 3.x and 2.3+
        if version in ("1.6", "2.0", "2.1", "2.2"):
            continue

        status = info.get("status", "")
        first_release = info.get("first_release", "")
        end_of_life = info.get("end_of_life", "")

        try:
            release_date = dt.date.fromisoformat(first_release[:10])
            is_unreleased = release_date > today
        except (ValueError, TypeError):
            is_unreleased = False

        try:
            eol_date = dt.date.fromisoformat(end_of_life[:10])
        except (ValueError, TypeError):
            eol_date = None

        if status == "end-of-life":
            majors[version] = Status(eol=True)
        elif eol_date and eol_date <= today + dt.timedelta(days=274):  # ~9 months
            majors[version] = Status(dying=True)
        elif status == "feature" and is_unreleased:
            phase = get_prerelease_phase(releases.get(version, []))
            if phase == "dev":
                majors[version] = Status(dev=True)
            elif phase == "alpha":
                majors[version] = Status(alpha=True)
            elif phase == "beta":
                majors[version] = Status(beta=True)
            elif phase == "rc":
                majors[version] = Status(rc=True)
            else:
                majors[version] = Status()
        else:
            majors[version] = Status()

    return dict(
        sorted(
            majors.items(),
            key=lambda x: [int(p) for p in x[0].split(".")],
            reverse=True,
        )
    )


MAJORS = build_majors()


QUERY = """
SELECT
  file.project,
  COUNT(*) AS total_downloads
FROM
  `bigquery-public-data.pypi.file_downloads`
WHERE
  timestamp BETWEEN TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  AND details.python LIKE '{major}.%'
GROUP BY
  file.project
ORDER BY
  total_downloads DESC
LIMIT
  360
"""


def project_json(name: str) -> dict:
    print(f"Fetching '{name}'")
    try:
        response = urllib.request.urlopen(PYPI_URL.format(name=name))
        return json.loads(response.read())
    except urllib.error.HTTPError as e:
        print(f"Failed to fetch '{name}': {e}")
        return {"info": {"classifiers": []}}


def supports(major: str, classifiers: set[str], status: Status) -> bool:
    return (f"Programming Language :: Python :: {major}" in classifiers) != (
        status.eol or status.dying
    )


def fetch_top_projects() -> dict[str, list[str]]:
    print("Fetching top projects")
    bq_client = bigquery.Client()
    projects = {
        major: [
            row["project"]
            for row in bq_client.query(QUERY.format(major=major)).result()
        ]
        for major in ["2", "3"]
    }
    print(projects)
    print("Fetching top projects complete")
    return projects


def fetch_classifiers(names: set[str]) -> dict[str, set[str]]:
    print("Fetching classifiers")
    classifiers = {
        name: set(project_json(name)["info"]["classifiers"]) for name in names
    }
    print(classifiers)
    print("Fetching classifiers complete")
    return classifiers


def write_local_file(filename: str, contents: str) -> None:
    print(f"Writing file '{filename}' locally")
    path = Path("docs") / filename
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(contents)


def main() -> None:
    updated = dt.datetime.now()
    projects = fetch_top_projects()
    classifiers = fetch_classifiers(set().union(*projects.values()))

    template_loader = jinja2.FileSystemLoader(searchpath="./templates/")
    template_env = jinja2.Environment(loader=template_loader)
    major_template = template_env.get_template("major.html")
    index_template = template_env.get_template("index.html")

    for major, status in MAJORS.items():
        results = [
            (name, supports(major, classifiers[name], status))
            for name in projects[major[0]]
        ]
        print(major, status, results)
        do_support = sum(result[1] for result in results)
        write_local_file(
            f"{major}/index.html",
            major_template.render(
                results=results,
                major=major,
                status=status,
                updated=updated,
                do_support=do_support,
            ),
        )

    write_local_file(
        "index.html", index_template.render(updated=updated, majors=MAJORS)
    )


if __name__ == "__main__":
    main()
