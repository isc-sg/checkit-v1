import cv2
import math
import numpy as np


def get_coordinates(r, h, w):
    var_list = []
    if r == 0 or r == "[]":
        var_list.append(((0, 0), (w, h)))
    else:
        for i in r:
            i = int(i)
            qh = math.floor(h / 8)
            qw = math.floor(w / 8)
            if i % 8 == 0:
                row = math.floor(i / 8)
            else:
                row = math.floor(i / 8) + 1

            column = i - ((row - 1) * 8)

            x = (column - 1) * qw
            y = (row - 1) * qh

            var_list.append(((x, y), (qw, qh)))
            # print('Region', i, '', "Row", row, '', 'Column', column, '', "X", x, 'Y', y, '', "qw", qw, 'qh', qh)
    return var_list


def draw_grid(c_list, img, h, w):
    qh = int(h / 8)
    qw = int(w / 8)
    count = 0
    if not c_list:
        resized_image = img

    font_size = .8
    font_thickness = 1
    line_thickness = 1
    while count < 8:
        count += 1
        img = cv2.line(img, ((count * qw), 0), ((count * qw), h), (0, 255, 0), line_thickness)
        img = cv2.line(img, (0, (count * qh)), (w, (count * qh)), (0, 255, 0), line_thickness)

    count = 0
    row = 0
    while row < 8:
        while count < 8:
            start_pos_x = int(qw / 2)
            start_pos_y = int(qh / 2)

            img = cv2.putText(img, str(count + (row * 8) + 1),
                              (start_pos_x + (count * qw), (start_pos_y + (row * qh))), cv2.FONT_HERSHEY_TRIPLEX, font_size,
                              (0, 255, 0), font_thickness, cv2.LINE_AA)
            count += 1
        count = 0
        row += 1

        image_grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.blur(image_grey, (5, 5))
        darkness = np.mean(blur)

    for i in c_list:
        (x, y), (qw, qh) = i
        sub_img = img[y:y + qh, x:x + qw]

        # if darkness > 100:
        blk_rect = np.ones(sub_img.shape, dtype=np.uint8) * 255
        red_rect = cv2.rectangle(blk_rect, (0,0), (qw, qh), (255,0,255), -1)
        res = cv2.addWeighted(sub_img, 0.7, red_rect, 0.7, 1.0)

        # else:
        #     blk_rect = np.ones(sub_img.shape, dtype=np.uint8) * 255
        #     res = cv2.addWeighted(sub_img, .3, blk_rect, .5, 1.0)

        # Putting the image back to its position
        img[y:y + qh, x:x + qw] = res
        resized_image = img
        if h > 640:
            scaling_factor = round(540 / h, 2)
            # resized_image = cv2.resize(img, (int(scaling_factor * w), int(scaling_factor * w)), cv2.INTER_AREA)
            resized_image = cv2.resize(img, (960, 720), cv2.INTER_AREA)

    return resized_image


# region = ['1', '3', '5', '29', '8', '11', '24', '44', '55', '64']
# original_image = cv2.imread('/home/sam/camera_checker/media/base_images/cam-1-c1-bbq-pit-1/02.jpg')
# height, width = original_image.shape[:2]
#
# co_ordinate_list = get_coordinates(region, height, width)
#
# new_image = draw_grid(co_ordinate_list, original_image, height, width)
# cv2.imshow("image", new_image)
# cv2.waitKey(0)

# count = 0
# while count < 8:
#     count2 = 0
#     while count2 < 8:
#         print(str(count2*240)+','+str(count*135))
#         count2 += 1
#     count += 1

