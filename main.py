import collections
import datetime
import json
import urllib.request

from google.cloud import bigquery
from google.cloud import storage
import jinja2

PYPI_URL = "https://pypi.org/pypi/{name}/json"

Status = collections.namedtuple(
    "Status", ("dying", "eol", "dev", "alpha", "beta", "rc"), defaults=(False,) * 6
)

MAJORS = {
    # version: (past_eol, alpha)
    "2.3": Status(eol=True),
    "2.4": Status(eol=True),
    "2.5": Status(eol=True),
    "2.6": Status(eol=True),
    "2.7": Status(eol=True),
    "3.0": Status(eol=True),
    "3.1": Status(eol=True),
    "3.2": Status(eol=True),
    "3.3": Status(eol=True),
    "3.4": Status(eol=True),
    "3.5": Status(eol=True),
    "3.6": Status(),
    "3.7": Status(),
    "3.8": Status(),
    "3.9": Status(),
    "3.10": Status(dev=True),
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

bq_client = bigquery.Client()
gcs_client = storage.Client()
bucket = gcs_client.bucket("www.pyreadiness.org")

templateLoader = jinja2.FileSystemLoader(searchpath="./templates/")
templateEnv = jinja2.Environment(loader=templateLoader)
major_template = templateEnv.get_template("major.html")
index_template = templateEnv.get_template("index.html")


def project_json(name):
    print(f"Fetching '{name}'")
    response = urllib.request.urlopen(PYPI_URL.format(name=name))
    return json.loads(response.read())


def supports(major, classifiers, status):
    return (f"Programming Language :: Python :: {major}" in classifiers) != (
        status.eol or status.dying
    )


def fetch_top_projects():
    print("Fetching top projects")
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


def fetch_classifiers(names):
    print("Fetching classifiers")
    classifiers = {
        name: set(project_json(name)["info"]["classifiers"]) for name in names
    }
    print(classifiers)
    print("Fetching classifiers complete")
    return classifiers


def write_file(filename, contents, content_type="text/html"):
    print(f"Writing file '{filename}'")
    blob = bucket.blob(filename)
    blob.upload_from_string(contents, content_type)


def run(request):
    updated = datetime.datetime.now()
    projects = fetch_top_projects()
    classifiers = fetch_classifiers(set().union(*projects.values()))

    for major, status in MAJORS.items():
        results = [
            (name, supports(major, classifiers[name], status))
            for name in projects[major[0]]
        ]
        print(major, status, results)
        write_file(
            f"{major}/index.html",
            major_template.render(
                results=results, major=major, status=status, updated=updated
            ),
        )

    write_file("index.html", index_template.render(updated=updated, majors=MAJORS))
