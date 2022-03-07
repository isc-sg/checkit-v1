import datetime
import os

from sys import exit
import sys

import mysql.connector
import cython
from mysql.connector import errorcode
import subprocess
from passlib.hash import sha512_crypt
import multiprocessing
import process_list_v2
import logging
from logging.handlers import RotatingFileHandler
import argparse


parser = argparse.ArgumentParser(description='Checkit image comparison')
parser.add_argument('list_of_cameras', metavar='N', type=int, nargs='*')
parser.add_argument('--debug', action='store_true',
                    help='set logging to debug level')

args = parser.parse_args()


if args.debug:
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                                   '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                        handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                      maxBytes=10000000, backupCount=10)])
else:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s [%(lineno)d] \t - '
                                                   '%(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                        handlers=[RotatingFileHandler('/home/checkit/camera_checker/logs/checkit.log',
                                                      maxBytes=10000000, backupCount=10)])


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


license_file = open("/etc/checkit/checkit.lic", "r")
registered_key = license_file.readline().strip('\n')
email = license_file.readline().strip('\n')
license_key, password = create_key(email)
if license_key != registered_key:
    logging.error("Licensing error")
    exit(1)

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

if args.list_of_cameras:
    joined_string = ' '.join(map(str, args.list_of_cameras))
    sql_statement = "SELECT id FROM main_menu_camera " + "WHERE camera_number in " + "(" + joined_string + ")"
else:
    sql_statement = "SELECT id FROM main_menu_camera"


try:
    checkit_cursor = checkit_db.cursor()
    checkit_cursor.execute(sql_statement)
    z = checkit_cursor.fetchall()
    list_to_process = [x[0] for x in z]
    # print(list_to_process)
except mysql.connector.Error as e:
    logging.error(f"Database connection error {e}")
    exit(1)

adm_db_config = {
    "host": "localhost",
    "user": "root",
    "password": password,
    "database": "adm"
}

adm_db = mysql.connector.connect(**adm_db_config)

try:
    admin_cursor = adm_db.cursor()
    sql_statement = "SELECT * FROM adm ORDER BY id DESC LIMIT 1"
    admin_cursor.execute(sql_statement)
    result = admin_cursor.fetchone()
    field_names = [i[0] for i in admin_cursor.description]

    transaction_count_index = field_names.index('tx_count')
    transaction_limit_index = field_names.index('tx_limit')
    end_date_index = field_names.index('end_date')
    camera_limit_index = field_names.index('camera_limit')

    transaction_count = result[transaction_count_index]
    transaction_limit = result[transaction_limit_index]
    end_date = result[end_date_index]
    camera_limit = result[camera_limit_index]

    adm_db.close()

except mysql.connector.Error as e:
    logging.error(f"Database connection error {e}")
    exit(1)

# sync up checkit and adm data - in case checkit has been manually modified.

try:
    checkit_cursor = checkit_db.cursor()
    sql = "UPDATE main_menu_licensing SET transaction_count =  " + str(transaction_count) + ", " + \
          "transaction_limit = " + str(transaction_limit) + " , " + \
          "end_date = " + "\"" + end_date.strftime('%Y-%m-%d') + "\" , " \
          "license_key = " + "\"" + license_key + "\"" + " ORDER BY id DESC LIMIT 1"
    checkit_cursor.execute(sql)
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


# checkit_cursor = checkit_db.cursor()
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
                    "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images) VALUES (%s,%s,%s,%s,%s)"
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
                    "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images) VALUES (%s,%s,%s,%s,%s)"
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
                "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images) VALUES (%s,%s,%s,%s,%s)"
values = (state, engine_process_id, transaction_rate, start_state_timestamp, 0)


# checkit_cursor = checkit_db.cursor()
checkit_cursor.execute(sql_statement, values)
checkit_db.commit()
current_process_row_id = checkit_cursor.lastrowid
# checkit_db.close


def calculate_transaction_rate():
    sql_statement = "SELECT COUNT(*) FROM main_menu_logimage WHERE creation_date > " + "\"" + start_state_timestamp + "\""
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


def count_failed():
    sql_statement = """SELECT COUNT(*) FROM main_menu_logimage WHERE action = "Failed" AND creation_date > """ + "\"" + start_state_timestamp + "\""
    checkit_cursor.execute(sql_statement)
    checkit_result = checkit_cursor.fetchall()[0][0]
    print("number of fails", checkit_result)
    return checkit_result

process_list_v2.main(list_to_process)

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
# TODO UPDATE transaction rate to STARTED record
# time.sleep(10)
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


transaction_rate = calculate_transaction_rate()
print(transaction_rate)
fails = count_failed()
print("Failed", fails)
sql_statement = "INSERT INTO main_menu_enginestate " \
                "(state, engine_process_id, transaction_rate, state_timestamp, number_failed_images) VALUES (%s,%s,%s,%s,%s)"
values = (state, engine_process_id, transaction_rate, state_timestamp, fails)
logging.info("Run completed")
checkit_cursor.execute(sql_statement, values)
checkit_db.commit()
checkit_db.close()


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
