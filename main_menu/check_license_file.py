from cryptography.fernet import Fernet, InvalidToken
import ast

# The section below should be used as the actual .py file - this file should only be distributed as .so

# import check_license_file  # Replace with the name of your .so file, without the extension
# import argparse
#
# # Initialize parser
# parser = argparse.ArgumentParser(description="Script for processing multiple cameras")
#
# parser.add_argument('file_name', type=str, help='File name of the license file')
#
# args = parser.parse_args()
# file_name = args.file_name
#
# # Call functions or use classes defined in the .pyx file
# check_license_file.check_license(file_name)
#


__version__ = 1.001

def array_to_string(array):
    new_string = ""
    for element in array:
        new_string += chr(element)
    return new_string


key_array = [66, 117, 45, 86, 77, 100, 121, 83, 73, 80, 114, 101, 78, 103, 118, 101, 56, 119, 95, 70, 85, 48, 89, 45,
             76, 72, 78, 118, 121, 103, 75, 108, 72, 105, 119, 80, 108, 74, 78, 79, 114, 54, 77, 61]

key = array_to_string(key_array).encode()

def check_license(file_name):
    if not file_name:
        print("Please provide a file name as a parameter on the command line")
        return

    try:
        with open(file_name, "rb") as license_file_fd:
                license_file = license_file_fd.read()
    except FileNotFoundError:
        print("File not found")
        return
    except PermissionError as e:
        print(f"Error: {e}")
        return

    f = Fernet(key)
    license_details = None
    try:
        decrypted_file = f.decrypt(license_file).decode()
        license_details = ast.literal_eval(decrypted_file)
        uploaded_end_date = license_details['end_date']
        uploaded_purchased_cameras = license_details['purchased_cameras']
        uploaded_purchased_transactions = license_details['purchased_transactions']
        uploaded_license_key = license_details['license_key']
        uploaded_machine_uuid = license_details['machine_uuid']
        uploaded_root_fs_uuid = license_details['root_fs_uuid']
        uploaded_product_uuid = license_details['product_uuid']
        uploaded_customer_name = license_details['customer_name']
        uploaded_site_name = license_details['site_name']
    except (ValueError, KeyError, InvalidToken) as e:
        print(f"Invalid License file - error {e}")

    if not license_details:
        print("Unable to extract license details")
    else:
        print(uploaded_license_key, uploaded_end_date, uploaded_site_name,
              uploaded_purchased_cameras, uploaded_purchased_transactions)
