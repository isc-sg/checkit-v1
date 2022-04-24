import os
import sys

import a_eye
import cv2
from skimage.exposure import is_low_contrast
import select_region
from bisect import bisect_left
import datetime
from termcolor import colored
from sewar.full_ref import mse, rmse, psnr, uqi, ssim, ergas, scc, rase, sam, msssim, vifp


# base_image_file_name = sys.argv[0]
# log_image_file_name = sys.argv[1]
# base_image_file_name = "/home/checkit/media/base_images/4/14.jpg"
# log_image_file_name = "/home/checkit/media/logs/2022/4/4/4-12:0:25.jpg"


def take_closest(my_list, my_number):
    pos = bisect_left(my_list, my_number)
    if pos == 0:
        return my_list[0]
    if pos == len(my_list):
        return my_list[-1]
    before = my_list[pos - 1]
    after = my_list[pos]
    if after - my_number < my_number - before:
        return after
    else:
        return before


def compare_images(base, frame, r, base_color, frame_color):
    # r = ['1', '3', '5', '29', '8', '11', '24', '44', '55', '64']
    h, w = frame.shape[:2]
    all_regions = []
    all_regions.extend(range(1, 65))
    region_scores = {}
    coordinates = select_region.get_coordinates(all_regions, h, w)
    scores = []
    # full_ss = movement(base, frame)
    wait_time = 200

    frame_equalised = cv2.equalizeHist(frame)
    resized_frame = cv2.resize(frame_color, (int(1920/2), int(1080/2)), interpolation=cv2.INTER_AREA)
    cv2.imshow("Log Original", resized_frame)
    cv2.moveWindow("Log Original", 625, 600)

    frame_bilateral = cv2.bilateralFilter(frame_equalised, 9, 100, 100)
    resized_frame_bilateral = cv2.resize(frame_bilateral, (int(1920/2), int(1080/2)), interpolation=cv2.INTER_AREA)
    cv2.imshow("Log Fixed", resized_frame_bilateral)
    cv2.moveWindow("Log Fixed", 1590, 600)

    based_equalised = cv2.equalizeHist(base)
    resized_base = cv2.resize(base_color, (int(1920/2), int(1080/2)), interpolation=cv2.INTER_AREA)
    cv2.imshow("Base Original", resized_base)
    cv2.moveWindow("Base Original", 625, 0)

    based_bilateral = cv2.bilateralFilter(based_equalised, 9, 100, 100)
    resized_base_bilateral = cv2.resize(based_bilateral, (int(1920/2), int(1080/2)), interpolation=cv2.INTER_AREA)
    cv2.imshow("Base Fixed", resized_base_bilateral)
    cv2.moveWindow("Base Fixed", 1590, 0)

    full_ss = a_eye.movement(based_equalised, frame_equalised)
    full_ss_bilateral = round(a_eye.movement(based_bilateral, frame_bilateral), 2)
    count = 0
    for i in coordinates:
        (x, y), (qw, qh) = i
        sub_img_frame = frame_bilateral[y:y + qh, x:x + qw]
        sub_img_base = based_bilateral[y:y + qh, x:x + qw]
        # cv2.imshow("sub of frame", sub_img_frame)
        # cv2.imshow("sub of base", sub_img_base)
        # cv2.waitKey(0)
        ss = 0
        try:
            ss = a_eye.movement(sub_img_base, sub_img_frame)
        except Exception as e:
            print(f"Failed to get movement data {e}")

        # scores.append(ss)
        # print("region", count, "score", round(ss, 2))
        count += 1
        region_scores[count] = round(ss, 2)
    # print("r is ", r)
    # print("Region scores are", region_scores)
    for i in r:
        ss = region_scores[int(i)]
        scores.append(ss)
    # scores_average = mean(scores)

    # print("Scores list is ", scores)
    number_of_regions = len(r)
    # print('number of regions ', number_of_regions)
    scores.sort(reverse=True)
    sum_scores = sum(scores)

    scores_average = sum_scores / number_of_regions
    # print("scores", scores)

    fv = cv2.Laplacian(frame_color, cv2.CV_64F).var()
    # print("Focus Score is %.2f" % fv)
    if scores_average < full_ss:
        full_ss = scores_average
    full_ss = round(full_ss, 2)
    scores_average = round(scores_average, 2)
    fv = round(fv, 2)

    if is_low_contrast(frame, 0.25):
        print("Log image is of poor quality")
        wait_time = 0
    if is_low_contrast(base, 0.25):
        print("Base image is of poor quality")
        wait_time = 0

    blur = cv2.blur(frame, (5, 5))
    brightness = cv2.mean(blur)
    hsldark = cv2.cvtColor(frame_color, cv2.COLOR_BGR2HLS)
    Lchanneld = hsldark[:, :, 1]
    lvalueld = cv2.mean(Lchanneld)[0]
    print("L values", lvalueld, brightness)
    if brightness[0] < 50:
        print(colored(f'Base brightness is {brightness}', "red"))
        wait_time = 0

    blur = cv2.blur(frame, (5, 5))
    brightness = cv2.mean(blur)

    if brightness[0] < 50:
        print(colored(f'Log brightness is {brightness}', "red"))
        wait_time = 0

    print(f"Match Score for full image is {full_ss}")
    print(f"Match Score for full image bilateral is {full_ss_bilateral}")
    # print("VIF: ", vifp(base, frame))
    # print("SSIM: ", ssim(base, frame))
    # print("MSSSIM: ", msssim(base, frame))
    # print(f"Match Score for regions is {scores_average}")
    print(f"Focus value is {fv}")
    # print(f"All region scores are {region_scores}")

    if full_ss_bilateral < .6:
        wait_time = 0
    cv2.waitKey(0)

    return full_ss, fv, region_scores


base_files_directory = "/home/checkit/media/base_images/"
base_files = os.listdir(base_files_directory)
log_files_directory = "/home/checkit/media/logs/2022/"

for camera_id in base_files:
    time_stamp = datetime.datetime.now()
    hour = time_stamp.strftime('%H')
    hours = []
    reference_images_list = os.listdir(base_files_directory + camera_id)
    log_months = os.listdir(log_files_directory)
    for month in log_months:
        days = os.listdir(log_files_directory + month)
        for day in days:
            log_files = os.listdir(log_files_directory + month + "/" + day)
            # print(log_files)
            for log_file in log_files:
                camera_logged, time_logged = log_file.split("-")
                time_logged, _ext = time_logged.split(".jpg")
                hour_logged, min_logged, second_logged = time_logged.split(":")
                # print(camera_logged, time_logged)
                if os.path.isfile(base_files_directory + camera_id + "/" + hour_logged + ".jpg"):
                    base_image_file_name = base_files_directory + camera_logged + "/" + hour_logged + ".jpg"
                    log_image_file_name = log_files_directory + month + "/" + day + "/" + log_file
                    print(base_files_directory + camera_logged + "/" + hour_logged + ".jpg", log_files_directory +
                          month + "/" + day + "/" + log_file)
                    base_image = cv2.imread(base_image_file_name)
                    log_image = cv2.imread(log_image_file_name)
                    base_image_gray = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
                    log_image_gray = cv2.cvtColor(log_image, cv2.COLOR_BGR2GRAY)
                    regions = [*range(1, 65)]
                    compare_images(base_image_gray, log_image_gray, regions, base_image, log_image)


# base_image = cv2.imread(base_image_file_name)
# log_image = cv2.imread(log_image_file_name)
# base_image_gray = cv2.cvtColor(base_image, cv2.COLOR_BGR2GRAY)
# log_image_gray = cv2.cvtColor(log_image, cv2.COLOR_BGR2GRAY)
# regions = [*range(1, 65)]
# compare_images(base_image_gray, log_image_gray, regions)
