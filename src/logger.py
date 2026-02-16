import logging
import os

# Create logs directory if it doesn't exist
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)

# Set up logging to a file with custom formatting and timestamp
log_file = os.path.join(log_dir, "app.log")
logging.basicConfig(
    filename=log_file, level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


def log_to_file(prefix, message):
    logging.info(f"{prefix}: {message}")


def colored(r, g, b, text):
    return f"\033[38;2;{r};{g};{b}m{text}\033[38;2;255;255;255m"


def print_error(message):
    formatted_message = colored(255, 0, 0, message)
    print(formatted_message, flush=True)
    log_to_file("ERROR", message)


def print_warn(message):
    formatted_message = colored(255, 255, 0, message)
    print(formatted_message, flush=True)
    log_to_file("WARN", message)


def print_info(message):
    formatted_message = colored(0, 255, 0, message)
    print(formatted_message, flush=True)
    log_to_file("INFO", message)


def print_misc(*args):
    message = " ".join(str(arg) for arg in args)
    formatted_message = colored(255, 255, 255, message)
    print(formatted_message, flush=True)
    log_to_file("MISC", message)
