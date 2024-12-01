import os
import collections
import datetime
import json
import urllib.request
from pathlib import Path

from google.cloud import bigquery
import jinja2

PYPI_URL = "https://pypi.org/pypi/{name}/json"

Status = collections.namedtuple(
    "Status", ("dying", "eol", "dev", "alpha", "beta", "rc"), defaults=(False,) * 6
)

MAJORS = {
    # version: (past_eol, alpha)
    "3.14": Status(alpha=True),
    "3.13": Status(),
    "3.12": Status(),
    "3.11": Status(),
    "3.10": Status(),
    "3.9": Status(),
    "3.8": Status(eol=True),
    "3.7": Status(eol=True),
    "3.6": Status(eol=True),
    "3.5": Status(eol=True),
    "3.4": Status(eol=True),
    "3.3": Status(eol=True),
    "3.2": Status(eol=True),
    "3.1": Status(eol=True),
    "3.0": Status(eol=True),
    "2.7": Status(eol=True),
    "2.6": Status(eol=True),
    "2.5": Status(eol=True),
    "2.4": Status(eol=True),
    "2.3": Status(eol=True),
}

QUERY = """
SELECT
  file.project,
  COUNT(*) AS total_downloads
FROM
  `bigquery-public-data.pypi.file_downloads`
WHERE
  DATE(timestamp) BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
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
    updated = datetime.datetime.now()
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
