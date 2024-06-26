import os
import sys

import yaml
from PySide2 import QtWidgets, QtCore
from PySide2.QtUiTools import QUiLoader
from PySide2.QtWidgets import QApplication, QStackedWidget, QFileDialog, QMessageBox
from functools import partial
from pynput import mouse,keyboard

import TaskWindow

import socket
import threading
import pandas as pd
import sys
import time
import datetime
from pathlib import Path
import pickle


class PrecisionEmailSimulator(QtWidgets.QWidget):

    def __init__(self):
        super(PrecisionEmailSimulator, self).__init__()
        self.ui = QUiLoader().load('resources/UI_files/welcome.ui')
        self.study = None
        self.imotionConnection = True
        self.mouseAndKeyboard = True

        self.ui.startBtn.clicked.connect(self.start)
        self.ui.loadConfigBtn.clicked.connect(self.loadConfig)

        self.ui.instructionText.setHidden(True)
        self.ui.pisText.setHidden(True)
        self.ui.sensorsWidget.hide()

        self.ui.imotionConnectBtn.clicked.connect(partial(self.startImotionConnection, self.ui.imotionLabel))
        self.folderPath = ''
        # eye tracker data is collected through iMotion
        self.eyeColumns = ['timestamp', 'timestamp_device', 'GazeLeftX', 'GazeLeftY', 'GazeRightX', 'GazeRightY',
                           'LeftPupilDiameter', 'RightPupilDiameter', 'LeftEyeDistance', 'RightEyeDistance',
                           'LeftEyePosX', 'LeftEyePosY', 'RightEyePosX', 'RightEyePosY']
        self.eyeData = pd.DataFrame(columns=self.eyeColumns)

        # shimmer data is collected through iMotion
        self.shimmerColumns = ['timestamp', 'timestamp_device', 'VSenseBatt RAW', 'VSenseBatt CAL',
                               'Internal ADC A13 PPG RAW', 'Internal ADC A13 PPG CAL', 'GSR RAW', 'GSR Resistance CAL',
                               'GSR Conductance CAL', 'Heart Rate PPG ALG', 'IBI PPG ALG']
        self.shimmerData = pd.DataFrame(columns=self.shimmerColumns)

        self.mouseColumns = ['timestamp', 'mouse_event', 'x', 'y', 'button', 'pressed', 'scroll_x', 'scroll_y']
        self.mouseData = pd.DataFrame(columns=self.mouseColumns)

        self.keyboardColumns = ['timestamp', 'keys']
        self.keyboardData = pd.DataFrame(columns=self.keyboardColumns)

        self.startTime = datetime.datetime.now()
        #
        self.startRecording = False

    def setConfig(self, config):
        self.study = config
        self.updateUI()

    def loadConfig(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getOpenFileName(self, "QFileDialog.getOpenFileName()", "",
                                                  "*.yaml", options=options)
        if fileName:
            with open(fileName) as f:
                self.study = yaml.load(f, Loader=yaml.SafeLoader)
                self.updateUI()

    def updateUI(self):

        if self.study.get('welcomeText') != '':
            self.ui.welcomeText.setText(self.study.get('welcomeText'))
        self.folderPath = self.study.get('saveLocation')

        self.ui.sensorsWidget.show()

    def start(self):
        self.startRecording = True
        self.setup_folder()
        if self.mouseAndKeyboard:
            self.mouseActivity()
            self.keyboardActivity()

        study = TaskWindow.TaskWindow(self.ui.usernameBox.text(), self.study)

        study.ui.show()
        study.activateWindow()
        self.ui.close()

        # self.login_ui = QUiLoader().load('resources/UI_files/login.ui')
        # self.login_ui.show()
        #
        # self.ui.hide()
        #
        # self.login_ui.loginBtn.clicked.connect(self.verifyLogin)

    def setup_folder(self):
        # create folder and csv files
        if self.ui.usernameBox.text() != '':
            Path("./data/" + self.ui.usernameBox.text()).mkdir(parents=True, exist_ok=True)
            self.folderPath = './data/' + self.ui.usernameBox.text() + '/'
        else:
            Path("./data/no_user_name/" + self.startTime.strftime("%d-%m-%Y_%H-%M-%S")).mkdir(parents=True,
                                                                                              exist_ok=True)
            self.folderPath = './data/no_user_name/' + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '/'

        if self.imotionConnection:
            self.eyeData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_eye.csv', index=False)
            # self.shimmerData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_shimmer.csv',
            #                         index=False)
        if self.mouseAndKeyboard:
            self.mouseData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_mouse.csv',
                                  index=False)
            self.keyboardData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_keyboard.csv',
                                     index=False)

    def verifyLogin(self):

        if self.login_ui.username.text() == 'uoavrclub@auckland.ac.nz' and self.login_ui.password.text() == 'VrClub123':

            study = TaskWindow.TaskWindow(self.ui.usernameBox.text(), self.study)
            self.startRecording = True

            study.ui.show()
            study.activateWindow()
            self.login_ui.close()
            self.ui.close()

        else:
            msgBox = QMessageBox()
            msgBox.setIcon(QMessageBox.Information)
            msgBox.setText(
                "The combination of credentials you have entered is incorrect. \nPlease check that you have entered a valid University username \nor an email previously registered with us and your correct \npassword.")
            msgBox.setWindowTitle("Warning")
            msgBox.setStandardButtons(QMessageBox.Ok)
            msgBox.show()
            returnValue = msgBox.exec()

    def startImotionConnection(self, label):
        print(label)
        backgroundThread = threading.Thread(target=self.imotionConnect, args=(label,))
        backgroundThread.deamon = True
        backgroundThread.start()

    def mouseActivity(self):

        def on_click(x, y, button, pressed):
            # print('c')
            if self.startRecording:
                self.mouseData = self.mouseData.append(
                    {'timestamp': time.time() * 1000, 'mouse_event': 'click', 'x': x, 'y': y, 'button': str(button),
                     'pressed': pressed, 'scroll_x': None,
                     'scroll_y': None}, ignore_index=True)

                if self.mouseData.shape[0] > 20:
                    print(self.folderPath)
                    self.mouseData.to_csv(
                        self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_mouse.csv',
                        mode='a', header=False,
                        index=False)
                    self.mouseData = self.mouseData.iloc[0:0]

        def on_scroll(x, y, dx, dy):
            if self.startRecording:
                self.mouseData = self.mouseData.append(
                    {'timestamp': time.time() * 1000, 'mouse_event': 'scroll', 'x': x, 'y': y, 'button': None,
                     'pressed': None, 'scroll_x': dx,
                     'scroll_y': dy}, ignore_index=True)
                if self.mouseData.shape[0] > 20:
                    self.mouseData.to_csv(
                        self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_mouse.csv',
                        mode='a', header=False,
                        index=False)
                    self.mouseData = self.mouseData.iloc[0:0]

        listener = mouse.Listener(on_click=on_click, on_scroll=on_scroll)
        listener.start()

    def keyboardActivity(self):
        def on_press(key):
            if self.startRecording:
                try:
                    # Handle character keys
                    self.keyboardData = self.keyboardData.append({'timestamp': time.time() * 1000, 'keys': str(key.char)}, ignore_index=True)
                except AttributeError:
                    # Handle special keys (e.g., ctrl, alt, etc.)
                    self.keyboardData = self.keyboardData.append({'timestamp': time.time() * 1000,  'keys': str(key)}, ignore_index=True)

                if self.keyboardData.shape[0] > 20:
                    print(self.folderPath)
                    self.keyboardData.to_csv(
                        self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_keyboard.csv',
                        mode='a', header=False,
                        index=False)
                    self.keyboardData = self.keyboardData.iloc[0:0]

        listener = keyboard.Listener(on_press=on_press)
        listener.start()

    def imotionConnect(self, label):
        # Create a TCP/IP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # Connect the socket to the port where the server is listening
        server_address = ('localhost', 8088)
        print('connecting to %s port %s' % server_address)
        sock.connect(server_address)
        label.setText("iMotion: Connected")

        # create folder and csv files
        if self.ui.usernameBox.text() != '':

            Path("./data/" + self.ui.usernameBox.text()).mkdir(parents=True, exist_ok=True)
            self.folderPath = './data/' + self.ui.usernameBox.text() + '/'
        else:
            Path("./data/no_user_name/" + self.startTime.strftime("%d-%m-%Y_%H-%M-%S")).mkdir(parents=True,
                                                                                              exist_ok=True)
            self.folderPath = './data/no_user_name/' + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '/'

        self.eyeData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_eye.csv', index=False)
        # self.shimmerData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_shimmer.csv',
        #                         index=False)
        self.mouseData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_mouse.csv',
                              index=False)
        self.keyboardData.to_csv(self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_keyboard.csv',
                                 index=False)

        try:
            while self.imotionConnection:
                incomingDataStr = sock.recv(1024)

                d = incomingDataStr.decode().split("\r\n")
                for dataStr in d:
                    data = dataStr.split(";")
                    if self.startRecording:
                        if len(data) == 18:  # eye tracker data
                            rowDF = pd.DataFrame(
                                [[time.time() * 1000, data[3], data[6], data[7], data[8], data[9], data[10],
                                  data[11], data[12], data[13], data[14], data[15], data[16], data[17]]],
                                columns=self.eyeColumns)
                            self.eyeData = pd.concat([self.eyeData, rowDF]).reset_index(drop=True)
                            if self.eyeData.shape[0] > 1000:
                                self.eyeData.to_csv(
                                    self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_eye.csv',
                                    mode='a',
                                    header=False, index=False)
                                self.eyeData = self.eyeData.iloc[0:0]

                        # elif len(data) == 19:  # shimmer data
                        #     rowDF = pd.DataFrame(
                        #         [[time.time() * 1000, data[3], data[7], data[8], data[9], data[10], data[11],
                        #           data[12], data[13], data[14], data[15]]],
                        #         columns=self.shimmerColumns)
                        #     self.shimmerData = pd.concat([self.shimmerData, rowDF]).reset_index(drop=True)
                        #     if self.shimmerData.shape[0] > 1000:
                        #         self.shimmerData.to_csv(
                        #             self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_shimmer.csv',
                        #             mode='a', header=False,
                        #             index=False)
                        #         self.shimmerData = self.shimmerData.iloc[0:0]

                        elif len(data) == 10:  # mouse data
                            rowDF = pd.DataFrame(

                                [[time.time() * 1000, data[3], data[5], data[6], data[7], data[8]]],
                                columns=self.mouseColumns)
                            self.mouseData = pd.concat([self.mouseData, rowDF]).reset_index(drop=True)
                            if self.mouseData.shape[0] > 5:
                                self.mouseData.to_csv(
                                    self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_mouse.csv',
                                    mode='a', header=False,
                                    index=False)
                                self.mouseData = self.mouseData.iloc[0:0]
                            print("mouse data")
                            print(data)
                        elif len(data) == 6:  # keyboard data
                            rowDF = pd.DataFrame(
                                [[time.time() * 1000, data[3], data[5]]],
                                columns=self.keyboardColumns)
                            self.keyboardData = pd.concat([self.keyboardData, rowDF]).reset_index(drop=True)
                            if self.keyboardData.shape[0] > 5:
                                self.keyboardData.to_csv(
                                    self.folderPath + self.startTime.strftime("%d-%m-%Y_%H-%M-%S") + '_keyboard.csv',
                                    mode='a', header=False,
                                    index=False)
                                self.keyboardData = self.keyboardData.iloc[0:0]

                        # elif len(data) != 1:
                        #     print('unknown type of data')
                        #     print(data)
                    # eye tracking data has 18 columns
                    # mouse has 10 columns
                    # shimmer has 19 columns
        finally:
            sock.close()


if __name__ == '__main__':
    app = QApplication([])
    mainWindow = PrecisionEmailSimulator()
    mainWindow.ui.show()
    app.exec_()
