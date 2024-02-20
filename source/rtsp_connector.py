import socket
import ipaddress
import base64
# import time
import re
import csv
from termcolor import colored
import cv2
import os
import subprocess
from wurlitzer import pipes

# camera_uri = 'rtsp://192.168.100.29/axis-media/media.amp'
camera_uri = 'rtsp://192.168.100.11:554/h264'
user_name = None
# user_name = "admin"
# user_name = 'root'
# passwd = "pass"
passwd = "admin"
# passwd = '5ynect1c'
cameras = []
with open("cameras.csv", "r", newline="") as fd:
    csv_reader = csv.reader(fd)
    for row in csv_reader:
        cameras.append(row)

# print(cameras)

def read_video_frame(cap):
    with pipes() as (out, err):
        able_to_read, image = cap.read()
    c_error = err.read()
    c_out = out.read()
    # print("output of read", c_out, c_error)

    if "SEI type" in c_error:
        c_error = ""

    if c_error != "":
        # print(c_error)
        err_count = 0
        while err_count < 5:
            # print("re-trying", err_count)
            print((colored("re-trying " + str(err_count), 'red', attrs=['reverse', 'blink'])))
            err_count += 1
            with pipes() as (out, err):
                able_to_read, image = cap.read()
            c_error = err.read()
            if c_error == "":
                print("successful recapture on attempt", err_count)
                break
        if err_count == 5:
            print("Error reading frame")
    return able_to_read, image

def add_auth(username, password):
    if username:
        # Combine username and password into a single string
        credentials = f"{username}:{password}"
        # Encode credentials in Base64
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        # Add the Authorization header
        return f"Authorization: Basic {encoded_credentials}\r\n"
    else:
        return ""


def extract_ip_from_rtsp_url(rtsp_url):
    # Define a regular expression pattern to match IP addresses
    ip_pattern = r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}'

    # Define a regular expression pattern to match the RTSP protocol part
    protocol_pattern = r'rtsp://'

    # Define a regular expression pattern to match the username:password part
    auth_pattern = r'(?:\S+:\S+@)?'
    # auth_pattern = r'(?:[^@]*@)?'

    # Define a regular expression pattern to match the port number part
    port_pattern = r'(?::\d+)?'

    # Combine the patterns to create a full regular expression
    rtsp_pattern = f'{protocol_pattern}{auth_pattern}({ip_pattern}){port_pattern}(/.*)?'

    # Use re.search to find the IP address in the URL
    match = re.search(rtsp_pattern, rtsp_url)

    if match:
        ip_address = match.group(1)
        return ip_address
    else:
        return None


def check_uri(uri):
    camera_ip_address = extract_ip_from_rtsp_url(uri)

    try:
        ipaddress.ip_address(camera_ip_address)
    except ValueError:
        print((colored("Invalid IP address" + str(uri), 'red', attrs=['reverse', 'blink'])))
        # print needs to be changed to logging
        return "Error"
    return camera_ip_address


def describe(uri, username=None, password=None):
    connection_error = False
    camera_ip_address = check_uri(uri)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((camera_ip_address, 554))
        request = f"DESCRIBE {uri} RTSP/1.0\r\nCSeq: 0\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        s.close()
        if response[0] != "RTSP/1.0 200 OK":
            connection_error = True
    except socket.error:
        print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        response = "Error connecting to device"
        connection_error = True

    return response, connection_error


def options(uri, username=None, password=None):
    connection_error = False
    camera_ip_address = check_uri(uri)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((camera_ip_address, 554))
        request = f"OPTIONS {uri} RTSP/1.0\r\nCSeq: 0\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        if response[0] != "RTSP/1.0 200 OK":
            connection_error = True
        s.close()
    except socket.error:
        print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        response = "Error connecting to device"

    return response, connection_error


def setup(uri,  username=None, password=None):
    connection_error = False
    camera_ip_address = check_uri(uri)
    transport = None

    # check SETUP assuming multicast  - UDP is underlying transport
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((camera_ip_address, 554))
        request = f"SETUP {uri} RTSP/1.0\r\nCSeq: 1\r\n"
        request += "Transport: RTP/AVP;multicast\r\n"
        request += add_auth(username=username, password=password)
        request += "\r\n"
        s.sendall(request.encode())
        data = s.recv(1024).decode()
        response = data.split("\r\n")
        s.close()
        if response[0] == "RTSP/1.0 200 OK":
            for response_line in response:
                if response_line.startswith("Transport: "):
                    describe_parameters = response_line.split("Transport: ")[1].split(";")
                    if describe_parameters[1] == "unicast":
                        transport = "UNICAST/UDP"
                    elif describe_parameters[1] == "multicast":
                        transport = "MULTICAST"

        # check SETUP assuming unicast and TCP as underlying transport
        if response[0] != "RTSP/1.0 200 OK":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((camera_ip_address, 554))
                request = f"SETUP {uri} RTSP/1.0\r\nCSeq: 1\r\n"
                request += "Transport: RTP/AVP;unicast\r\n"
                request += add_auth(username=username, password=password)
                request += "\r\n"
                s.sendall(request.encode())
                data = s.recv(1024).decode()
                response = data.split("\r\n")
                s.close()
                if response[0] == "RTSP/1.0 200 OK":
                    transport = "UNICAST/TCP"
            except socket.error:
                pass

        # check SETUP assuming unicast and UDP as underlying transport
        if response[0] != "RTSP/1.0 200 OK":
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.connect((camera_ip_address, 554))
                request = f"SETUP {uri} RTSP/1.0\r\nCSeq: 1\r\n"
                request += "Transport: RTP/AVP/UDP;unicast\r\n"
                request += add_auth(username=username, password=password)
                request += "\r\n"
                s.sendall(request.encode())
                data = s.recv(1024).decode()
                response = data.split("\r\n")
                s.close()
                if response[0] == "RTSP/1.0 200 OK":
                    transport = "UNICAST/UDP"
            except socket.error:
                pass
        if response[0] != "RTSP/1.0 200 OK":
            connection_error = True

    except socket.error:
        print((colored("Error connecting to device " + str(uri), 'red', attrs=['reverse', 'blink'])))
        response = "Error connecting to device"
        connection_error = True

    return response, connection_error, transport


for camera in cameras:
    camera_uri = camera[0]
    configured_multicast_address = camera[1]
    configured_port = camera[2]
    user_name = camera[3]
    passwd = camera[4]

    ip_address = extract_ip_from_rtsp_url(camera_uri)

    # start_time = time.time()
    rtsp_describe, error = describe(uri=camera_uri, username=user_name, password=passwd)
    # remove all lines that are not sdp file compliant - must have single_char then =
    rtsp_describe = [item for item in rtsp_describe if len(item) >= 2 and item[1] == "="]
    print(ip_address)
    with open(f"/tmp/{ip_address}.sdp", "w") as fd:

        for line in rtsp_describe:
            fd.write(line + "\n")
    fd.close()

    # if not error:
    #     # print("\nSDP file video parameters")
    #     # print("Original details", camera_uri, user_name, passwd)
    #     # print("DESCRIBE Time", round((time.time() - start_time) * 1000, 2))
    #     for line in rtsp_describe:
    #         # print(line)
    #         pass
    # else:
    #     continue

    # start_time = time.time()


    port = None
    inside_video_section = False
    video_a_parameters = {}
    video_c_parameter = None
    control = None


    for index, line in enumerate(rtsp_describe):

        # Check for the start of the video section (m=video)
        if line.startswith("a="):
            key = line[2:].split(":")
            # need to cater for cases where multiple ":" exist eg a=control:rtsp://1.1.1.1:554/h264
            if key[0] == "control":
                # join the remainder of the values in key to be value
                value = ":".join(key[1:])
                if camera_uri in value:
                    control = value.split(camera_uri)[1][1:]
                else:
                    control = value
        if line.startswith("m=video"):
            inside_video_section = True
            port = line.split()[1]
            if configured_multicast_address and configured_port:
                if port == "0":
                    fixed_entry = line.replace("m=video 0", f"m=video {configured_port}")
                    rtsp_describe[index] = fixed_entry
            # print("Port number", port)
            continue

        if line.startswith("m=") and inside_video_section:
            inside_video_section = False
            break
        if inside_video_section and line.startswith("c="):
            video_c_parameter = line[2:]
            if configured_multicast_address:
                if video_c_parameter.split(" ")[-1] == "0.0.0.0":
                    fixed_entry = line.replace("0.0.0.0", configured_multicast_address)
                    rtsp_describe[index] = fixed_entry
                    video_c_parameter = fixed_entry[2:]

        if inside_video_section and line.startswith("a="):
            # video_a_parameters.append(line[2:])
            try:
                key, value = line[2:].split(":")
                video_a_parameters[key] = value

                if key == "control":
                    if camera_uri in value:
                        control = value.split(camera_uri)[2]
                    else:
                        control = value

            except ValueError:
                video_a_parameters[line[2:]] = True

    # for key in video_a_parameters:
    #     print(key, video_a_parameters[key])
    # print("c= parameter in video section", video_c_parameter)
    # print("control", control)
    # print("port", port)


    # rtsp_setup, error, rtp_transport = setup(uri=f"{camera_uri}/{control}", username=user_name, password=passwd)
    # # print("SETUP Time", round((time.time() - start_time)*1000, 2))
    # print(rtsp_setup)
    # if configured_multicast_address:
    #     multicast = True
    # else:
    #     multicast = False
    # reported_port = None
    # destination_address = None
    # if not error:
    #     for line in rtsp_setup:
    #         # print(line)
    #
    #         if "Transport:" in line:
    #             params = line[9:].split(";")
    #             if params[1] == "multicast":
    #                 multicast = True
    #             if params[1] == "unicast" and configured_multicast_address:
    #                 multicast = True
    #             for param in params:
    #                 if param.startswith("destination="):
    #                     destination_address = param.split("=")[1]
    #                 if param.startswith("port="):
    #                     reported_port = param.split("=")[1]
    # else:
    #     print(rtsp_setup, error)
    # print("destination_address", destination_address)
    # print("reported_port", reported_port)
    # print("multicast", multicast)
    # print("transport", rtp_transport)
    # print("\n")

    if configured_multicast_address and configured_port:
        reported_multicast_address = video_c_parameter.split(" ")[2].split("/")[0]
        with open(f"/tmp/{configured_multicast_address}.sdp", "w") as fd:

            for line in rtsp_describe:
                # print(line)
                fd.write(line + "\n")

        fd.close()

        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'add',
                             str(configured_multicast_address) + '/32', 'dev', "enp89s0", 'autojoin'])
        c_error = err.read()
        # if already connected then clear the error
        if "File exists" in c_error:
            c_error = ""
        if c_error:
            print((colored("Error joining multicast group " + str(camera_uri) + " " + c_error, 'red', attrs=['reverse', 'blink'])))
            # continue
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'protocol_whitelist;file,rtp,udp'
        cap = cv2.VideoCapture(f"/tmp/{reported_multicast_address}.sdp", cv2.CAP_FFMPEG)
        if not cap.isOpened():
            print((colored("Error unable to open stream " + str(camera_uri), 'red', attrs=['reverse', 'blink'])))
            continue
        able_to_read, image = read_video_frame(cap)
        if able_to_read:
            if image.shape[0] != 0:
                cv2.imwrite("/tmp/image_uncompressed.jpg", image)
                cv2.imwrite("/tmp/image_compressed.jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                compressed_image = cv2.imread("/tmp/image_compressed.jpg")
                new_width = int(image.shape[1] / 4)
                new_height = int(image.shape[0] / 4)
                image = cv2.resize(image, (new_width, new_height))
                compressed_image = cv2.resize(compressed_image, (new_width, new_height))
                cv2.imshow("compressed", compressed_image)
                cv2.imshow(reported_multicast_address, image)
                cv2.waitKey(0)
                cv2.destroyWindow(reported_multicast_address)
                cv2.destroyWindow("compressed")
                cap.release()
        else:
            print((colored("Error unable to open stream " + str(camera_uri), 'red', attrs=['reverse', 'blink'])))
        with pipes() as (out, err):
            subprocess.call(['sudo', 'ip', 'addr', 'del',
                             str(configured_multicast_address) + '/32', 'dev', "enp89s0"])
        c_error = err.read()
        if c_error:
            print((colored("Error deleting multicast group" + str(camera_uri) + " " + c_error, 'red', attrs=['reverse', 'blink'])))
            # continue
    else:
        print((colored("Try Unicast " + str(camera_uri), 'red', attrs=['reverse', 'blink'])))
        os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;udp'
        cap = cv2.VideoCapture(camera_uri, cv2.CAP_FFMPEG)
        if cap.isOpened():
            able_to_read, image = read_video_frame(cap)
            if able_to_read:
                if image.shape[0] != 0:
                    cv2.imwrite("/tmp/image_uncompressed.jpg", image)
                    cv2.imwrite("/tmp/image_compressed.jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    new_width = int(image.shape[1] / 4)
                    new_height = int(image.shape[0] / 4)
                    image = cv2.resize(image, (new_width, new_height))
                    cv2.imshow(camera_uri, image)
                    cv2.waitKey(0)
                    cv2.destroyWindow(camera_uri)
                    cap.release()
            else:
                print((colored("Error unable to open stream " + str(camera_uri), 'red', attrs=['reverse', 'blink'])))

    #
    # if not multicast:
    #     print((colored("Doing Unicast on " + str(camera_uri), 'yellow', attrs=['reverse', 'blink'])))
    #     cap = cv2.VideoCapture(camera_uri, cv2.CAP_FFMPEG)
    #     if not cap.isOpened():
    #         print((colored("Error unable to open stream" + str(camera_uri), 'red', attrs=['reverse', 'blink'])))
    #         continue
    #     able_to_read, image = read_video_frame(cap)
    #     if image.shape[0] != 0:
    #         new_width = int(image.shape[1] / 4)
    #         new_height = int(image.shape[0] / 4)
    #         image = cv2.resize(image, (new_width, new_height))
    #         cv2.imshow(camera_uri, image)
    #         cv2.waitKey(0)