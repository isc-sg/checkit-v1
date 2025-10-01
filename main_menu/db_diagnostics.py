import mysql.connector
import hashlib
import subprocess
import csv


def array_to_string(array):
    new_string = ""
    for element in array:
        new_string += chr(element)
    return new_string


# checkit_secret = "Checkit65911760424"[::-1].encode()
# convert strings to ascii decimal values as an array - this helps obfuscate the string after compiling
checkit_array = [52, 50, 52, 48, 54, 55, 49, 49, 57, 53, 54, 116, 105, 107, 99, 101, 104, 67]

checkit_secret = array_to_string(checkit_array).encode()

# key = b'Bu-VMdySIPreNgve8w_FU0Y-LHNvygKlHiwPlJNOr6M='

key_array = [66, 117, 45, 86, 77, 100, 121, 83, 73, 80, 114, 101, 78, 103, 118, 101, 56, 119, 95, 70, 85, 48, 89, 45,
             76, 72, 78, 118, 121, 103, 75, 108, 72, 105, 119, 80, 108, 74, 78, 79, 114, 54, 77, 61]

key = array_to_string(key_array).encode()


def get_hash(key_string):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(key_string.encode())
    return h.hexdigest().upper()

def get_encrypted(password):
    h = hashlib.blake2b(digest_size=64, key=checkit_secret)
    h.update(password.encode())
    h_in_hex = h.hexdigest().upper()
    return h_in_hex


def get_mysql_password():

    machine_command_array = [47, 101, 116, 99, 47, 109, 97, 99, 104, 105, 110, 101, 45, 105, 100]
    machine_file = array_to_string(machine_command_array)

    fd = open(machine_file, "r")
    _machine_uuid = fd.read()
    _machine_uuid = _machine_uuid.strip("\n")

    command_array = [109, 111, 117, 110, 116, 32, 124, 32, 103, 114, 101, 112, 32, 39, 111, 110, 32, 47, 32, 116, 121,
                     112, 101, 39]
    command = array_to_string(command_array)
    command_output = subprocess.check_output(command, shell=True).decode()
    root_device = command_output.split()[0]

    command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 47, 115, 98, 105, 110, 47, 98,
                     108, 107, 105, 100, 32, 124, 32, 103, 114, 101, 112, 32]

    command = array_to_string(command_array) + root_device
    command_output = subprocess.check_output(command, shell=True).decode()
    _root_fs_uuid = command_output.split()[1].strip("UUID=").strip("\"")


    command_array = [47, 117, 115, 114, 47, 98, 105, 110, 47, 115, 117, 100, 111, 32, 100, 109, 105, 100, 101, 99, 111,
                     100, 101, 32, 45, 115, 32, 115, 121, 115, 116, 101, 109, 45, 117, 117, 105, 100]
    command = array_to_string(command_array)
    product_uuid = subprocess.check_output(command, shell=True).decode().strip("\n")

    finger_print = (_root_fs_uuid + _machine_uuid + product_uuid)
    print("root", _root_fs_uuid, "machine", _machine_uuid, "prod", product_uuid)
    fingerprint_encrypted = get_encrypted(finger_print)
    password = fingerprint_encrypted[10:42][::-1]

    return ("root", _root_fs_uuid, "machine", _machine_uuid, "prod", product_uuid)

mysql_password = get_mysql_password()
# print(mysql_password)
# MySQL connection details
MYSQL_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "checkit",
}

# SQL query to run

TABLE_NAMES = ["main_menu_logimage", "main_menu_camera", "main_menu_reference_image", "main_menu_enginestate"]

# Diagnostic queries including table-specific checks
QUERIES = {
    "Running Queries": "SHOW FULL PROCESSLIST;",
    "Slow Query Count": "SHOW GLOBAL STATUS LIKE 'Slow_queries';",
    "InnoDB Status": "SHOW ENGINE INNODB STATUS;",
    "Lock Waits": "SELECT * FROM information_schema.INNODB_LOCKS;",
    "Buffer Pool Usage": "SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool%';",
    "High Write Tables": "SELECT TABLE_NAME, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH, DATA_FREE, AUTO_INCREMENT "
                         "FROM information_schema.TABLES "
                         "WHERE TABLE_SCHEMA = DATABASE() AND DATA_LENGTH > 0 "
                         "ORDER BY DATA_LENGTH DESC LIMIT 5;",
    "Performance Schema Data": "SELECT * FROM performance_schema.events_statements_summary_by_digest",
    
    # Table-specific checks on logimage
    "Table Structure main_menu_logimage": f"SHOW CREATE TABLE {TABLE_NAMES[0]};",
    "Row Count main_menu_logimage": f"SELECT COUNT(*) FROM {TABLE_NAMES[0]};",
    "Indexes main_menu_logimage": f"SHOW INDEXES FROM {TABLE_NAMES[0]};",
    "Table Size main_menu_logimage": f"SHOW TABLE STATUS LIKE '{TABLE_NAMES[0]}';",
    "Open Tables main_menu_logimage": f"SHOW OPEN TABLES WHERE 'Table' = '{TABLE_NAMES[0]}';",

    # Check for index usage on logimage
    "Index Usage main_menu_logimage": f"SELECT * "
                                      f"FROM sys.schema_index_statistics "
                                      f"WHERE table_name = '{TABLE_NAMES[0]}';",

    # Table-specific checks on camera
    "Table Structure main_menu_camera": f"SHOW CREATE TABLE {TABLE_NAMES[1]};",
    "Row Count main_menu_camera": f"SELECT COUNT(*) FROM {TABLE_NAMES[1]};",
    "Indexes main_menu_camera": f"SHOW INDEXES FROM {TABLE_NAMES[1]};",
    "Table Size main_menu_camera": f"SHOW TABLE STATUS LIKE '{TABLE_NAMES[1]}';",
    "Open Tables main_menu_camera": f"SHOW OPEN TABLES WHERE 'Table' = '{TABLE_NAMES[1]}';",

    # Check for index usage on camera
    "Index Usage main_menu_camera": f"SELECT * "
                                    f"FROM sys.schema_index_statistics "
                                    f"WHERE table_name = '{TABLE_NAMES[1]}';",

    # Table-specific checks on reference_image
    "Table Structure main_menu_reference_image": f"SHOW CREATE TABLE {TABLE_NAMES[2]};",
    "Row Count main_menu_reference_image": f"SELECT COUNT(*) FROM {TABLE_NAMES[2]};",
    "Indexes main_menu_reference_image": f"SHOW INDEXES FROM {TABLE_NAMES[2]};",
    "Table Size main_menu_reference_image": f"SHOW TABLE STATUS LIKE '{TABLE_NAMES[2]}';",
    "Open Tables main_menu_reference_image": f"SHOW OPEN TABLES WHERE 'Table' = '{TABLE_NAMES[2]}';",

    # Check for index usage on reference_image
    "Index Usage main_menu_reference_image": f"SELECT * "
                                             f"FROM sys.schema_index_statistics "
                                             f"WHERE table_name = '{TABLE_NAMES[2]}';",

    # Table-specific checks on enginestate
    "Table Structure main_menu_enginestate ": f"SHOW CREATE TABLE {TABLE_NAMES[3]};",
    "Row Count main_menu_enginestate": f"SELECT COUNT(*) FROM {TABLE_NAMES[3]};",
    "Indexes main_menu_enginestate": f"SHOW INDEXES FROM {TABLE_NAMES[3]};",
    "Table Size main_menu_enginestate": f"SHOW TABLE STATUS LIKE '{TABLE_NAMES[3]}';",
    "Open Tables main_menu_enginestate": f"SHOW OPEN TABLES WHERE 'Table' = '{TABLE_NAMES[3]}';",

    # Check for index usage on enginestate
    "Index Usage main_menu_enginestate": f"SELECT * "
                                         f"FROM sys.schema_index_statistics "
                                         f"WHERE table_name = '{TABLE_NAMES[3]}';",
}
def get_diagnostics():

    try:
        # Connect to MySQL
        conn = mysql.connector.connect(**MYSQL_CONFIG)
        cursor = conn.cursor()
        get_mysql_password()

        with open("results.txt", "w", newline="") as f:
            for title, query in QUERIES.items():
                f.write(f"\n--- {title} ---\n")
                try:
                    cursor.execute(query)
                    rows = cursor.fetchall()

                    # Get column names
                    column_names = [desc[0] for desc in cursor.description]
                    # f.write("\t".join(column_names) + "\n")
                    #
                    # # Write row data
                    # for row in rows:
                    #     f.write("\t".join(str(col) for col in row) + "\n")

                    writer = csv.writer(f)
                    writer.writerow(column_names)  # Write headers
                    writer.writerows(rows)  # Write data

                except mysql.connector.Error as e:
                    f.write(f"Error running query: {e}\n")

        print("MySQL diagnostics saved to results.txt")

    except mysql.connector.Error as e:
        print(f"Error: {e}")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals():
            conn.close()

get_diagnostics()
