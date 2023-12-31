import random
import sys
#define constants

#these constants depend on the bitness of the OS - the DRIS is 4 bytes bigger for 64-bit code
if sys.maxsize > 2**32:
	DRIS_SIZE = 564         # DRIS size is bigger for 64-bit (it has an 8-byte pointer)
	python64 = 4            # so we can adjust structure offsets for 64-bit python
else:
	DRIS_SIZE = 560
	python64 = 0

#function values
PROTECTION_CHECK    = 1     # checks for dongle, check program params...
EXECUTE_ALGORITHM   = 2     # protection check + calculate answer for specified algorithm with specified inputs
WRITE_DATA_AREA     = 3     # protection check + writes dongle data area
READ_DATA_AREA      = 4     # protection check + reads dongle data area
ENCRYPT_USER_DATA   = 5     # protection check + the dongle will encrypt user data
DECRYPT_USER_DATA   = 6     # protection check + the dongle will decrypt user data
FAST_PRESENCE_CHECK	= 7     # checks for the presence of the correct dongle only with minimal security, no flags allowed.
STOP_NET_USER       = 8     # stops a network user (a protection check is NOT performed)

# flags - can specify as many as you like
DEC_ONE_EXEC            = 1     # decrement execs by 1
DEC_MANY_EXECS          = 2     # decrement execs by number specified in execs_decrement
START_NET_USER          = 4     # starts a network user
USE_FUNCTION_ARGUMENT   = 16    # use the extra argument in the function for pointers
CHECK_LOCAL_FIRST       = 32    # always look in local ports before looking in network ports
CHECK_NETWORK_FIRST     = 64    # always look on the network before looking in local ports
USE_ALT_LICENCE_NAME    = 128	# use name specified in alt_licence_name instead of the default one
DONT_SET_MAXDAYS_EXPIRY = 256   # if the max days expiry date has not been calculated then do not do it this time
MATCH_DONGLE_NUMBER     = 512   # restrict the search to match the dongle number specified in the DRIS
DONT_RETURN_FD_DRIVE    = 1024  # if an FD dongle has been detected then don't return the flash drive/mount name

# set 4 bytes in our DRIS byte array from an integer
def set4bytes(data, offset, value):
	data[offset] = value & 0xff
	data[offset+1] = (value >> 8) & 0xff
	data[offset+2] = (value >> 16) & 0xff
	data[offset+3] = (value >> 24) & 0xff
	return

# trunctates a value to 32-bit and converts to a signed integer
def make_signed32bit(value):
	value = value & 0xffffffff
	if (value > (2**31)):
		value = value - (2**32)
	return value	

# get 4 bytes in our DRIS byte array and convert to an unsigned integer
# this returns an unsigned value, which is useful for dongle number, features, etc... 
def get4bytes(data, offset):
	return (data[offset] + data[offset+1]*0x100 + data[offset+2]*0x10000 + data[offset+3]*0x1000000)

# this returns a signed value, which is useful for alg_answer, expiry day...
def get4bytes_signed(data, offset):
	value = data[offset] + data[offset+1]*0x100 + data[offset+2]*0x10000 + data[offset+3]*0x1000000
	if (value > (2**31)):
		value = value - (2**32)
	return value

# create the DRIS structure as a byte array, populate it with random values, initialise the header and size fields
def create():
	dris = bytearray(DRIS_SIZE)
	random.seed()
	for n in range(DRIS_SIZE):
		dris[n] = random.randint(0, 255)
	dris[0] = ord('D')
	dris[1] = ord('R')
	dris[2] = ord('I')
	dris[3] = ord('S')
	set4bytes(dris, 4, DRIS_SIZE)
	return dris

# these functions set various values in the DRIS
def set_function(dris, value):
	set4bytes(dris, 16, value)

def set_flags(dris, value):
	set4bytes(dris, 20, value)

def set_execs_decrement(dris, value):
	set4bytes(dris, 24, value)

def set_data_crypt_key_num(dris, value):
	set4bytes(dris, 28, value)

def set_rw_offset(dris, value):
	set4bytes(dris, 32, value)

def set_rw_length(dris, value):
	set4bytes(dris, 36, value)

def set_alt_licence_name(dris, licence_name):
	dris[44+python64:44+python64+len(licence_name)] = licence_name
	dris[44+python64+len(licence_name)] = 0					# null-terminate the string

def set_var_a(dris, value):
	set4bytes(dris, 300+python64, value)

def set_var_b(dris, value):
	set4bytes(dris, 304+python64, value)

def set_var_c(dris, value):
	set4bytes(dris, 308+python64, value)

def set_var_d(dris, value):
	set4bytes(dris, 312+python64, value)

def set_var_e(dris, value):
	set4bytes(dris, 316+python64, value)

def set_var_f(dris, value):
	set4bytes(dris, 320+python64, value)

def set_var_g(dris, value):
	set4bytes(dris, 324+python64, value)

def set_var_h(dris, value):
	set4bytes(dris, 328+python64, value)

def set_alg_number(dris, value):
	set4bytes(dris, 332+python64, value)

# these functions get values from the DRIS
def get_ret_code(dris):
	return get4bytes(dris, 336+python64)

def get_ext_err(dris):
	return get4bytes(dris, 340+python64)

def get_type(dris):
	return get4bytes(dris, 344+python64)

def get_model(dris):
	return get4bytes(dris, 348+python64)

def get_sdsn(dris):
	return get4bytes(dris, 352+python64)

def get_prodcode(dris):
	for n in range(356+python64,368+python64):
		if dris[n] == 0:
			break
	return dris[356+python64:n].decode("utf-8")

def get_dongle_number(dris):
	return get4bytes(dris, 368+python64)

def get_update_number(dris):
	return get4bytes(dris, 372+python64)

def get_data_area_size(dris):
	return get4bytes(dris, 376+python64)

def get_max_alg_num(dris):
	return get4bytes(dris, 380+python64)

def get_execs(dris):
	return get4bytes(dris, 384+python64)

def get_exp_day(dris):
	return get4bytes_signed(dris, 388+python64)

def get_exp_month(dris):
	return get4bytes_signed(dris, 392+python64)

def get_exp_year(dris):
	return get4bytes_signed(dris, 396+python64)

def get_features(dris):
	return get4bytes(dris, 400+python64)

def get_net_users(dris):
	return get4bytes(dris, 404+python64)

def get_alg_answer(dris):
	return get4bytes_signed(dris, 408+python64)

def get_fd_capacity(dris):
	return get4bytes(dris, 412+python64)

def get_fd_drive(dris):
	for n in range(416+python64,544+python64):
		if dris[n] == 0:
			break
	return dris[416+python64:n].decode("utf-8")

def get_swkey_type(dris):
    return get4bytes(dris, 544+python64)

def get_swkey_exp_day(dris):
    return get4bytes(dris, 548+python64)

def get_swkey_exp_month(dris):
    return get4bytes(dris, 552+python64)

def get_swkey_exp_year(dris):
    return get4bytes(dris, 556+python64)
	
# you may also want to retrieve var_a values that you already entered into the dris!
def get_var_a(dris):
	return get4bytes_signed(dris, 300+python64)

def get_var_b(dris):
	return get4bytes_signed(dris, 304+python64)

def get_var_c(dris):
	return get4bytes_signed(dris, 308+python64)

def get_var_d(dris):
	return get4bytes_signed(dris, 312+python64)

def get_var_e(dris):
	return get4bytes_signed(dris, 316+python64)

def get_var_f(dris):
	return get4bytes_signed(dris, 320+python64)

def get_var_g(dris):
	return get4bytes_signed(dris, 324+python64)

def get_var_h(dris):
	return get4bytes_signed(dris, 328+python64)

# function to display the most common error codes.
# You will want to change this with your own error messages
def DisplayError(ret_code, extended_error):
	if (ret_code == 401):
		print("Error! No dongles detected!")
	elif (ret_code == 403):
		print("Error! The dongle detected has a different type to the one specified in DinkeyAdd.")
	elif (ret_code == 404):
		print("Error! The dongle detected has a different model to those specified in DinkeyAdd.")
	elif (ret_code == 409):
		print("Error! The dongle detected has not been programmed by DinkeyAdd.")
	elif (ret_code == 410):
		print("Error! The dongle detected has a different Product Code to the one specified in DinkeyAdd.")
	elif (ret_code == 411):
		print("Error! The dongle detected does not contain the licence associated with this program.")
	elif (ret_code == 413):
		print("Error! This program has not been protected by DinkeyAdd. For guidance please read the DinkeyAdd chapter of the Dinkey manual.")
	elif (ret_code == 417):
		print("Error! One or more of the parameters set in the DRIS is incorrect. This could be caused if you are encrypting the DRIS in your code but did not specify DRIS encryption in DinkeyAdd - or vice versa.")
	elif (ret_code == 423):
		print("Error! The number of network users has been exceeded.")
	elif (ret_code == 435):
		print("Error! DinkeyServer has not been detected on the network.")
	elif (ret_code == 922):
		print("Error! The Software Key has expired.")
	else:
		print("An error occurred checking the dongle.\nError: " + str(ret_code) + ", Extended Error: " + str(extended_error))
	return
