import signal
import multiprocessing as mp
from multiprocessing import cpu_count
import sys
import os


number_of_cpus = cpu_count
pid = os.getpid()
print("pid", pid)

def signal_handler(signum, frame):
    signal_name = signal.Signals(signum).name
    print(f"Received signal: {signal_name}")
    match signal_name:
        case "SIGINT":
            print("Exiting")
            sys.exit()
        case "SIGTERM":
            print("Exiting")
            sys.exit()
        case "SIGQUIT":
            print("Exiting")
            sys.exit()
        case "SIGHUP":
            print("Exiting")
            sys.exit()


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)   # SIGINT (Ctrl+C)
signal.signal(signal.SIGTERM, signal_handler)  # SIGTERM (Termination signal)
signal.signal(signal.SIGTSTP, signal_handler)  # SIGTSTP (Ctrl+Z)
signal.signal(signal.SIGQUIT, signal_handler)  # SIGQUIT (Ctrl+\)
signal.signal(signal.SIGPIPE, signal_handler)  # SIGPIPE for handling broken pipes
signal.signal(signal.SIGALRM, signal_handler)  # SIGALRM for timeouts
signal.signal(signal.SIGCHLD, signal_handler)  # might be handy in multiprocessing but use process.join() instead
signal.signal(signal.SIGHUP, signal_handler)   # SIGHUP Sent to a process when its controlling terminal is closed.
#                                              # This signal is often used to trigger a reload or restart of a daemon.
# Note: SIGKILL cannot be caught or ignored


def main():
    while True:
        pass


if __name__ == "__main__":
    main()