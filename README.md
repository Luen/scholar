# Scholar API

This project uses a home server cronjob to scrape [Google Scholar](https://scholar.google.com.au/) data via the [scholarly](https://github.com/scholarly-python-package/scholarly) Python package and the [wikipedia](https://github.com/goldsmith/Wikipedia) Python package to get the journal's impact factor (IF). The script that uploads the data to a publicly accessible server via Secure Copy (SCP) or rsync that serves the json data via a Flask application.

# Installation

## Prerequisites
- Python 3.6+
- Flask
- scholarly
- Wikipedia

## Setup
1. Clone this repository to your local machine.
2. Install the required packages.
3. Setup cronjob on home computer.

```
git clone https://github.com/Luen/scholarly-api
python -m venv scholarly-api
source scholarly-api/bin/activate
pip install -r requirements.txt
0 * * * * /path/to/your_bash_script.sh
```

# Testing
install pytest and run by using comman pytest. 

# Starting teh flask app
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
Alternative wikipedia package: [wikipedia-api](https://github.com/martin-majlis/Wikipedia-API)