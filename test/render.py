import os
import main

main.fetch_top_projects = lambda: {
    "2": ["foobar", "bizbaz", "blaha", "blahb", "blahc", "blahd"],
    "3": ["foobar", "bizbaz", "blaha", "blahb", "blahc", "blahd"],
}
main.fetch_classifiers = lambda a: {
    "foobar": set(),
    "bizbaz": set(["Programming Language :: Python :: 2.6"]),
    "blaha": set(),
    "blahb": set(),
    "blahc": set(),
    "blahd": set(),
}


def write_file(filename, contents):
    filename = f"./output/{filename}"
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as o:
        o.write(contents)


main.write_file = write_file


main.run(None)
