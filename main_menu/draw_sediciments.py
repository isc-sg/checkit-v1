import cv2

img = cv2.imread("/home/checkit/camera_checker/media/base_images/101-04-02-20210816-132009.jpg")
height, width, channels = img.shape
qw = int(width / 4)
qh = int(height / 4)

count = 0
while count < 4:
    count += 1
    img = cv2.line(img, ((count * qw), 0), ((count * qw), height), (0, 255, 0), 5)
    img = cv2.line(img, (0, (count*qh)), (width, (count*qh)), (0, 255, 0), 5)

count = 0
row = 0
while row < 4:
    while count < 4:
        start_pos_x = int(qw/2)
        start_pos_y = int(qh/2)

        img = cv2.putText(img, str(((count + 1) + (row * 4))), (start_pos_x + (count * qw), (start_pos_y + (row * qh))), cv2.FONT_HERSHEY_DUPLEX, 3, (0, 255, 0), 10, cv2.LINE_AA)
        print(str(((count + 1) * (row + 1))), (start_pos_x + (count * qw), (start_pos_y + (row * qh))))
        count += 1
    count = 0
    row += 1

# resized_image = cv2.resize(img, ((2*qw), (2*qh)), cv2.INTER_AREA)
resized_image = cv2.resize(img, (1280, 960), cv2.INTER_AREA)
cv2.imshow("window", resized_image)
cv2.waitKey(0)

