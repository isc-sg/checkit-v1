import datetime
import os
# import multiprocessing
import pathos
import math
from sys import exit
import cython

import mysql.connector
from mysql.connector import errorcode
import subprocess
from passlib.hash import sha512_crypt
import process_list_v2
import logging
from logging.handlers import RotatingFileHandler
import hashlib

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                               '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                    handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                  maxBytes=10000000, backupCount=10)])

checkit_secret = "Checkit65911760424"[::-1].encode()

key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='


def get_encrypted(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def get_mysql_password():
    fd = open("/etc/machine-id", "r")
    machine_id = fd.read()
    machine_id = machine_id.strip("\n")

    shell_output = subprocess.check_output("/bin/df", shell=True)
    l1 = shell_output.decode('utf-8').split("\n")
    command = "mount | sed -n 's|^/dev/\(.*\) on / .*|\\1|p'"
    root_dev = subprocess.check_output(command, shell=True).decode().strip("\n")

    command = "/usr/bin/sudo /sbin/blkid | grep " + root_dev
    root_fs_uuid = subprocess.check_output(command, shell=True).decode().split(" ")[1].split("UUID=")[1].strip("\"")

    command = "/usr/bin/sudo dmidecode | grep -i uuid"
    product_uuid = subprocess.check_output(command, shell=True).decode(). \
        strip("\n").strip("\t").split("UUID:")[1].strip(" ")

    finger_print = (root_fs_uuid + machine_id + product_uuid)
    fingerprint_encrypted = get_encrypted(finger_print)
    mysql_password = fingerprint_encrypted[10:42][::-1]
    return mysql_password


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
            command = "/usr/bin/sudo /sbin/blkid | grep " + line[0]
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
            finger_print = uuid+machine_id+em
            hash1 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(finger_print)

    key = hash1.split("$6$rounds="+str(rounds) + "$" + salt + "$")
    seg = ''.join(reversed(key[1][11:65]))
    h2 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(seg)
    pw = h2.split("$6$rounds="+str(rounds) + "$" + salt + "$")
    return key[1], pw[1]


def check_license():
    # replace below with code to open adm
    # get fingerprint data from machine use this along with 3 parameters to create license
    license_file = open("/etc/checkit/checkit.lic", "r")
    registered_key = license_file.readline().strip('\n')
    email = license_file.readline().strip('\n')
    license_key, password = create_key(email)
    if license_key != registered_key:
        logging.error("Licensing error")
        exit(1)
    return license_key, password


def check_main_databases_initialised():
    try:
        checkit_db = mysql.connector.connect(
            host="localhost",
            user="checkit",
            password="checkit",
            database="checkit"
        )
        return checkit_db
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error("Invalid password on main database")
            exit(1)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logging.error("Database not initialised")
            exit(1)


def get_camera_ids(camera_numbers, checkit_cursor):
    if camera_numbers:
        joined_string = ' '.join(map(str, camera_numbers))
        sql_statement = "SELECT id FROM main_menu_camera " + "WHERE camera_number in " + "(" + joined_string + ")"
    else:
        # sql_statement = "SELECT id FROM main_menu_camera"

        current_hour = datetime.datetime.now().hour
        current_day = datetime.datetime.now().strftime("%A")

        sql_statement = """select id from main_menu_daysofweek where day_of_the_week = """ + "\"" + current_day + "\""
        checkit_cursor.execute(sql_statement)
        day_index = checkit_cursor.fetchone()[0]

        sql_statement = """select id from main_menu_hoursinday where hour_in_the_day = """ + str(current_hour)
        checkit_cursor.execute(sql_statement)
        hour_index = checkit_cursor.fetchone()[0]

        sql_statement = "SELECT main_menu_camera_scheduled_hours.camera_id FROM main_menu_camera_scheduled_hours " \
                        "JOIN main_menu_camera_scheduled_days " \
                        "ON main_menu_camera_scheduled_days.camera_id = main_menu_camera_scheduled_hours.camera_id " \
                        "WHERE main_menu_camera_scheduled_days.daysofweek_id = " + str(day_index) + \
                        " AND main_menu_camera_scheduled_hours.hoursinday_id = " + str(hour_index)

    try:
        # checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement)
        z = checkit_cursor.fetchall()
        ids = [x[0] for x in z]
        # print(ids)
    except mysql.connector.Error as e:
        logging.error(f"Database connection error {e} {sql_statement}")
        exit(1)
    return ids


def check_adm_database(password):
    adm_db_config = {
        "host": "localhost",
        "user": "root",
        "password": password,
        "database": "adm"
    }

    try:
        adm_db = mysql.connector.connect(**adm_db_config)
        admin_cursor = adm_db.cursor()
        sql_statement = "SELECT * FROM adm ORDER BY id DESC LIMIT 1"
        admin_cursor.execute(sql_statement)
        result = admin_cursor.fetchone()
        if not result:
            logging.error("License not setup")
            exit(33)
        field_names = [i[0] for i in admin_cursor.description]

        transaction_count_index = field_names.index('tx_count')
        transaction_limit_index = field_names.index('tx_limit')
        end_date_index = field_names.index('end_date')
        camera_limit_index = field_names.index('camera_limit')
        customer_name_index = field_names.index('customer_name')
        site_name_index = field_names.index('site_name')
        license_key_index = field_names.index('license_key')

        transaction_count = result[transaction_count_index]
        transaction_limit = result[transaction_limit_index]
        end_date = result[end_date_index]
        camera_limit = result[camera_limit_index]
        customer_name = result[customer_name_index]
        site_name = result[site_name_index]
        license_key = result[license_key_index]

        adm_db.close()
        return transaction_count, transaction_limit, end_date, camera_limit, customer_name, site_name, license_key

    except mysql.connector.Error as e:
        logging.error(f"Database connection error {e}")
        exit(1)


# sync up checkit and adm data - in case checkit has been manually modified.


def sync_adm_and_main_databases(checkit_db, transaction_count, transaction_limit, end_date, camera_limit, license_key, customer_name, site_name):
    try:
        checkit_cursor = checkit_db.cursor()
        sql = "SELECT * FROM main_menu_licensing"
        checkit_cursor.execute(sql)
        result = checkit_cursor.fetchone()
        if result:
            sql = "UPDATE main_menu_licensing SET transaction_count =  " + str(transaction_count) + ", " + \
                  "transaction_limit = " + str(transaction_limit) + " , " + \
                  "end_date = " + "\"" + end_date.strftime('%Y-%m-%d') + "\" , " \
                  "license_key = " + "\"" + license_key + "\"" + " ORDER BY id DESC LIMIT 1"
            # print(sql)
            checkit_cursor.execute(sql)
        else:
            sql = """INSERT INTO main_menu_licensing (transaction_count, transaction_limit, end_date, license_key, license_owner, site_name, start_date, run_schedule) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
            values = (transaction_count, transaction_limit, str(end_date), license_key, customer_name, site_name, datetime.datetime.now().strftime("%Y-%m-%d"), 0)
            # print(sql, values)
            checkit_cursor.execute(sql, values)
        checkit_db.commit()
    except mysql.connector.Error as e:
        logging.error(f"Database connection error {e}")

    if transaction_count >= transaction_limit or datetime.date.today() > end_date:
        logging.error("Licenses expired or transaction limit reached")
        exit(1)
    camera_count = 0

    try:
        checkit_cursor = checkit_db.cursor()
        sql = "SELECT COUNT(id) from main_menu_camera"
        checkit_cursor.execute(sql)
        camera_count = checkit_cursor.fetchone()[0]

    except mysql.connector.Error as e:
        logging.error(f"Database connection error {e}")

    if camera_count > camera_limit:
        logging.error("Camera limit reached")
        exit(1)


def check_engine_state(checkit_db):
    checkit_cursor = checkit_db.cursor()
    checkit_cursor.execute("SELECT * FROM main_menu_enginestate ORDER BY id DESC LIMIT 1")
    checkit_result = checkit_cursor.fetchone()
    field_names = [i[0] for i in checkit_cursor.description]

    state_index = field_names.index('state')
    transaction_rate_index = field_names.index('transaction_rate')
    engine_process_id_index = field_names.index('engine_process_id')
    state_timestamp_index = field_names.index('state_timestamp')

    # this will get the last record/state in the state file
    # this format allows us to keep a history the engine states
    # should always be started followed by stopped - if not then engine crashed or still running
    # use process id field in table to check if its actually running

    # initialise for first time
    state_timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
    state = "STARTED"
    engine_process_id = os.getpid()
    transaction_rate = 0

    if checkit_result is None:
        # this is needed if there are no records in enginestate table ( ie first time run )
        sql_statement = "INSERT INTO main_menu_enginestate " \
                        "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images)" \
                        " VALUES (%s,%s,%s,%s,%s)"
        values = (state, engine_process_id, transaction_rate, state_timestamp, 0)

        # checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement, values)
        checkit_db.commit()

    else:

        state = checkit_result[state_index]
        transaction_rate = checkit_result[transaction_rate_index]
        state_timestamp = checkit_result[state_timestamp_index]
        engine_process_id = checkit_result[engine_process_id_index]

    try:
        os.kill(engine_process_id, 0)
    except OSError:
        process_state = "NOT RUNNING"
    else:
        process_state = "RUNNING"

    if state == "STARTED":
        if process_state == "RUNNING":
            logging.info("Engine already running - exiting")
            exit(0)

        # exit gracefully because engine is running

        # no need to check for state = "STOPPED" just start it.
        # just make sure we add a record at the end of processing to state STOPPED
        # start the engine because the process_state not running so engine must have crashed ie state != STARTED and
        # process_state = "NOT RUNNING"
        # lines below add ERROR entry to show improper exit of previous engine run

    if state == "STARTED" and process_state == "NOT RUNNING":
        state = "ERROR"
        state_timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
        sql_statement = "INSERT INTO main_menu_enginestate " \
                        "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images)" \
                        " VALUES (%s,%s,%s,%s,%s)"
        values = (state, engine_process_id, transaction_rate, state_timestamp, 0)
        logging.info("transaction rate %s", transaction_rate)
        logging.error("Last run failed to exit properly")
        # checkit_cursor = checkit_db.cursor()
        checkit_cursor.execute(sql_statement, values)
        checkit_db.commit()

    # now insert a STARTED state for this process
    start_state_timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
    state = "STARTED"
    engine_process_id = os.getpid()
    transaction_rate = 0

    sql_statement = "INSERT INTO main_menu_enginestate " \
                    "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images)" \
                    " VALUES (%s,%s,%s,%s,%s)"
    values = (state, engine_process_id, transaction_rate, start_state_timestamp, 0)

    # checkit_cursor = checkit_db.cursor()
    checkit_cursor.execute(sql_statement, values)
    checkit_db.commit()
    return start_state_timestamp


def calculate_transaction_rate(checkit_cursor, start_state_timestamp):
    sql_statement = "SELECT COUNT(*) FROM main_menu_logimage WHERE creation_date > " +\
                    "\"" + start_state_timestamp + "\""
    # below used for testing
    # sql_statement = "SELECT COUNT(*) FROM main_menu_logimage WHERE creation_date > " + "\"" + "2021-07-08" + "\""

    checkit_cursor.execute(sql_statement)
    checkit_result = checkit_cursor.fetchall()[0][0]
    time_elapsed = datetime.datetime.now() - datetime.datetime.strptime(start_state_timestamp, "%Y-%m-%d %H:%M:%S.%f")
    time_elapsed = time_elapsed.seconds
    try:
        tr = checkit_result/time_elapsed
    except ZeroDivisionError:
        tr = 0
    return tr


def count_failed(checkit_cursor, start_state_timestamp):
    sql_statement = """SELECT COUNT(*) FROM main_menu_logimage WHERE action = "Failed" AND creation_date > """ +\
                    "\"" + start_state_timestamp + "\""
    checkit_cursor.execute(sql_statement)
    checkit_result = checkit_cursor.fetchall()[0][0]
    return checkit_result


def shutdown_engine_state(start_state_timestamp):
    state_timestamp = datetime.datetime.strftime(datetime.datetime.now(), "%Y-%m-%d %H:%M:%S.%f")
    state = "RUN COMPLETED"
    engine_process_id = os.getpid()

    try:
        checkit_db = mysql.connector.connect(
            host="localhost",
            user="checkit",
            password="checkit",
            database="checkit"
        )
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            logging.error("Invalid password on main database")
            exit(1)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            logging.error("Database not initialised")
            exit(1)

    checkit_cursor = checkit_db.cursor()

    transaction_rate = calculate_transaction_rate(checkit_cursor, start_state_timestamp)
    fails = count_failed(checkit_cursor, start_state_timestamp)
    sql_statement = "INSERT INTO main_menu_enginestate " \
                    "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images)" \
                    " VALUES (%s,%s,%s,%s,%s)"
    values = (state, engine_process_id, transaction_rate, state_timestamp, fails)
    logging.info("Run completed")
    checkit_cursor.execute(sql_statement, values)
    checkit_db.commit()
    checkit_db.close()


def main(ids):
    checkit_db = check_main_databases_initialised()
    checkit_cursor = checkit_db.cursor()
    mysql_password = get_mysql_password()
    transaction_count, transaction_limit, end_date, camera_limit, customer_name, site_name, license_key = check_adm_database(mysql_password)
    sync_adm_and_main_databases(checkit_db, transaction_count, transaction_limit, end_date, camera_limit, license_key, customer_name, site_name)
    start_state_timestamp = check_engine_state(checkit_db)

    list_of_cameras = get_camera_ids(ids, checkit_cursor)
    list_pointer = 0

    number_of_cores = pathos.multiprocessing.cpu_count()*4
    incrementer = math.ceil(len(list_of_cameras)/number_of_cores)
    list_of_lists = []
    while len(list_of_cameras[list_pointer:list_pointer + incrementer]) > 0:
        list_to_process = list_of_cameras[list_pointer:list_pointer + incrementer]
        list_of_lists.append(list_to_process)
        list_pointer += incrementer
    #
    # logging.info(f"about to process list, {list_of_lists}")
    process_list_v2.start_processes(list_of_lists)
    # logging.info("c4 done process")
    shutdown_engine_state(start_state_timestamp)


if __name__ == '__main__':
    main()


# this will compare last_check_date which includes time as well but still returns values less than today's date
# sql_statement = "SELECT * FROM main_menu_camera WHERE last_check_date < " + \
#                 "\"" + datetime.date.today().strftime("%Y-%m-%d") + "\""
# print(sql_statement)

# create API to report "status" - "start" - "stop" - "transaction_count" ( number of entries in log )

# read config file - how often do I run this - also check number of transactions
# class or def to get list call engine start
# set state flag running or stopped
# get list of urls to scan - should be all cameras in DB - if dont want to scan then delete the url
# check if base image exists - if not then get and report ( work out logging method )
# maybe add field to log file which is action - "base_scan" - "compared" - "not_reachable"

# new class - get base image.
# get image and look for people - blank out quadrant with people - up to 16

# new class
# use list as feed to multi-threaded engine via a queue
# use queue length to report cameras remaining to scan - status of engine


# insert records for proper shutdown
# time.sleep(10)

#
# image_a = cv2.imread(args.file1)
# image_b = cv2.imread(args.file2)
#
# image_a_grey = cv2.cvtColor(image_a, cv2.COLOR_BGR2GRAY)
# image_b_grey = cv2.cvtColor(image_b, cv2.COLOR_BGR2GRAY)
#
# compare_images(image_a_grey, image_b_grey, "ImageA vs. ImageB")
#
# height, width, a = image_a.shape
# alpha = 0.5
# beta = (1.0 - alpha)
# for r in range(0, height, int(height / 4)):
#     for c in range(0, width, int(width / 4)):
#         image_sedecimant_a = image_a_grey[r:r + int(height / 4), c:c + int(width / 4)]
#         image_sedecimant_b = image_b_grey[r:r + int(height / 4), c:c + int(width / 4)]
#         cv2.imshow("Image A", image_sedecimant_a)
#         cv2.imshow("Image B", image_sedecimant_b)
#         dst = cv2.addWeighted(image_a, alpha, image_b, beta, 0.0)
#         # cv2.imshow("Blended A/B", dst)
#         # cv2.resizeWindow("Blended A/B", 480, 270)
#
#         compare_images(image_sedecimant_a, image_sedecimant_b, "Segment")
#
#         cv2.waitKey(0)
