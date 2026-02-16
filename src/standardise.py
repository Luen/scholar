import numpy as np


# https://stackoverflow.com/questions/41005700/function-that-returns-capitalized-initials-of-name
def initialize(fullname):
    if not fullname or not isinstance(fullname, str):
        return ""
    xs = fullname.strip()
    name_list = xs.split()
    if not name_list:
        return ""
    surname = name_list[-1]
    initials = ""
    for name in name_list:  # go through each name
        if name != surname:
            initials += name[0].upper() + "."
            if name != name_list[-2]:
                initials += " "  # append a space except for the end one
        else:
            initials = surname.title() + ", " + initials  # prepend the surname
    return initials


# Get authors in a usable format
def standardise_authors(authors):  # prettify_authors
    if authors is None:
        return ""
    author_list = authors.lower().split(" and ")
    authors = ""
    for a in author_list:
        if a != author_list[0]:
            authors += ", "
        authors += initialize(a)
        # et al.
    return authors


# https://stackabuse.com/levenshtein-distance-and-text-similarity-in-python/
def levenshtein(seq1, seq2):
    size_x = len(seq1) + 1
    size_y = len(seq2) + 1
    matrix = np.zeros((size_x, size_y))
    for x in range(size_x):
        matrix[x, 0] = x
    for y in range(size_y):
        matrix[0, y] = y

    for x in range(1, size_x):
        for y in range(1, size_y):
            if seq1[x - 1] == seq2[y - 1]:
                matrix[x, y] = min(matrix[x - 1, y] + 1, matrix[x - 1, y - 1], matrix[x, y - 1] + 1)
            else:
                matrix[x, y] = min(
                    matrix[x - 1, y] + 1, matrix[x - 1, y - 1] + 1, matrix[x, y - 1] + 1
                )
    return matrix[size_x - 1, size_y - 1]
