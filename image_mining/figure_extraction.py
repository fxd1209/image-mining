#!/usr/bin/env python

import cv
import cv2


class ImageRegion(object):
    def __init__(self, x1, y1, x2, y2, poly=None, contour_index=None):
        assert x1 < x2
        assert y1 < y2
        self.x1 = x1
        self.x2 = x2
        self.y1 = y1
        self.y2 = y2

        self.poly = poly
        self.contour_index = contour_index

    def __repr__(self):
        return "({0.x1}, {0.y1})-({0.x2}, {0.y2})".format(self)

    @property
    def image_slice(self):
        """Return a Python slice suitable for use on an OpenCV image (i.e. numpy 2D array)"""
        return slice(self.y1, self.y2), slice(self.x1, self.x2)


class FigureExtractor(object):
    MORPH_TYPES = {"cross": cv2.MORPH_CROSS,
                   "ellipse": cv2.MORPH_ELLIPSE,
                   "rectangle": cv2.MORPH_RECT}
    MORPH_TYPE_KEYS = sorted(MORPH_TYPES.keys())

    def __init__(self, canny_threshold=0, erosion_element=None, erosion_size=4,
                 dilation_element=None, dilation_size=4,
                 min_area=0.01,
                 min_height=0.1, max_height=0.9,
                 min_width=0.1, max_width=0.9):
        # TODO: reconsider whether we should split to global config + per-image extractor instances

        # TODO: better way to set configuration options & docs
        self.canny_threshold = canny_threshold
        self.erosion_element = self.MORPH_TYPE_KEYS.index(erosion_element)
        self.erosion_size = erosion_size
        self.dilation_element = self.MORPH_TYPE_KEYS.index(dilation_element)
        self.dilation_size = dilation_size

        self.min_area_percentage = min_area
        self.min_height = min_height
        self.max_height = max_height
        self.min_width = min_width
        self.max_width = max_width

    def find_figures(self, source_image):
        output_image = self.filter_image(source_image)

        contours, hierarchy = self.find_contours(output_image)

        for bbox in self.get_bounding_boxes_from_contours(contours, source_image):
            yield bbox

    def find_contours(self, image):
        return cv2.findContours(image, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    def filter_image(self, source_image):
        # TODO: Refactor this into a more reusable filter chain

        output_image = cv2.cvtColor(source_image, cv.CV_BGR2GRAY)
        # TODO: make blurring configurable:
        # output_image = cv2.medianBlur(output_image, 7)
        # output_image = cv2.blur(output_image, (3, 3))

        # TODO: make thresholding configurable
        # TODO: investigate automatic threshold options
        threshold_rc, output_image = cv2.threshold(output_image, 192, 255, cv2.THRESH_BINARY)
        output_image = cv2.bitwise_not(output_image)

        if self.erosion_size > 0:
            element_name = self.MORPH_TYPE_KEYS[self.erosion_element]
            element = self.MORPH_TYPES[element_name]

            structuring_element = cv2.getStructuringElement(element, (self.erosion_size, self.erosion_size))
            output_image = cv2.erode(output_image, structuring_element)

        if self.dilation_size > 0:
            element_name = self.MORPH_TYPE_KEYS[self.dilation_element]
            element = self.MORPH_TYPES[element_name]

            structuring_element = cv2.getStructuringElement(element, (self.dilation_size, self.dilation_size))
            output_image = cv2.dilate(output_image, structuring_element)

        if self.canny_threshold > 0:
            # TODO: Make all of Canny options configurable
            output_image = cv2.Canny(output_image, self.canny_threshold, self.canny_threshold * 3, 12)

        return output_image

    def detect_lines(self, source_image):
        # TODO: Make HoughLinesP a configurable option
        lines = cv2.HoughLinesP(source_image, rho=1, theta=cv.CV_PI / 180,
                                threshold=160, minLineLength=80, maxLineGap=10)

        # for line in lines[0]:
        #     cv2.line(output_image, (line[0], line[1]), (line[2], line[3]), (0, 0, 255), 2, 4)
        return lines

    def get_bounding_boxes_from_contours(self, contours, source_image):
        # TODO: confirm that the min area check buys us anything over the bounding box min/max filtering
        min_area = self.min_area_percentage * source_image.size

        # TODO: more robust algorithm for detecting likely scan edge artifacts which can handle cropped scans of large images (e.g. http://dl.wdl.org/107_1_1.png)
        max_height = int(round(self.max_height * source_image.shape[0]))
        max_width = int(round(self.max_width * source_image.shape[1]))
        min_height = int(round(self.min_height * source_image.shape[0]))
        min_width = int(round(self.min_width * source_image.shape[1]))

        print "\tContour length & area (area: >%d pixels, box: height >%d, <%d, width >%d, <%d)" % (
            min_area, min_height, max_height, min_width, max_width)

        for i, contour in enumerate(contours):
            area = cv2.contourArea(contours[i], False)

            if area < min_area:
                print "\t\t%4d: failed area check" % (i, )
                continue

            poly = cv2.approxPolyDP(contour, 0.01 * cv2.arcLength(contour, False), False)
            x, y, w, h = cv2.boundingRect(poly)
            bbox = ImageRegion(x, y, x + w, y + h, poly=poly, contour_index=i)

            if w > max_width or w < min_width or h > max_height or h < min_height:
                print "\t\t%4d: failed min/max check: %s" % (i, bbox)
            else:
                yield bbox
