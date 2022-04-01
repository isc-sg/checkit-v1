#! /home/checkit/env/bin/python
import cv2
import numpy as np
import socket
import sys
import xml.etree.ElementTree as ET


def recvall(sock):
    fragments = b''
    while True:
        chunk = s.recv(10000)
        if not chunk:
            break
        fragments.append(chunk)

    print("".join(fragments))
    return fragments


HOST = "192.168.100.211"  # Standard loopback interface address (localhost)
PORT = 9876

logon = "<Request command=\"logOn\" id=\"123\"><user>engineer</user>" \
        "<password>engineerx</password><workstation>VirtualWorkstation1</workstation></Request>"
get_cameras = """<Request command=\"getCameraConfiguration\" id=\"123\"></Request>""" + "\x00"
get_incident_types = """<Request command=\"getIncidentTypes\" id=\"123\"></Request>""" + "\x00"
get_incident_lockers = """<Request command=\"getIncidentLockers\" id=\"123\"></Request>""" + "\x00"
# print(logon)
logon = logon + "\x00"

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect((HOST, PORT))
s.send(logon.encode())
data = s.recv(8192).decode().rstrip("\x00")
# print('data', data)
s.send(get_cameras.encode())
data = s.recv(8192).decode().rstrip("\x00")
# print('data', data)
myroot = ET.fromstring(data)
for camera in myroot.iter('cameras'):
    for camera_detail in camera.iter('camera'):
        id = camera_detail.find('id').text
        print('id=' + id)
        name = camera_detail.find('name').text
        print('name=' + name)
        description = camera_detail.find('description').text
        print('description=' + description)
        ptz = camera_detail.find('ptz').text
        print('ptz=' + ptz)
        absolutePosition = camera_detail.find('absolutePosition').text
        print('absolutePosition=' + absolutePosition)
        ipAddress = camera_detail.find('ipAddress').text
        print('ipAddress=' + ipAddress)
        recordedPort = camera_detail.find('recordedPort').text
        print('recordedPort=' + recordedPort)
        livePort = camera_detail.find('livePort').text
        print('livePort=' + livePort)
        liveStreamType = camera_detail.find('liveStreamType').text
        print('liveStreamType=' + liveStreamType)
        ipCameraDetails = camera_detail.find('ipCameraDetails')
        for key in ipCameraDetails.attrib:
            print(key, ipCameraDetails.attrib[key])
        liveIPAddress = camera_detail.find('liveIPAddress').text
        print('liveIPAddress=' + liveIPAddress)
        liveStreamId = camera_detail.find('liveStreamId').text
        print('liveStreamId=' + liveStreamId)
        multicastIPAddress = camera_detail.find('multicastIPAddress').text
        print('multicastIPAddress=' + multicastIPAddress)
        synav2 = camera_detail.find('synav2').text
        print('synav2=' + synav2)
        synxfs2 = camera_detail.find('synxfs2').text
        print('synxfs2=' + synxfs2)
        recordedVideoPath = camera_detail.find('recordedVideoPath').text
        print('recordedVideoPath=' + recordedVideoPath)
        ipCameraUsername = camera_detail.find('ipCameraUsername').text
        print('ipCameraUsername=' + ipCameraUsername)
        ipCameraPassword = camera_detail.find('ipCameraPassword').text
        print('ipCameraPassword=' + ipCameraPassword)


# print(ET.tostring(myroot))

# s.send(get_incident_types.encode())
# data = s.recv(8192).decode().rstrip("\x00")
# print('data', data)
# s.send(get_incident_lockers.encode())
# data = s.recv(8192).decode().rstrip("\x00")
# print('data', data)
exit()

def get_transparent_edge(input_image, color):
    edge_image = cv2.Canny(input_image, 100, 200)
    edge_image = cv2.cvtColor(edge_image, cv2.COLOR_RGB2BGR)
    edge_image[np.where((edge_image == [255, 255, 255]).all(axis=2))] = color
    gray_image = cv2.cvtColor(edge_image, cv2.COLOR_BGR2GRAY)
    _, alpha = cv2.threshold(gray_image, 0, 255, cv2.THRESH_BINARY)
    b, g, r = cv2.split(edge_image)
    rgba_image = [b, g, r, alpha]
    final_image = cv2.merge(rgba_image, 4)
    return final_image


base = cv2.imread(sys.argv[1])
image = get_transparent_edge(base, [255, 0, 0])
cv2.imshow("Base", image)
cv2.waitKey(0)

img = cv2.imread(sys.argv[2])
image2 = get_transparent_edge(img, [0, 0, 255])
cv2.imwrite("/tmp/blended.jpg", image2)

cv2.imshow("Captured", image2)
cv2.waitKey(0)

dst = cv2.addWeighted(image, 1, image2, 1, 0)
cv2.imshow("Edges", dst)
cv2.imwrite("/tmp/dst.jpg", dst)

cv2.waitKey(0)

f2 = cv2.imread("/tmp/blended.jpg")

dst3 = cv2.addWeighted(f2, 1, base, 1, 0)
cv2.imshow("f", dst3)
cv2.imwrite("/tmp/dst3.jpg", dst3)
cv2.waitKey(0)
