import requests
import requests.auth
import struct
import ffmpeg
import cv2
import numpy as np
import datetime
from datetime import timedelta
import io

from requests_toolbelt.multipart import decoder

basic = requests.auth.HTTPBasicAuth('user', 'pass')
# response = requests.get('https://192.168.15.113:2242/services/v1/synav?streamID=7848&frameTypes=IP&time=2024-12-18T12:50:00Z', auth=basic, verify=False)
#response = requests.get('https://localhost:2242/services/v1/synav?streamID=6000&frameTypes=IP&time=2024-10-23T12:16:36Z', auth=basic, verify=False)
current_time = datetime.datetime.now(datetime.timezone.utc)

# Subtract one minute
one_minute_prior = current_time - timedelta(minutes=1)

# Format the time in the desired ISO 8601 format with 'Z'
formatted_time = one_minute_prior.strftime("%Y-%m-%dT%H:%M:%SZ")

psn_api_url = (f"https://192.168.15.113:2242/services/v1/synav?streamID=" +
               f"7848&frameTypes=I&time={formatted_time}")

response = requests.get(psn_api_url, auth=basic, verify=False)
d = decoder.MultipartDecoder(response.content, response.headers['Content-Type'])
if response.status_code != 200:
    print("Request Failed with status code:", response.status_code)
    print(response.content)
    quit()

print("Headers:", response.headers)

d = decoder.MultipartDecoder(response.content, response.headers['Content-Type'])

print("Boundary:", d.boundary)
print("Parts:", len(d.parts))


def decode_frame(frame_data):
    process = (
        ffmpeg
        .input('pipe:0', format='h264')
        .output('pipe:1', format='image2', frames='1')
        .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True)
    )
    out, _ = process.communicate(input=frame_data)
    # print(_)
    if len(out) == 0:
        print(f"Decode failed - {_}")
        return out, False

    return out, True


class RawSynAV2ComponentHeader:
    def __init__(self, data):
        self.FileID = data.decode('utf-8')


class RawSynAV2ComponentHeader2:
    def __init__(self, data):
        # Define the format string for struct.unpack
        fmt = '<10I'
        unpacked_data = struct.unpack(fmt, data)

        self.version_format_2ndID = unpacked_data[0]
        self.file_offset_supplementary_data = unpacked_data[1]
        self.file_offset_primary_index = unpacked_data[2]
        self.file_offset_configuration_data_index = unpacked_data[3]
        self.file_offset_authentication_data = unpacked_data[4]
        self.file_offset_configuration_data_entries = unpacked_data[5]
        self.number_of_entries_in_primary_index = unpacked_data[6]
        self.number_of_entries_in_configuration_index = unpacked_data[7]
        self.bytes_of_configuration_data_stored = unpacked_data[8]
        self.bits_of_presentation_timestamp = unpacked_data[9]


class ContentFrameHeader:
    def __init__(self, data):
        # Define the format string for struct.unpack
        fmt = '<IIIIHQ'
        unpacked_data = struct.unpack(fmt, data)

        self.file_offset_to_frame_entry = unpacked_data[0]
        self.frame_size = unpacked_data[1]
        self.frame_type_and_gop = unpacked_data[2]
        self.date_time = unpacked_data[3]
        self.seconds_and_frame_index = unpacked_data[4]
        self.bits_of_presentation_timestamp = unpacked_data[5]


class ContentFrameInPlaceHeader:
    def __init__(self, data):
        # Define the format string for struct.unpack
        fmt = '<I'
        unpacked_data = struct.unpack(fmt, data)

        self.S = unpacked_data[0] >> 1 & 0b1
        self.decoder_configuration_data_index = unpacked_data[0] >> 17 & 0b1111111111111111
        self.frame_time_stamp_millisecond = unpacked_data[0] >> 18 & 0b1111111111


class ConfigurationDataHeader:
    def __init__(self, data):
        fmt = '<II'
        unpacked_data = struct.unpack(fmt, data)

        self.offset = unpacked_data[0]
        self.size = unpacked_data[1]


def read_from_file(file_data):
    buffer = io.BytesIO(file_data)
    count = 0
    # logger.info(datetime.datetime.now())
    # logger.info(f"FILES {files}")
    # for file in files:
    # time.sleep(1)
    # logger.info(f"Reading file {file}")
    # with open(file, 'rb') as f:
    data = buffer.read(8)
    if len(data) < 8:
        # raise ValueError("File too short to contain a valid header")
        return None, "Error - File too short to contain a valid header"

    header = RawSynAV2ComponentHeader(data)
    # print(header.FileID)
    # print(count)
    if header.FileID != 'SYN-AV-2':
        print("File ID is not SYN-AV-2")
        return None , "Error in Header"
    data = buffer.read(40)
    header2 = RawSynAV2ComponentHeader2(data)

    major_version = header2.version_format_2ndID & 0b1111  # bits 0-3
    minor_version = (header2.version_format_2ndID >> 4) & 0b1111  # bits 4-7
    stream_format = (header2.version_format_2ndID >> 8) & 0b11111111
    secondary_ID_tag_1st = (header2.version_format_2ndID >> 16) & 0b11111111
    secondary_ID_tag_2nd = (header2.version_format_2ndID >> 24) & 0b11111111
    # file_offset_supplementary_data = header2.file_offset_supplementary_data
    file_offset_primary_index = header2.file_offset_primary_index
    file_offset_configuration_data_index = header2.file_offset_configuration_data_index
    # file_offset_authentication_data = header2.file_offset_authentication_data
    file_offset_configuration_data_entries = header2.file_offset_configuration_data_entries
    number_of_entries_in_primary_index = header2.number_of_entries_in_primary_index
    number_of_entries_in_configuration_index = header2.number_of_entries_in_configuration_index
    bytes_of_configuration_data_stored = header2.bytes_of_configuration_data_stored
    # bits_of_presentation_timestamp = header2.bits_of_presentation_timestamp

    # print("Major Version:", major_version)
    # print("Minor Version:", minor_version)
    # print("Stream Format:", stream_format)
    # print("2nd ID Tag:", chr(secondary_ID_tag_1st) + chr(secondary_ID_tag_2nd))
    buffer.seek(file_offset_configuration_data_index)
    config_header_data = buffer.read(8)
    config_header = ConfigurationDataHeader(config_header_data)
    offset_within_configuration_data_entries = config_header.offset
    length_of_configuration_data = config_header.size
    buffer.seek(file_offset_configuration_data_entries)
    configuration_data = buffer.read(length_of_configuration_data)
    frame = bytearray(configuration_data)
    integer_value = int.from_bytes(configuration_data[0:4], byteorder='big')
    frame[0:4] = b'\x00\x00\x00\x01'
    start = integer_value + 4
    end = integer_value + 4 + 4
    frame[start:end] = b'\x00\x00\x00\x01'
    configuration_data = bytes(frame)
    buffer.seek(file_offset_primary_index)
    frames = []
    for frame_primary_index in range(number_of_entries_in_primary_index):
        data = buffer.read(26)
        frame_data_header = ContentFrameHeader(data)
        file_offset_to_frame_entry = frame_data_header.file_offset_to_frame_entry
        frame_size = frame_data_header.frame_size & 0b11111111111111111111111
        size_of_data = frame_data_header.frame_size >> 23
        frame_type = frame_data_header.frame_type_and_gop & 0b111
        frames.append((file_offset_to_frame_entry, frame_size, frame_type, size_of_data))
    frames_processed = 0
    # logger.info(f"frames {frames}")
    for frame_count, frame in enumerate(frames):
        # f.seek(frames[0][0])
        # inplace_header = ContentFrameInPlaceHeader(f.read(4))
        # can delete this loop later as we only want 1 frame anyway.
        # logger.info(f"frames_processed {frames_processed}")

        offset = frame[0]
        size = frame[1]
        # size_of_nal = 4

        buffer.seek(offset + 4)  # Add 4 bytes for Frame in place header.
        # now read the frame
        in_bytes = buffer.read(size)
        # logger.info(f"in_bytes length {len(in_bytes)}")
        # move the bytes into a bytearray, so we can manipulate the NAL's
        # frame = bytearray(in_bytes)


        nal_offset = 0
        nal_count = 0
        nal_positions = []
        frame = bytearray(in_bytes)

        while nal_offset < len(in_bytes):
            if nal_offset + 4 > len(in_bytes):
                return None, "Error in NAL offset"
            nal_size = int.from_bytes(in_bytes[nal_offset: nal_offset + 4], byteorder='big')
            if nal_offset + nal_size > len(in_bytes):
                return None, "Error in NAL offset"
            nal_count += 1
            nal_offset += nal_size + 4

            nal_positions.append(nal_offset)
            pass
        nal_positions.insert(0, 0)
        for position in nal_positions:
            frame[position:position + 4] = b'\x00\x00\x00\x01'

        in_bytes = bytes(frame)
        in_bytes = configuration_data + in_bytes
        # with open("/tmp/image.h264", "wb") as wf:
        #     wf.write(in_bytes)
        #     wf.close()
        image_bytes, status = decode_frame(in_bytes)

        # logger.info(f"image_bytes {len(image_bytes)} {image_bytes}")
        if not image_bytes:
            print("Error decoding data", )
            return None, "Error Decoding"
        np_array = np.frombuffer(image_bytes, np.uint8)
        # Decode image from the NumPy array
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)
        h, w, _ = img.shape
        print(count, "Decoded image", h, w)
        frames_processed += 1
        if frames_processed == 1:
            return img, "Success"
    return img, "Success"

            # img = cv2.resize(img, (int(w/2), int(h/2)), interpolation=cv2.INTER_AREA)
            # cv2.imshow('frame', img)
            # cv2.waitKey(1)
            # count += 1
            # frames_processed += 1
            # logger.info(count, "Decoded image", file, h, w)
    # print("Total successful reads", count)
    # logger.info(f"Total successful reads {count}")


for part in d.parts:
    print("Part Headers:", part.headers)
    filename = "/tmp/" + part.headers[b'content-disposition'].decode('utf-8').split('"')[3]
    print("Filename:", filename)

    # f = open(filename, 'wb')
    # f.write(part.content)
    binary_data = part.content
    image, status = read_from_file(binary_data)
    h, w, c = image.shape
    image = cv2.resize(image, (int(h/2), int(w/2)), interpolation=cv2.INTER_AREA)
    cv2.imshow("Image", image)
    cv2.waitKey(0)