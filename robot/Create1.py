#______ _                       ___  ______________
#| ___ \ |                      |  \/  |  _  | ___ \
#| |_/ / |_   _ _ __ ___   ___  | .  . | | | | |_/ /
#|  __/| | | | | '_ ` _ \ / _ \ | |\/| | | | |  __/
#| |   | | |_| | | | | | |  __/ | |  | \ \/' / |
#\_|   |_|\__,_|_| |_| |_|\___| \_|  |_/\_/\_\_|
#
#
#Create1.py
#
#Python interface for Plume MQP robot
#
#Ryan Wiesenberg
#Eric Fast
#Stepthen Harnais

from pycreate import create
import time
import sys
import math
from threading import Thread, Lock
import socket
import pickle
import serial

from custom_libs import encoding_TCP as encode
from custom_libs import RobotNavigationEKF as EKF
import argparse

import logging
from Adafruit_BNO055 import BNO055

import sympy
from sympy import symbols, Matrix

class Robot:
	#driving constants
	#cm/s (probably. taken from create.py)
	MAX_SPEED = 50
	MIN_SPEED = -50
	DRIVE_SPEED = 20
	TURN_SPEED = 5
	STOP = 0

	#SENSING A TREND HERE
	#delay for sensor update. Too fast and the encoders get pissy
	SENS_DELAY = .1
	COMMS_DELAY = 1
	ANGMARG = .05

	#robot initialization
	ROBOT_SERIAL_PORT = "/dev/ttyUSB1"

	#TCP/IP socket
	#Create a TCP/IP socket
	PORT = 5732
	SERVER_IP = "192.168.0.101"
	server_address = (SERVER_IP, PORT)

	#imu initialization
	IMU_SERIAL_PORT = "/dev/ttyUSB0"
	IMU_GPIO_PIN = 18

	#arduino initialization
	#TODO: Is this real? Sorrect port? Might conflict with robot
	ARDU_SERIAL_PORT = '/dev/ttyACM0'
	ARDU_BAUD_RATE = 9600


	def __init__(self, id):
		self.id = id

		#position initalization
		self.curpos = [0, 0, 0]	#x,y,theta (cm,cm,rad)
		self.desired = [0, 0]	#x_dot, y_dot

		#desired velocity and theta
		self.veld  = 0
		self.thetad = 0
		self.vel = 0 					#actual velocity

		#time variables
		self.startt = 0
		self.endt = 0
		self.keepRunning = True			#leave while loop

		#encoder tidbits
		self.dist = 0
		self.ang = self.curpos[2]

		#start in full mode so it can charge and not be a pain
		self.robot = create.Create(Robot.ROBOT_SERIAL_PORT, startingMode=3)

		#open connection to imu (BNO055)
		self.bno = BNO055.BNO055(serial_port=Robot.IMU_SERIAL_PORT, rst=Robot.IMU_GPIO_PIN)

		#open connection to arduino
		self.ardu = serial.Serial(Robot.ARDU_SERIAL_PORT, Robot.ARDU_BAUD_RATE)

		# Initialize the BNO055 and stop if something went wrong.
		if not self.bno.begin():
			raise RuntimeError('Failed to initialize BNO055! Is the sensor connected?')

		# Print BNO055 status and self test result.
		status, self_test, error = self.bno.get_system_status()
		print('System status: {0}'.format(status))
		print('Self test result (0x0F is normal): 0x{0:02X}'.format(self_test))
		# Print out an error if imu status is in error mode.
		if status == 0x01:
			print('System error: {0}'.format(error))
			print('See datasheet section 4.3.59 for the meaning.')

		# Create Robot's Kalman filter
		# Inputs stdTheta, stdV, stdD, stdAD, stdAV, stdAG
		self.filter = EKF.RobotNavigationEKF(0, 0, 0, 0, 0, 0)

		# Start TCP Connention
		self.initComms()

		# # Thread initializations
		# self.robot_thread = threading.Thread(name="robot_thread", target=self.run_robot)
		# self.update_sens = threading.Thread(name="update_robot", target=self.update_robot)
		# self.comms_thread = threading.Thread(name="comms_thread", target=self.comms)


	###################
	#Sensor Functions#
	###################

	#update sensors
	def updatePosn(self):
		deltadist = 0
		deltaang = 0

		#update time change
		self.endt = time.time()
		deltat = self.endt - self.startt
		self.startt = time.time()

		#calculate encoder bits
		deltadist = self.robot.getSensor("DISTANCE")
		deltaang = self.robot.getSensor("ANGLE")*math.pi/180
		# self.dist += deltadist
		# self.curpos[2] += deltaang

		#pull imu bits
		gyro_x, gyro_y, gyro_z = self.bno.read_gyroscope()
		accl_x, accl_y, accl_z = self.bno.read_accelerometer()

		#send to EKF
		z = Matrix([[accl_x],
					[accl_y],
					[accl_x],
					[accl_y],
					[gyro_z]])
		estX = self.filter.KalmanFilter(z, deltadist, deltaang, deltat)

		#update position bits
		self.curpos[0] = z[0]
		self.curpos[1] = z[1]
		self.curpos[2] = math.fmod(z[4], (2 * math.pi))
		self.vel = math.sqrt(math.pow(z[3], 2) + math.pow(z[4], 2))

		return

	# grabs serial port data
	def updateGas(self):
		if 0:
			ardu.readLine


	#########################
	#Communication Functions#
	#########################

	def initComms(self):
		# Connect the socket to the port where the server is listening
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		print("connecting to %s port %s" %Robot.server_address)
		self.sock.connect(Robot.server_address)

		time.sleep(Robot.COMMS_DELAY)

	def loopComms(self):
		try:
			#send curpos
			encode.sendPacket(sock=sock, message=curpos)

			#recieve message
			rcv = encode.recievePacket(sock=sock)

			print(rcv)

			#determine what to do with message
			if rcv == "out":
				quit()
			else:
				desired[0] = rcv[0]
				desired[1] = rcv[1]

		except:
			pass

	def terminateComms(self):
		#close socket
		print("Closing Socket")
		sock.close()


	#change input velocities to v and theta
	def tCoord(self):
		self.veld = math.sqrt(self.desired[0]**2 + self.desired[1]**2)

		if(self.desired[0] == 0 and self.desired[1] == 0):
			self.thetad = self.curpos[2]
		elif(self.desired[0] == 0 and self.desired[1] > 0):
			self.thetad = math.pi/2
		elif(self.desired[0] == 0 and self.desired[1] < 0):
			self.thetad = math.pi/(-2)
		elif(self.desired[0] > 0):
			self.thetad = math.atan(self.desired[1]/self.desired[0])
		elif(self.desired[0] < 0):
			self.thetad = math.pi + math.atan(self.desired[1]/self.desired[0])

		return

	###################
	#Driving Functions#
	###################

	#movement control
	#decide turn or straight
	def move(self):
		upper = thetad + ANGMARG
		lower = thetad - ANGMARG

		if((self.curpos[2] <= upper) and (self.curpos[2] >= lower)):
			self.drive()
			return True
		elif(self.curpos[2] < lower):
			self.turnCCW()
		elif(self.curpos[2] > upper):
			self.turnCW()
		return False

	#drive desired velocity
	def drive(self):
		self.robot.go(self.veld, 0)
		return

	#turn Counter Clockwise
	def turnCCW(self):
		self.robot.driveDirect(-TURN_SPEED, TURN_SPEED)
		return

	#turn Clockwise
	def turnCW(self):
		self.robot.driveDirect(TURN_SPEED, -TURN_SPEED)
		return

	#stop robot
	def stop(self):
		self.veld = 0
		self.thetad = self.curpos[2]
		return

	#end robot
	def quit(self):
		self.stop()
		self.keepRunning = False


	##################
	#Thread Functions#
	##################

	#run_robot function for robot_thread
	#just drivey bits
	def run_robot(self):
		while self.keepRunning:
			self.tCoord()
			self.move()

	#update_robot function for update_sens
	#sensors will love me
	def update_robot(self):
		while self.keepRunning:
			self.updatePosn()
			self.updateGas()
			# time.sleep(SENS_DELAY)


	#comms function for comms thread
	def comms(self):
		initComms(self)
		while keepRunning:
			loopComms(self)


	#where the buisness happens
	#comms_thread 	~ send/recieve information across TCP/IP
	#robot_thread	~ driving and turning
	#update_sens	~ sensor updates
	def main(self):
		# #essentially initializes the threads
		# self.robot_thread.start()
		# self.update_sens.start()
		# self.comms_thread.start()
		#
		# #adds them on to the main thread (this one)
		# self.robot_thread.join()
		# self.update_sens.join()
		# self.comms_thread.join()

		while self.keepRunning:
			self.updatePosn()
			self.updateGas()
			self.loopComms()
			self.tCoord()
			self.move()
		self.terminate()

	def terminate(self):
		self.terminateComms()


############################
#Create and Run Robot on Pi#
############################
parser = argparse.ArgumentParser()
parser.add_argument("id", type=int, help="assign ID to robot")
args = parser.parse_args()
robot = Robot(args.id)
robot.main()
