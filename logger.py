def colored(r, g, b, text):
    return "\033[38;2;{};{};{}m{} \033[38;2;255;255;255m".format(r, g, b, text)
  
print_error = lambda x: print(colored(255, 0, 0, x))
print_warn = lambda x: print(colored(255, 255, 0, x))
print_info = lambda x: print(colored(0, 255, 0, x))