import time
from scholarly import scholarly

def get_scholar_id(author_id):
    try:
        author = scholarly.search_author_id(author_id)
        if not author or author is None:
            return None

        author = scholarly.fill(author)
        filled_publications = []
        for pub in author["publications"]:
            filled_pub = scholarly.fill(pub)
            filled_publications.append(filled_pub)
            time.sleep(10)
        author["publications"] = filled_publications

        return author
    except Exception as e:
        print(f"An error occurred: {e}")
        return None