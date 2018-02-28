#!/usr/bin/env python

import sys
import rospy
import math
import tf
import numpy as np
from nav_msgs.srv import GetMap
from comp313p_planner_controller.occupancy_grid import OccupancyGrid
from comp313p_planner_controller.search_grid import SearchGrid
from comp313p_planner_controller.grid_drawer import SearchGridDrawer
from comp313p_planner_controller.cell import CellLabel
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry


# This class creates a simulation of SLAM data:
# uses True data to create a map that is initialised from robot starting location and publishes robot odometry
#  that is initialised at starting location

class Mock_Slam_Node(object):
    def __init__(self):
        rospy.init_node('mock_slam_node', anonymous=True)
        rospy.wait_for_service('static_map')
        rospy.loginfo('------> 0')
        self.mapServer = rospy.ServiceProxy('static_map', GetMap)
        rospy.loginfo('------> 1')
        resp = self.mapServer()
        self.occupancyGrid = OccupancyGrid(resp.map.info.width, resp.map.info.height, resp.map.info.resolution)
        self.occupancyGrid.setScale(rospy.get_param('plan_scale', 5))
        self.occupancyGrid.scaleMap()
        rospy.loginfo('------> 2')
        self.searchGrid = SearchGrid.fromOccupancyGrid(self.occupancyGrid)
        rospy.loginfo('------> 3')
        self.gridDrawer = SearchGridDrawer('Map', self.searchGrid, 600)
        self.gridDrawer.open()
        rospy.loginfo('------> 4')
        self.local_odometry = Odometry()
        self.laser_sub = rospy.Subscriber("robot0/laser_0", LaserScan, self.parse_scan)
        self.odom_sub = rospy.Subscriber("robot0/odom", Odometry, self.update_odometry)
        # rospy.Timer(rospy.Duration(1),self.update_visualisation)
        rospy.loginfo('------> Initialised')

    def update_odometry(self, msg):
        self.local_odometry = msg

    def parse_scan(self, msg):

        for ii in range(int(math.floor((msg.angle_max - msg.angle_min) / msg.angle_increment))):
            # rospy.loginfo("{} {} {}".format(msg.ranges[ii],msg.angle_min,msg.angle_max))
            valid = (msg.ranges[ii] > msg.range_min) and (msg.ranges[ii] < msg.range_max)
            if valid:
                quaternion = (self.local_odometry.pose.pose.orientation.x, self.local_odometry.pose.pose.orientation.y,
                              self.local_odometry.pose.pose.orientation.z, self.local_odometry.pose.pose.orientation.w)
                euler = tf.transformations.euler_from_quaternion(quaternion)
                angle = msg.angle_min + msg.angle_increment * ii + euler[2]

                point_world_coo = [math.cos(angle) * msg.ranges[ii] + self.local_odometry.pose.pose.position.x,
                                   math.sin(angle) * msg.ranges[ii] + self.local_odometry.pose.pose.position.y]

                point_cell_coo = self.occupancyGrid.getCellCoordinatesFromWorldCoordinates(point_world_coo)
                robot_world_coo = [self.local_odometry.pose.pose.position.x, self.local_odometry.pose.pose.position.y]
                robot_cell_coo = self.occupancyGrid.getCellCoordinatesFromWorldCoordinates(robot_world_coo)
                between = self.ray_trace(robot_cell_coo, point_cell_coo)

                for point in between:
                    try:
                        self.occupancyGrid.setCell(point[0], point[1], 0)
                    except IndexError as e:
                        print(e)

                self.occupancyGrid.setCell(point_cell_coo[0], point_cell_coo[1], 1)
                self.searchGrid.updateFromOccupancyGrid()

        self.searchGrid.updateFromOccupancyGrid()

    def ray_trace(self, origin, end):
        """
        Function to get a list of points between two points
        :param origin: position of the origin
        :param end: position of the end
        :return: list of points in between the origin and end
        """
        points = []
        diff_x = end[0] - origin[0]
        diff_y = end[1] - origin[1]

        slope = float(diff_y) / float(diff_x)

        if diff_x > diff_y:
            step = int(diff_x / math.fabs(diff_x))
            for x in range(origin[0], end[0], step):
                y = int((slope * x))
                points.append([x,y])
        else:
            step = int(diff_y / math.fabs(diff_y))
            for y in range(origin[1], end[1], step):
                x = int(((1/slope) * y))
                points.append([x, y])

        return points

    def update_visualisation(self):
        # self.gridDrawer.setSearchGrid(self.searchGrid)
        self.gridDrawer.update()


if __name__ == '__main__':
    mock = Mock_Slam_Node()

    rate = rospy.Rate(10)
    while not rospy.is_shutdown():
        mock.update_visualisation()
        rate.sleep()
