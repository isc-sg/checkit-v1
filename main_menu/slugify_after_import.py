import mysql.connector
import slugify


# database settings
my_db = mysql.connector.connect(
    host="localhost",
    user="checkit",
    password="checkit",
    database="checkit"
)
# suggest we use a string that is found in the binary as the password. eg AWAVAUATUSH

my_cursor = my_db.cursor()

# logic to check license key valid and also check transaction limit not exceeded.

sql_statement = "SELECT * FROM main_menu_camera WHERE slug is NULL"

my_cursor.execute(sql_statement)
result = my_cursor.fetchall()
for camera in result:
    slug = slugify.slugify(camera[4])+"-"+str(camera[3])
    sql_statement = "UPDATE main_menu_camera SET slug = " + "\"" + slug + "\"" + " WHERE id = " + str(camera[0])
    print(sql_statement)
    my_cursor.execute(sql_statement)
    my_db.commit()

