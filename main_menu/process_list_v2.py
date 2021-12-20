import datetime
import json
import os
import pathlib
import time

from sys import exit
from skimage.metrics import structural_similarity as ssim
import cv2
import mysql.connector
from mysql.connector.pooling import MySQLConnectionPool
from mysql.connector import errorcode
import multiprocessing as mp
import subprocess
from passlib.hash import sha512_crypt
import logging


import select_region as select_region

# list_to_process = 3573
# list_to_process = sys.argv[1].split(",")


def create_key(em):
    hash1 = ''
    salt = ''.join(reversed("Checkit"))
    rounds = 656911

    f = open("/etc/machine-id", "r")
    machine_id = f.read()
    machine_id = machine_id.strip("\n")
    shell_output = subprocess.check_output("/bin/df", shell=True)
    l1 = shell_output.decode('utf-8').split("\n")

    for i in l1:
        line = i.split(" ")
        if line[-1] == "/":
            command = "/sbin/blkid | grep " + line[0]
            uuid = ""
            try:
                shell_output = subprocess.check_output(command, shell=True)
            except subprocess.CalledProcessError as error:
                f = open("/etc/fstab", "r")
                fstab_file = f.read()
                fstab_list = fstab_file.split("\n")
                for fstab_line in fstab_list:
                    if fstab_line[0:1] != '#' and fstab_line != '':
                        fstab_line_elements = fstab_line.split()
                        if fstab_line_elements[1] == "/":
                            uuid = fstab_line.split("/dev/disk/by-uuid/")[1].split()[0]
            else:
                l2 = shell_output.decode('utf-8').split(" ")
                uuid = l2[1].strip("UUID=").strip("\"")
            finger_print = uuid + machine_id + em
            hash1 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(finger_print)

    key = hash1.split("$6$rounds=" + str(rounds) + "$" + salt + "$")
    seg = ''.join(reversed(key[1][11:65]))
    h2 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(seg)
    pw = h2.split("$6$rounds=" + str(rounds) + "$" + salt + "$")
    return key[1], pw[1]


# check for license validity
license_file = open("/etc/checkit/checkit.lic", "r")
registered_key = license_file.readline().strip('\n')
email = license_file.readline().strip('\n')
license_key, password = create_key(email)
if license_key != registered_key:
    logging.error("Licensing error")
    exit(0)

# initialise global variables.
pool_for_checkit = None
pool_for_adm = None
camera_id_index = None
camera_url_index = None
camera_number_index = None
camera_name_index = None
image_regions_index = None
matching_threshold_index = None
slug_index = None
reference_image_id_index = None
reference_image_url_index = None
reference_image_index = None


def init_pools():
    global pool_for_checkit
    global pool_for_adm
    global camera_id_index
    global camera_url_index
    global camera_number_index
    global camera_name_index
    global image_regions_index
    global matching_threshold_index
    global slug_index
    global reference_image_id_index
    global reference_image_url_index
    global reference_image_index
    # print("PID %d: initializing pool..." % os.getpid())
    try:
        db_config_checkit = {
            "host": "localhost",
            "user": "checkit",
            "password": "checkit",
            "database": "checkit"
        }
        pool_for_checkit = MySQLConnectionPool(pool_name="pool_for_checkit",
                                               pool_size=2,
                                               connection_timeout=4,
                                               **db_config_checkit)
        connection = pool_for_checkit.get_connection()
        checkit_cursor = connection.cursor()
        checkit_cursor.execute("SELECT * FROM main_menu_camera LIMIT 1")
        checkit_result = checkit_cursor.fetchone()

        field_names = [i[0] for i in checkit_cursor.description]

        camera_id_index = field_names.index('id')
        camera_url_index = field_names.index('url')
        camera_number_index = field_names.index('camera_number')
        camera_name_index = field_names.index('camera_name')
        image_regions_index = field_names.index('image_regions')
        matching_threshold_index = field_names.index('matching_threshold')
        slug_index = field_names.index('slug')

        checkit_cursor.execute("SELECT * FROM main_menu_referenceimage LIMIT 1")
        checkit_result = checkit_cursor.fetchone()

        field_names = [i[0] for i in checkit_cursor.description]
        reference_image_id_index = field_names.index('id')
        reference_image_url_index = field_names.index('url_id')
        reference_image_index = field_names.index('image')
        connection.close()

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Invalid password on main database")
            exit(0)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database not initialised")
            exit(0)

    try:

        adm_db_config = {
            "host": "localhost",
            "user": "root",
            "password": password,
            "database": "adm"
        }
        pool_for_adm = MySQLConnectionPool(pool_name="pool_for_checkit",
                                           pool_size=2,
                                           connection_timeout=4,
                                           **adm_db_config)
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Invalid password")
            exit(0)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database not initialised")
            exit(0)


def compare_images(base, frame, r):
    # r = ['1', '3', '5', '29', '8', '11', '24', '44', '55', '64']
    h, w = frame.shape[:2]
    all_regions = []
    all_regions.extend(range(1, 65))
    region_scores = {}
    coordinates = select_region.get_coordinates(all_regions, h, w)
    scores = []
    # full_ss = ssim(base, frame)
    frame_equalised = cv2.equalizeHist(frame)
    based_equalised = cv2.equalizeHist(base)
    full_ss = ssim(based_equalised, frame_equalised)
    count = 0
    for i in coordinates:
        (x, y), (qw, qh) = i
        sub_img_frame = frame_equalised[y:y + qh, x:x + qw]
        sub_img_base = based_equalised[y:y + qh, x:x + qw]
        # cv2.imshow("sub of frame", sub_img_frame)
        # cv2.imshow("sub of base", sub_img_base)
        # cv2.waitKey(0)
        ss = 0
        try:
            ss = ssim(sub_img_base, sub_img_frame)
        except Exception as e:
            print(e)

        # scores.append(ss)
        # print("region", count, "score", round(ss, 2))
        count += 1
        region_scores[count] = round(ss, 2)
    # print("r is ", r)
    # print("Region scores are", region_scores)
    for i in r:
        ss = region_scores[int(i)]
        scores.append(ss)
    # scores_average = mean(scores)

    # print("Scores list is ", scores)
    number_of_regions = len(r)
    # print('number of regions ', number_of_regions)
    scores.sort(reverse=True)
    sum_scores = sum(scores)

    scores_average = sum_scores / number_of_regions
    # print("scores", scores)

    fv = cv2.Laplacian(frame, cv2.CV_64F).var()
    # print("Focus Score is %.2f" % fv)
    if scores_average > full_ss:
        full_ss = scores_average
    full_ss = round(full_ss, 2)
    scores_average = round(scores_average, 2)
    fv = round(fv, 2)
    logging.debug(f"Match Score for full image is {full_ss}")
    logging.debug(f"Match Score for regions is {scores_average}")
    logging.debug(f"Focus value is {fv}")
    logging.debug(f"All region scores are {region_scores}")

    return full_ss, fv, region_scores


def no_base_image(record):
    # connection = connection_pool.get_connection()
    # checkit_cursor = connection.cursor()
    logging.debug(f"No base image for {record}")
    try:
        capture_device = cv2.VideoCapture(record[camera_url_index])
        if not capture_device.isOpened():
            raise NameError()
    except cv2.error as e:
        logging.error(f"cv2 error {e}")
    except NameError:
        logging.error(f"Unable to read camera {record[camera_number_index]} - {record[camera_name_index]}")

        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")

        connected = False
        while not connected:
            try:
                connection = pool_for_checkit.get_connection()
                checkit_cursor = connection.cursor()

                sql_statement = "INSERT INTO main_menu_logimage " \
                                "(url_id, image, matching_score, region_scores, current_matching_threshold, " \
                                "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                values = (str(record[camera_id_index]), "", "0", "0", "0", "0", "Capture Error", now)

                checkit_cursor.execute(sql_statement, values)
                connection.commit()
                connection.close()
                connected = True
            except mysql.connector.Error as e:
                logging.error(f"Database connection error {e}")
                connected = False

        # TODO: This looks wrong - think else captures all other exceptions
    else:
        try:
            able_to_read, frame = capture_device.read()
            if not able_to_read:
                raise NameError()
        except cv2.error as e:
            logging.error(f"cv2 error {e}")
        except NameError:
            logging.error(f"Unable to read camera {record[camera_number_index]} - {record[camera_name_index]}")
        else:
            logging.debug(f"Able to capture base image on {record[camera_name_index]}")
            time_stamp = datetime.datetime.now()
            file_name = "/home/checkit/camera_checker/media/base_images/" + record[slug_index] + "/" + \
                        time_stamp.strftime('%H') + ".jpg"
            directory = "/home/checkit/camera_checker/media/base_images/" + record[slug_index]

            try:
                pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                if not os.path.isfile(file_name):
                    cv2.imwrite(file_name, frame)

                    connected = False
                    while not connected:
                        try:
                            connection = pool_for_checkit.get_connection()
                            checkit_cursor = connection.cursor()
                            sql_file_name = file_name.strip("/home/checkit/camera_checker/media/")
                            sql_statement = "INSERT INTO main_menu_referenceimage " \
                                            "(url_id, image, hour)" \
                                            " VALUES (%s,%s,%s)"
                            values = (str(record[camera_id_index]), sql_file_name, time_stamp.strftime('%H'))
                            checkit_cursor.execute(sql_statement, values)

                            connection.commit()
                            connection.close()
                            connected = True
                        except mysql.connector.Error as e:
                            logging.error(f"Database connection error {e}")
                            connected = False

            except OSError as error:
                print(error)
            # increment_transaction_count()


def increment_transaction_count():
    connected = False
    while not connected:
        try:
            time.sleep(1)
            connection = pool_for_checkit.get_connection()
            checkit_cursor = connection.cursor()
            sql = "UPDATE main_menu_licensing SET transaction_count =  transaction_count + 1 WHERE id = 1"
            checkit_cursor.execute(sql)
            connection.commit()
            connection.close()
            connected = True
        except mysql.connector.Error as e:
            logging.error(f"Database connection error {e}")
            connected = False

    connected = False
    while not connected:
        try:
            adm_connection = pool_for_adm.get_connection()
            admin_cursor = adm_connection.cursor()
            sql = "UPDATE adm SET tx_count =  tx_count + 1 WHERE id = 1"
            admin_cursor.execute(sql)
            adm_connection.commit()
            adm_connection.close()
            connected = True
        except mysql.connector.Error as e:
            logging.error(f"Database connection error {e}")
            connected = False


def process_list(x):
    connected = False
    while not connected:
        try:
            connection = pool_for_checkit.get_connection()
            sql_statement = "SELECT * from main_menu_camera WHERE id = " + "\"" + str(x) + "\""
            cursor = connection.cursor()
            cursor.execute(sql_statement)
            current_record = cursor.fetchone()
            connection.close()
            connected = True
        except mysql.connector.Error as e:
            logging.error(f"Database connection error {e}")
            connected = False
    regions = current_record[image_regions_index]

    if regions == '0' or regions == "[]":
        regions = []
        regions.extend(range(1, 65))
    else:
        regions = eval(regions)
    current_time = datetime.datetime.now()
    connected = False
    while not connected:
        try:
            connection = pool_for_checkit.get_connection()
            hour = current_time.strftime('%H')
            sql_statement = "SELECT hour FROM main_menu_referenceimage WHERE url_id = " + "\"" \
                            + str(current_record[camera_id_index]) + "\""
            checkit_cursor = connection.cursor()
            checkit_cursor.execute(sql_statement)
            hours = checkit_cursor.fetchall()
            connection.close()
            connected = True

        except mysql.connector.Error as e:
            logging.error(f"Database connection error {e}")
            connected = False

    int_hours = []

    if hours:
        for i in range(0, len(hours)):
            int_hours.append(hours[i][0])
            int_hours[i] = int(int_hours[i])
        hour = int(hour)
        if hour not in int_hours:
            no_base_image(current_record)
        else:
            connected = False
            while not connected:
                try:
                    connection = pool_for_checkit.get_connection()
                    absolute_difference_function = lambda list_value: abs(list_value - hour)
                    closest_hour = min(int_hours, key=absolute_difference_function)
                    closest_hour = str(closest_hour).zfill(2)

                    sql_statement = "SELECT * FROM main_menu_referenceimage WHERE url_id = " + "\"" \
                                    + str(current_record[camera_id_index]) + "\"" + " AND hour = " \
                                    + "\"" + closest_hour + "\""
                    checkit_cursor = connection.cursor()
                    checkit_cursor.execute(sql_statement)
                    image = checkit_cursor.fetchone()
                    connection.close()
                    connected = True
                except mysql.connector.Error as e:
                    logging.error(f"Database connection error {e}")
                    connected = False

            image = image[1]

            # img = cv2.imread(os.path.join('/home/checkit/camera_checker/media/', str(image)))
            # height, width, channels = img.shape

            # TODO: logic if no reference images

            base_image = "/home/checkit/camera_checker/media/" + image
            # print("reading from camera", current_record[camera_name_index],
            #       current_record[camera_number_index], "and comparing with", base_image)
            try:
                # capture_device = cv2.VideoCapture(current_record[camera_url_index])
                capture_device = cv2.VideoCapture(current_record[camera_url_index], cv2.CAP_FFMPEG)
            except cv2.error as err:
                logging.error(f"Error reading video {e}")
            # print("read frame")
            ret, image_frame = capture_device.read()

            if ret:
                image_base = cv2.imread(base_image)
                time_stamp = datetime.datetime.now()
                time_stamp_string = datetime.datetime.strftime(time_stamp, "%Y-%m-%d %H:%M:%S.%f")
                directory = "/home/checkit/camera_checker/media/logs/" + str(time_stamp.year) + "/" + \
                            str(time_stamp.month) + "/" + str(time_stamp.day)
                log_image_file_name = directory + "/" + str(current_record[camera_id_index]) + \
                                      "-" + str(time_stamp.hour) + ":" + str(time_stamp.minute) + ":" + \
                                      str(time_stamp.second) + ".jpg"

                try:
                    pathlib.Path(directory).mkdir(parents=True, exist_ok=True)
                except OSError as error:
                    logging.error(f"Error saving log file {e}")

                cv2.imwrite(log_image_file_name, image_frame)
                # write the log file - create variable to store in DB
                image_base_grey = cv2.cvtColor(image_base, cv2.COLOR_BGR2GRAY)
                image_frame_grey = cv2.cvtColor(image_frame, cv2.COLOR_BGR2GRAY)
                reference_dimensions = image_base_grey.shape[:2]
                capture_dimensions = image_frame_grey.shape[:2]
                # print(reference_dimensions, capture_dimensions)
                if reference_dimensions != capture_dimensions:
                    logging.error(f"Image sizes don't match on camera number {current_record[camera_number_index]}")
                    # TODO: clean up below - replicated and no need
                    now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
                    sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                    sql_statement = "INSERT INTO main_menu_logimage " \
                                    "(url_id, image, matching_score, region_scores, current_matching_threshold, " \
                                    "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                    values = (str(current_record[camera_id_index]), sql_file_name,
                              "0", "{}", "0", "0", "Image Size Error", now)
                    connected = False
                    while not connected:
                        try:
                            connection = pool_for_checkit.get_connection()
                            checkit_cursor = connection.cursor()
                            checkit_cursor.execute(sql_statement, values)
                            connection.commit()
                            connection.close()
                            connected = True
                        except mysql.connector.Error as e:
                            logging.error(f"Database connection error {e}")
                            connected = False

                    increment_transaction_count()
                else:
                    matching_score, focus_value, region_scores = compare_images(image_base_grey,
                                                                                image_frame_grey, regions)
                    sql_file_name = log_image_file_name.strip("/home/checkit/camera_checker/media/")
                    if matching_score < current_record[matching_threshold_index]:
                        action = "Failed"
                    else:
                        action = "Pass"

                    connected = False
                    while not connected:
                        try:
                            connection = pool_for_checkit.get_connection()
                            sql_statement = "INSERT INTO main_menu_logimage " \
                                            "(url_id, image, matching_score, region_scores, " \
                                            "current_matching_threshold, " \
                                            "focus_value, action, creation_date) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                            values = (str(current_record[camera_id_index]), sql_file_name, float(matching_score),
                                      json.dumps(region_scores),
                                      float(current_record[matching_threshold_index]), float(focus_value),
                                      action, time_stamp_string)
                            checkit_cursor.execute(sql_statement, values)
                            connection.commit()

                            sql_statement = "UPDATE main_menu_camera SET  last_check_date = " + "\"" + \
                                            time_stamp_string + "\"" + " WHERE id = " + "\"" + str(
                                current_record[camera_id_index]) + "\""

                            checkit_cursor.execute(sql_statement)
                            connection.commit()
                            connection.close()
                            connected = True
                        except mysql.connector.Error as e:
                            logging.error(f"Database connection error {e}")
                            connected = False

                    increment_transaction_count()
            else:
                # print("unable to read")
                connected = False
                while not connected:
                    try:
                        connection = pool_for_checkit.get_connection()
                        now = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")

                        sql_statement = "INSERT INTO main_menu_logimage " \
                                        "(url_id, image, matching_score, region_scores, " \
                                        "current_matching_threshold, focus_value, action, creation_date) " \
                                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
                        values = (str(current_record[camera_id_index]), "", "0", "{}", "0", "0", "Capture Error", now)

                        checkit_cursor = connection.cursor()
                        checkit_cursor.execute(sql_statement, values)
                        connection.commit()
                        connection.close()
                        connected = True
                    except mysql.connector.Error as e:
                        logging.error(f"Database connection error {e}")
                        connected = False

                increment_transaction_count()
    else:
        # only gets here with new camera
        logging.info(f"No base image for camera number {current_record[camera_number_index]} - "
                     f"{current_record[camera_name_index]}")
        no_base_image(current_record)
        increment_transaction_count()


def main(list_to_process):
    logging.info(f"Processing list {list_to_process}")
    mp.set_start_method("fork")
    with mp.Pool(32, initializer=init_pools) as p:
        p.map(process_list, list_to_process)
    p.close()
    p.join()


if __name__ == '__main__':
    main()
