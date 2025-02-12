# Scholar API

This project uses a home server cronjob to scrape [Google Scholar](https://scholar.google.com.au/) data via the [scholarly](https://github.com/scholarly-python-package/scholarly) Python package and the Google Sheets to get the journal's impact factor (IF) and the publication's [DOI](https://doi.org/).

The JSON can then be used, for example, by uploading the data to a publicly accessible server via Secure Copy (SCP) or rsync, which serves the JSON data via a Flask application.

[Meltwater](https://www.meltwater.com/) is the news gathering tool used by some universities. See also Isentia Medaiportal.
See also [Zotera](https://www.zotero.org/), an [open source citation manager](https://github.com/zotero/zotero).

altmetrics

## Installation

### Prerequisites

- Python 3.6+
- Flask
- scholarly
- Wikipedia

### Setup

1. Clone this repository to your local machine.
2. Install the required packages.
3. Setup.

    ```bash
    git clone https://github.com/Luen/scholarly-api
    python -m venv scholar
    source scholar/bin/activate
    pip install -r requirements.txt
    ```

4. Test run.

    ```bash
    python main.py ynWS968AAAAJ
    ```

5. Set up cronjob.

    ```bash
    0 * * * * /path/to/your_bash_script.sh
    ```

## Docker

First build the base image:

`docker build -t scholar-base:latest -f Dockerfile.base .`

Then start the services:

`docker-compose up -d`

Wait for containers to be ready (check status with `docker compose ps`). Then to manually run the script:

```bash
# First check if containers are ready
docker compose ps

# If containers are running, execute the script
docker compose exec cron python main.py ynWS968AAAAJ

# If you get a "container is restarting" error, check logs
docker compose logs web
```

## Testing

Install pytest and run it using the command `pytest`.

## Starting the flask app

Navigate to the project directory and run the Flask application:
`python ./serve.py`

### Index Welcome Message

URL: /
Method: GET
Description: Displays a welcome message in plain text.
Example: [/](http://127.0.0.1:5000/)

### Get Author Id

URL: /author_id
Method: GET
Description: Searches for authors by id.
Parameter: id
Example: [/ynWS968AAAAJ](http://127.0.0.1:5000/ynWS968AAAAJ)
