#!/usr/bin/env python

import sys
import rospy
import math
import tf
import copy

import numpy as np
from nav_msgs.srv import GetMap
from comp313p_reactive_planner_controller.occupancy_grid import OccupancyGrid
from comp313p_reactive_planner_controller.grid_drawer import OccupancyGridDrawer
from comp313p_reactive_planner_controller.cell import CellLabel
from sensor_msgs.msg import LaserScan
from nav_msgs.msg import Odometry

# This class implements basic mapping capabilities. Given knowledge
# about the robot's position and orientation, it processes laser scans
# to produce a new occupancy grid. If this grid differs from the
# previous one, a new grid is created and broadcast.

class MapperNode(object):

    def __init__(self):

        rospy.init_node('mapper_node', anonymous=True)
	rospy.wait_for_service('static_map')
	rospy.loginfo('------> 0')
        self.mapServer = rospy.ServiceProxy('static_map', GetMap)
	rospy.loginfo('------> 1')
        resp = self.mapServer()
        self.occupancyGrid = OccupancyGrid(resp.map.info.width, resp.map.info.height, resp.map.info.resolution, 0.5)
	self.occupancyGrid.setScale(rospy.get_param('plan_scale',5))
	self.occupancyGrid.scaleEmptyMap()
                         
        self.deltaOccupancyGrid = OccupancyGrid(resp.map.info.width, resp.map.info.height, resp.map.info.resolution, 0)
	self.deltaOccupancyGrid.setScale(rospy.get_param('plan_scale',5))
	self.deltaOccupancyGrid.scaleEmptyMap()

	rospy.loginfo('------> 2')
	rospy.loginfo('------> 3')
        self.occupancyGridDrawer = OccupancyGridDrawer('Mapper Node Occupancy Grid',\
                                                       self.occupancyGrid,rospy.get_param('maximum_window_height_in_pixels', 700))
	self.occupancyGridDrawer.open()
        #self.deltaOccupancyGridDrawer = OccupancyGridDrawer('Mapper Node Delta Occupancy Grid',\
#                                                            self.deltaOccupancyGrid,rospy.get_param('maximum_window_height_in_pixels', 700))
	#self.deltaOccupancyGridDrawer.open()
	rospy.loginfo('------> 4')
        self.local_odometry = Odometry()
        self.laser_sub= rospy.Subscriber("robot0/laser_0", LaserScan, self.parse_scan, queue_size=1)
        self.odom_sub = rospy.Subscriber("robot0/odom", Odometry, self.update_odometry)
	rospy.loginfo('------> Initialised')

    def update_odometry(self, msg):
        self.local_odometry = msg

    def compare_pose(self, pos1, pos2):
        """
        Function to see if the pose is different
        :param pos1: First pose
        :param pos2: Second pose
        :return: boolean true if they are the same
        """
        check_x = math.fabs(pos1.position.x - pos2.position.x) < 0.001
        check_y = math.fabs(pos1.position.y - pos2.position.y) < 0.001

        theta1 = 2 * math.atan2(pos1.orientation.z, pos1.orientation.w) * 180 / math.pi
        theta2 = 2 * math.atan2(pos2.orientation.z, pos2.orientation.w) * 180 / math.pi
        check_theta = math.fabs(theta1 - theta2) < 0.1

        if check_x and check_y and check_theta:
            return True
        else:
            return False

    def parse_scan(self, msg):
        # Only map when not moving

        pose1 = copy.deepcopy(self.local_odometry.pose.pose)
        rospy.sleep(0.2)
        pose2 = copy.deepcopy(self.local_odometry.pose.pose)

        if self.compare_pose(pose1, pose2):
            occupied_points = []
            current_pose = copy.deepcopy(self.local_odometry.pose.pose)
            gridHasChanged = False

            for ii in range(int(math.floor((msg.angle_max - msg.angle_min) / msg.angle_increment))):
                # rospy.loginfo("{} {} {}".format(msg.ranges[ii],msg.angle_min,msg.angle_max))
                valid = (msg.ranges[ii] > msg.range_min) and (msg.ranges[ii] < msg.range_max)

                quaternion = (current_pose.orientation.x, current_pose.orientation.y,
                              current_pose.orientation.z, current_pose.orientation.w)
                euler = tf.transformations.euler_from_quaternion(quaternion)
                angle = msg.angle_min + msg.angle_increment * ii + euler[2]

                # If the range is valid find the end point add it to occupied points and set the distance for ray tracing
                if valid:
                    point_world_coo = [math.cos(angle) * msg.ranges[ii] + current_pose.position.x,
                                       math.sin(angle) * msg.ranges[ii] + current_pose.position.y]

                    occupied_points.append(self.occupancyGrid.getCellCoordinatesFromWorldCoordinates(point_world_coo))
                    dist = msg.ranges[ii]
                else:
                    dist = msg.range_max
                between = self.ray_trace(dist- 0.1, angle, msg)

                for point in between:
                    try:
                        if self.occupancyGrid.getCell(point[0], point[1]) != 0.0:
                            self.occupancyGrid.setCell(point[0], point[1], 0)
                            self.deltaOccupancyGrid.setCell(point[0], point[1], 1.0)
                            gridHasChanged = True
                    except IndexError as e:
                        print(e)
                        print "between: " + str(point[0]) + ", " + str(point[1])

            for point in occupied_points:
                try:
                    if self.occupancyGrid.getCell(point[0], point[1]) != 1.0:
                        self.occupancyGrid.setCell(point[0], point[1], 1.0)
                        self.deltaOccupancyGrid.setCell(point[0], point[1], 1.0)
                        gridHasChanged = True
                except IndexError as e:
                    print(e)
                    print "occupied_points: " + str(point[0]) + ", " + str(point[1])

            if gridHasChanged is True:
                print "grid has changed"

        else:
            print ("Robot moving ignoring scan\n")

    def ray_trace(self, dist, angle, scanmsg):
        """
        Function to get a list of points between two points
        :param origin: position of the origin in world coordinates
        :param dist: distance to end point
        :param angle: angle from robot
        :param scanmsg: Laser Scan message
        :return: list of points in between the origin and end point
        """
        points = []

        space = np.linspace(scanmsg.range_min, dist, scanmsg.range_max * 5)
        for a in space:
            point_world_coo = [math.cos(angle) * a + self.local_odometry.pose.pose.position.x,
                               math.sin(angle) * a + self.local_odometry.pose.pose.position.y]
            points.append(self.occupancyGrid.getCellCoordinatesFromWorldCoordinates(point_world_coo))
        return points
        
    def update_visualisation(self):	 
	self.occupancyGridDrawer.update()
	#self.deltaOccupancyGridDrawer.update()
        self.deltaOccupancyGrid.clearMap(0)
	
    def run(self):
        while not rospy.is_shutdown():
            rospy.sleep(1)
            self.update_visualisation()
        
  

  
