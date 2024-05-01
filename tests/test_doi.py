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
#print(get_doi("https://repository.library.noaa.gov/view/noaa/42440/noaa_42440_DS1.pdf#page=124"))
#print(get_doi("https://repository.library.noaa.gov/view/noaa/42440/noaa_42440_DS1.pdf"))

#test = get_doi("https://www.frontiersin.org/articles/10.3389/fmars.2021.724913/full?trk=public_post_comment-text")
#print(test)
#print(get_doi_short(test))
#test = get_doi("https://journals.biologists.com/jeb/article-pdf/doi/10.1242/jeb.243973/2170187/jeb243973.pdf")
#print(test)
#print(get_doi_short(test))

# https://www.researchgate.net/profile/Gael-Lecellier/publication/329841906_Distribution_patterns_of_ocellated_eagle_rays_Aetobatus_ocellatus_along_two_sites_in_Moorea_Island_French_Polynesia/links/5ef14ac5299bf1faac6f23ae/Distribution-Patterns-of-Ocellated-Eagle-Rays-Aetobatus-Ocellatus-along-Two-Sites-in-Moorea-Island-French-Polynesia.pdf
# https://sfi-cybium.fr/sites/default/files/pdfs-cybium/19-Berthe%20949%20%5B402%5D181-184.pdf\
# https://scholar.google.com/scholar?cluster=4186906934658759747&hl=en&oi=scholarr
#Processing publication: Optimism and opportunities for conservation physiology in the Anthropocene: a synthesis and conclusions
#Getting DOI for http://www.fecpl.ca/wp-content/uploads/2021/01/Optimism_and_opportunities_for_conservation_physiology_in_the_Anthropocenea_synthesis_and_conclusions.pdf
#Extracting text from PDF http://www.fecpl.ca/wp-content/uploads/2021/01/Optimism_and_opportunities_for_conservation_physiology_in_the_Anthropocenea_synthesis_and_conclusions.pdf
#Optimism_and_opportunities_for_conservation_physiology_in_the_Anthropocenea_synthesis_and_conclusions.pdf 10.1093/oso/9780198843610.003.0019OUP
#Failed to verify DOI 10.1093/oso/9780198843610.003.0019OUP against http://www.fecpl.ca/wp-content/uploads/2021/01/Optimism_and_opportunities_for_conservation_physiology_in_the_Anthropocenea_synthesis_and_conclusions.pdf: HTTP Error 404: Not Found
#HTTP error 404 for DOI 10.1093/oso/9780198843610.003.0019OUP: Not Found
#Optimism_and_opportunities_for_conservation_physiology_in_the_Anthropocenea_synthesis_and_conclusions.pdf 10.1093/conphys/cot001
#DOI: 10.1093/oso/9780198843610.003.0019OUP

#doi = '10.1111/gcb.12455'
#print(get_doi_link(doi))
#print(get_doi_short(doi))
#print(get_doi_short_link(doi))