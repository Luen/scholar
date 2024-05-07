# Scholar API

This project uses a home server cronjob to scrape [Google Scholar](https://scholar.google.com.au/) data via the [scholarly](https://github.com/scholarly-python-package/scholarly) Python package and the [wikipedia](https://github.com/goldsmith/Wikipedia) Python package to get the journal's impact factor (IF) and the publication's [DOI](https://doi.org/). 

The JSON can then be used, for example, by uploading the data to a publicly accessible server via Secure Copy (SCP) or rsync, which serves the JSON data via a Flask application.

# Installation

## Prerequisites
- Python 3.6+
- Flask
- scholarly
- Wikipedia

## Setup
1. Clone this repository to your local machine.
2. Install the required packages.
3. Setup.

```
git clone https://github.com/Luen/scholarly-api
python -m venv scholar
source scholar/bin/activate
pip install -r requirements.txt
playwright install
```
4. Test run.
```
python main.py ynWS968AAAAJ
```
5. Set up cronjob.
```
0 * * * * /path/to/your_bash_script.sh
```

# Testing
Install pytest and run it using the command `pytest`. 

# Starting the flask app
Navigate to the project directory and run the Flask application:
`python ./serve.py`

## Index Welcome Message
URL: /
Method: GET
Description: Displays a welcome message in plain text.
Example: [/](http://127.0.0.1:5000/)

## Get Author Id
URL: /author_id
Method: GET
Description: Searches for authors by id.
Parameter: id
Example: [/ynWS968AAAAJ](http://127.0.0.1:5000/ynWS968AAAAJ)


# License
This open-sourced project is released under the [Unlicense](http://unlicense.org/).

# Notes 
Alternative wikipedia packages: [wikipedia-api](https://github.com/martin-majlis/Wikipedia-API) and [pymediawiki](https://pypi.org/project/pymediawiki/)
