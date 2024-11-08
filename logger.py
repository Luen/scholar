import logging

# Set up logging to a file with custom formatting
logging.basicConfig(filename='logfile.txt', level=logging.DEBUG, format='%(message)s')

def log_to_file(prefix, message):
    logging.info(f"{prefix}: {message}")

def colored(r, g, b, text):
    return "\033[38;2;{};{};{}m{} \033[38;2;255;255;255m".format(r, g, b, text)

def print_error(message):
    formatted_message = colored(255, 0, 0, message)
    print(formatted_message)
    log_to_file("ERROR", message)

def print_warn(message):
    formatted_message = colored(255, 255, 0, message)
    print(formatted_message)
    log_to_file("WARN", message)

def print_info(message):
    formatted_message = colored(0, 255, 0, message)
    print(formatted_message)
    log_to_file("INFO", message)

def print_misc(message):
    formatted_message = colored(255, 255, 255, message)
    print(formatted_message)
    log_to_file("MISC", message)
