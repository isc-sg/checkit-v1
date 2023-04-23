from cryptography.fernet import Fernet, InvalidToken
import datetime
import mysql.connector
import hashlib
import subprocess
from subprocess import PIPE, Popen

checkit_secret = "Checkit65911760424"[::-1].encode()

key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='


def get_encrypted(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def get_license_details():
    f = Fernet(key)

    fd = open("/etc/machine-id", "r")
    machine_uuid = fd.read()
    machine_uuid = machine_uuid.strip("\n")

    shell_output = subprocess.check_output("/bin/df", shell=True)
    l1 = shell_output.decode('utf-8').split("\n")
    command = "mount | sed -n 's|^/dev/\(.*\) on / .*|\\1|p'"
    root_dev = subprocess.check_output(command, shell=True).decode().strip("\n")

    command = "/usr/bin/sudo /sbin/blkid | grep " + root_dev
    root_fs_uuid = subprocess.check_output(command, shell=True).decode().split(" ")[1].split("UUID=")[1].strip("\"")

    command = "sudo dmidecode | grep -i uuid"
    product_uuid = subprocess.check_output(command, shell=True).decode(). \
        strip("\n").strip("\t").split("UUID:")[1].strip(" ")

    finger_print = (root_fs_uuid + machine_uuid + product_uuid)
    fingerprint_encrypted = get_encrypted(finger_print)
    mysql_password = fingerprint_encrypted[10:42][::-1]

    return machine_uuid, root_fs_uuid, product_uuid, mysql_password


result = get_license_details()
new_password = result[3]
print(new_password)
try:
    adm_db_config = {
        "host": "localhost",
        "user": "root",
        "password": new_password,
        "database": "adm"
    }
    adm_db = mysql.connector.connect(**adm_db_config)

except mysql.connector.Error as e:
    print(e)
    try:
        adm_db_config = {
            "host": "localhost",
            "user": "root",
            "password": "",
            "database": "adm"
        }
    except mysql.connector.Error as e:
        print("Database access denied")
        exit(1)
else:
    print("password is already set")
    exit(0)


adm_db = mysql.connector.connect(**adm_db_config)
admin_cursor = adm_db.cursor()
sql_statement = """USE adm"""
admin_cursor.execute(sql_statement)
sql_statement = """SELECT COUNT(TABLE_NAME) FROM information_schema.TABLES WHERE TABLE_SCHEMA LIKE 'adm' AND TABLE_NAME = 'adm'"""
admin_cursor.execute(sql_statement)
result = admin_cursor.fetchone()
if result[0] != 1:
    print("adm does not exist")
    try:
        sql_statement = """CREATE TABLE adm (id SMALLINT NOT NULL AUTO_INCREMENT, 
        tx_count INT, tx_limit INT, end_date DATE, license_key VARCHAR(256), 
        customer_name VARCHAR(255), camera_limit SMALLINT, site_name VARCHAR(255), PRIMARY KEY (id))"""
        admin_cursor.execute(sql_statement)

    except mysql.connector.Error as e:
        print("Error occurred when trying to create database", e)
    else:
        print("Successfully created adm table")
else:
    print("Tables already exists")

try:
    sql_statement = """ALTER USER 'root'@'localhost' IDENTIFIED BY """ + "\"" + new_password + "\""
    admin_cursor.execute(sql_statement)
    warnings = admin_cursor.fetchwarnings()
    print("warning", warnings)
except Exception as e:
    print("Error ", e)
else:
    print("changed password")