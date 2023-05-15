import base64
import datetime

from passlib.hash import sha512_crypt, hex_sha512
import subprocess
import mysql.connector
from mysql.connector import errorcode
import pathlib
from pathlib import Path
import os
import re
from sys import exit

salt = ''.join(reversed("Checkit"))
rounds = 656911

#  comment the code below for testing uncomment for compiling
# if not os.geteuid() == 0:
#     sys.exit("\nPlease run as superuser only\n")

if not os.path.isfile('/etc/checkit/checkit.lic'):
    Path("/etc/checkit").mkdir(parents=True, exist_ok=True, )
    license_file = open("/etc/checkit/checkit.lic", "w+")


def create_key(em):

    hash1 = ''
    salt = ''.join(reversed("Checkit"))
    rounds = 656911

    f = open("/etc/machine-id", "r")
    machine_id = f.read()
    machine_id = machine_id.strip("\n")
    result = subprocess.check_output("df", shell=True)
    l1 = result.decode('utf-8').split("\n")

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


"""
Install script needs to create checkit and adm databases
apt install all components
setup virtual environment
copy over django files and core engine
https://blog.toadworld.com/2017/03/06/data-encryption-at-rest-in-mysql-5-7
ALTER TABLE adm encryption='Y';
need to ensure plugin is loaded in  /etc/mysql/mysql.cnf
[mysqld]
early-plugin-load=keyring_file.so
keyring_file_data=/var/lib/mysql/keyring-data/keyring
innodb_file_per_table=ON

"""
create_key("sam.corbo@isc.sg")
transaction_limit = 0
end_date_string = ""
# TODO: check if adm exists and password set - this may have occurred after failed license
# TODO: initialise main_menu_licensing table in checkit DB (start_date, end_date, transaction_limit, transaction_count
# TODO: license_key, license_owner, site_name, run_schedule )


try:
    admin_db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
    )

    regex = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'

    while True:
        email = input("Enter email for license registration: ")
        if re.fullmatch(regex, email):
            break
        else:
            print("Please enter a valid email address")

    license_key, password = create_key(email)
    print("key", license_key, "passwd", password)
    admin_cursor = admin_db.cursor()

    sql_statement = "ALTER USER 'root'@'localhost' IDENTIFIED BY " + "\'" + password + "\'"
    admin_cursor.execute(sql_statement)
    sql_statement = "CREATE DATABASE adm"
    admin_cursor.execute(sql_statement)
    sql_statement = "USE adm"
    admin_cursor.execute(sql_statement)
    sql_statement = "CREATE TABLE adm (id SMALLINT NOT NULL AUTO_INCREMENT, " \
                    "tx_count INT, tx_limit INT, end_date DATE, " \
                    "license_key VARCHAR(256), customer_name VARCHAR(255), camera_limit SMALLINT," \
                    " site_name VARCHAR(255), email VARCHAR(255), PRIMARY KEY (id))"
    admin_cursor.execute(sql_statement)
    sql_statement = "ALTER TABLE adm ENCRYPTION = \'Y\'"
    admin_cursor.execute(sql_statement)

    while True:
        try:
            transaction_limit = int(input("Enter transactions license limit: "))
            # going to set upper limit of transactions to 9 million - based on 24x1000x365.  Agreed with MS 6/11/21
            if transaction_limit > (9*1000*1000):
                raise ValueError
            break
        except ValueError:
            print("Please enter a valid number between 1 and 9,000,000")

    while True:
        try:
            end_date_string = input("Enter license end date (format YYYY-MM-DD): ")
            end_date_date_format = datetime.datetime.strptime(end_date_string, '%Y-%m-%d')
            if end_date_date_format <= datetime.datetime.now():
                raise ValueError
            break
        except ValueError:
            print("Please enter a valid date (format YYYY-MM-DD)")

    while True:
        try:
            camera_limit = int(input("Enter camera limit: "))
            # going to set upper limit of transactions to 9 million - based on 24x1000x365.  Agreed with MS 6/11/21
            if camera_limit < 1:
                raise ValueError
            break
        except ValueError:
            print("Please enter a number greater than 1")

    try:
        sql_statement = "INSERT INTO adm (tx_limit, tx_count, end_date, license_key, email, " \
                        "camera_limit) VALUES (%s, %s, %s, %s, %s, %s)"
        admin_cursor.execute(sql_statement, (transaction_limit, "0", end_date_string, license_key, email, camera_limit))
        admin_db.commit()
    except mysql.connector.Error as err:
        print(err)

    try:
        checkit_db = mysql.connector.connect(
            host="localhost",
            user="checkit",
            password="checkit",
            database="checkit"
        )

        license_owner = input("Enter license owner name:")
        site_name = input("Enter site name:")
        start_date = datetime.datetime.strftime(datetime.datetime.today(), '%Y-%m-%d')

        checkit_cursor = checkit_db.cursor()
        sql_statement = "INSERT INTO main_menu_licensing " \
                        "(start_date,end_date,transaction_limit, transaction_count, license_key, " \
                        "license_owner, site_name, run_schedule) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
        checkit_cursor.execute(sql_statement, (start_date, end_date_string, transaction_limit, "0", license_key,
                                               license_owner, site_name, "0"))
        sql_statement = "INSERT INTO main_menu_enginestate " \
                        "(state,transaction_rate, state_timestamp, engine_process_id, number_failed_images) VALUES (%s, %s, %s, %s, %s)"
        checkit_cursor.execute(sql_statement, ("RUN COMPLETED", "0", start_date, "0", 0))
        checkit_db.commit()
        sql_statement = "UPDATE adm SET customer_name = " + "\"" + license_owner + "\", " +\
                        "site_name = " + "\"" + site_name + "\" WHERE id=1"
        admin_cursor.execute(sql_statement)
        admin_db.commit()

    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Invalid password on main database")
            exit(0)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database not initialised")
            exit(0)

    license_file = open("/etc/checkit/checkit.lic", "w+")
    license_file.write(license_key+"\n")
    license_file.write(email+"\n")
    license_file.close()
    print("New license details set")
    exit(0)

except mysql.connector.Error as err:
    try:
        license_file = open("/etc/checkit/checkit.lic", "r")
        license_key = license_file.readline().strip('\n')
        email = license_file.readline().strip('\n')
        segment = ''.join(reversed(license_key[11:65]))
        hash2 = sha512_crypt.using(rounds=rounds, salt=salt).encrypt(segment)
        _tmp, password = hash2.split("$6$rounds="+str(rounds) + "$" + salt + "$")

        admin_db = mysql.connector.connect(
            host="localhost",
            user="root",
            password=password,
            database="adm"
        )
        admin_cursor = admin_db.cursor()
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Invalid password")
            exit(0)
        elif err.errno == errorcode.ER_BAD_DB_ERROR:
            print("Database does not exist")
            exit(0)
        else:
            print(err)
            exit(0)

while True:
    try:
        transaction_limit = int(input("Enter RENEWAL transactions license limit: "))
        if transaction_limit > (100 * 1000 * 1000):
            raise ValueError
        break
    except ValueError:
        print("Please enter a valid integer")

while True:
    try:
        end_date_string = input("Enter RENEWAL license end date (format YYYY-MM-DD): ")
        end_date_date_format = datetime.datetime.strptime(end_date_string, '%Y-%m-%d')
        if end_date_date_format <= datetime.datetime.now():
            raise ValueError
        break
    except ValueError:
        print("Please enter a valid date (format YYYY-MM-DD)")

sql_statement = "UPDATE adm SET tx_limit = %s, end_date = %s WHERE id = 1"

try:
    admin_cursor.execute(sql_statement, (transaction_limit, end_date_string))
    admin_db.commit()
    print("New license details set")
except Exception as err:
    print(err)
