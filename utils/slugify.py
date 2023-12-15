import re


def slugify(*args):
    """
    Generates a slug from the given strings.
    """
    slug = "-".join(arg.lower() for arg in args if arg)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-")
    return slug
