import pytest
from doi import get_doi

def test_get_doi():
    publication_url = "https://www.nature.com/articles/nclimate2195"
    expected_doi = "10.1038/nclimate2195"
    assert get_doi(publication_url) == expected_doi



# test doi
#print(get_doi("https://onlinelibrary.wiley.com/doi/abs/10.1111/gcb.12455"))
#print(get_doi("https://journals.biologists.com/jeb/article-abstract/216/11/2103/11461"))
#print(get_doi("https://www.sciencedirect.com/science/article/pii/S1095643313002031"))