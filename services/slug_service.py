from utils.slugify import slugify


class SlugService:
    @staticmethod
    def create_slug(*args):
        return slugify(*args)
