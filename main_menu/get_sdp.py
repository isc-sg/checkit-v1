import socket
import ipaddress
import logging
from logging.handlers import RotatingFileHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])


def get_sdp(uri):

    camera_ip_address = uri.split(" ")[1][7:].split("/")[0]
    try:
        ipaddress.ip_address(camera_ip_address)
        # print(camera_ip_address)
    except ValueError:
        logging.error(f"Invalid IP address {uri}")
        return "Error"

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((camera_ip_address, 554))
        s.sendall(uri.encode())
        data = s.recv(1024).decode()
        lines = data.split("\r\n")

        index = next((i for i, line in enumerate(lines) if line.startswith("v=0")), None)
        if index is not None:
            lines = lines[index:]

    except socket.error as err:
        lines = "Error " + str(err)

    return lines

